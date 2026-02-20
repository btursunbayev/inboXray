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

    filter {}

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

  attribute {
    name = "alias"
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

# DynamoDB table for analysis results
resource "aws_dynamodb_table" "analysis_results" {
  name           = "${var.project_name}-analysis-results"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "message_id"
  range_key      = "timestamp"

  attribute {
    name = "message_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  attribute {
    name = "threat_level"
    type = "S"
  }

  global_secondary_index {
    name            = "ThreatLevelIndex"
    hash_key        = "threat_level"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  tags = {
    Name        = "${var.project_name}-analysis-results"
    Project     = var.project_name
    Environment = "production"
  }
}

# Get current AWS account ID for bucket naming
data "aws_caller_identity" "current" {}

# IAM role for Lambda function
resource "aws_iam_role" "lambda_execution" {
  name = "${var.project_name}-lambda-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name    = "${var.project_name}-lambda-execution"
    Project = var.project_name
  }
}

# IAM policy for Lambda function
resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "${aws_s3_bucket.raw_emails.arn}",
          "${aws_s3_bucket.raw_emails.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.aliases.arn,
          aws_dynamodb_table.blocklist.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:GetQueueUrl",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.email_analysis.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem"
        ]
        Resource = aws_dynamodb_table.analysis_results.arn
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
      }
    ]
  })
}

# SES receipt rule set
resource "aws_ses_receipt_rule_set" "main" {
  rule_set_name = "${var.project_name}-receipt-rules"
}

# Activate the receipt rule set
resource "aws_ses_active_receipt_rule_set" "main" {
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
}

# SNS topic for SES notifications
resource "aws_sns_topic" "ses_notifications" {
  name = "${var.project_name}-ses-notifications"

  tags = {
    Name    = "${var.project_name}-ses-notifications"
    Project = var.project_name
  }
}

# SNS topic policy to allow SES to publish
resource "aws_sns_topic_policy" "ses_publish" {
  arn = aws_sns_topic.ses_notifications.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ses.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.ses_notifications.arn
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# SNS subscription to SQS
resource "aws_sns_topic_subscription" "ses_to_sqs" {
  topic_arn = aws_sns_topic.ses_notifications.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.email_analysis.arn
}

# SQS queue policy to allow SNS to send messages
resource "aws_sqs_queue_policy" "allow_sns" {
  queue_url = aws_sqs_queue.email_analysis.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "sns.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.email_analysis.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.ses_notifications.arn
          }
        }
      }
    ]
  })
}

# SES receipt rule to save emails to S3 and notify SNS
resource "aws_ses_receipt_rule" "save_to_s3" {
  name          = "${var.project_name}-save-to-s3"
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
  recipients    = [var.domain_name]
  enabled       = true
  scan_enabled  = true

  s3_action {
    bucket_name       = aws_s3_bucket.raw_emails.bucket
    object_key_prefix = "incoming/"
    position          = 1
    topic_arn         = aws_sns_topic.ses_notifications.arn
  }

  depends_on = [aws_s3_bucket_policy.ses_write]
}

# S3 bucket policy to allow SES to write emails
resource "aws_s3_bucket_policy" "ses_write" {
  bucket = aws_s3_bucket.raw_emails.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSESPuts"
        Effect = "Allow"
        Principal = {
          Service = "ses.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.raw_emails.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# Lambda function for email analysis with Bedrock
resource "aws_lambda_function" "email_analyzer" {
  filename      = "../lambda_function.zip"
  function_name = "${var.project_name}-email-analyzer"
  role          = aws_iam_role.lambda_execution.arn
  handler       = "src.handlers.handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 60
  memory_size   = 512

  environment {
    variables = {
      FORWARD_TO_EMAIL        = var.forward_to_email
      SENDER_EMAIL            = "noreply@${var.domain_name}"
      ANALYSIS_RESULTS_TABLE  = aws_dynamodb_table.analysis_results.name
      BLOCKLIST_TABLE         = aws_dynamodb_table.blocklist.name
    }
  }

  tags = {
    Name    = "${var.project_name}-email-analyzer"
    Project = var.project_name
  }
}

# Lambda event source mapping from SQS
resource "aws_lambda_event_source_mapping" "sqs_to_lambda" {
  event_source_arn                   = aws_sqs_queue.email_analysis.arn
  function_name                      = aws_lambda_function.email_analyzer.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  enabled                            = true
  function_response_types            = ["ReportBatchItemFailures"]
}

# SQS queue for async email analysis
resource "aws_sqs_queue" "email_analysis_dlq" {
  name                      = "${var.project_name}-analysis-dlq"
  message_retention_seconds = 1209600  # 14 days

  tags = {
    Name    = "${var.project_name}-analysis-dlq"
    Project = var.project_name
  }
}

resource "aws_sqs_queue" "email_analysis" {
  name                       = "${var.project_name}-analysis-queue"
  visibility_timeout_seconds = 300  # 5 minutes for agent processing
  message_retention_seconds  = 345600  # 4 days
  receive_wait_time_seconds  = 20  # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.email_analysis_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name    = "${var.project_name}-analysis-queue"
    Project = var.project_name
  }
}

# ── REST API ──────────────────────────────────────────────────────────────────

resource "aws_iam_role" "api_lambda_execution" {
  name = "${var.project_name}-api-lambda-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = {
    Name    = "${var.project_name}-api-lambda-execution"
    Project = var.project_name
  }
}

resource "aws_iam_role_policy" "api_lambda_policy" {
  name = "${var.project_name}-api-lambda-policy"
  role = aws_iam_role.api_lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Effect = "Allow"
        Action = ["dynamodb:Query", "dynamodb:Scan", "dynamodb:GetItem"]
        Resource = [
          aws_dynamodb_table.analysis_results.arn,
          "${aws_dynamodb_table.analysis_results.arn}/index/*",
        ]
      },
      {
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
        Resource = aws_dynamodb_table.blocklist.arn
      },
    ]
  })
}

resource "aws_lambda_function" "api" {
  filename      = "../lambda_function.zip"
  function_name = "${var.project_name}-api"
  role          = aws_iam_role.api_lambda_execution.arn
  handler       = "src.api.app.handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      ANALYSIS_RESULTS_TABLE = aws_dynamodb_table.analysis_results.name
      BLOCKLIST_TABLE        = aws_dynamodb_table.blocklist.name
    }
  }

  tags = {
    Name    = "${var.project_name}-api"
    Project = var.project_name
  }
}

resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "DELETE", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
  }

  tags = {
    Name    = "${var.project_name}-api"
    Project = var.project_name
  }
}

resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_gateway_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
