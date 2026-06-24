"""
Thin wrapper around ChromaDB.

This deliberately exposes only two operations - upsert_chunks() and query() -
because that's the exact interface OpenSearch Serverless (or any vector DB)
would need to expose. When porting to AWS, this file is the *only* file
that should need to change; ingest.py and query.py call this interface,
not Chroma directly.
"""

import os

import chromadb
from chromadb.config import Settings

import config


class VectorStore:
    def __init__(self):
        chroma_host = os.environ.get("CHROMA_HOST")
        if chroma_host:
            self._client = chromadb.HttpClient(
                host=chroma_host,
                port=int(os.environ.get("CHROMA_PORT", "8000")),
                settings=Settings(anonymized_telemetry=False),
            )
        else:
            self._client = chromadb.PersistentClient(
                path=str(config.CHROMA_DIR),
                settings=Settings(anonymized_telemetry=False),
            )
        self._collection = self._client.get_or_create_collection(
            name=config.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(self, ids, embeddings, documents, metadatas):
        """
        ids: list[str]            unique chunk id, e.g. "invoice.pdf::chunk_3"
        embeddings: list[list[float]]
        documents: list[str]      the raw chunk text
        metadatas: list[dict]     e.g. {"source": "invoice.pdf", "page": 2}
        """
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(self, query_embedding, top_k):
        """
        Returns top_k most similar chunks as a list of dicts:
        [{"text": ..., "metadata": {...}, "distance": float}, ...]
        """
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
        hits = []
        for text, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append({"text": text, "metadata": metadata, "distance": distance})
        return hits

    def count(self):
        return self._collection.count()
