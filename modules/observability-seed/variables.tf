variable "kibana_endpoint" {
  type = string
}

variable "elasticsearch_endpoint" {
  type = string
}

variable "elasticsearch_username" {
  type = string
}

variable "elasticsearch_password" {
  type      = string
  sensitive = true
}

variable "space_id" {
  type    = string
  default = "default"
}

variable "enable_ml_jobs" {
  type    = bool
  default = true
}

variable "start_ml_datafeeds" {
  type        = bool
  description = "Start ML datafeeds during apply. Disable for greenfield projects until source indices exist."
  default     = true
}

variable "enable_ai_agents" {
  type    = bool
  default = true
}

variable "enable_observability_alerts" {
  type    = bool
  default = true
}

# Optional: run the CSPM findings ML job on the Security project ES
# (where CSPM data lives). When empty, CSPM ML uses the Observability ES.
variable "security_elasticsearch_endpoint" {
  type    = string
  default = ""
}

variable "security_elasticsearch_username" {
  type    = string
  default = ""
}

variable "security_elasticsearch_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "security_findings_indices" {
  type        = list(string)
  description = "Index patterns used by the security findings alert and ML rate job."
  default     = ["logs-cloud_security_posture.findings-*"]
}

variable "cloud_slug" {
  type        = string
  description = "Short cloud id used in ML job / Agent Builder ids (e.g. gcp, aws, azure)."
  default     = "gcp"
}

variable "cloud_display_name" {
  type        = string
  description = "Human-readable cloud name used in alert/agent copy."
  default     = "GCP"
}

variable "additional_tool_ids" {
  type        = list(string)
  description = "Extra Agent Builder tool IDs to attach to cockpit agents (e.g. workflow tools created after this module)."
  default     = []
}
