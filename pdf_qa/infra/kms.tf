# Customer-managed KMS key, used to encrypt both S3 buckets at rest.
# Using a CMK instead of the default AWS-managed S3 key (SSE-S3) is deliberate:
# it lets us write an explicit key policy controlling exactly which IAM
# roles may encrypt/decrypt — the same "separate key policy per environment/team"
# principle from the architecture diagram, just scoped to one account here.

resource "aws_kms_key" "pdf_qa" {
  description             = "CMK for encrypting PDF QA project S3 buckets"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableRootAccountFullAccess"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid    = "AllowAppRolesToUseKey"
        Effect = "Allow"
        Principal = {
          AWS = [
            aws_iam_role.ingest_role.arn,
            aws_iam_role.query_role.arn,
          ]
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowAuditorToDecryptOnly"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.auditor_role.arn
        }
        Action   = "kms:Decrypt"
        Resource = "*"
      }
    ]
  })
}

resource "aws_kms_alias" "pdf_qa" {
  name          = "alias/${var.project_prefix}-key"
  target_key_id = aws_kms_key.pdf_qa.key_id
}
