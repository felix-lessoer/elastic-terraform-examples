variable "deployment_mode" {
  type    = string
  default = "serverless"
}

variable "product_tier" {
  type    = string
  default = "complete"
}

variable "cps_hub" {
  type        = string
  description = "Which cloud project is the Cross-Project Search / CCS hub: aws, azure, or gcp."
  default     = "aws"

  validation {
    condition     = contains(["aws", "azure", "gcp"], var.cps_hub)
    error_message = "cps_hub must be aws, azure, or gcp."
  }
}

variable "deploy_aws" {
  type    = bool
  default = true
}

variable "deploy_azure" {
  type    = bool
  default = false
}

variable "deploy_gcp" {
  type    = bool
  default = false
}

check "hub_is_deployed" {
  assert {
    condition = (
      (var.cps_hub == "aws" && var.deploy_aws) ||
      (var.cps_hub == "azure" && var.deploy_azure) ||
      (var.cps_hub == "gcp" && var.deploy_gcp)
    )
    error_message = "cps_hub must refer to a cloud with deploy_*=true."
  }
}

variable "enable_cspm" {
  type    = bool
  default = true
}

variable "enable_detection_rules" {
  type    = bool
  default = true
}

# --- AWS ---
variable "aws_region" {
  type    = string
  default = "eu-west-1"
}

variable "elastic_aws_region" {
  type    = string
  default = "aws-eu-west-1"
}

variable "elastic_aws_project_name" {
  type    = string
  default = "AWS Observe and Protect"
}

variable "aws_deployment_template_id" {
  type    = string
  default = "aws-general-purpose-arm"
}

# --- Azure ---
variable "azure_region" {
  type    = string
  default = "westeurope"
}

variable "elastic_azure_region" {
  type    = string
  default = "azure-westeurope"
}

variable "elastic_azure_project_name" {
  type    = string
  default = "Azure Observe and Protect"
}

variable "azure_deployment_template_id" {
  type    = string
  default = "azure-general-purpose"
}

variable "azure_resource_group" {
  type    = string
  default = "elastic-cloud-poc"
}

variable "azure_subscription_id" {
  type    = string
  default = ""
}

variable "azure_tenant_id" {
  type    = string
  default = ""
}

variable "azure_client_id" {
  type    = string
  default = ""
}

variable "azure_client_secret" {
  type      = string
  default   = ""
  sensitive = true
}

# --- GCP ---
variable "google_cloud_project" {
  type    = string
  default = ""
}

variable "google_cloud_region" {
  type    = string
  default = "europe-west3"
}

variable "elastic_gcp_region" {
  type    = string
  default = "gcp-europe-west3"
}

variable "elastic_gcp_project_name" {
  type    = string
  default = "GCP Observe and Protect"
}

variable "gcp_deployment_template_id" {
  type    = string
  default = "gcp-general-purpose"
}

variable "google_cloud_credentials_file" {
  type    = string
  default = ""
}

variable "elastic_version" {
  type    = string
  default = "latest"
}

variable "name_prefix" {
  type    = string
  default = "elastic-poc"
}

variable "company_tags" {
  type        = map(string)
  description = "Company-policy tags/labels applied to all cloud resources (GCP keys/values are normalized)."

  validation {
    condition     = length(var.company_tags) > 0
    error_message = "Set company_tags according to your company tagging policy."
  }
}

variable "required_tag_keys" {
  type        = list(string)
  description = "Optional list of tag keys that must appear in company_tags (AWS/Azure exact match; GCP after normalization)."
  default     = []
}

variable "required_label_keys" {
  type        = list(string)
  description = "Optional GCP-specific required keys (normalized). Defaults to required_tag_keys when empty."
  default     = []
}
