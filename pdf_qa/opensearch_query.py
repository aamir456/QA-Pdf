"""
Query pipeline using OpenSearch Serverless instead of local ChromaDB.
Uses query_role credentials -- read-only, proving the same least-privilege
split extends from S3 into the vector store itself.

Usage:
    python opensearch_query.py "What is the notice period?"
"""

import sys

from anthropic import Anthropic
from sentence_transformers import SentenceTransformer

import config
import opensearch_store
from query import SYSTEM_PROMPT, build_prompt  # reuse stage 1's prompt logic exactly


def answer_question(question, embedder, os_client, client):
    query_embedding = embedder.encode(question).tolist()
    hits = opensearch_store.knn_search(os_client, query_embedding, top_k=config.TOP_K)

    if not hits:
        print("No results. Run 'python opensearch_ingest.py' first.")
        return

    print(f"\nRetrieved {len(hits)} relevant chunks from OpenSearch Serverless:")
    for i, hit in enumerate(hits, start=1):
        src = hit["metadata"].get("source", "unknown")
        page = hit["metadata"].get("page", "?")
        print(f"  [{i}] {src} (p.{page}) - score {hit['score']:.3f}")

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
        sys.exit(1)
    if len(sys.argv) < 2:
        print('Usage: python opensearch_query.py "your question"')
        sys.exit(1)

    question = " ".join(sys.argv[1:])

    print(f"Loading embedding model '{config.EMBEDDING_MODEL}' ...")
    embedder = SentenceTransformer(config.EMBEDDING_MODEL)

    print("Assuming query_role for OpenSearch Serverless read access ...")
    os_client = opensearch_store.get_client_with_role(config.QUERY_ROLE_ARN, "pdfqa-opensearch-query-session")

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    answer_question(question, embedder, os_client, client)


if __name__ == "__main__":
    main()
