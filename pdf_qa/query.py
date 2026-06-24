"""
Query pipeline: question -> embed -> retrieve top-k chunks -> Claude -> cited answer.

Usage:
    python query.py "What is the termination notice period?"
    python query.py   (interactive mode, asks repeatedly)

Mirrors the "query path" lane in the architecture diagram:
API Gateway -> query service (embed + retrieve) -> Bedrock LLM (RAG answer).
Here: this script (embed + retrieve) -> Claude API (RAG answer).
"""

import sys

from anthropic import Anthropic
from sentence_transformers import SentenceTransformer

import config
from vector_store import VectorStore

SYSTEM_PROMPT = """You are a precise document Q&A assistant. You answer ONLY using the provided context chunks from the user's PDFs.

Rules:
- If the context does not contain the answer, say so plainly. Do not guess or use outside knowledge.
- When you state a fact, cite the source file and page it came from, like this: (source: contract.pdf, p.3)
- Keep answers concise and directly responsive to the question.
"""


def build_prompt(question: str, hits: list[dict]) -> str:
    context_blocks = []
    for hit in hits:
        src = hit["metadata"].get("source", "unknown")
        page = hit["metadata"].get("page", "?")
        context_blocks.append(f"[source: {src}, page {page}]\n{hit['text']}")

    context = "\n\n---\n\n".join(context_blocks)

    return f"""Context chunks retrieved from the document store:

{context}

---

Question: {question}

Answer the question using only the context above, citing sources as instructed."""


def answer_question(question: str, embedder: SentenceTransformer, store: VectorStore, client: Anthropic):
    query_embedding = embedder.encode(question).tolist()
    hits = store.query(query_embedding, top_k=config.TOP_K)

    if not hits:
        print("No documents in the vector store yet. Run ingest.py first.")
        return

    print(f"\nRetrieved {len(hits)} relevant chunks:")
    for i, hit in enumerate(hits, start=1):
        src = hit["metadata"].get("source", "unknown")
        page = hit["metadata"].get("page", "?")
        print(f"  [{i}] {src} (p.{page}) - distance {hit['distance']:.3f}")

    prompt = build_prompt(question, hits)

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_ANSWER_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    answer_text = "".join(block.text for block in response.content if block.type == "text")
    print(f"\nAnswer:\n{answer_text}\n")


def main():
    if not config.ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY environment variable is not set.")
        print("Set it with: export ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    print(f"Loading embedding model '{config.EMBEDDING_MODEL}' ...")
    embedder = SentenceTransformer(config.EMBEDDING_MODEL)
    store = VectorStore()
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    if store.count() == 0:
        print("Vector store is empty. Run ingest.py first to add PDFs.")
        sys.exit(1)

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        answer_question(question, embedder, store, client)
    else:
        print("Interactive mode. Type a question, or 'exit' to quit.\n")
        while True:
            question = input("Question: ").strip()
            if question.lower() in ("exit", "quit"):
                break
            if not question:
                continue
            answer_question(question, embedder, store, client)


if __name__ == "__main__":
    main()
