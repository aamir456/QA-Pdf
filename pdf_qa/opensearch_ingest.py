"""
Pushes chunk data into the OpenSearch Serverless vector index, using
temporary credentials from assuming ingest_role.

Source of chunk data: downloads the chunk JSON already sitting in your
S3 chunks bucket (uploaded by `python ingest.py --to-s3` in stage 3) --
re-embeds the text locally with the same model used originally, then
indexes into OpenSearch. This avoids re-parsing PDFs; it reuses what's
already in S3, which is itself a nice demonstration of the pipeline
stages composing together.

Usage:
    python opensearch_ingest.py
"""

import sys

from sentence_transformers import SentenceTransformer

import config
import aws_storage
import opensearch_store


def main():
    print("Assuming ingest_role for both S3 (read chunks) and OpenSearch (write) access ...")
    s3_client = aws_storage.get_ingest_s3_client()
    print("S3 access via ingest_role confirmed.\n")

    print(f"Downloading chunk files from s3://{config.CHUNKS_BUCKET} ...")
    keys = aws_storage.list_chunk_files(s3_client)
    if not keys:
        print("No chunk files found in S3. Run 'python ingest.py --to-s3' first.")
        sys.exit(1)

    all_records = []
    for key in keys:
        records = aws_storage.download_chunk_file(s3_client, key)
        all_records.extend(records)
        print(f"  {key}: {len(records)} records")

    print(f"\nTotal chunk records to index: {len(all_records)}")

    print(f"\nLoading embedding model '{config.EMBEDDING_MODEL}' ...")
    embedder = SentenceTransformer(config.EMBEDDING_MODEL)

    texts = [r["text"] for r in all_records]
    print("Re-embedding chunk text (same model as original ingestion) ...")
    embeddings = embedder.encode(texts, show_progress_bar=False).tolist()

    print("\nAssuming ingest_role again for OpenSearch Serverless access ...")
    os_client = opensearch_store.get_client_with_role(config.INGEST_ROLE_ARN, "pdfqa-opensearch-ingest-session")

    print(f"Ensuring index '{config.OPENSEARCH_INDEX}' exists ...")
    opensearch_store.ensure_index(os_client)

    ids = [r["id"] for r in all_records]
    metadatas = [r["metadata"] for r in all_records]

    print(f"Indexing {len(all_records)} chunks into OpenSearch Serverless ...")
    response = opensearch_store.upsert_chunks(os_client, ids, embeddings, texts, metadatas)

    if not response.get("errors"):
        print(f"\nSuccess. {len(all_records)} chunks indexed into '{config.OPENSEARCH_INDEX}'.")
    else:
        print("\nIndexing completed with some errors (see above).")


if __name__ == "__main__":
    main()
