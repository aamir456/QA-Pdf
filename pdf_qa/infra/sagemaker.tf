# SageMaker Serverless Inference endpoint hosting the all-MiniLM-L6-v2
# embedding model -- replaces local sentence-transformers inference with
# a managed AWS endpoint.
#
# COST NOTE: unlike OpenSearch Serverless, this has NO idle cost -- billing
# is per-millisecond of actual inference compute plus data processed. The
# endpoint can be left running without an hourly charge ticking. Cold starts
# (10-60s) occur after periods of no traffic. Still recommended to destroy
# when done experimenting, mainly to keep the account tidy, not urgently
# for cost reasons the way OpenSearch was.

variable "sagemaker_image_uri" {
  description = "HuggingFace inference container image URI for this region. Resolve with resolve_image_uri.py -- do not guess this value, container tags change over time."
  type        = string
}

variable "sagemaker_model_data_url" {
  description = "S3 URI to model.tar.gz, e.g. s3://pdfqa-chunks-xxxx/sagemaker/model.tar.gz. Build with build_sagemaker_package.py, then upload manually before terraform apply."
  type        = string
}

# --- Execution role: SageMaker (the service) assumes this, not your IAM user ---
# Different trust pattern from ingest_role/query_role: those trust YOUR user;
# this trusts the sagemaker.amazonaws.com service principal, because it's
# SageMaker's infrastructure -- not your script -- that needs to pull the
# model from S3 and write logs to CloudWatch.
resource "aws_iam_role" "sagemaker_execution_role" {
  name = "${var.project_prefix}-sagemaker-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "sagemaker.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "sagemaker_execution_policy" {
  name = "${var.project_prefix}-sagemaker-execution-policy"
  role = aws_iam_role.sagemaker_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadModelArtifactFromS3"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.chunks.arn}/*"
      },
      {
        Sid      = "ListChunksBucketForModelRead"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.chunks.arn
      },
      {
        Sid    = "WriteCloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/sagemaker/*"
      },
      {
        Sid      = "DecryptModelArtifact"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource = aws_kms_key.pdf_qa.arn
      },
      {
        Sid    = "PullInferenceContainerImage"
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = "arn:aws:ecr:${var.aws_region}:763104351884:repository/huggingface-pytorch-inference"
      },
      {
        Sid      = "EcrAuthToken"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      }
    ]
  })
}

# --- SageMaker Model: registers the container + model artifact location ---
resource "aws_sagemaker_model" "embedding_model" {
  name               = "${var.project_prefix}-embedding-model"
  execution_role_arn = aws_iam_role.sagemaker_execution_role.arn

  primary_container {
    image          = var.sagemaker_image_uri
    model_data_url = var.sagemaker_model_data_url
  }
}

# --- Endpoint Configuration: serverless, not provisioned instances ---
resource "aws_sagemaker_endpoint_configuration" "embedding_config" {
  name = "${var.project_prefix}-embedding-endpoint-config"

  production_variants {
    variant_name = "AllTraffic"
    model_name   = aws_sagemaker_model.embedding_model.name

    serverless_config {
      max_concurrency   = 5
      memory_size_in_mb = 3072 # model is ~90MB but transformers/torch runtime needs headroom
    }
  }
}

# --- Endpoint: the actual invokable resource ---
resource "aws_sagemaker_endpoint" "embedding_endpoint" {
  name                 = "${var.project_prefix}-embedding-endpoint"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.embedding_config.name
}

# --- Extend ingest_role and query_role to invoke this endpoint ---
resource "aws_iam_role_policy" "ingest_sagemaker_invoke" {
  name = "${var.project_prefix}-ingest-sagemaker-invoke"
  role = aws_iam_role.ingest_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeEmbeddingEndpoint"
      Effect   = "Allow"
      Action   = ["sagemaker:InvokeEndpoint"]
      Resource = aws_sagemaker_endpoint.embedding_endpoint.arn
    }]
  })
}

resource "aws_iam_role_policy" "query_sagemaker_invoke" {
  name = "${var.project_prefix}-query-sagemaker-invoke"
  role = aws_iam_role.query_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeEmbeddingEndpoint"
      Effect   = "Allow"
      Action   = ["sagemaker:InvokeEndpoint"]
      Resource = aws_sagemaker_endpoint.embedding_endpoint.arn
    }]
  })
}

output "sagemaker_endpoint_name" {
  value = aws_sagemaker_endpoint.embedding_endpoint.name
}

output "sagemaker_execution_role_arn" {
  value = aws_iam_role.sagemaker_execution_role.arn
}
