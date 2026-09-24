variable "deployment_mode" {
  type    = string
  default = "serverless"
}

variable "elastic_project_name" {
  type    = string
  default = "AWS Observe and Protect"
}

variable "elastic_region" {
  type    = string
  default = "aws-eu-west-1"
}

variable "product_tier" {
  type    = string
  default = "complete"
}

variable "elastic_version" {
  type    = string
  default = "latest"
}

variable "deployment_template_id" {
  type    = string
  default = "aws-general-purpose-arm"
}

variable "aws_region" {
  type    = string
  default = "eu-west-1"
}

variable "name_prefix" {
  type    = string
  default = "elastic-poc"
}

variable "bucket_name" {
  type    = string
  default = "elastic-cloud-logs"
}

variable "enable_cloudtrail" {
  type    = bool
  default = true
}

variable "enable_vpc_flow_logs" {
  type    = bool
  default = true
}

variable "enable_cspm" {
  type    = bool
  default = true
}

variable "enable_detection_rules" {
  type    = bool
  default = true
}

variable "detection_rule_tags" {
  type = list(object({
    key   = string
    value = string
  }))
  default = [
    { key = "Data Source", value = "AWS" }
  ]
}
