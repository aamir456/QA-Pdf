# Two buckets, mirroring the "S3 raw-pdfs" and "S3 chunks" boxes in the
# architecture diagram. Kept separate (rather than one bucket with prefixes)
# so IAM policies can be scoped per-bucket cleanly: the query role never
# needs write access to raw PDFs, for example.

resource "random_id" "suffix" {
  byte_length = 4
}

# ---- Raw PDFs bucket ----

resource "aws_s3_bucket" "raw_pdfs" {
  bucket = "${var.project_prefix}-raw-pdfs-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_versioning" "raw_pdfs" {
  bucket = aws_s3_bucket.raw_pdfs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_pdfs" {
  bucket = aws_s3_bucket.raw_pdfs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.pdf_qa.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "raw_pdfs" {
  bucket                  = aws_s3_bucket.raw_pdfs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---- Processed chunks bucket ----

resource "aws_s3_bucket" "chunks" {
  bucket = "${var.project_prefix}-chunks-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_versioning" "chunks" {
  bucket = aws_s3_bucket.chunks.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "chunks" {
  bucket = aws_s3_bucket.chunks.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.pdf_qa.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "chunks" {
  bucket                  = aws_s3_bucket.chunks.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
