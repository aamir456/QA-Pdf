# Stage 2 — Terraform: S3 + IAM (least privilege)

Provisions the storage and access-control layer for the PDF QA pipeline:
two encrypted S3 buckets, a customer-managed KMS key, and three IAM roles
with least-privilege policies (ingest, query, auditor).

This is infrastructure only — it does not yet touch `ingest.py` / `query.py`.
That wiring happens in a later stage, once you're comfortable with what's
been provisioned and why.

## What gets created

| Resource | Purpose |
|---|---|
| `aws_s3_bucket.raw_pdfs` | Stores uploaded PDFs. Versioned, KMS-encrypted, no public access. |
| `aws_s3_bucket.chunks` | Stores extracted text chunks + metadata. Same protections. |
| `aws_kms_key.pdf_qa` | Customer-managed key encrypting both buckets at rest. |
| `aws_iam_role.ingest_role` | Can write raw PDFs, read+write chunks. Cannot delete anything. |
| `aws_iam_role.query_role` | Read-only on chunks. No access at all to raw PDFs. |
| `aws_iam_role.auditor_role` | Read-only on both buckets. For compliance review. |

Each role currently trusts only your own IAM user (`terraform_iam_user_arn`)
— this is a single-developer project. The trust policy is written as a list
specifically so adding a teammate later is a one-line change.

## Setup

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and confirm `terraform_iam_user_arn` matches what
`aws sts get-caller-identity` printed for you earlier (the `Arn` field).

## Run it

```bash
terraform init      # downloads the AWS + random providers
terraform validate  # checks syntax and internal consistency, no AWS calls
terraform plan       # shows exactly what would be created — review before applying
terraform apply       # type 'yes' when prompted — actually creates the resources
```

`terraform plan` is the most important command to read carefully here: it
should show **11 resources to add** (2 buckets + their versioning/encryption/
public-access-block configs + 1 KMS key + 1 alias + 3 IAM roles + 3 IAM role
policies + 1 random_id), **0 to change, 0 to destroy**. If it proposes
changing or destroying anything on a first run, stop and paste me the output
before applying.

## Verify in the AWS Console

After `apply` finishes, it prints outputs including bucket names and role
ARNs. Spot-check in the Console:
- **S3** → both buckets exist, "Block all public access" shows as on
- **KMS** → the key exists with rotation enabled
- **IAM → Roles** → all three roles exist, each with one inline policy

## Cost

All of this is in AWS's always-free tier at this scale: S3 storage for a
handful of PDFs, a single KMS key (small monthly fee, around $1/month per
key — this is the one thing here that isn't fully free), and IAM roles
(IAM itself has no cost). If you want true $0, you can swap the KMS CMK
for the default AWS-managed S3 key (`aws:kms` with no `kms_master_key_id` —
the `SSE-S3`/default path) — ask me and I'll show the one-line change.

## Tearing it down

When you're done experimenting and want to stop any small ongoing charges:

```bash
terraform destroy
```

Review what it proposes to delete before confirming with `yes`.

## Next stage

Stage 3 wires `ingest.py` and `query.py` to assume these roles via `sts:AssumeRole`
and read/write the real S3 buckets instead of local disk — at which point this
infrastructure stops being decorative and becomes the actual data path.
