variable "elastic_project_name" {
  type        = string
  description = "Name of the Elastic Serverless Observability project."
  default     = "AWS Observability"
}

variable "elastic_region" {
  type        = string
  description = "Elastic Cloud region for the Serverless Observability project."
  default     = "aws-eu-west-1"
}

variable "product_tier" {
  type        = string
  description = "Elastic Serverless Observability product tier."
  default     = "complete"
}

variable "aws_region" {
  type        = string
  description = "Bootstrap region for global AWS API calls. Metrics collection itself uses all regions."
  default     = "eu-west-1"
}

variable "name_prefix" {
  type        = string
  description = "Prefix used for the AWS IAM role and Elastic managed connector."
  default     = "elastic-observability"
}

variable "elastic_managed_collector_role_arn" {
  type        = string
  description = "Elastic's AWS super-role used by managed integrations for identity federation."
  default     = "arn:aws:iam::254766567737:role/cloud_connectors"
}

variable "company_tags" {
  type        = map(string)
  description = "Company-policy tags applied to AWS resources and sanitized onto the Elastic project."

  validation {
    condition     = length(var.company_tags) > 0
    error_message = "Set company_tags according to your company tagging policy."
  }
}

variable "required_tag_keys" {
  type        = list(string)
  description = "Optional tag keys that must be present in company_tags."
  default     = []
}
