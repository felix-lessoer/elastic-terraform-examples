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
  type = list(object({
    name                 = string
    description          = optional(string, "")
    package_name         = string
    prerelease           = optional(bool, false)
    package_version      = optional(string, null)
    agent_policy         = optional(bool, true)
    managed              = optional(bool, false)
    policy_template      = optional(string, null)
    vars_json            = optional(string, null)
    var_group_selections = optional(map(string), {})
    inputs               = optional(any, {})
    cloud_connector = optional(object({
      enabled            = bool
      cloud_connector_id = optional(string)
      name               = optional(string)
      target_csp         = optional(string)
    }), null)
  }))
  description = "Fleet integrations to install. Prefer managed=true for agentless when supported."
  default     = []
}
