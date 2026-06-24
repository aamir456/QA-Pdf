# OpenSearch Serverless for vector search — replaces ChromaDB for this demo.
#
# COST WARNING: OpenSearch Serverless bills a minimum of ~4 OCUs (2 indexing
# + 2 search) the moment this collection is ACTIVE, whether or not you send
# it any traffic. At current list pricing that's roughly $0.96/hour. This is
# intentionally built as a demo-and-destroy resource: apply it, test it,
# screenshot it, then `terraform destroy` in the same session. Do not leave
# it running unattended.

locals {
  collection_name = "${var.project_prefix}-vectors"
}

# 1. Encryption policy — required before the collection can be created.
# Reuses the same KMS key already encrypting your S3 buckets.
resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "${var.project_prefix}-enc-policy"
  type = "encryption"
  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${local.collection_name}"]
      }
    ]
    AWSOwnedKey = false
    KmsARN      = aws_kms_key.pdf_qa.arn
  })
}

# 2. Network policy — public access, simplest path since no VPC exists yet.
# In a real production setup this would restrict to a VPC endpoint instead.
resource "aws_opensearchserverless_security_policy" "network" {
  name = "${var.project_prefix}-net-policy"
  type = "network"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.collection_name}"]
        },
        {
          ResourceType = "dashboard"
          Resource     = ["collection/${local.collection_name}"]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

# 3. Data access policy — the least-privilege part. ingest_role can write
# and create indices; query_role can only read. Mirrors the S3 IAM split.
resource "aws_opensearchserverless_access_policy" "data_access" {
  name = "${var.project_prefix}-access-policy"
  type = "data"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.collection_name}"]
          Permission   = ["aoss:CreateCollectionItems", "aoss:DescribeCollectionItems"]
        },
        {
          ResourceType = "index"
          Resource     = ["index/${local.collection_name}/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:UpdateIndex",
          ]
        }
      ]
      Principal = [aws_iam_role.ingest_role.arn]
    },
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.collection_name}"]
          Permission   = ["aoss:DescribeCollectionItems"]
        },
        {
          ResourceType = "index"
          Resource     = ["index/${local.collection_name}/*"]
          Permission = [
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
          ]
        }
      ]
      Principal = [aws_iam_role.query_role.arn]
    },
    {
      # Your own user needs access too, for the index-creation script you'll
      # run interactively (assuming a role from a script adds complexity
      # that isn't worth it for a same-day demo; this keeps setup simple).
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.collection_name}"]
          Permission   = ["aoss:CreateCollectionItems", "aoss:DescribeCollectionItems", "aoss:UpdateCollectionItems"]
        },
        {
          ResourceType = "index"
          Resource     = ["index/${local.collection_name}/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:UpdateIndex",
            "aoss:DeleteIndex",
          ]
        }
      ]
      Principal = [var.terraform_iam_user_arn]
    }
  ])
}

resource "aws_opensearchserverless_collection" "pdf_qa" {
  name = local.collection_name
  type = "VECTORSEARCH"

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]
}

output "opensearch_collection_endpoint" {
  description = "OpenSearch Serverless collection endpoint — used by the Python OpenSearch client"
  value       = aws_opensearchserverless_collection.pdf_qa.collection_endpoint
}

output "opensearch_collection_arn" {
  value = aws_opensearchserverless_collection.pdf_qa.arn
}
