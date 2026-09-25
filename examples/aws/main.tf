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
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5"
    }
  }
}

provider "ec" {}

provider "aws" {
  region = var.aws_region
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
  cloud_slug                      = "aws"
  cloud_display_name              = "AWS"

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
  title                      = "AWS Observe & Protect Cockpit"
  dashboard_id               = "a1b2c3d4-e5f6-4789-a012-3456789abcde"
  ndjson_path                = "${path.module}/../../modules/cockpit-dashboard/cockpit-aws.ndjson"
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

module "aws_cloud" {
  source = "../../modules/aws-cloud"

  name_prefix          = var.name_prefix
  bucket_name          = var.bucket_name
  enable_cloudtrail    = var.enable_cloudtrail
  enable_vpc_flow_logs = var.enable_vpc_flow_logs
  company_tags         = var.company_tags
  required_tag_keys    = var.required_tag_keys
  additional_tags = {
    Cloud = "aws"
  }
}

locals {
  # Shared assume-role vars for agent-based AWS package streams.
  aws_assume_role_vars = {
    "aws.credentials.type" = "assume_role"
    role_arn               = module.aws_cloud.elastic_role_arn
    external_id            = module.aws_cloud.external_id
  }

  # ---------------------------------------------------------------------------
  # Security Fleet: agentless CSPM (+ optional CNVM) + agent CloudTrail.
  # Prefer agentless whenever Elastic supports it; keep agent for the rest.
  # ---------------------------------------------------------------------------
  security_integrations = concat(
    var.enable_cspm ? [
      {
        name                 = "cspm-aws"
        description          = "Agentless CSPM for AWS (CIS)"
        package_name         = "cloud_security_posture"
        managed              = true
        agent_policy         = false
        prerelease           = false
        package_version      = null
        policy_template      = "cspm"
        vars_json            = jsonencode({ posture = "cspm", deployment = "aws" })
        var_group_selections = { deployment = "aws" }
        cloud_connector      = null
        inputs = {
          "cspm-cloudbeat/cis_aws" = {
            enabled = true
            streams = {
              "cloud_security_posture.findings" = {
                enabled = true
                vars = jsonencode({
                  role_arn               = module.aws_cloud.elastic_role_arn
                  "aws.credentials.type" = "assume_role"
                  "aws.account_type"     = "single-account"
                  external_id            = module.aws_cloud.external_id
                })
              }
            }
          }
        }
      }
    ] : [],
    var.enable_cnvm ? [
      {
        name                 = "cnvm-aws"
        description          = "Agentless Cloud Native Vulnerability Management for AWS"
        package_name         = "cloud_security_posture"
        managed              = true
        agent_policy         = false
        prerelease           = false
        package_version      = null
        policy_template      = "vuln_mgmt"
        vars_json            = jsonencode({ posture = "vuln_mgmt", deployment = "aws" })
        var_group_selections = { deployment = "aws" }
        cloud_connector      = null
        inputs = {
          "vuln_mgmt-cloudbeat/vuln_mgmt_aws" = {
            enabled = true
            streams = {
              "cloud_security_posture.vulnerabilities" = {
                enabled = true
                vars = jsonencode({
                  role_arn               = module.aws_cloud.elastic_role_arn
                  "aws.credentials.type" = "assume_role"
                  external_id            = module.aws_cloud.external_id
                })
              }
            }
          }
        }
      }
    ] : [],
    [
      {
        name                 = "aws-security"
        description          = "AWS security logs (CloudTrail via S3/SQS) — agent-based (not available agentless)"
        package_name         = "aws"
        managed              = false
        agent_policy         = true
        prerelease           = false
        package_version      = null
        policy_template      = null
        vars_json            = jsonencode(local.aws_assume_role_vars)
        var_group_selections = {}
        cloud_connector      = null
        inputs = {
          "aws-s3-aws.cloudtrail" = {
            enabled = true
            vars    = jsonencode(local.aws_assume_role_vars)
            streams = {
              "aws.cloudtrail" = {
                enabled = true
                vars = jsonencode({
                  queue_url = module.aws_cloud.cloudtrail_queue_url
                })
              }
            }
          }
        }
      }
    ]
  )

  # ---------------------------------------------------------------------------
  # Observability Fleet: agent-based VPC flow + CloudWatch/EC2/S3/billing metrics.
  # ---------------------------------------------------------------------------
  observability_integrations = [
    {
      name                 = "aws-observe"
      description          = "AWS observability (vpcflow + metrics) — agent-based"
      package_name         = "aws"
      managed              = false
      agent_policy         = true
      prerelease           = false
      package_version      = null
      policy_template      = null
      vars_json            = jsonencode(local.aws_assume_role_vars)
      var_group_selections = {}
      cloud_connector      = null
      inputs = merge(
        var.enable_vpc_flow_logs && module.aws_cloud.vpcflow_queue_url != null ? {
          "aws-s3-aws.vpcflow" = {
            enabled = true
            vars    = jsonencode(local.aws_assume_role_vars)
            streams = {
              "aws.vpcflow" = {
                enabled = true
                vars = jsonencode({
                  queue_url = module.aws_cloud.vpcflow_queue_url
                })
              }
            }
          }
        } : {},
        {
          "aws/metrics-cloudwatch" = {
            enabled = true
            vars    = jsonencode(local.aws_assume_role_vars)
            streams = {
              "aws.cloudwatch_metrics" = {
                enabled = true
                vars = jsonencode({
                  period  = "5m"
                  latency = "5m"
                  regions = [var.aws_region]
                })
              }
            }
          }
          "aws/metrics-ec2" = {
            enabled = true
            vars    = jsonencode(local.aws_assume_role_vars)
            streams = {
              "aws.ec2_metrics" = {
                enabled = true
                vars = jsonencode({
                  period  = "5m"
                  regions = [var.aws_region]
                })
              }
            }
          }
          "aws/metrics-s3" = {
            enabled = true
            vars    = jsonencode(local.aws_assume_role_vars)
            streams = {
              "aws.s3_daily_storage" = {
                enabled = true
                vars = jsonencode({
                  period  = "24h"
                  regions = [var.aws_region]
                })
              }
              "aws.s3_request" = {
                enabled = true
                vars = jsonencode({
                  period  = "5m"
                  regions = [var.aws_region]
                })
              }
            }
          }
          "aws/metrics-billing" = {
            enabled = var.enable_billing_metrics
            vars    = jsonencode(local.aws_assume_role_vars)
            streams = {
              "aws.billing" = {
                enabled = var.enable_billing_metrics
                vars = jsonencode({
                  period = "12h"
                })
              }
            }
          }
        }
      )
    }
  ]
}

# Security project Fleet: agentless CSPM/CNVM + agent CloudTrail + detection rules.
module "stack" {
  source = "../../modules/elastic-stack"

  kibana_endpoint        = module.elastic.kibana_endpoint
  elasticsearch_endpoint = module.elastic.elasticsearch_endpoint
  elasticsearch_username = module.elastic.username
  elasticsearch_password = module.elastic.password
  policy_name            = "aws-observe-protect"
  enable_detection_rules = var.enable_detection_rules
  detection_rule_tags    = var.detection_rule_tags
  integrations           = local.security_integrations

  depends_on = [module.elastic, module.aws_cloud]
}

# Observability project Fleet: metrics + vpcflow + observability agent.
module "stack_obs" {
  count  = length(module.observability) > 0 ? 1 : 0
  source = "../../modules/elastic-stack"

  kibana_endpoint        = module.observability[0].kibana_endpoint
  elasticsearch_endpoint = module.observability[0].elasticsearch_endpoint
  elasticsearch_username = module.observability[0].username
  elasticsearch_password = module.observability[0].password
  policy_name            = "aws-observability"
  enable_detection_rules = false
  integrations           = local.observability_integrations

  depends_on = [module.observability, module.aws_cloud]
}

module "elastic_agent" {
  count  = var.enable_elastic_agent ? 1 : 0
  source = "../../modules/elastic-agent-ec2"

  name             = "${var.name_prefix}-agent"
  instance_type    = var.elastic_agent_instance_type
  company_tags     = merge(module.aws_cloud.applied_tags, { Role = "elastic-agent-security" })
  fleet_url        = module.elastic.fleet_endpoint
  enrollment_token = module.stack.enrollment_token
  agent_version    = var.elastic_agent_version

  depends_on = [module.stack]
}

module "elastic_agent_obs" {
  count  = var.enable_elastic_agent && length(module.stack_obs) > 0 ? 1 : 0
  source = "../../modules/elastic-agent-ec2"

  name             = "${var.name_prefix}-obs-agent"
  instance_type    = var.elastic_agent_instance_type
  company_tags     = merge(module.aws_cloud.applied_tags, { Role = "elastic-agent-observability" })
  fleet_url        = module.observability[0].fleet_endpoint
  enrollment_token = module.stack_obs[0].enrollment_token
  agent_version    = var.elastic_agent_version

  depends_on = [module.stack_obs]
}
