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

# Per-resource kibana_connection blocks in modules/elastic-stack supply credentials.
provider "elasticstack" {}

module "elastic" {
  source = "../../modules/elastic-project"

  deployment_mode = var.deployment_mode
  name            = var.elastic_project_name
  region          = var.elastic_region
  product_tier    = var.product_tier

  elastic_version        = var.elastic_version
  deployment_template_id = var.deployment_template_id
}

module "aws_cloud" {
  source = "../../modules/aws-cloud"

  name_prefix          = var.name_prefix
  bucket_name          = var.bucket_name
  enable_cloudtrail    = var.enable_cloudtrail
  enable_vpc_flow_logs = var.enable_vpc_flow_logs

  tags = {
    Environment = "poc"
    Cloud       = "aws"
  }
}

locals {
  # Agent-based AWS package: enable high-value metrics + CloudTrail via SQS.
  # CSPM is separate (agentless). Static keys are never embedded — assume_role only.
  aws_agent_inputs = {
    "aws/metrics-cloudwatch" = {
      enabled = true
      vars = jsonencode({
        "aws.credentials.type" = "assume_role"
        role_arn               = module.aws_cloud.elastic_role_arn
        external_id            = module.aws_cloud.external_id
      })
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
    "aws/metrics-billing" = {
      enabled = true
      vars = jsonencode({
        "aws.credentials.type" = "assume_role"
        role_arn               = module.aws_cloud.elastic_role_arn
        external_id            = module.aws_cloud.external_id
      })
      streams = {
        "aws.billing" = {
          enabled = true
          vars = jsonencode({
            period = "12h"
          })
        }
      }
    }
    "aws/metrics-ec2" = {
      enabled = true
      vars = jsonencode({
        "aws.credentials.type" = "assume_role"
        role_arn               = module.aws_cloud.elastic_role_arn
        external_id            = module.aws_cloud.external_id
      })
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
      vars = jsonencode({
        "aws.credentials.type" = "assume_role"
        role_arn               = module.aws_cloud.elastic_role_arn
        external_id            = module.aws_cloud.external_id
      })
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
    "aws-s3-aws.cloudtrail" = {
      enabled = true
      vars = jsonencode({
        "aws.credentials.type" = "assume_role"
        role_arn               = module.aws_cloud.elastic_role_arn
        external_id            = module.aws_cloud.external_id
      })
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

  aws_integrations = concat(
    var.enable_cspm ? [
      {
        name            = "cspm-aws"
        description     = "Agentless Cloud Security Posture Management for AWS"
        package_name    = "cloud_security_posture"
        managed         = true
        agent_policy    = false
        policy_template = "cspm"
        vars_json = jsonencode({
          posture    = "cspm"
          deployment = "aws"
        })
        var_group_selections = {
          deployment = "aws"
        }
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
    [
      {
        name         = "aws-observe"
        description  = "AWS metrics and CloudTrail (latest package; assume_role)"
        package_name = "aws"
        managed      = false
        agent_policy = true
        prerelease   = false
        inputs       = local.aws_agent_inputs
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
  policy_name            = "aws-observe-protect"
  enable_detection_rules = var.enable_detection_rules
  detection_rule_tags    = var.detection_rule_tags
  integrations           = local.aws_integrations

  depends_on = [module.elastic, module.aws_cloud]
}
