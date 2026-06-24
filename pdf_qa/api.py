"""
FastAPI service wrapping the PDF Q&A query pipeline.

Endpoints:
  GET  /health        — liveness + chunk count
  POST /upload        — upload a PDF, ingest it into ChromaDB
  POST /query         — ask a question, get a cited answer
"""

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from anthropic import Anthropic
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

import config
from ingest import ingest_pdf
from query import SYSTEM_PROMPT, build_prompt
from vector_store import VectorStore

_resources: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _resources["embedder"] = SentenceTransformer(config.EMBEDDING_MODEL)
    _resources["store"] = VectorStore()
    _resources["client"] = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    yield
    _resources.clear()


app = FastAPI(title="PDF Q&A API", version="1.0.0", lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    chunks_used: int
    sources: list[dict]


class UploadResponse(BaseModel):
    filename: str
    chunks_ingested: int
    total_chunks_in_store: int


@app.get("/health")
def health():
    store: VectorStore = _resources.get("store")
    chunk_count = store.count() if store else 0
    return {"status": "ok", "chunks_in_store": chunk_count}


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    embedder: SentenceTransformer = _resources["embedder"]
    store: VectorStore = _resources["store"]

    # Write the uploaded bytes to a temp file so ingest_pdf can read it
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
        # Rename so the chunk IDs carry the original filename
        named_path = tmp_path.with_name(file.filename)
        tmp_path.rename(named_path)

    try:
        chunks = ingest_pdf(named_path, embedder, store)
    finally:
        named_path.unlink(missing_ok=True)

    return UploadResponse(
        filename=file.filename,
        chunks_ingested=chunks,
        total_chunks_in_store=store.count(),
    )


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    embedder: SentenceTransformer = _resources["embedder"]
    store: VectorStore = _resources["store"]
    client: Anthropic = _resources["client"]

    query_embedding = embedder.encode(req.question).tolist()
    hits = store.query(query_embedding, top_k=config.TOP_K)

    if not hits:
        raise HTTPException(
            status_code=503,
            detail="Vector store is empty. Upload a PDF via POST /upload first.",
        )

    prompt = build_prompt(req.question, hits)
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_ANSWER_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    answer_text = "".join(block.text for block in response.content if block.type == "text")

    sources = [
        {
            "source": h["metadata"].get("source", "unknown"),
            "page": h["metadata"].get("page", "?"),
        }
        for h in hits
    ]
    return QueryResponse(answer=answer_text, chunks_used=len(hits), sources=sources)
