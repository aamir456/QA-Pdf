"""
Ingestion pipeline: PDF -> extracted text -> overlapping chunks -> embeddings -> vector store.

Usage:
    python ingest.py
    python ingest.py --pdf data/pdfs/specific_file.pdf
    python ingest.py --to-s3              # also upload PDF + chunks to S3 (stage 3)

With --to-s3, this additionally uploads the original PDF and the extracted
chunks to the real S3 buckets provisioned in infra/, using temporary
credentials obtained by assuming ingest_role (see aws_storage.py).

This mirrors the "embedding pipeline" lane in the architecture diagram:
S3 raw-pdfs -> ECS worker (parse + chunk) -> Bedrock endpoint (embed) -> OpenSearch (store).
Here: local disk -> this script (parse + chunk) -> sentence-transformers (embed) -> Chroma (store).
"""

import argparse
import sys
from pathlib import Path

from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

import config
from vector_store import VectorStore


def extract_pages(pdf_path: Path):
    """Yield (page_number, text) for each non-empty page in the PDF."""
    reader = PdfReader(str(pdf_path))
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            yield page_num, text


def chunk_text(text: str, chunk_size: int, overlap: int):
    """
    Simple sliding-window chunker over characters.
    Good enough for a portfolio project; a production system would chunk
    on sentence/paragraph boundaries (e.g. via langchain's RecursiveCharacterTextSplitter).
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def ingest_pdf(pdf_path: Path, embedder: SentenceTransformer, store: VectorStore, s3_client=None):
    print(f"Processing {pdf_path.name} ...")

    ids, texts, metadatas = [], [], []
    chunk_counter = 0

    for page_num, page_text in extract_pages(pdf_path):
        for chunk in chunk_text(page_text, config.CHUNK_SIZE, config.CHUNK_OVERLAP):
            chunk_counter += 1
            ids.append(f"{pdf_path.name}::chunk_{chunk_counter}")
            texts.append(chunk)
            metadatas.append({"source": pdf_path.name, "page": page_num})

    if not texts:
        print(f"  No extractable text found in {pdf_path.name} (scanned image PDF?). Skipping.")
        return 0

    print(f"  Extracted {chunk_counter} chunks. Embedding ...")
    embeddings = embedder.encode(texts, show_progress_bar=False).tolist()

    store.upsert_chunks(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    print(f"  Stored {chunk_counter} chunks in vector store.")
    print(f"  Stored {chunk_counter} chunks in local vector store.")

    if s3_client is not None:
        import aws_storage

        pdf_uri = aws_storage.upload_pdf(s3_client, pdf_path)
        print(f"  Uploaded original PDF to {pdf_uri}")

        chunk_records = [
            {"id": cid, "text": text, "metadata": meta}
            for cid, text, meta in zip(ids, texts, metadatas)
        ]
        chunks_uri = aws_storage.upload_chunks(s3_client, pdf_path.name, chunk_records)
        print(f"  Uploaded {chunk_counter} chunk records to {chunks_uri}")
    return chunk_counter


def main():
    parser = argparse.ArgumentParser(description="Ingest PDFs into the local vector store.")
    parser.add_argument("--pdf", type=str, help="Path to a single PDF. If omitted, processes all PDFs in data/pdfs/.")
    parser.add_argument(
        "--to-s3",
        action="store_true",
        help="Also upload the original PDF and extracted chunks to S3, using ingest_role credentials.",
    )
    args = parser.parse_args()

    if args.pdf:
        pdf_paths = [Path(args.pdf)]
    else:
        pdf_paths = sorted(config.PDF_DIR.glob("*.pdf"))

    if not pdf_paths:
        print(f"No PDFs found. Drop files into {config.PDF_DIR} or pass --pdf <path>.")
        sys.exit(1)

    s3_client = None
    if args.to_s3:
        import aws_storage

        print("Assuming ingest_role to obtain temporary AWS credentials ...")
        s3_client = aws_storage.get_ingest_s3_client()
        print("Role assumed successfully. Uploads will use these scoped-down credentials.\n")

    print(f"Loading embedding model '{config.EMBEDDING_MODEL}' (first run downloads it, ~90MB) ...")
    embedder = SentenceTransformer(config.EMBEDDING_MODEL)
    store = VectorStore()

    total_chunks = 0
    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            print(f"  File not found: {pdf_path}")
            continue
        total_chunks += ingest_pdf(pdf_path, embedder, store, s3_client=s3_client)

    print(f"\nDone. Vector store now holds {store.count()} chunks total ({total_chunks} added this run).")


if __name__ == "__main__":
    main()
