# Three roles, mirroring the IAM governance diagram:
#   ingest_role   -> what ingest.py would assume: write raw PDFs, read+write chunks
#   query_role    -> what query.py would assume: read-only on chunks, no write access anywhere
#   auditor_role  -> read-only on everything, for compliance/governance review
#
# All three trust only your own IAM user for now (single-developer project),
# but the trust policy is written as a list so adding teammates later is a
# one-line change, not a restructure.

locals {
  trusted_principals = [var.terraform_iam_user_arn]
}

# ---------------------------------------------------------------------------
# INGEST ROLE — mirrors role/BackendEngineer or the ECS worker in the diagram
# ---------------------------------------------------------------------------

resource "aws_iam_role" "ingest_role" {
  name = "${var.project_prefix}-ingest-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = local.trusted_principals }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ingest_policy" {
  name = "${var.project_prefix}-ingest-policy"
  role = aws_iam_role.ingest_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "WriteRawPdfs"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
        ]
        Resource = "${aws_s3_bucket.raw_pdfs.arn}/*"
      },
      {
        Sid      = "ListRawPdfsBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.raw_pdfs.arn
      },
      {
        Sid    = "ReadWriteChunks"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
        ]
        Resource = "${aws_s3_bucket.chunks.arn}/*"
      },
      {
        Sid      = "ListChunksBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.chunks.arn
      },
      {
        Sid    = "OpenSearchServerlessDataPlaneAccess"
        Effect = "Allow"
        Action = ["aoss:APIAccessAll"]
        Resource = "*"
      }
      # Deliberately NOT granted: s3:DeleteObject, s3:PutBucketPolicy,
      # any IAM actions. Ingestion can add data; it cannot destroy data
      # or change who has access to it.
    ]
  })
}

# ---------------------------------------------------------------------------
# QUERY ROLE — mirrors role/FrontendEngineer / the query service in the diagram
# ---------------------------------------------------------------------------

resource "aws_iam_role" "query_role" {
  name = "${var.project_prefix}-query-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = local.trusted_principals }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "query_policy" {
  name = "${var.project_prefix}-query-policy"
  role = aws_iam_role.query_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadOnlyChunks"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.chunks.arn}/*"
      },
      {
        Sid      = "ListChunksBucketForQuery"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.chunks.arn
      },
      {
        Sid      = "OpenSearchServerlessDataPlaneAccessQuery"
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = "*"
      }
      # No access at all to raw_pdfs — the query path never needs the
      # original PDF, only the processed chunks. No write permissions
      # anywhere: a compromised query service cannot tamper with data.
    ]
  })
}

# ---------------------------------------------------------------------------
# AUDITOR ROLE — read-only across everything, for governance/compliance review
# ---------------------------------------------------------------------------

resource "aws_iam_role" "auditor_role" {
  name = "${var.project_prefix}-auditor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = local.trusted_principals }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "auditor_policy" {
  name = "${var.project_prefix}-auditor-policy"
  role = aws_iam_role.auditor_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadOnlyEverything"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = [
          "${aws_s3_bucket.raw_pdfs.arn}/*",
          "${aws_s3_bucket.chunks.arn}/*",
        ]
      },
      {
        Sid    = "ListBucketsForAuditor"
        Effect = "Allow"
        Action = ["s3:ListBucket"]
        Resource = [
          aws_s3_bucket.raw_pdfs.arn,
          aws_s3_bucket.chunks.arn,
        ]
      }
      # No GetObject on anything implies no PutObject either — auditor
      # is strictly read-only, cannot modify or delete a single byte.
    ]
  })
}
