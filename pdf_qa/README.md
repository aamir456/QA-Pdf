# PDF Q&A Pipeline (Stage 1 — local, $0 cost)

A local RAG pipeline: PDF -> chunks -> local embeddings -> ChromaDB -> retrieval -> Claude answer.

This is stage 1 of a larger project. The full architecture (with AWS S3, IAM,
Terraform, CI/CD) gets layered on top in later stages — see the project notes.
The interfaces here (`vector_store.py`) are written so swapping ChromaDB for
OpenSearch Serverless later only touches one file.

## Setup

```bash
# 1. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate          # on Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your Anthropic API key (only needed for query.py, not ingest.py)
export ANTHROPIC_API_KEY=sk-ant-...          # on Windows (PowerShell): $env:ANTHROPIC_API_KEY="sk-ant-..."
```

## Usage

```bash
# 1. Drop one or more PDFs into data/pdfs/
cp ~/Downloads/some_contract.pdf data/pdfs/

# 2. Ingest: parse, chunk, embed, store
python ingest.py
# (first run downloads the embedding model, ~90MB, one-time)

# 3. Ask questions
python query.py "What is the notice period for termination?"

# or run interactively:
python query.py
```

## How it works

- `ingest.py` — reads every PDF in `data/pdfs/`, extracts text per page,
  splits into overlapping ~1000-character chunks, embeds each chunk locally
  with `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim, free, offline),
  and stores vectors + text + `{source, page}` metadata in ChromaDB.
- `query.py` — embeds your question with the same model, retrieves the
  top-k most similar chunks from Chroma, builds a context-grounded prompt,
  and calls Claude to generate a cited answer. If the answer isn't in the
  retrieved context, Claude is instructed to say so rather than guess.
- `vector_store.py` — the only file that talks to Chroma directly. This is
  intentional: it's the seam where a future AWS port (OpenSearch Serverless)
  plugs in without touching ingestion or query logic.

## Known limitations (by design, for a stage-1 portfolio build)

- Chunking is character-based, not sentence/paragraph-aware. Fine for prose
  documents; less precise for tables or structured PDFs.
- Scanned/image-only PDFs won't extract text (no OCR yet — Textract fills
  this gap in the AWS version).
- No incremental re-ingestion check — re-running `ingest.py` on the same
  PDF re-embeds and upserts by the same chunk IDs, so it's idempotent but
  not cache-aware.

## Next stages

1. ~~Local PDF -> embed -> query pipeline~~ (this stage)
2. Terraform: S3 buckets + IAM roles/policies (least privilege per team)
3. Terraform: CI/CD via GitHub Actions with OIDC (no long-lived AWS keys)
4. CloudTrail audit logging + guardrail policies
5. Wire this local pipeline to read/write real S3 buckets via the IAM roles
