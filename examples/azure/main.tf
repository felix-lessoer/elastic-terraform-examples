terraform {
  required_version = ">= 1.2.7"

  required_providers {
    ec = {
      source  = "elastic/ec"
      version = "~> 0.13"
    }
    elasticstack = {
      source  = "elastic/elasticstack"
      version = "~> 0.16"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.100"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = ">= 2.47"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5"
    }
  }
}

provider "ec" {}

provider "azurerm" {
  features {}
  subscription_id = var.azure_subscription_id
  tenant_id       = var.azure_tenant_id
  client_id       = var.azure_client_id
  client_secret   = var.azure_client_secret
}

provider "azuread" {
  tenant_id     = var.azure_tenant_id
  client_id     = var.azure_client_id
  client_secret = var.azure_client_secret
}

provider "elasticstack" {}

module "elastic" {
  source = "../../modules/elastic-project"

  deployment_mode        = var.deployment_mode
  name                   = var.elastic_project_name
  region                 = var.elastic_region
  product_tier           = var.product_tier
  elastic_version        = var.elastic_version
  deployment_template_id = var.deployment_template_id
  tags = {
    for k, v in var.company_tags :
    substr(regexreplace(regexreplace(lower(k), "[^a-z0-9_-]", "-"), "^[^a-z]+", "x"), 0, 32) =>
    substr(regexreplace(lower(tostring(v)), "[^a-z0-9_-]", "-"), 0, 32)
  }
}

module "azure_cloud" {
  source = "../../modules/azure-cloud"

  name_prefix         = var.name_prefix
  location            = var.azure_region
  resource_group_name = var.azure_resource_group
  company_tags        = var.company_tags
  required_tag_keys   = var.required_tag_keys
  additional_tags = {
    Cloud = "azure"
  }
}

locals {
  azure_integrations = concat(
    var.enable_cspm ? [
      {
        name            = "cspm-azure"
        description     = "Agentless CSPM for Azure"
        package_name    = "cloud_security_posture"
        managed         = true
        agent_policy    = false
        policy_template = "cspm"
        vars_json = jsonencode({
          posture    = "cspm"
          deployment = "azure"
        })
        var_group_selections = {
          deployment = "azure"
        }
        inputs = {
          "cspm-cloudbeat/cis_azure" = {
            enabled = true
            streams = {
              "cloud_security_posture.findings" = {
                enabled = true
                vars = jsonencode({
                  "azure.account_type"              = "single-account"
                  "azure.credentials.type"          = "service_principal"
                  "azure.credentials.client_id"     = module.azure_cloud.client_id
                  "azure.credentials.client_secret" = module.azure_cloud.client_secret
                  "azure.credentials.tenant_id"     = module.azure_cloud.tenant_id
                })
              }
            }
          }
        }
      }
    ] : [],
    [
      {
        name         = "azure-logs"
        description  = "Azure Event Hub activity/platform logs"
        package_name = "azure"
        managed      = false
        agent_policy = true
        inputs = {
          "azure-eventhub" = {
            enabled = true
            streams = {
              "azure.activitylogs" = {
                enabled = true
                vars = jsonencode({
                  connection_string = module.azure_cloud.eventhub_connection_string
                  storage_account   = module.azure_cloud.storage_account_name
                  eventhub          = module.azure_cloud.eventhub_name
                  consumer_group    = "$Default"
                })
              }
              "azure.platformlogs" = {
                enabled = true
                vars = jsonencode({
                  connection_string = module.azure_cloud.eventhub_connection_string
                  storage_account   = module.azure_cloud.storage_account_name
                  eventhub          = module.azure_cloud.eventhub_name
                  consumer_group    = "$Default"
                })
              }
            }
          }
        }
      },
      {
        name         = "azure-metrics"
        description  = "Azure Monitor metrics"
        package_name = "azure_metrics"
        managed      = false
        agent_policy = true
        inputs = {
          "azure/metrics" = {
            enabled = true
            vars = jsonencode({
              client_id       = module.azure_cloud.client_id
              client_secret   = module.azure_cloud.client_secret
              tenant_id       = module.azure_cloud.tenant_id
              subscription_id = module.azure_cloud.subscription_id
            })
            streams = {
              "azure.compute_vm" = {
                enabled = true
                vars    = jsonencode({ period = "5m" })
              }
              "azure.storage_account" = {
                enabled = true
                vars    = jsonencode({ period = "5m" })
              }
              "azure.container_instance" = {
                enabled = true
                vars    = jsonencode({ period = "5m" })
              }
            }
          }
        }
      },
      {
        name         = "azure-billing"
        description  = "Azure billing metrics"
        package_name = "azure_billing"
        managed      = false
        agent_policy = true
        inputs = {
          "azure/billing" = {
            enabled = true
            vars = jsonencode({
              client_id       = module.azure_cloud.client_id
              client_secret   = module.azure_cloud.client_secret
              tenant_id       = module.azure_cloud.tenant_id
              subscription_id = module.azure_cloud.subscription_id
            })
            streams = {
              "azure.billing" = {
                enabled = true
                vars    = jsonencode({ period = "24h" })
              }
            }
          }
        }
      }
    ]
  )
}

module "stack" {
  source = "../../modules/elastic-stack"

  kibana_endpoint        = module.elastic.kibana_endpoint
  elasticsearch_endpoint = module.elastic.elasticsearch_endpoint
  elasticsearch_username = module.elastic.username
  elasticsearch_password = module.elastic.password
  policy_name            = "azure-observe-protect"
  enable_detection_rules = var.enable_detection_rules
  detection_rule_tags    = var.detection_rule_tags
  integrations           = local.azure_integrations

  depends_on = [module.elastic, module.azure_cloud]
}
