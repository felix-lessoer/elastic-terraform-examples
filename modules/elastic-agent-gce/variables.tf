variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "name" {
  type        = string
  description = "GCE instance name."
  default     = "elastic-agent"
}

variable "zone" {
  type        = string
  description = "GCE zone (e.g. europe-west3-b)."
}

variable "machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "network" {
  type        = string
  description = "VPC network name."
  default     = "default"
}

variable "subnetwork" {
  type        = string
  description = "Optional subnetwork self-link or name. Empty uses the network default."
  default     = ""
}

variable "company_labels" {
  type        = map(string)
  description = "Labels applied to the GCE instance (already GCP-normalized preferred)."
  default     = {}
}

variable "fleet_url" {
  type        = string
  description = "Fleet Server URL used for enrollment (https://...fleet...:443)."
}

variable "enrollment_token" {
  type        = string
  sensitive   = true
  description = "Fleet enrollment token for the target agent policy."
}

variable "agent_version" {
  type        = string
  description = "Elastic Agent version to install from artifacts.elastic.co."
  default     = "9.5.4"
}

variable "service_account_email" {
  type        = string
  description = "Optional GCE service account email. Empty uses the project default compute SA."
  default     = ""
}
