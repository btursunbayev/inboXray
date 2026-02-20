# Changelog

## 2026-02-19 - Concurrent batch processing + Bedrock integration

### Added
- Amazon Bedrock (Claude 3 Haiku) replaced Ollama for threat analysis
- `ThreadPoolExecutor` concurrent processing — all records in a batch run in parallel (I/O-bound: S3, Bedrock, SES)
- `batchItemFailures` partial batch failure — failed messages retry individually, not the whole batch
- Structured metric logging (`METRIC name value tags`) for CloudWatch Logs Insights P50/P95/P99 queries
- `scripts/benchmark.py` - injects synthetic emails into SQS, waits for drain, queries CWL Insights for latency stats
- `deploy.sh` - deploys infrastructure

### Changed
- SQS batch_size 1 → 10, added 5s batching window
- Lambda IAM: added `s3:ListBucket` permission

## 2026-02-09 - Phase 2: AI Agent Worker

### Added
- LangGraph agent
- Ollama integration for local LLM inference
- Playwright browser automation
- SQS queue with dead letter queue for async analysis
- DynamoDB table for analysis results
- Docker deployment

### Changed
- Lambda optionally pushes suspicious emails to SQS
- Emails kept in S3 if analysis enabled

### Fixed
- Hardcoded SQS ARN in Terraform IAM policy
- Missing DynamoDB table implementation

## 2026-02-08 - Deployment and bug fixes
- Added deploy.sh script to package Lambda function
- Fixed DynamoDB bug
- Added filter {} to S3 lifecycle rule

## 2026-02-07 - Tests
- Added unit tests for the sanitizer

## 2026-02-07 - AWS integration
- Added AWS adapter layer
- Added Lambda handler

## 2026-02-07 - Core sanitizer
- Implemented email parsing (sanitizer.py)
  - Handles multipart MIME messages
  - Extracts HTML and plain text
  - Removes tracking pixels (1x1 images, URLs with 'track')

## 2026-02-07 - Lambda and SES infrastructure  
- Added Lambda function to Terraform
- Set up SES receipt rule to save emails to S3
- Configured S3 notifications to trigger Lambda
- Set up IAM permissions (S3, DynamoDB, SES, CloudWatch Logs)

## 2026-02-07 - Schema fix
- Fixed DynamoDB table schema (was experimenting with composite keys)

## 2026-02-05 - Project setup
- Added license
- Added Makefile
- Added changelog

## 2026-02-05 - Infrastructure
- Set up Terraform for AWS
- Created Python package structure
- Added requirements.txt

## 2026-02-05 - Initial commit
- Project README
- .gitignore
- .env.example