variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "name_prefix" {
  type    = string
  default = "elastic-poc"
}

variable "region" {
  type    = string
  default = "europe-west3"
}

variable "company_labels" {
  type        = map(string)
  description = <<-EOT
    Mandatory company-policy labels applied to every labelable GCP resource.
    Keys/values are normalized to GCP label rules (lowercase, [a-z0-9_-], max 63).
    Example: { cost-center = "1234", owner = "platform-team", environment = "poc" }
  EOT

  validation {
    condition     = length(var.company_labels) > 0
    error_message = "company_labels must contain at least one label required by company policy."
  }
}

variable "required_label_keys" {
  type        = list(string)
  description = "Label keys that must be present in company_labels (after normalization). Empty skips the check."
  default     = []
}

variable "additional_labels" {
  type        = map(string)
  description = "Optional extra labels merged on top of company_labels (e.g. elastic-specific)."
  default     = {}
}

variable "fetch_project_number" {
  type        = bool
  description = "Look up project number via resourcemanager.projects.get (requires that IAM permission)."
  default     = false
}

variable "audit_filter" {
  type    = string
  default = "logName:\"cloudaudit.googleapis.com\""
}

variable "firewall_filter" {
  type    = string
  default = "log_id(\"compute.googleapis.com/firewall\")"
}

variable "vpcflow_filter" {
  type    = string
  default = "log_id(\"compute.googleapis.com/vpc_flows\")"
}

variable "dns_filter" {
  type    = string
  default = "resource.type=\"dns_query\""
}

variable "lb_filter" {
  type    = string
  default = "resource.type=\"http_load_balancer\""
}
