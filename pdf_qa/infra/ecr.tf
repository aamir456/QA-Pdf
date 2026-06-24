# ---------------------------------------------------------------------------
# ECR — container registry for the PDF Q&A Docker image.
# The CI/CD role is granted push access; node group role gets pull access
# via the AmazonEC2ContainerRegistryReadOnly managed policy in eks.tf.
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "pdf_qa" {
  name                 = "${var.project_prefix}-pdf-qa"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "${var.project_prefix}-pdf-qa" }
}

resource "aws_ecr_lifecycle_policy" "pdf_qa" {
  repository = aws_ecr_repository.pdf_qa.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images tagged with a git SHA"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["sha-", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      }
    ]
  })
}
