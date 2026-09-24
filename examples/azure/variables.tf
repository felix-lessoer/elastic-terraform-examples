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
