# Changelog

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

