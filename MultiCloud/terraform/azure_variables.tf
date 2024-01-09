# -------------------------------------------------------------
# Elastic configuration
# -------------------------------------------------------------
variable "elastic_azure_region" {
  type = string
  default = "azure-westeurope"
}

variable "elastic_azure_deployment_name" {
  type = string
  default = "Azure Observe and Protect"
}

variable "elastic_azure_deployment_template_id" {
  type = string
  default = "azure-general-purpose"
}

# -------------------------------------------------------------
# Azure configuration
# -------------------------------------------------------------

variable "azure_region" {
  type = string
  default = "West Europe"
}

variable "azure_resource_group" {
  type = string
  default = "tf-elastic-group"
}

variable  "azure_subscription_id" {
 type = string
 default = ""   
}

variable  "azure_client_id" {
 type = string
 default = ""     
}

variable  "azure_client_secret" {
 type = string 
 default = ""    
}

variable  "azure_tenant_id" {
 type = string 
 default = ""    
}



