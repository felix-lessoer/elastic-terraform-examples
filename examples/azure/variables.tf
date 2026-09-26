variable "deployment_mode" {
  type    = string
  default = "serverless"
}

variable "elastic_project_name" {
  type    = string
  default = "Azure Observe and Protect"
}

variable "observability_project_name" {
  type    = string
  default = "Azure Observability Cockpit"
}

variable "enable_observability_project" {
  type        = bool
  description = "Create a serverless Observability project linked to Security via Cross-Project Search and deploy the cockpit dashboard."
  default     = true
}

variable "enable_ml_jobs" {
  type    = bool
  default = true
}

variable "enable_ai_agents" {
  type    = bool
  default = true
}

variable "enable_observability_alerts" {
  type    = bool
  default = true
}

variable "elastic_region" {
  type    = string
  default = "azure-westeurope"
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
  default = "azure-general-purpose"
}

variable "azure_region" {
  type    = string
  default = "westeurope"
}

variable "azure_resource_group" {
  type    = string
  default = "elastic-cloud-poc"
}

variable "azure_subscription_id" {
  type = string
}

variable "azure_tenant_id" {
  type = string
}

variable "azure_client_id" {
  type = string
}

variable "azure_client_secret" {
  type      = string
  sensitive = true
}

variable "name_prefix" {
  type    = string
  default = "elastic-poc"
}

variable "company_tags" {
  type        = map(string)
  description = "Company-policy tags applied to all Azure resources (and sanitized onto the Elastic project)."

  validation {
    condition     = length(var.company_tags) > 0
    error_message = "Set company_tags according to your company tagging policy."
  }
}

variable "required_tag_keys" {
  type        = list(string)
  description = "Optional list of tag keys that must appear in company_tags."
  default     = []
}

variable "enable_cspm" {
  type        = bool
  description = "Agentless CSPM (CIS Azure) via cloud_security_posture managed integration."
  default     = true
}

variable "enable_billing_metrics" {
  type        = bool
  description = "Collect Azure billing metrics on the Observability Fleet policy."
  default     = true
}

variable "enable_container_instance_metrics" {
  type        = bool
  description = "Collect Azure Container Instance metrics."
  default     = true
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
    { key = "Data Source", value = "Azure" }
  ]
}

variable "enable_workflows" {
  type        = bool
  description = "Deploy pinned Kibana Workflow YAML from examples/azure/workflows/ after greenfield create."
  default     = true
}

variable "execute_workflows_on_apply" {
  type        = bool
  description = "Manually execute each enabled workflow once after Terraform creates/updates it."
  default     = true
}

variable "deploy_workflows_to_security" {
  type        = bool
  description = "Also deploy the same pinned workflows into the Security project Kibana."
  default     = false
}

variable "enable_elastic_agent" {
  type        = bool
  description = "Deploy Azure Linux VMs enrolled into Security and Observability Fleet policies."
  default     = true
}

variable "elastic_agent_vm_size" {
  type    = string
  default = "Standard_B2s"
}

variable "elastic_agent_version" {
  type        = string
  description = "Elastic Agent version installed on the Azure VMs."
  default     = "9.5.4"
}

variable "elastic_agent_admin_username" {
  type    = string
  default = "elastic"
}

variable "elastic_agent_admin_password" {
  type        = string
  sensitive   = true
  default     = null
  description = "Optional VM admin password. Defaults to the Security project elasticsearch password."
}
