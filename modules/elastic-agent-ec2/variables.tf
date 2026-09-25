variable "name" {
  type        = string
  description = "EC2 instance name tag / Name."
  default     = "elastic-agent"
}

variable "subnet_id" {
  type        = string
  description = "Subnet id for the agent EC2 instance. Empty picks the default VPC's first subnet."
  default     = ""
}

variable "vpc_id" {
  type        = string
  description = "Optional VPC id when creating a security group. Empty uses the default VPC."
  default     = ""
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "company_tags" {
  type        = map(string)
  description = "Tags applied to the EC2 instance and related resources."
  default     = {}
}

variable "fleet_url" {
  type        = string
  description = "Fleet Server URL used for enrollment."
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

variable "associate_public_ip" {
  type        = bool
  description = "Associate a public IP so the instance can reach Fleet and artifacts.elastic.co."
  default     = true
}
