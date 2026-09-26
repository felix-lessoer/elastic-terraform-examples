variable "kibana_endpoint" {
  type        = string
  description = "Kibana HTTPS endpoint."
}

variable "elasticsearch_endpoint" {
  type        = string
  description = "Elasticsearch HTTPS endpoint."
}

variable "elasticsearch_username" {
  type        = string
  description = "Elasticsearch/Kibana username."
}

variable "elasticsearch_password" {
  type        = string
  sensitive   = true
  description = "Elasticsearch/Kibana password."
}

variable "policy_name" {
  type        = string
  description = "Fleet agent policy name."
  default     = "cloud-observe-protect"
}

variable "policy_namespace" {
  type        = string
  description = "Fleet namespace for the agent policy."
  default     = "default"
}

variable "space_id" {
  type        = string
  description = "Kibana space id."
  default     = "default"
}

variable "enable_detection_rules" {
  type        = bool
  description = "Install prebuilt Security rules and enable CSP-tagged rules."
  default     = true
}

variable "detection_rule_tags" {
  type = list(object({
    key   = string
    value = string
  }))
  description = "Tag key/value pairs used to enable prebuilt detection rules."
  default     = []
}

variable "integrations" {
  type        = any
  description = "Fleet integrations to install (list of objects). Prefer managed=true for agentless when supported."
  default     = []
}
