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

variable "existing_topic_names" {
  type        = map(string)
  description = "Customer-owned Pub/Sub topic names to reuse by stream key (audit, firewall, vpcflow, dns, lb). The module will not manage these topics."
  default     = {}

  validation {
    condition = alltrue([
      for key, name in var.existing_topic_names :
      contains(["audit", "firewall", "vpcflow", "dns", "lb"], key) && trimspace(name) != ""
    ])
    error_message = "existing_topic_names keys must be audit, firewall, vpcflow, dns, or lb and names must be non-empty."
  }
}

variable "existing_sink_names" {
  type        = map(string)
  description = "Customer-owned Logging sink names to reuse by stream key. Reusing a sink also requires the matching existing_topic_names entry."
  default     = {}

  validation {
    condition = alltrue([
      for key, name in var.existing_sink_names :
      contains(["audit", "firewall", "vpcflow", "dns", "lb"], key) && trimspace(name) != ""
    ])
    error_message = "existing_sink_names keys must be audit, firewall, vpcflow, dns, or lb and names must be non-empty."
  }
}

variable "existing_subscription_names" {
  type        = map(string)
  description = "Customer-owned Pub/Sub subscription names to reuse by stream key. Reusing a subscription also requires the matching existing_topic_names entry."
  default     = {}

  validation {
    condition = alltrue([
      for key, name in var.existing_subscription_names :
      contains(["audit", "firewall", "vpcflow", "dns", "lb"], key) && trimspace(name) != ""
    ])
    error_message = "existing_subscription_names keys must be audit, firewall, vpcflow, dns, or lb and names must be non-empty."
  }
}

variable "grant_existing_subscription_access" {
  type        = bool
  description = "Grant the collector service account subscriber access on customer-owned subscriptions. False preserves customer IAM ownership."
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
