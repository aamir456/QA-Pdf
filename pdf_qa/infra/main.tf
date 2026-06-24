terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Local state for this portfolio project — fine for a single developer.
  # In a real team setup this would be an S3 backend with DynamoDB state locking;
  # noted here deliberately so the tradeoff is visible, not hidden.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "pdf-qa-genai"
      ManagedBy = "terraform"
      Owner     = var.owner_tag
    }
  }
}

data "aws_caller_identity" "current" {}
