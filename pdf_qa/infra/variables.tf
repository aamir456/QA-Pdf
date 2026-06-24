variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "eu-central-1"
}

variable "project_prefix" {
  description = "Short prefix used in resource names to keep them unique and identifiable"
  type        = string
  default     = "pdfqa"
}

variable "owner_tag" {
  description = "Name tag applied to all resources, for cost tracking / accountability"
  type        = string
}

variable "terraform_iam_user_arn" {
  description = "ARN of the IAM user running Terraform (used as the trusted principal that can assume the app roles). Get this from: aws sts get-caller-identity"
  type        = string
}

variable "eks_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.30"
}

variable "eks_node_instance_type" {
  description = "EC2 instance type for EKS managed node group"
  type        = string
  default     = "t3.medium"
}

variable "github_repo" {
  description = "GitHub repository in OWNER/REPO format (e.g. myorg/pdf-qa). Used in the OIDC trust policy so GitHub Actions can assume the CI role without long-lived keys."
  type        = string
}
