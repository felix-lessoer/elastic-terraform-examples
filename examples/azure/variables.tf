variable "deployment_mode" {
  type    = string
  default = "serverless"
}

variable "elastic_project_name" {
  type    = string
  default = "Azure Observe and Protect"
}

variable "elastic_region" {
  type    = string
  default = "azure-westeurope"
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
  default = "azure-general-purpose"
}

variable "azure_region" {
  type    = string
  default = "westeurope"
}

variable "azure_resource_group" {
  type    = string
  default = "elastic-cloud-poc"
}

variable "azure_subscription_id" {
  type = string
}

variable "azure_tenant_id" {
  type = string
}

variable "azure_client_id" {
  type = string
}

variable "azure_client_secret" {
  type      = string
  sensitive = true
}

variable "name_prefix" {
  type    = string
  default = "elastic-poc"
}

variable "company_tags" {
  type        = map(string)
  description = "Company-policy tags applied to all Azure resources (and sanitized onto the Elastic project)."

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

variable "enable_cspm" {
  type    = bool
  default = true
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
  default = [
    { key = "Data Source", value = "Azure" }
  ]
}
