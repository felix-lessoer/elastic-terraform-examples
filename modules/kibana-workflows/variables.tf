variable "kibana_endpoint" {
  type        = string
  description = "Kibana endpoint URL for the target project."
}

variable "elasticsearch_username" {
  type        = string
  description = "Kibana/Elasticsearch username."
}

variable "elasticsearch_password" {
  type        = string
  sensitive   = true
  description = "Kibana/Elasticsearch password."
}

variable "space_id" {
  type        = string
  description = "Kibana space id."
  default     = "default"
}

variable "workflows_dir" {
  type        = string
  description = "Directory of workflow YAML files (*.yml / *.yaml) to deploy. Filename (without extension) becomes the stable workflow_id."
}

variable "enabled_workflow_ids" {
  type        = set(string)
  description = "Optional allow-list of workflow ids to deploy. Null deploys every YAML file in workflows_dir."
  default     = null
  nullable    = true
}

variable "execute_on_apply" {
  type        = bool
  description = "After create/update, manually run each enabled workflow once (POST /api/workflows/workflow/{id}/run)."
  default     = true
}
