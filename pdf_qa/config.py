"""
Central configuration for the PDF QA pipeline.
Keeping these in one place makes it trivial to swap local components
for AWS equivalents later (e.g. EMBEDDING_MODEL -> Bedrock Titan,
CHROMA_DIR -> OpenSearch Serverless endpoint) without touching pipeline logic.
"""

import os
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "data" / "pdfs"
CHROMA_DIR = BASE_DIR / "data" / "chroma_db"
COLLECTION_NAME = "pdf_chunks"

# --- Chunking ---
# Measured in characters, not tokens, to keep this dependency-free.
# ~1000 chars ≈ 200-250 tokens, a reasonable retrieval granularity.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# --- Embedding model ---
# Runs fully locally via sentence-transformers, no API key, no cost.
# 384-dim output, good quality/speed tradeoff for a portfolio project.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# --- Retrieval ---
TOP_K = 4

# --- Claude (answer generation) ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-4-5"
MAX_ANSWER_TOKENS = 1024

# --- AWS / S3 (stage 3) ---
# Bucket names and role ARNs come from `terraform output` after running
# infra/ — set these as environment variables rather than hardcoding,
# since they contain an account-specific random suffix.
#
#   PowerShell:  $env:PDFQA_RAW_BUCKET = "pdfqa-raw-pdfs-xxxxxxxx"
#
AWS_REGION = os.environ.get("AWS_REGION", "eu-central-1")
RAW_PDFS_BUCKET = os.environ.get("PDFQA_RAW_BUCKET")
CHUNKS_BUCKET = os.environ.get("PDFQA_CHUNKS_BUCKET")
INGEST_ROLE_ARN = os.environ.get("PDFQA_INGEST_ROLE_ARN")
QUERY_ROLE_ARN = os.environ.get("PDFQA_QUERY_ROLE_ARN")

# How long the assumed-role session lasts before it must be re-assumed.
# 1 hour is the AWS default minimum and is plenty for a single ingest/query run.
ASSUME_ROLE_SESSION_SECONDS = 3600

# --- OpenSearch Serverless (demo-and-destroy stage) ---
# Endpoint comes from `terraform output opensearch_collection_endpoint`.
# COST NOTE: this collection bills ~$0.96/hour while ACTIVE regardless of
# traffic. Run terraform destroy in infra/ when you're done testing.
OPENSEARCH_ENDPOINT = os.environ.get("PDFQA_OPENSEARCH_ENDPOINT")
OPENSEARCH_INDEX = "pdf-chunks"
OPENSEARCH_VECTOR_DIM = 384  # matches all-MiniLM-L6-v2 output size

