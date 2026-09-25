variable "deployment_mode" {
  type    = string
  default = "serverless"
}

variable "elastic_project_name" {
  type    = string
  default = "AWS Observe and Protect"
}

variable "observability_project_name" {
  type    = string
  default = "AWS Observability Cockpit"
}

variable "enable_observability_project" {
  type        = bool
  description = "Create a serverless Observability project linked to Security via Cross-Project Search and deploy the cockpit dashboard."
  default     = true
}

variable "enable_ml_jobs" {
  type    = bool
  default = true
}

variable "enable_ai_agents" {
  type    = bool
  default = true
}

variable "enable_observability_alerts" {
  type    = bool
  default = true
}

variable "elastic_region" {
  type    = string
  default = "aws-eu-west-1"
}

variable "product_tier" {
  type    = string
  default = "complete"
}

variable "elastic_version" {
  type    = string
  default = "latest"
}

variable "deployment_template_id" {
  type    = string
  default = "aws-general-purpose-arm"
}

variable "aws_region" {
  type    = string
  default = "eu-west-1"
}

variable "name_prefix" {
  type    = string
  default = "elastic-poc"
}

variable "company_tags" {
  type        = map(string)
  description = "Company-policy tags applied to all AWS resources (and sanitized onto the Elastic project)."

  validation {
    condition     = length(var.company_tags) > 0
    error_message = "Set company_tags according to your company tagging policy."
  }
}

variable "required_tag_keys" {
  type        = list(string)
  description = "Optional list of tag keys that must appear in company_tags."
  default     = []
}

variable "bucket_name" {
  type    = string
  default = "elastic-cloud-logs"
}

variable "enable_cloudtrail" {
  type    = bool
  default = true
}

variable "enable_vpc_flow_logs" {
  type    = bool
  default = true
}

variable "enable_sqs" {
  type        = bool
  description = "Create SQS queues for CloudTrail/vpcflow. Set false when org SCPs deny sqs:CreateQueue."
  default     = true
}

variable "enable_cspm" {
  type        = bool
  description = "Agentless CSPM (CIS AWS) via cloud_security_posture managed integration."
  default     = true
}

variable "enable_cnvm" {
  type        = bool
  description = "Agentless Cloud Native Vulnerability Management for AWS (vuln_mgmt policy template)."
  default     = true
}

variable "enable_billing_metrics" {
  type        = bool
  description = "Collect AWS billing metrics via the agent-based aws package (Cost Explorer permissions on the collector role)."
  default     = true
}

variable "enable_security_hub" {
  type        = bool
  description = "Collect AWS Security Hub findings/insights (console Security findings widget)."
  default     = true
}

variable "enable_guardduty" {
  type        = bool
  description = "Collect Amazon GuardDuty findings (feeds console security widgets / Security Hub)."
  default     = true
}

variable "enable_aws_health" {
  type        = bool
  description = "Collect AWS Health events/metrics (console Health widget)."
  default     = true
}

variable "enable_trusted_advisor" {
  type        = bool
  description = "Collect Trusted Advisor check metrics via CloudWatch namespace AWS/TrustedAdvisor (no first-class Elastic TA stream)."
  default     = true
}

variable "enable_detection_rules" {
  type    = bool
  default = true
}

variable "detection_rule_tags" {
  type = list(object({
    key   = string
    value = string
  }))
  # Prebuilt AWS rules use "Data Source: AWS".
  default = [
    { key = "Data Source", value = "AWS" }
  ]
}

variable "enable_workflows" {
  type        = bool
  description = "Deploy pinned Kibana Workflow YAML from examples/aws/workflows/ after greenfield create."
  default     = true
}

variable "execute_workflows_on_apply" {
  type        = bool
  description = "Manually execute each enabled workflow once after Terraform creates/updates it."
  default     = true
}

variable "deploy_workflows_to_security" {
  type        = bool
  description = "Also deploy the same pinned workflows into the Security project Kibana."
  default     = false
}

variable "enable_elastic_agent" {
  type        = bool
  description = "Deploy EC2 Elastic Agents for agent-based integrations (CloudTrail, vpcflow, metrics)."
  default     = true
}

variable "elastic_agent_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "elastic_agent_version" {
  type        = string
  description = "Elastic Agent version installed on the EC2 VMs."
  default     = "9.5.4"
}
