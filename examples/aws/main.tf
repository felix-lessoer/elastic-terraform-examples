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
    external = {
      source  = "hashicorp/external"
      version = ">= 2.3"
    }
  }
}

provider "ec" {}

provider "aws" {
  region = var.aws_region

  # Ensure every taggable AWS resource carries org-policy tags (SCP enforcement).
  default_tags {
    tags = var.company_tags
  }
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
  title                      = "AWS Observe & Protect Cockpit updated"
  dashboard_id               = "752a1ac0-26e4-49d8-a2b4-5483068809b9"
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
  enable_sqs           = var.enable_sqs
  company_tags         = var.company_tags
  required_tag_keys    = var.required_tag_keys
  additional_tags = {
    Cloud = "aws"
  }
}

# GuardDuty httpjson requires an explicit detector id (package does not auto-discover).
data "aws_guardduty_detector" "this" {
  count = var.enable_guardduty ? 1 : 0
}

locals {
  # Always include the primary infra region; extras are collection-only.
  # Empty regions contribute zero docs — queries must tolerate partial coverage
  # (Billing/TA/Health often only exist in us-east-1).
  aws_metric_regions = distinct(concat([var.aws_region], var.aws_regions))

  aws_cloud_connector_name = "${var.name_prefix}-managed-aws"

  aws_package_vars = {
    default_region = var.aws_region
  }

  aws_managed_package_vars = {
    default_region               = var.aws_region
    role_arn                     = module.aws_cloud.elastic_role_arn
    supports_identity_federation = true
  }

  # The aws package enables EVERY policy template by default. Explicitly disable
  # unused inputs (same pattern as examples/gcp extra metrics).
  aws_all_input_datasets = {
    "awshealth-aws/metrics"       = ["aws.awshealth"]
    "billing-aws/metrics"         = ["aws.billing"]
    "cloudtrail-aws-s3"           = ["aws.cloudtrail"]
    "cloudtrail-aws-cloudwatch"   = ["aws.cloudtrail"]
    "cloudwatch-aws-cloudwatch"   = ["aws.cloudwatch_logs"]
    "cloudwatch-aws/metrics"      = ["aws.cloudwatch_metrics"]
    "config-cel"                  = ["aws.config"]
    "dynamodb-aws/metrics"        = ["aws.dynamodb"]
    "ebs-aws/metrics"             = ["aws.ebs"]
    "ec2-aws-s3"                  = ["aws.ec2_logs"]
    "ec2-aws-cloudwatch"          = ["aws.ec2_logs"]
    "ec2-aws/metrics"             = ["aws.ec2_metrics"]
    "ecs-aws/metrics"             = ["aws.ecs_metrics"]
    "elb-aws-s3"                  = ["aws.elb_logs"]
    "elb-aws-cloudwatch"          = ["aws.elb_logs"]
    "elb-aws/metrics"             = ["aws.elb_metrics"]
    "lambda-aws/metrics"          = ["aws.lambda"]
    "lambda-aws-cloudwatch"       = ["aws.lambda_logs"]
    "natgateway-aws/metrics"      = ["aws.natgateway"]
    "firewall-aws-s3"             = ["aws.firewall_logs"]
    "firewall-aws-cloudwatch"     = ["aws.firewall_logs"]
    "firewall-aws/metrics"        = ["aws.firewall_metrics"]
    "rds-aws/metrics"             = ["aws.rds"]
    "s3-aws-s3"                   = ["aws.s3access"]
    "s3-aws/metrics"              = ["aws.s3_daily_storage", "aws.s3_request"]
    "s3_storage_lens-aws/metrics" = ["aws.s3_storage_lens"]
    "sns-aws/metrics"             = ["aws.sns"]
    "sqs-aws/metrics"             = ["aws.sqs"]
    "transitgateway-aws/metrics"  = ["aws.transitgateway"]
    "usage-aws/metrics"           = ["aws.usage"]
    "vpcflow-aws-s3"              = ["aws.vpcflow"]
    "vpcflow-aws-cloudwatch"      = ["aws.vpcflow"]
    "vpn-aws/metrics"             = ["aws.vpn"]
    "waf-aws-s3"                  = ["aws.waf"]
    "waf-aws-cloudwatch"          = ["aws.waf"]
    "route53-aws-cloudwatch"      = ["aws.route53_public_logs", "aws.route53_resolver_logs"]
    "route53-aws-s3"              = ["aws.route53_resolver_logs"]
    "cloudfront-aws-s3"           = ["aws.cloudfront_logs"]
    "redshift-aws/metrics"        = ["aws.redshift"]
    "kinesis-aws/metrics"         = ["aws.kinesis"]
    "securityhub-httpjson"        = ["aws.securityhub_findings", "aws.securityhub_findings_full_posture", "aws.securityhub_insights"]
    "inspector-httpjson"          = ["aws.inspector"]
    "guardduty-httpjson"          = ["aws.guardduty"]
    "guardduty-aws-s3"            = ["aws.guardduty"]
    "apigateway-aws/metrics"      = ["aws.apigateway_metrics"]
    "apigateway-aws-s3"           = ["aws.apigateway_logs"]
    "apigateway-aws-cloudwatch"   = ["aws.apigateway_logs"]
    "emr-aws/metrics"             = ["aws.emr_metrics"]
    "emr-aws-s3"                  = ["aws.emr_logs"]
    "emr-aws-cloudwatch"          = ["aws.emr_logs"]
    "kafka-aws/metrics"           = ["aws.kafka_metrics"]
  }

  aws_disabled_input_stubs = {
    for input_key, datasets in local.aws_all_input_datasets : input_key => {
      enabled = false
      streams = { for ds in datasets : ds => { enabled = false } }
    }
  }

  # Fleet still validates required vars on these even when disabled.
  aws_httpjson_disabled_overrides = {
    "inspector-httpjson" = {
      enabled = false
      streams = {
        "aws.inspector" = {
          enabled = false
          vars = jsonencode({
            interval                         = "1h"
            initial_interval                 = "24h"
            aws_region                       = var.aws_region
            tld                              = "amazonaws.com"
            tags                             = ["forwarded", "aws-inspector"]
            preserve_original_event          = false
            preserve_duplicate_custom_fields = false
          })
        }
      }
    }
    "securityhub-httpjson" = {
      enabled = false
      streams = {
        "aws.securityhub_findings" = {
          enabled = false
          vars = jsonencode({
            interval                         = "1h"
            initial_interval                 = "24h"
            aws_region                       = var.aws_region
            tld                              = "amazonaws.com"
            tags                             = ["forwarded", "aws_securityhub_findings"]
            preserve_original_event          = false
            preserve_duplicate_custom_fields = false
          })
        }
        "aws.securityhub_insights" = {
          enabled = false
          vars = jsonencode({
            interval                         = "1h"
            aws_region                       = var.aws_region
            tld                              = "amazonaws.com"
            tags                             = ["forwarded", "aws_securityhub_insights"]
            preserve_original_event          = false
            preserve_duplicate_custom_fields = false
          })
        }
        "aws.securityhub_findings_full_posture" = {
          enabled = false
          vars = jsonencode({
            aws_region                       = var.aws_region
            tld                              = "amazonaws.com"
            tags                             = ["forwarded", "aws_securityhub_findings_full_posture"]
            preserve_original_event          = false
            preserve_duplicate_custom_fields = false
          })
        }
      }
    }
    "guardduty-httpjson" = {
      enabled = false
      streams = {
        "aws.guardduty" = {
          enabled = false
          vars = jsonencode({
            interval                         = "1h"
            initial_interval                 = "24h"
            detector_id                      = try(data.aws_guardduty_detector.this[0].id, "00000000000000000000000000000000")
            aws_region                       = var.aws_region
            tld                              = "amazonaws.com"
            http_client_timeout              = "30s"
            tags                             = ["forwarded", "aws-guardduty"]
            preserve_original_event          = false
            preserve_duplicate_custom_fields = false
          })
        }
      }
    }
  }

  aws_security_enabled_inputs = merge(
    var.enable_cloudtrail && module.aws_cloud.cloudtrail_queue_url != null ? {
      "cloudtrail-aws-s3" = {
        enabled = true
        streams = {
          "aws.cloudtrail" = {
            enabled = true
            vars = jsonencode({
              queue_url               = module.aws_cloud.cloudtrail_queue_url
              collect_s3_logs         = false
              preserve_original_event = false
              actor_target_mapping    = true
            })
          }
        }
      }
    } : {},
    var.enable_security_hub ? {
      "securityhub-httpjson" = {
        enabled = true
        streams = {
          "aws.securityhub_findings" = {
            enabled = true
            vars = jsonencode({
              interval                         = "1h"
              initial_interval                 = "24h"
              aws_region                       = var.aws_region
              tld                              = "amazonaws.com"
              tags                             = ["forwarded", "aws_securityhub_findings"]
              preserve_original_event          = false
              preserve_duplicate_custom_fields = false
            })
          }
          "aws.securityhub_insights" = {
            enabled = true
            vars = jsonencode({
              interval                         = "1h"
              aws_region                       = var.aws_region
              tld                              = "amazonaws.com"
              tags                             = ["forwarded", "aws_securityhub_insights"]
              preserve_original_event          = false
              preserve_duplicate_custom_fields = false
            })
          }
          "aws.securityhub_findings_full_posture" = {
            enabled = true
            vars = jsonencode({
              aws_region                       = var.aws_region
              tld                              = "amazonaws.com"
              tags                             = ["forwarded", "aws_securityhub_findings_full_posture"]
              preserve_original_event          = false
              preserve_duplicate_custom_fields = false
            })
          }
        }
      }
    } : {},
    var.enable_guardduty ? {
      "guardduty-httpjson" = {
        enabled = true
        streams = {
          "aws.guardduty" = {
            enabled = true
            vars = jsonencode({
              interval                         = "1h"
              initial_interval                 = "24h"
              detector_id                      = data.aws_guardduty_detector.this[0].id
              aws_region                       = var.aws_region
              tld                              = "amazonaws.com"
              http_client_timeout              = "30s"
              tags                             = ["forwarded", "aws-guardduty"]
              preserve_original_event          = false
              preserve_duplicate_custom_fields = false
            })
          }
        }
      }
    } : {},
    var.enable_aws_health && !var.enable_managed_aws_metrics ? {
      "awshealth-aws/metrics" = {
        enabled = true
        streams = {
          "aws.awshealth" = {
            enabled = true
            vars = jsonencode({
              period  = "24h"
              regions = local.aws_metric_regions
            })
          }
        }
      }
    } : {}
  )

  aws_observe_enabled_inputs = merge(
    var.enable_vpc_flow_logs && module.aws_cloud.vpcflow_queue_url != null ? {
      "vpcflow-aws-s3" = {
        enabled = true
        streams = {
          "aws.vpcflow" = {
            enabled = true
            vars = jsonencode({
              queue_url               = module.aws_cloud.vpcflow_queue_url
              collect_s3_logs         = false
              tags                    = ["forwarded", "aws-vpcflow"]
              preserve_original_event = false
            })
          }
        }
      }
    } : {},
    # Metrics move to Managed Integrations when enable_managed_aws_metrics=true.
    # Keep agent-based multi-region metrics as a fallback path.
    !var.enable_managed_aws_metrics ? {
      "cloudwatch-aws/metrics" = {
        enabled = true
        streams = {
          "aws.cloudwatch_metrics" = {
            enabled = true
            vars = jsonencode(merge(
              {
                period  = "5m"
                latency = "5m"
                regions = local.aws_metric_regions
              },
              var.enable_trusted_advisor ? {
                metrics = <<-YAML
                  - namespace: AWS/TrustedAdvisor
                    name:
                      - RedResources
                      - YellowResources
                      - ServiceLimitUsage
                    statistic:
                      - Average
                      - Maximum
                YAML
              } : tomap({})
            ))
          }
        }
      }
      "ec2-aws/metrics" = {
        enabled = true
        streams = {
          "aws.ec2_metrics" = {
            enabled = true
            vars = jsonencode({
              period  = "5m"
              regions = local.aws_metric_regions
            })
          }
        }
      }
      "s3-aws/metrics" = {
        enabled = true
        streams = {
          "aws.s3_daily_storage" = {
            enabled = true
            vars = jsonencode({
              period  = "24h"
              regions = local.aws_metric_regions
            })
          }
          "aws.s3_request" = {
            enabled = true
            vars = jsonencode({
              period  = "5m"
              regions = local.aws_metric_regions
            })
          }
        }
      }
      "billing-aws/metrics" = {
        enabled = var.enable_billing_metrics
        streams = {
          "aws.billing" = {
            enabled = var.enable_billing_metrics
            vars = jsonencode({
              period = "12h"
            })
          }
        }
      }
    } : {}
  )

  # Elastic Managed Integrations (agentless) — one policy template per service,
  # each collecting across aws_metric_regions. Regions without resources return
  # empty CloudWatch results; the integration keeps running.
  aws_managed_metric_integrations = var.enable_managed_aws_metrics ? concat(
    [
      {
        name                 = "aws-managed-ec2"
        description          = "Managed (agentless) EC2 metrics across ${join(", ", local.aws_metric_regions)}"
        package_name         = "aws"
        managed              = true
        agent_policy         = false
        prerelease           = false
        package_version      = null
        policy_template      = "ec2"
        vars_json            = jsonencode(local.aws_managed_package_vars)
        var_group_selections = { credential_type = "identity_federation" }
        cloud_connector = {
          enabled            = true
          cloud_connector_id = data.external.aws_cloud_connector[0].result.id
          target_csp         = "aws"
        }
        inputs = {
          "ec2-aws/metrics" = {
            enabled = true
            streams = {
              "aws.ec2_metrics" = {
                enabled = true
                vars = jsonencode({
                  period  = "5m"
                  regions = local.aws_metric_regions
                })
              }
            }
          }
          "ec2-aws-s3" = {
            enabled = false
            streams = { "aws.ec2_logs" = { enabled = false } }
          }
          "ec2-aws-cloudwatch" = {
            enabled = false
            streams = { "aws.ec2_logs" = { enabled = false } }
          }
        }
      },
      {
        name                 = "aws-managed-s3"
        description          = "Managed (agentless) S3 metrics across ${join(", ", local.aws_metric_regions)}"
        package_name         = "aws"
        managed              = true
        agent_policy         = false
        prerelease           = false
        package_version      = null
        policy_template      = "s3"
        vars_json            = jsonencode(local.aws_managed_package_vars)
        var_group_selections = { credential_type = "identity_federation" }
        cloud_connector = {
          enabled            = true
          cloud_connector_id = data.external.aws_cloud_connector[0].result.id
          target_csp         = "aws"
        }
        inputs = {
          "s3-aws/metrics" = {
            enabled = true
            streams = {
              "aws.s3_daily_storage" = {
                enabled = true
                vars = jsonencode({
                  period  = "24h"
                  regions = local.aws_metric_regions
                })
              }
              "aws.s3_request" = {
                enabled = true
                vars = jsonencode({
                  period  = "5m"
                  regions = local.aws_metric_regions
                })
              }
            }
          }
          "s3-aws-s3" = {
            enabled = false
            streams = { "aws.s3access" = { enabled = false } }
          }
        }
      },
      {
        name                 = "aws-managed-cloudwatch"
        description          = "Managed CloudWatch metrics (Trusted Advisor) across ${join(", ", local.aws_metric_regions)}"
        package_name         = "aws"
        managed              = true
        agent_policy         = false
        prerelease           = false
        package_version      = null
        policy_template      = "cloudwatch"
        vars_json            = jsonencode(local.aws_managed_package_vars)
        var_group_selections = { credential_type = "identity_federation" }
        cloud_connector = {
          enabled            = true
          cloud_connector_id = data.external.aws_cloud_connector[0].result.id
          target_csp         = "aws"
        }
        inputs = {
          "cloudwatch-aws/metrics" = {
            enabled = true
            streams = {
              "aws.cloudwatch_metrics" = {
                enabled = true
                vars = jsonencode(merge(
                  {
                    period  = "5m"
                    latency = "5m"
                    regions = local.aws_metric_regions
                  },
                  var.enable_trusted_advisor ? {
                    metrics = <<-YAML
                      - namespace: AWS/TrustedAdvisor
                        name:
                          - RedResources
                          - YellowResources
                          - ServiceLimitUsage
                        statistic:
                          - Average
                          - Maximum
                    YAML
                  } : tomap({})
                ))
              }
            }
          }
          "cloudwatch-aws-cloudwatch" = {
            enabled = false
            streams = { "aws.cloudwatch_logs" = { enabled = false } }
          }
        }
      }
    ],
    var.enable_billing_metrics ? [
      {
        name                 = "aws-managed-billing"
        description          = "Managed (agentless) AWS billing metrics (Cost Explorer; global / us-east-1)"
        package_name         = "aws"
        managed              = true
        agent_policy         = false
        prerelease           = false
        package_version      = null
        policy_template      = "billing"
        vars_json            = jsonencode(local.aws_managed_package_vars)
        var_group_selections = { credential_type = "identity_federation" }
        cloud_connector = {
          enabled            = true
          cloud_connector_id = data.external.aws_cloud_connector[0].result.id
          target_csp         = "aws"
        }
        inputs = {
          "billing-aws/metrics" = {
            enabled = true
            streams = {
              "aws.billing" = {
                enabled = true
                vars = jsonencode({
                  period = "12h"
                })
              }
            }
          }
        }
      }
    ] : [],
    var.enable_aws_health ? [
      {
        name                 = "aws-managed-awshealth"
        description          = "Managed (agentless) AWS Health across ${join(", ", local.aws_metric_regions)}"
        package_name         = "aws"
        managed              = true
        agent_policy         = false
        prerelease           = false
        package_version      = null
        policy_template      = "awshealth"
        vars_json            = jsonencode(local.aws_managed_package_vars)
        var_group_selections = { credential_type = "identity_federation" }
        cloud_connector = {
          enabled            = true
          cloud_connector_id = data.external.aws_cloud_connector[0].result.id
          target_csp         = "aws"
        }
        inputs = {
          "awshealth-aws/metrics" = {
            enabled = true
            streams = {
              "aws.awshealth" = {
                enabled = true
                vars = jsonencode({
                  period  = "24h"
                  regions = local.aws_metric_regions
                })
              }
            }
          }
        }
      }
    ] : []
  ) : []

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
                  role_arn                      = module.aws_cloud.elastic_role_arn
                  "aws.credentials.type"        = "assume_role"
                  "aws.account_type"            = "single-account"
                  "aws.credentials.external_id" = module.aws_cloud.external_id
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
        description          = "AWS console-home security: Security Hub, GuardDuty, AWS Health (+ CloudTrail when SQS allowed)"
        package_name         = "aws"
        managed              = false
        agent_policy         = true
        prerelease           = false
        package_version      = null
        policy_template      = null
        vars_json            = jsonencode(local.aws_package_vars)
        var_group_selections = {}
        cloud_connector      = null
        inputs               = merge(local.aws_disabled_input_stubs, local.aws_httpjson_disabled_overrides, local.aws_security_enabled_inputs)
      }
    ]
  )

  # Observability: Managed Integrations for multi-region metrics + optional agent for vpcflow.
  observability_integrations = concat(
    local.aws_managed_metric_integrations,
    [
      {
        name                 = "aws-observe"
        description          = var.enable_managed_aws_metrics ? "AWS observability agent (vpcflow via SQS; metrics via Managed Integrations)" : "AWS observability (multi-region metrics + Trusted Advisor; vpcflow when SQS allowed)"
        package_name         = "aws"
        managed              = false
        agent_policy         = true
        prerelease           = false
        package_version      = null
        policy_template      = null
        vars_json            = jsonencode(local.aws_package_vars)
        var_group_selections = {}
        cloud_connector      = null
        inputs               = merge(local.aws_disabled_input_stubs, local.aws_httpjson_disabled_overrides, local.aws_observe_enabled_inputs)
      }
    ]
  )
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

  depends_on = [module.observability, module.aws_cloud, data.external.aws_cloud_connector]
}

# Resolve / create a single Fleet cloud connector for all Managed Integrations.
data "external" "aws_cloud_connector" {
  count = var.enable_managed_aws_metrics && length(module.observability) > 0 ? 1 : 0

  program = [
    "python3",
    "${path.module}/../../modules/cockpit-dashboard/scripts/ensure_aws_cloud_connector_external.py",
  ]

  query = {
    kb_url   = module.observability[0].kibana_endpoint
    kb_user  = module.observability[0].username
    kb_pass  = module.observability[0].password
    name     = local.aws_cloud_connector_name
    role_arn = module.aws_cloud.elastic_role_arn
  }

  depends_on = [module.observability, module.aws_cloud]
}

module "elastic_agent" {
  count  = var.enable_elastic_agent ? 1 : 0
  source = "../../modules/elastic-agent-ec2"

  name                 = "${var.name_prefix}-agent"
  instance_type        = var.elastic_agent_instance_type
  company_tags         = merge(module.aws_cloud.applied_tags, { Role = "elastic-agent-security" })
  fleet_url            = module.elastic.fleet_endpoint
  enrollment_token     = module.stack.enrollment_token
  agent_version        = var.elastic_agent_version
  iam_instance_profile = module.aws_cloud.agent_instance_profile_name

  depends_on = [module.stack]
}

module "elastic_agent_obs" {
  count  = var.enable_elastic_agent && length(module.stack_obs) > 0 ? 1 : 0
  source = "../../modules/elastic-agent-ec2"

  name                 = "${var.name_prefix}-obs-agent"
  instance_type        = var.elastic_agent_instance_type
  company_tags         = merge(module.aws_cloud.applied_tags, { Role = "elastic-agent-observability" })
  fleet_url            = module.observability[0].fleet_endpoint
  enrollment_token     = module.stack_obs[0].enrollment_token
  agent_version        = var.elastic_agent_version
  iam_instance_profile = module.aws_cloud.agent_instance_profile_name

  depends_on = [module.stack_obs]
}
