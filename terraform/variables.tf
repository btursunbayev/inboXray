variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "inboxray"
}

variable "domain_name" {
  description = "Domain name for SES email receiving"
  type        = string
}

variable "forward_to_email" {
  description = "Email address to forward clean emails to"
  type        = string
}

variable "api_key" {
  description = "Secret key required in x-api-key header for all API requests"
  type        = string
  sensitive   = true
}
