variable "name_prefix" {
  type        = string
  default     = "elastic-poc"
  description = "Prefix for Azure resource names."
}

variable "location" {
  type        = string
  description = "Azure region."
  default     = "westeurope"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group name."
  default     = "elastic-cloud-poc"
}

variable "company_tags" {
  type        = map(string)
  description = "Mandatory company-policy tags applied to every taggable Azure resource."

  validation {
    condition     = length(var.company_tags) > 0
    error_message = "company_tags must contain at least one tag required by company policy."
  }
}

variable "required_tag_keys" {
  type        = list(string)
  description = "Tag keys that must be present in company_tags. Empty skips the check."
  default     = []
}

variable "additional_tags" {
  type        = map(string)
  description = "Optional extra tags merged on top of company_tags."
  default     = {}
}
