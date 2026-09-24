variable "deployment_mode" {
  type    = string
  default = "serverless"
}

variable "elastic_project_name" {
  type    = string
  default = "GCP Observe and Protect"
}

variable "elastic_region" {
  type    = string
  default = "gcp-europe-west3"
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
  default = "gcp-general-purpose"
}

variable "google_cloud_project" {
  type = string
}

variable "google_cloud_region" {
  type    = string
  default = "europe-west3"
}

variable "google_cloud_credentials_file" {
  type        = string
  description = "Path to GCP service account JSON used by Terraform. Leave empty to use ADC."
  default     = ""
}

variable "name_prefix" {
  type    = string
  default = "elastic-poc"
}

variable "company_labels" {
  type        = map(string)
  description = "Company-policy labels applied to all GCP resources (and sanitized onto the Elastic project)."

  validation {
    condition     = length(var.company_labels) > 0
    error_message = "Set company_labels according to your company tagging policy."
  }
}

variable "required_label_keys" {
  type        = list(string)
  description = "Optional list of label keys that must appear in company_labels."
  default     = []
}

variable "enable_cspm" {
  type    = bool
  default = true
}

variable "enable_billing_metrics" {
  type        = bool
  description = "Enable GCP billing metrics stream (requires billing_dataset_id)."
  default     = false
}

variable "billing_dataset_id" {
  type        = string
  description = "BigQuery dataset id for GCP billing export (required when enable_billing_metrics is true)."
  default     = ""
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
    { key = "Data Source", value = "Google Cloud" }
  ]
}
