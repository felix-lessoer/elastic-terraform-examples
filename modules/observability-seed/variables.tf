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
