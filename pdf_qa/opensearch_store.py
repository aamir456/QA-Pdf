"""
OpenSearch Serverless client wrapper.

OpenSearch Serverless (unlike a plain REST API) requires every HTTP request
to be SigV4-signed using real AWS credentials -- it's authenticated the same
way S3/STS calls are, not via a separate API key. This module takes the
temporary credentials from assuming ingest_role/query_role (see aws_storage.py)
and uses them to sign requests to the collection endpoint.

This mirrors vector_store.py's interface on purpose (upsert + query) so
ingest.py/query.py could swap ChromaDB for this with minimal changes --
that swap isn't done in this demo-and-destroy stage, but the seam is here.
"""

import sys

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
from opensearchpy.exceptions import RequestError

import config


def _client_from_session(session: boto3.Session) -> OpenSearch:
    """Builds a SigV4-authenticated OpenSearch client from a boto3 session (real creds or assumed-role temp creds)."""
    if not config.OPENSEARCH_ENDPOINT:
        print("PDFQA_OPENSEARCH_ENDPOINT is not set. Run 'terraform output opensearch_collection_endpoint'")
        print("in infra/ and set it as an environment variable.")
        sys.exit(1)

    host = config.OPENSEARCH_ENDPOINT.replace("https://", "")
    credentials = session.get_credentials()
    auth = AWSV4SignerAuth(credentials, config.AWS_REGION, "aoss")

    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
        timeout=120,
    )


def get_client_with_role(role_arn: str, session_name: str) -> OpenSearch:
    """Assumes the given role and returns an OpenSearch client signed with its temporary credentials."""
    import aws_storage

    session = aws_storage._assume_role(role_arn, session_name)
    return _client_from_session(session)


def ensure_index(client: OpenSearch, index_name: str = None, vector_dim: int = None):
    """
    Creates the vector index if it doesn't already exist. OpenSearch Serverless
    vector search requires a knn_vector field with a fixed dimension declared
    up front, plus text/metadata fields for retrieval display.
    """
    index_name = index_name or config.OPENSEARCH_INDEX
    vector_dim = vector_dim or config.OPENSEARCH_VECTOR_DIM

    if client.indices.exists(index=index_name):
        print(f"  Index '{index_name}' already exists.")
        return

    body = {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "knn_vector",
                    "dimension": vector_dim,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                    },
                },
                "text": {"type": "text"},
                "source": {"type": "keyword"},
                "page": {"type": "integer"},
                "chunk_id": {"type": "keyword"},
            }
        },
    }
    try:
        client.indices.create(index=index_name, body=body)
        print(f"  Created index '{index_name}' (vector dim={vector_dim}).")
    except RequestError as e:
        print(f"  Failed to create index: {e}")
        raise


def upsert_chunks(client: OpenSearch, ids, embeddings, documents, metadatas, index_name: str = None):
    """
    Bulk-indexes chunk records into OpenSearch.

    Note: OpenSearch Serverless VECTORSEARCH collections do not support
    custom document IDs on bulk index/create operations -- the service
    must generate its own _id. So the original chunk id (e.g.
    "file.pdf::chunk_3") is stored as a regular field (chunk_id) instead
    of passed as _id; it's still fully retrievable and useful for display,
    just not usable as a lookup key the way it was in ChromaDB.
    """
    index_name = index_name or config.OPENSEARCH_INDEX

    bulk_body = []
    for cid, embedding, text, meta in zip(ids, embeddings, documents, metadatas):
        bulk_body.append({"index": {"_index": index_name}})
        bulk_body.append(
            {
                "embedding": embedding,
                "text": text,
                "source": meta.get("source"),
                "page": meta.get("page"),
                "chunk_id": cid,
            }
        )

    response = client.bulk(body=bulk_body)
    if response.get("errors"):
        print("  Some documents failed to index:")
        for item in response["items"]:
            if "error" in item.get("index", {}):
                print(f"    {item['index']['error']}")
    return response


def knn_search(client: OpenSearch, query_embedding, top_k: int, index_name: str = None):
    """Vector similarity search, returns list of {"text", "metadata", "score"}."""
    index_name = index_name or config.OPENSEARCH_INDEX

    body = {
        "size": top_k,
        "query": {"knn": {"embedding": {"vector": query_embedding, "k": top_k}}},
    }
    response = client.search(index=index_name, body=body)

    hits = []
    for hit in response["hits"]["hits"]:
        source = hit["_source"]
        hits.append(
            {
                "text": source["text"],
                "metadata": {"source": source.get("source"), "page": source.get("page")},
                "score": hit["_score"],
            }
        )
    return hits
