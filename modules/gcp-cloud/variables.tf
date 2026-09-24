variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "name_prefix" {
  type    = string
  default = "elastic-poc"
}

variable "region" {
  type    = string
  default = "europe-west3"
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "audit_filter" {
  type    = string
  default = "logName:\"cloudaudit.googleapis.com\""
}

variable "firewall_filter" {
  type    = string
  default = "log_id(\"compute.googleapis.com/firewall\")"
}

variable "vpcflow_filter" {
  type    = string
  default = "log_id(\"compute.googleapis.com/vpc_flows\")"
}

variable "dns_filter" {
  type    = string
  default = "resource.type=\"dns_query\""
}

variable "lb_filter" {
  type    = string
  default = "resource.type=\"http_load_balancer\""
}
