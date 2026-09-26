variable "deployment_mode" {
  type        = string
  description = "Elastic topology: serverless (default) or hosted."
  default     = "serverless"

  validation {
    condition     = contains(["serverless", "hosted"], var.deployment_mode)
    error_message = "deployment_mode must be \"serverless\" or \"hosted\"."
  }
}

variable "project_kind" {
  type        = string
  description = "Serverless project kind: security (default) or observability."
  default     = "security"

  validation {
    condition     = contains(["security", "observability"], var.project_kind)
    error_message = "project_kind must be \"security\" or \"observability\"."
  }
}

variable "name" {
  type        = string
  description = "Name of the Elastic Cloud project or hosted deployment."
}

variable "region" {
  type        = string
  description = "Elastic Cloud region id (e.g. aws-eu-west-1, gcp-europe-west3, azure-westeurope)."
}

variable "product_tier" {
  type        = string
  description = "Product tier for serverless (complete required for CPS)."
  default     = "complete"

  validation {
    condition     = contains(["complete", "essentials"], var.product_tier)
    error_message = "product_tier must be \"complete\" or \"essentials\"."
  }
}

variable "product_lines" {
  type        = list(string)
  description = "Security product lines to enable (security projects only)."
  default     = ["security", "cloud", "endpoint"]
}

variable "linked_projects" {
  type = map(object({
    type = string
  }))
  description = "Map of project_id => { type } for Cross-Project Search links (serverless hub)."
  default     = {}
}

variable "tags" {
  type        = map(string)
  description = "Optional metadata tags for the serverless project."
  default     = {}
}

# Hosted-only
variable "elastic_version" {
  type        = string
  description = "Hosted stack version, or \"latest\"."
  default     = "latest"
}

variable "deployment_template_id" {
  type        = string
  description = "Hosted deployment template id."
  default     = "aws-general-purpose-arm"
}

variable "remote_clusters" {
  type = list(object({
    id    = string
    alias = string
  }))
  description = "Hosted CCS remote cluster connections."
  default     = []
}
