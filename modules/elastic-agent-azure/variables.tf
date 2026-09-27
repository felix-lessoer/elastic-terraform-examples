variable "name" {
  type        = string
  description = "Azure Linux VM name for the Elastic Agent."
  default     = "elastic-agent"
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "subnet_id" {
  type        = string
  description = "Subnet id for the agent NIC."
}

variable "vm_size" {
  type    = string
  default = "Standard_B2s"
}

variable "admin_username" {
  type    = string
  default = "elastic"
}

variable "admin_password" {
  type        = string
  sensitive   = true
  description = "VM admin password (Azure password complexity rules apply)."
}

variable "company_tags" {
  type        = map(string)
  description = "Tags applied to the VM and NIC resources."
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
