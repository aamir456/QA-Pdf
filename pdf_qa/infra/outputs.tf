output "raw_pdfs_bucket_name" {
  description = "S3 bucket for raw uploaded PDFs"
  value       = aws_s3_bucket.raw_pdfs.bucket
}

output "chunks_bucket_name" {
  description = "S3 bucket for processed text chunks"
  value       = aws_s3_bucket.chunks.bucket
}

output "ingest_role_arn" {
  description = "Role to assume when running ingest.py"
  value       = aws_iam_role.ingest_role.arn
}

output "query_role_arn" {
  description = "Role to assume when running query.py"
  value       = aws_iam_role.query_role.arn
}

output "auditor_role_arn" {
  description = "Read-only role for compliance/governance review"
  value       = aws_iam_role.auditor_role.arn
}

output "kms_key_arn" {
  description = "Customer-managed KMS key used to encrypt both buckets"
  value       = aws_kms_key.pdf_qa.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL — use this as the IMAGE prefix in CI/CD"
  value       = aws_ecr_repository.pdf_qa.repository_url
}

output "eks_cluster_name" {
  description = "EKS cluster name — pass to: aws eks update-kubeconfig --name <value>"
  value       = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "github_actions_role_arn" {
  description = "IAM role ARN for GitHub Actions OIDC — set as GH secret AWS_ROLE_ARN"
  value       = aws_iam_role.github_actions.arn
}
