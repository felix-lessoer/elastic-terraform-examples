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

variable "tags" {
  type    = map(string)
  default = {}
}
