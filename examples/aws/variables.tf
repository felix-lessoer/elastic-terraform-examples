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

variable "bucket_name" {
  type        = string
  description = "Prefix for the S3 bucket that receives CloudTrail and VPC Flow Logs."
  default     = "elastic-observability-logs"
}

variable "existing_cloudtrail_bucket_name" {
  type        = string
  description = "Existing multi-region CloudTrail S3 bucket to poll directly. Empty creates a new trail."
  default     = ""
}

variable "cloudfront_queue_url" {
  type        = string
  description = "Optional SQS queue URL receiving CloudFront S3 log notifications. Empty leaves CloudFront collection unconfigured."
  default     = ""
}

variable "elastic_agent_instance_type" {
  type        = string
  description = "EC2 instance type for the agent-only AWS integrations."
  default     = "t3.medium"
}

variable "elastic_agent_version" {
  type        = string
  description = "Elastic Agent version installed on EC2."
  default     = "9.5.4"
}

variable "elastic_managed_collector_role_arn" {
  type        = string
  description = "Elastic's AWS super-role used by managed integrations for identity federation."
  default     = "arn:aws:iam::254766567737:role/cloud_connectors"
}

variable "enable_cockpit_dashboard" {
  type        = bool
  description = "Import the pinned AWS Observability cockpit dashboard."
  default     = true
}

variable "enable_ml_jobs" {
  type        = bool
  description = "Create and start AWS telemetry/security anomaly detection jobs."
  default     = true
}

variable "enable_ai_agents" {
  type        = bool
  description = "Create AWS cockpit Agent Builder tools and specialist agents."
  default     = true
}

variable "enable_observability_alerts" {
  type        = bool
  description = "Create telemetry-gap and security-findings alert rules."
  default     = true
}

variable "enable_workflows" {
  type        = bool
  description = "Deploy pinned Kibana Workflow YAML from examples/aws/workflows."
  default     = true
}

variable "execute_workflows_on_apply" {
  type        = bool
  description = "Execute each enabled pinned workflow once after create or update."
  default     = true
}

variable "deployment_creator_mode" {
  type        = bool
  description = "Enables behavior used only by the local Elastic PoC Deployment Creator."
  default     = false
}

variable "elastic_tags_required" {
  type        = bool
  description = "Whether organization-specific tags must be applied to the Elastic project and provisioned AWS resources."
  default     = true
}

variable "company_tags" {
  type        = map(string)
  description = "Company-policy tags applied to AWS resources and sanitized onto the Elastic project."
}

variable "required_tag_keys" {
  type        = list(string)
  description = "Optional tag keys that must be present in company_tags."
  default     = []
}
