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

# Per-resource kibana_connection blocks supply credentials.
provider "elasticstack" {}

module "elastic" {
  source = "../../modules/elastic-project"

  deployment_mode        = var.deployment_mode
  project_kind           = "security"
  name                   = var.elastic_project_name
  region                 = var.elastic_region
  product_tier           = var.product_tier
  elastic_version        = var.elastic_version
  deployment_template_id = var.deployment_template_id
  tags = {
    for k, v in var.company_tags :
    substr(lower(replace(replace(replace(replace(k, " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32) =>
    substr(lower(replace(replace(replace(replace(tostring(v), " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32)
  }
}

# Observability hub with Cross-Project Search into the Security project.
module "observability" {
  count  = var.enable_observability_project && var.deployment_mode == "serverless" ? 1 : 0
  source = "../../modules/elastic-project"

  deployment_mode = "serverless"
  project_kind    = "observability"
  name            = var.observability_project_name
  region          = var.elastic_region
  product_tier    = var.product_tier
  linked_projects = {
    (module.elastic.id) = { type = "security" }
  }
  tags = {
    for k, v in var.company_tags :
    substr(lower(replace(replace(replace(replace(k, " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32) =>
    substr(lower(replace(replace(replace(replace(tostring(v), " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32)
  }

  depends_on = [module.elastic]
}

module "observability_seed" {
  count  = length(module.observability) > 0 ? 1 : 0
  source = "../../modules/observability-seed"

  kibana_endpoint                 = module.observability[0].kibana_endpoint
  elasticsearch_endpoint          = module.observability[0].elasticsearch_endpoint
  elasticsearch_username          = module.observability[0].username
  elasticsearch_password          = module.observability[0].password
  security_elasticsearch_endpoint = module.elastic.elasticsearch_endpoint
  security_elasticsearch_username = module.elastic.username
  security_elasticsearch_password = module.elastic.password
  enable_ml_jobs                  = var.enable_ml_jobs
  enable_ai_agents                = var.enable_ai_agents
  enable_observability_alerts     = var.enable_observability_alerts
  cloud_slug                      = "azure"
  cloud_display_name              = "Azure"

  depends_on = [module.observability, module.elastic]
}

module "cockpit" {
  count  = length(module.observability) > 0 ? 1 : 0
  source = "../../modules/cockpit-dashboard"

  kibana_endpoint            = module.observability[0].kibana_endpoint
  elasticsearch_username     = module.observability[0].username
  elasticsearch_password     = module.observability[0].password
  security_project_name      = module.elastic.name
  observability_project_name = module.observability[0].name
  title                      = "Azure Observe & Protect Cockpit"
  dashboard_id               = "b8e4c2f1-9a7d-4e3b-8c5a-1d6f0e9b2a47"
  ndjson_path                = "${path.module}/../../modules/cockpit-dashboard/cockpit-azure.ndjson"
  ml_jobs                    = try(module.observability_seed[0].ml_jobs, [])
  ai_agents                  = try(module.observability_seed[0].ai_agents, [])

  depends_on = [module.observability, module.observability_seed]
}

module "workflows_obs" {
  count  = var.enable_workflows && length(module.observability) > 0 ? 1 : 0
  source = "../../modules/kibana-workflows"

  kibana_endpoint        = module.observability[0].kibana_endpoint
  elasticsearch_username = module.observability[0].username
  elasticsearch_password = module.observability[0].password
  workflows_dir          = "${path.module}/workflows"
  execute_on_apply       = var.execute_workflows_on_apply

  depends_on = [module.observability, module.observability_seed, module.cockpit]
}

module "workflows_security" {
  count  = var.enable_workflows && var.deploy_workflows_to_security ? 1 : 0
  source = "../../modules/kibana-workflows"

  kibana_endpoint        = module.elastic.kibana_endpoint
  elasticsearch_username = module.elastic.username
  elasticsearch_password = module.elastic.password
  workflows_dir          = "${path.module}/workflows"
  execute_on_apply       = var.execute_workflows_on_apply

  depends_on = [module.elastic, module.stack]
}

module "azure_cloud" {
  source = "../../modules/azure-cloud"

  name_prefix          = var.name_prefix
  location             = var.azure_region
  resource_group_name  = var.azure_resource_group
  company_tags         = var.company_tags
  required_tag_keys    = var.required_tag_keys
  enable_agent_network = var.enable_elastic_agent
  additional_tags = {
    Cloud = "azure"
  }
}

locals {
  azure_package_vars = {
    client_id       = module.azure_cloud.client_id
    client_secret   = module.azure_cloud.client_secret
    tenant_id       = module.azure_cloud.tenant_id
    subscription_id = module.azure_cloud.subscription_id
  }

  # Security Fleet: agentless CSPM + Event Hub activity/platform logs.
  security_integrations = concat(
    var.enable_cspm ? [
      {
        name                 = "cspm-azure"
        description          = "Agentless CSPM for Azure (CIS)"
        package_name         = "cloud_security_posture"
        managed              = true
        agent_policy         = false
        prerelease           = false
        package_version      = null
        policy_template      = "cspm"
        vars_json            = jsonencode({ posture = "cspm", deployment = "azure" })
        var_group_selections = { deployment = "azure" }
        cloud_connector      = null
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
        name                 = "azure-security"
        description          = "Azure Event Hub activity/platform logs (console-home security surface)"
        package_name         = "azure"
        managed              = false
        agent_policy         = true
        prerelease           = false
        package_version      = null
        policy_template      = null
        vars_json            = jsonencode({})
        var_group_selections = {}
        cloud_connector      = null
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
      }
    ]
  )

  # Observability Fleet: Azure Monitor metrics + billing.
  observability_integrations = [
    {
      name                 = "azure-metrics"
      description          = "Azure Monitor metrics (VM, storage, container instances)"
      package_name         = "azure_metrics"
      managed              = false
      agent_policy         = true
      prerelease           = false
      package_version      = null
      policy_template      = null
      vars_json            = jsonencode(local.azure_package_vars)
      var_group_selections = {}
      cloud_connector      = null
      inputs = {
        "azure/metrics" = {
          enabled = true
          vars    = jsonencode(local.azure_package_vars)
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
              enabled = var.enable_container_instance_metrics
              vars    = jsonencode({ period = "5m" })
            }
          }
        }
      }
    },
    {
      name                 = "azure-billing"
      description          = "Azure Cost Management / billing metrics"
      package_name         = "azure_billing"
      managed              = false
      agent_policy         = true
      prerelease           = false
      package_version      = null
      policy_template      = null
      vars_json            = jsonencode(local.azure_package_vars)
      var_group_selections = {}
      cloud_connector      = null
      inputs = {
        "azure/billing" = {
          enabled = var.enable_billing_metrics
          vars    = jsonencode(local.azure_package_vars)
          streams = {
            "azure.billing" = {
              enabled = var.enable_billing_metrics
              vars    = jsonencode({ period = "24h" })
            }
          }
        }
      }
    }
  ]
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
  integrations           = local.security_integrations

  depends_on = [module.elastic, module.azure_cloud]
}

module "stack_obs" {
  count  = length(module.observability) > 0 ? 1 : 0
  source = "../../modules/elastic-stack"

  kibana_endpoint        = module.observability[0].kibana_endpoint
  elasticsearch_endpoint = module.observability[0].elasticsearch_endpoint
  elasticsearch_username = module.observability[0].username
  elasticsearch_password = module.observability[0].password
  policy_name            = "azure-observability"
  enable_detection_rules = false
  integrations           = local.observability_integrations

  depends_on = [module.observability, module.azure_cloud]
}

resource "random_password" "agent_admin" {
  count       = var.enable_elastic_agent && var.elastic_agent_admin_password == null ? 1 : 0
  length      = 24
  special     = true
  min_lower   = 2
  min_upper   = 2
  min_numeric = 2
  min_special = 2
}

locals {
  agent_admin_password = coalesce(
    var.elastic_agent_admin_password,
    try(random_password.agent_admin[0].result, null),
  )
}

module "elastic_agent" {
  count  = var.enable_elastic_agent ? 1 : 0
  source = "../../modules/elastic-agent-azure"

  name                = "${var.name_prefix}-agent"
  resource_group_name = module.azure_cloud.resource_group_name
  location            = module.azure_cloud.location
  subnet_id           = module.azure_cloud.agent_subnet_id
  vm_size             = var.elastic_agent_vm_size
  admin_username      = var.elastic_agent_admin_username
  admin_password      = local.agent_admin_password
  company_tags        = var.company_tags
  fleet_url           = module.elastic.fleet_endpoint
  enrollment_token    = module.stack.enrollment_token
  agent_version       = var.elastic_agent_version

  depends_on = [module.stack, module.azure_cloud]
}

module "elastic_agent_obs" {
  count  = var.enable_elastic_agent && length(module.stack_obs) > 0 ? 1 : 0
  source = "../../modules/elastic-agent-azure"

  name                = "${var.name_prefix}-obs-agent"
  resource_group_name = module.azure_cloud.resource_group_name
  location            = module.azure_cloud.location
  subnet_id           = module.azure_cloud.agent_subnet_id
  vm_size             = var.elastic_agent_vm_size
  admin_username      = var.elastic_agent_admin_username
  admin_password      = local.agent_admin_password
  company_tags        = var.company_tags
  fleet_url           = module.observability[0].fleet_endpoint
  enrollment_token    = module.stack_obs[0].enrollment_token
  agent_version       = var.elastic_agent_version

  depends_on = [module.stack_obs, module.azure_cloud]
}
