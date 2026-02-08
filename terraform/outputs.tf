output "s3_bucket_name" {
  description = "Name of the S3 bucket for raw emails"
  value       = aws_s3_bucket.raw_emails.bucket
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table for aliases"
  value       = aws_dynamodb_table.aliases.name
}

output "dynamodb_blocklist_table_name" {
  description = "Name of the DynamoDB table for blocklist"
  value       = aws_dynamodb_table.blocklist.name
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.email_processor.function_name
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_execution.arn
}
