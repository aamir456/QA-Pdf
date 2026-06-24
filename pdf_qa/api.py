"""
FastAPI service wrapping the PDF Q&A query pipeline.
Exposes /health and /query endpoints for Kubernetes deployment.
"""

from contextlib import asynccontextmanager

from anthropic import Anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

import config
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


@app.get("/health")
def health():
    store: VectorStore = _resources.get("store")
    chunk_count = store.count() if store else 0
    return {"status": "ok", "chunks_in_store": chunk_count}


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
            status_code=503, detail="Vector store is empty. Run the ingest job first."
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
