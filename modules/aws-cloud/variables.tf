variable "name_prefix" {
  type        = string
  description = "Prefix for AWS resource names."
  default     = "elastic-poc"
}

variable "bucket_name" {
  type        = string
  description = "S3 bucket name prefix for CloudTrail and other logs."
  default     = "elastic-cloud-logs"
}

variable "enable_cloudtrail" {
  type        = bool
  description = "Create a multi-region CloudTrail trail writing to the log bucket."
  default     = true
}

variable "enable_vpc_flow_logs" {
  type        = bool
  description = "Enable VPC flow logs to S3 for the default VPC (if present)."
  default     = true
}

variable "enable_sqs" {
  type        = bool
  description = "Create SQS queues + S3 notifications for CloudTrail/vpcflow. Disable when org SCPs block sqs:CreateQueue."
  default     = true
}

variable "company_tags" {
  type        = map(string)
  description = "Mandatory company-policy tags applied to every taggable AWS resource."

  validation {
    condition     = length(var.company_tags) > 0
    error_message = "company_tags must contain at least one tag required by company policy."
  }
}

variable "required_tag_keys" {
  type        = list(string)
  description = "Tag keys that must be present in company_tags. Empty skips the check."
  default     = []
}

variable "additional_tags" {
  type        = map(string)
  description = "Optional extra tags merged on top of company_tags."
  default     = {}
}
