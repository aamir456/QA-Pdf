# PDF Q&A — GenAI RAG Pipeline on AWS EKS

A production-style Retrieval-Augmented Generation (RAG) pipeline that lets you upload PDF documents and ask natural-language questions about them. Answers are cited with source file and page number.

---

## Architecture

```
GitHub Push (main)
       │
       ▼
GitHub Actions CI/CD
  ├── Lint (Python syntax check)
  ├── Build Docker image
  ├── Push to Amazon ECR
  └── Deploy to EKS (kubectl rollout)
             │
             ▼
    ┌─────────────────────────────────────┐
    │         AWS EKS — eu-central-1      │
    │  Namespace: pdf-qa                  │
    │                                     │
    │  ┌─────────────┐  ┌─────────────┐  │
    │  │ query-api   │  │ query-api   │  │
    │  │ (FastAPI)   │  │ (FastAPI)   │  │
    │  │  pod 1      │  │  pod 2      │  │
    │  └──────┬──────┘  └──────┬──────┘  │
    │         └────────┬────────┘         │
    │                  ▼                  │
    │          ┌──────────────┐           │
    │          │  chromadb    │           │
    │          │  (HTTP svr)  │           │
    │          └──────┬───────┘           │
    │                 │                   │
    │          ┌──────▼───────┐           │
    │          │  EBS gp3 PVC │           │
    │          │   5 GiB      │           │
    │          └──────────────┘           │
    └─────────────────────────────────────┘
             │
             ▼
    AWS Network Load Balancer (port 80)
             │
             ▼
       External users
    POST /upload  →  ingest PDF
    POST /query   →  ask questions
```

**Data flow:**
1. User uploads PDF → `/upload` → text extracted → chunked → embedded (`all-MiniLM-L6-v2`) → stored in ChromaDB
2. User asks question → `/query` → question embedded → top-4 chunks retrieved → Claude generates cited answer

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Claude Sonnet (`claude-sonnet-4-5`) via Anthropic API |
| Embeddings | `all-MiniLM-L6-v2` via `sentence-transformers` (384-dim, CPU, free) |
| Vector Store | ChromaDB 0.5.23 (HTTP server mode in Kubernetes) |
| API | FastAPI + Uvicorn |
| Container Runtime | Docker (CPU-only PyTorch wheel) |
| Orchestration | AWS EKS (Kubernetes 1.30) |
| Container Registry | Amazon ECR |
| CI/CD | GitHub Actions (OIDC — no long-lived AWS keys) |
| Infrastructure | Terraform (AWS provider ~5.x) |
| PDF Parsing | pypdf |
| Language | Python 3.11 |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check + chunk count in vector store |
| `POST` | `/upload` | Upload a PDF — ingests it into ChromaDB |
| `POST` | `/query` | Ask a question — returns cited answer |
| `GET` | `/docs` | Swagger UI (interactive browser testing) |

### Upload a PDF
```bash
curl -X POST http://<LB_HOSTNAME>/upload \
  -F "file=@/path/to/document.pdf"
```
```json
{
  "filename": "document.pdf",
  "chunks_ingested": 42,
  "total_chunks_in_store": 42
}
```

### Ask a question
```bash
curl -X POST http://<LB_HOSTNAME>/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the key skills mentioned?"}'
```
```json
{
  "answer": "The key skills mentioned include... (source: document.pdf, p.3)",
  "chunks_used": 4,
  "sources": [
    {"source": "document.pdf", "page": 3},
    {"source": "document.pdf", "page": 5}
  ]
}
```

### PowerShell (Windows)
```powershell
# Upload (requires curl.exe — built into Windows 10/11)
$LB = "<your-NLB-hostname>"
curl.exe -X POST "http://$LB/upload" -F "file=@D:\path\to\document.pdf"

# Query
(Invoke-RestMethod -Uri "http://$LB/query" -Method Post `
  -ContentType "application/json" `
  -Body '{"question": "What certifications does the candidate have?"}').answer
```

---

## Live NLB Endpoint

```
http://a846973770638445ca69e46f6c6c852b-422ed4158e39b40f.elb.eu-central-1.amazonaws.com
```

Swagger UI:
```
http://a846973770638445ca69e46f6c6c852b-422ed4158e39b40f.elb.eu-central-1.amazonaws.com/docs
```

---

## AWS Resource Inventory

### Networking

| Resource | ID / Name | Detail |
|---|---|---|
| VPC | `vpc-0a737a901a3e7303e` | CIDR: 10.0.0.0/16 |
| Public Subnet 1 | `subnet-0f12c384d9cbb145d` | 10.0.1.0/24 — eu-central-1a (ALB) |
| Public Subnet 2 | `subnet-0ce5db975f0658119` | 10.0.2.0/24 — eu-central-1b (ALB) |
| Private Subnet 1 | `subnet-0c882cab40ccae6bb` | 10.0.11.0/24 — eu-central-1a (EKS nodes) |
| Private Subnet 2 | `subnet-0835901768bb27fb5` | 10.0.12.0/24 — eu-central-1b (EKS nodes) |
| Internet Gateway | `pdfqa-igw` | Public internet access for ALB |
| NAT Gateway | `nat-0a822671b6e58ef46` | Public IP: 63.179.156.135 — outbound for nodes |
| Network Load Balancer | `a846973770638445...` | Active — port 80 → query-api pods |

### Compute

| Resource | ID | Detail |
|---|---|---|
| EKS Cluster | `pdfqa-cluster` | Kubernetes 1.30, ACTIVE |
| EKS Node Group | `pdfqa-nodes` | 2 nodes (min 1, max 3), t3.medium |
| EC2 Node 1 | `i-028795ebb7951bc9d` | t3.medium, eu-central-1a, 10.0.11.127 |
| EC2 Node 2 | `i-031eed1632bd13b80` | t3.medium, eu-central-1b, 10.0.12.129 |
| EBS Volume | `vol-09139b1d48461f6df` | 5 GiB gp3 — ChromaDB persistent storage |

### Kubernetes Workloads (`pdf-qa` namespace)

| Resource | Replicas | Status |
|---|---|---|
| Deployment `query-api` | 2/2 | Running — FastAPI + Claude |
| Deployment `chromadb` | 1/1 | Running — HTTP vector store |
| Service `query-api` | LoadBalancer | Exposed via NLB on port 80 |
| Service `chromadb` | ClusterIP | Internal only — port 8000 |
| HPA `query-api` | 2 → 5 replicas | Scales on CPU (70%) / memory (80%) |
| PVC `chromadb-data` | 5 GiB gp3 EBS | Bound — persists ChromaDB data |
| StorageClass `ebs-gp3` | — | Encrypted EBS gp3 via EBS CSI driver |

### Storage & Registry

| Resource | Name | Detail |
|---|---|---|
| ECR Repository | `pdfqa-pdf-qa` | Docker images, scan-on-push enabled |
| S3 Bucket | `pdfqa-raw-pdfs-4b62e65c` | Raw PDF uploads |
| S3 Bucket | `pdfqa-chunks-4b62e65c` | Processed text chunks |
| KMS Key | `358ef63a-7f2c-4b12-a8dc-ceaa65b5544a` | Encrypts both S3 buckets, rotation enabled |

### IAM Roles

| Role | Purpose |
|---|---|
| `pdfqa-eks-cluster` | EKS control plane — trust: eks.amazonaws.com |
| `pdfqa-eks-node` | EC2 worker nodes — trust: ec2.amazonaws.com |
| `pdfqa-ebs-csi` | EBS CSI driver IRSA — provisions PVCs |
| `pdfqa-github-actions` | GitHub Actions OIDC — CI/CD without long-lived keys |
| `pdfqa-ingest-role` | App role: write to S3 + invoke SageMaker |
| `pdfqa-query-role` | App role: read-only S3 + OpenSearch |
| `pdfqa-auditor-role` | Read-only compliance/governance access |
| `pdfqa-sagemaker-execution-role` | SageMaker serverless inference |

### Other AWS Services (Stage 2 — provisioned, ready for Stage 3)

| Resource | Name | Detail |
|---|---|---|
| OpenSearch Serverless | `9vq5ahyfba5rkbskd1oe` | Vector search collection — eu-central-1 |
| SageMaker Endpoint | `pdfqa-embedding-endpoint` | Serverless `all-MiniLM-L6-v2` inference |

---

## CI/CD Pipeline

Every push to `main` triggers:

```
1. Lint       — python -m py_compile on all source files
2. Build      — docker buildx build ./pdf_qa (linux/amd64)
3. Push       — ECR: pdfqa-pdf-qa:<git-sha> + :latest
4. Apply K8s  — namespace, configmap, chromadb, service, HPA, secret
5. Deploy     — kubectl set image + rollout status (5 min timeout)
6. Print URL  — NLB hostname printed at end of run
```

Authentication: GitHub Actions assumes `pdfqa-github-actions` IAM role via OIDC — no AWS access keys stored in GitHub.

### GitHub Secrets Required

| Secret | Description |
|---|---|
| `AWS_ROLE_ARN` | `arn:aws:iam::140023408970:role/pdfqa-github-actions` |
| `ANTHROPIC_API_KEY` | Anthropic API key (sk-ant-...) |

---

## Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── ci-cd.yml          # GitHub Actions pipeline
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── storageclass.yaml      # EBS gp3
│   ├── chromadb/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── pvc.yaml
│   ├── query-api/
│   │   ├── deployment.yaml
│   │   ├── service.yaml       # NLB LoadBalancer
│   │   ├── serviceaccount.yaml
│   │   └── hpa.yaml
│   └── ingest/
│       └── job.yaml           # On-demand ingest job
└── pdf_qa/
    ├── api.py                 # FastAPI — /health, /upload, /query
    ├── ingest.py              # PDF → chunks → embeddings → ChromaDB
    ├── query.py               # Question → retrieve → Claude → answer
    ├── vector_store.py        # ChromaDB wrapper (local or HTTP)
    ├── config.py              # Centralised configuration
    ├── Dockerfile             # CPU-only PyTorch image
    ├── requirements.txt       # Pinned dependencies
    └── infra/                 # Terraform
        ├── main.tf
        ├── vpc.tf             # VPC, subnets, NAT GW
        ├── eks.tf             # EKS cluster, node group, OIDC
        ├── ecr.tf             # ECR repository
        ├── s3.tf              # S3 buckets
        ├── iam.tf             # App IAM roles
        ├── kms.tf             # KMS encryption key
        ├── opensearch.tf      # OpenSearch Serverless
        ├── sagemaker.tf       # SageMaker serverless endpoint
        ├── variables.tf
        └── outputs.tf
```

---

## Local Development (Stage 1 — no AWS required)

```bash
cd pdf_qa
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Set API key
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Ingest PDFs
python ingest.py

# Query
python query.py "What is the notice period?"
```

---

## Infrastructure Setup (one-time)

```bash
cd pdf_qa/infra
terraform init
terraform apply
```

Add these to `terraform.tfvars`:
```hcl
owner_tag              = "your-name"
terraform_iam_user_arn = "arn:aws:iam::ACCOUNT_ID:user/USERNAME"
github_repo            = "aamir456/QA-Pdf"
```

**Estimated AWS cost (eu-central-1):**
| Resource | Cost |
|---|---|
| 2× t3.medium EKS nodes | ~$0.088/hr |
| NAT Gateway | ~$0.045/hr + data |
| NLB | ~$0.008/hr + LCU |
| EBS 5 GiB gp3 | ~$0.40/month |
| ECR storage | ~$0.10/GB/month |
| **Total (approx)** | **~$4–5/day** |
