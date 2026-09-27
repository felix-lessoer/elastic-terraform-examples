variable "kibana_endpoint" {
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

# Kept for callers that still pass display names / inventory; the pinned
# NDJSON already embeds the values from the saved Kibana dashboard.
variable "security_project_name" {
  type        = string
  description = "Unused — retained for backward-compatible module inputs."
  default     = ""
}

variable "observability_project_name" {
  type        = string
  description = "Unused — retained for backward-compatible module inputs."
  default     = ""
}

variable "title" {
  type    = string
  default = "GCP Observe & Protect Cockpit"
}

variable "description" {
  type    = string
  default = "Aggregated security + observability posture across linked Elastic serverless projects."
}

variable "dashboard_id" {
  type        = string
  description = "Saved object id embedded in the pinned NDJSON (used for dashboard_url output)."
  default     = "fcf1246c-6ee2-4c91-94f8-f034e8d345bc"
}

variable "ndjson_path" {
  type        = string
  description = "Path to cockpit NDJSON export. Empty uses the module's default cockpit.ndjson."
  default     = ""
}

variable "ml_jobs" {
  type = list(object({
    id          = string
    description = string
    state       = string
  }))
  description = "Unused — ML inventory is frozen in cockpit.ndjson."
  default     = []
}

variable "ai_agents" {
  type = list(object({
    id    = string
    role  = string
    state = string
  }))
  description = "Unused — AI agent inventory is frozen in cockpit.ndjson."
  default     = []
}
