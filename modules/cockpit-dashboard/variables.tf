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

variable "title" {
  type    = string
  default = "GCP Observe & Protect Cockpit"
}

variable "description" {
  type    = string
  default = "Aggregated security + observability posture across linked Elastic serverless projects."
}

variable "space_id" {
  type    = string
  default = "default"
}

variable "security_project_name" {
  type        = string
  description = "Display name of the linked Security project (for cockpit copy)."
}

variable "observability_project_name" {
  type        = string
  description = "Display name of the Observability hub project."
}
