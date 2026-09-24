# =============================================================================
# AWS cloud plumbing + Fleet stack
# =============================================================================

module "aws_cloud" {
  source = "../../modules/aws-cloud"
  count  = local.deploy_aws ? 1 : 0

  name_prefix = "${var.name_prefix}-aws"
  tags = {
    Environment = "poc"
    Cloud       = "aws"
  }
}

module "stack_aws" {
  source = "../../modules/elastic-stack"
  count  = local.deploy_aws ? 1 : 0

  kibana_endpoint        = local.elastic_aws.kibana_endpoint
  elasticsearch_endpoint = local.elastic_aws.elasticsearch_endpoint
  elasticsearch_username = local.elastic_aws.username
  elasticsearch_password = local.elastic_aws.password
  policy_name            = "aws-observe-protect"
  enable_detection_rules = var.enable_detection_rules
  detection_rule_tags    = [{ key = "Data Source", value = "AWS" }]

  integrations = concat(
    var.enable_cspm ? [
      {
        name                 = "cspm-aws"
        package_name         = "cloud_security_posture"
        managed              = true
        agent_policy         = false
        policy_template      = "cspm"
        vars_json            = jsonencode({ posture = "cspm", deployment = "aws" })
        var_group_selections = { deployment = "aws" }
        inputs = {
          "cspm-cloudbeat/cis_aws" = {
            enabled = true
            streams = {
              "cloud_security_posture.findings" = {
                enabled = true
                vars = jsonencode({
                  role_arn               = module.aws_cloud[0].elastic_role_arn
                  "aws.credentials.type" = "assume_role"
                  "aws.account_type"     = "single-account"
                  external_id            = module.aws_cloud[0].external_id
                })
              }
            }
          }
        }
      }
    ] : [],
    [
      {
        name         = "aws-observe"
        package_name = "aws"
        managed      = false
        agent_policy = true
        inputs = {
          "aws/metrics-billing" = {
            enabled = true
            vars = jsonencode({
              "aws.credentials.type" = "assume_role"
              role_arn               = module.aws_cloud[0].elastic_role_arn
              external_id            = module.aws_cloud[0].external_id
            })
            streams = {
              "aws.billing" = {
                enabled = true
                vars    = jsonencode({ period = "12h" })
              }
            }
          }
          "aws-s3-aws.cloudtrail" = {
            enabled = true
            vars = jsonencode({
              "aws.credentials.type" = "assume_role"
              role_arn               = module.aws_cloud[0].elastic_role_arn
              external_id            = module.aws_cloud[0].external_id
            })
            streams = {
              "aws.cloudtrail" = {
                enabled = true
                vars    = jsonencode({ queue_url = module.aws_cloud[0].cloudtrail_queue_url })
              }
            }
          }
        }
      }
    ]
  )
}

# =============================================================================
# Azure
# =============================================================================

module "azure_cloud" {
  source = "../../modules/azure-cloud"
  count  = local.deploy_azure ? 1 : 0

  name_prefix         = "${var.name_prefix}-az"
  location            = var.azure_region
  resource_group_name = var.azure_resource_group
  tags = {
    Environment = "poc"
    Cloud       = "azure"
  }
}

module "stack_azure" {
  source = "../../modules/elastic-stack"
  count  = local.deploy_azure ? 1 : 0

  kibana_endpoint        = local.elastic_azure.kibana_endpoint
  elasticsearch_endpoint = local.elastic_azure.elasticsearch_endpoint
  elasticsearch_username = local.elastic_azure.username
  elasticsearch_password = local.elastic_azure.password
  policy_name            = "azure-observe-protect"
  enable_detection_rules = var.enable_detection_rules
  detection_rule_tags    = [{ key = "Data Source", value = "Azure" }]

  integrations = concat(
    var.enable_cspm ? [
      {
        name                 = "cspm-azure"
        package_name         = "cloud_security_posture"
        managed              = true
        agent_policy         = false
        policy_template      = "cspm"
        vars_json            = jsonencode({ posture = "cspm", deployment = "azure" })
        var_group_selections = { deployment = "azure" }
        inputs = {
          "cspm-cloudbeat/cis_azure" = {
            enabled = true
            streams = {
              "cloud_security_posture.findings" = {
                enabled = true
                vars = jsonencode({
                  "azure.account_type"              = "single-account"
                  "azure.credentials.type"          = "service_principal"
                  "azure.credentials.client_id"     = module.azure_cloud[0].client_id
                  "azure.credentials.client_secret" = module.azure_cloud[0].client_secret
                  "azure.credentials.tenant_id"     = module.azure_cloud[0].tenant_id
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
                  connection_string = module.azure_cloud[0].eventhub_connection_string
                  storage_account   = module.azure_cloud[0].storage_account_name
                  eventhub          = module.azure_cloud[0].eventhub_name
                  consumer_group    = "$Default"
                })
              }
            }
          }
        }
      },
      {
        name         = "azure-metrics"
        package_name = "azure_metrics"
        managed      = false
        agent_policy = true
        inputs = {
          "azure/metrics" = {
            enabled = true
            vars = jsonencode({
              client_id       = module.azure_cloud[0].client_id
              client_secret   = module.azure_cloud[0].client_secret
              tenant_id       = module.azure_cloud[0].tenant_id
              subscription_id = module.azure_cloud[0].subscription_id
            })
            streams = {
              "azure.compute_vm" = {
                enabled = true
                vars    = jsonencode({ period = "5m" })
              }
            }
          }
        }
      }
    ]
  )
}

# =============================================================================
# GCP
# =============================================================================

module "gcp_cloud" {
  source = "../../modules/gcp-cloud"
  count  = local.deploy_gcp ? 1 : 0

  project_id  = var.google_cloud_project
  name_prefix = "${var.name_prefix}-gcp"
  region      = var.google_cloud_region
  labels = {
    environment = "poc"
    cloud       = "gcp"
  }
}

module "stack_gcp" {
  source = "../../modules/elastic-stack"
  count  = local.deploy_gcp ? 1 : 0

  kibana_endpoint        = local.elastic_gcp.kibana_endpoint
  elasticsearch_endpoint = local.elastic_gcp.elasticsearch_endpoint
  elasticsearch_username = local.elastic_gcp.username
  elasticsearch_password = local.elastic_gcp.password
  policy_name            = "gcp-observe-protect"
  enable_detection_rules = var.enable_detection_rules
  detection_rule_tags    = [{ key = "Data Source", value = "Google Cloud" }]

  integrations = concat(
    var.enable_cspm ? [
      {
        name                 = "cspm-gcp"
        package_name         = "cloud_security_posture"
        managed              = true
        agent_policy         = false
        policy_template      = "cspm"
        vars_json            = jsonencode({ posture = "cspm", deployment = "gcp" })
        var_group_selections = { deployment = "gcp" }
        inputs = {
          "cspm-cloudbeat/cis_gcp" = {
            enabled = true
            streams = {
              "cloud_security_posture.findings" = {
                enabled = true
                vars = jsonencode({
                  "gcp.project_id"       = module.gcp_cloud[0].project_id
                  "gcp.credentials.type" = "credentials-json"
                  "gcp.credentials.json" = module.gcp_cloud[0].credentials_json
                })
              }
            }
          }
        }
      }
    ] : [],
    [
      {
        name         = "gcp-observe"
        package_name = "gcp"
        managed      = false
        agent_policy = true
        inputs = {
          "gcp-pubsub" = {
            enabled = true
            vars = jsonencode({
              credentials_json = module.gcp_cloud[0].credentials_json
              project_id       = module.gcp_cloud[0].project_id
            })
            streams = {
              "gcp.audit" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud[0].topic_names["audit"] })
              }
              "gcp.firewall" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud[0].topic_names["firewall"] })
              }
              "gcp.vpcflow" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud[0].topic_names["vpcflow"] })
              }
              "gcp.dns" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud[0].topic_names["dns"] })
              }
              "gcp.loadbalancing_logs" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud[0].topic_names["lb"] })
              }
            }
          }
        }
      }
    ]
  )
}
