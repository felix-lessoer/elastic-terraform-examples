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

variable "tags" {
  type        = map(string)
  description = "Tags applied to AWS resources."
  default     = {}
}
