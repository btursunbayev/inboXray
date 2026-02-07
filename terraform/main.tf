terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# S3 bucket for storing raw incoming emails
resource "aws_s3_bucket" "raw_emails" {
  bucket = "${var.project_name}-raw-emails-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name        = "${var.project_name}-raw-emails"
    Project     = var.project_name
    Environment = "production"
  }
}

# S3 bucket lifecycle rule to delete emails after 24 hours
resource "aws_s3_bucket_lifecycle_configuration" "raw_emails_lifecycle" {
  bucket = aws_s3_bucket.raw_emails.id

  rule {
    id     = "delete-after-24-hours"
    status = "Enabled"

    expiration {
      days = 1
    }
  }
}

# Block public access to S3 bucket
resource "aws_s3_bucket_public_access_block" "raw_emails" {
  bucket = aws_s3_bucket.raw_emails.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB table for email aliases
resource "aws_dynamodb_table" "aliases" {
  name           = "${var.project_name}-aliases"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "alias"
  range_key      = "status"

  attribute {
    name = "alias"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  ttl {
    attribute_name = "expiration_time"
    enabled        = true
  }

  tags = {
    Name        = "${var.project_name}-aliases"
    Project     = var.project_name
    Environment = "production"
  }
}

# DynamoDB table for blocked senders
resource "aws_dynamodb_table" "blocklist" {
  name           = "${var.project_name}-blocklist"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "sender"

  attribute {
    name = "sender"
    type = "S"
  }

  tags = {
    Name        = "${var.project_name}-blocklist"
    Project     = var.project_name
    Environment = "production"
  }
}

# Get current AWS account ID for bucket naming
data "aws_caller_identity" "current" {}
