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
  }
}

provider "ec" {}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.company_tags
  }
}

# Per-resource kibana_connection blocks supply credentials.
provider "elasticstack" {}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  elastic_tags = {
    for k, v in var.company_tags :
    substr(lower(replace(replace(replace(replace(k, " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32) =>
    substr(lower(replace(replace(replace(replace(tostring(v), " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32)
  }

  required_aws_tag_keys_missing = [
    for key in var.required_tag_keys : key
    if !contains(keys(var.company_tags), key)
  ]

  # An empty regions list is the AWS integration's documented "all regions"
  # setting. Every supported observability policy template is represented in
  # this single Elastic-managed integration.
  all_region_vars = jsonencode({
    regions = []
  })

  managed_inputs = {
    "awshealth-aws/metrics" = {
      enabled = true
      streams = {
        "aws.awshealth" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "billing-aws/metrics" = {
      enabled = true
      streams = {
        "aws.billing" = {
          enabled = true
          vars = jsonencode({
            period                  = "24h"
            include_linked_accounts = true
          })
        }
      }
    }
    "cloudwatch-aws/metrics" = {
      enabled = true
      streams = {
        "aws.cloudwatch_metrics" = {
          enabled = true
          vars = jsonencode({
            period                  = "5m"
            latency                 = "5m"
            regions                 = []
            include_linked_accounts = true
            metrics                 = <<-YAML
              - namespace: AWS/EC2
                resource_type: ec2:instance
                name:
                  - CPUUtilization
                  - DiskWriteOps
                statistic:
                  - Average
                  - Maximum
            YAML
          })
        }
      }
    }
    "dynamodb-aws/metrics" = {
      enabled = true
      streams = {
        "aws.dynamodb" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "ebs-aws/metrics" = {
      enabled = true
      streams = {
        "aws.ebs" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "ec2-aws/metrics" = {
      enabled = true
      streams = {
        "aws.ec2_metrics" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "ecs-aws/metrics" = {
      enabled = true
      streams = {
        "aws.ecs_metrics" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "elb-aws/metrics" = {
      enabled = true
      streams = {
        "aws.elb_metrics" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "lambda-aws/metrics" = {
      enabled = true
      streams = {
        "aws.lambda" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "firewall-aws/metrics" = {
      enabled = true
      streams = {
        "aws.firewall_metrics" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "rds-aws/metrics" = {
      enabled = true
      streams = {
        "aws.rds" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "s3-aws/metrics" = {
      enabled = true
      streams = {
        "aws.s3_daily_storage" = {
          enabled = true
          vars    = local.all_region_vars
        }
        "aws.s3_request" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "sns-aws/metrics" = {
      enabled = true
      streams = {
        "aws.sns" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "sqs-aws/metrics" = {
      enabled = true
      streams = {
        "aws.sqs" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
    "transitgateway-aws/metrics" = {
      enabled = true
      streams = {
        "aws.transitgateway" = {
          enabled = true
          vars    = local.all_region_vars
        }
      }
    }
  }

  # Inputs whose policy templates are not available in Elastic-managed mode.
  # Metrics use an empty region list to discover all enabled AWS regions. Log
  # inputs use Terraform-provisioned S3/SQS sources or well-known CloudWatch
  # log-group prefixes in the bootstrap region.
  agent_inputs = merge(
    {
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
      "natgateway-aws/metrics" = {
        enabled = true
        streams = {
          "aws.natgateway" = {
            enabled = true
            vars    = local.all_region_vars
          }
        }
      }
      "s3_storage_lens-aws/metrics" = {
        enabled = true
        streams = {
          "aws.s3_storage_lens" = {
            enabled = true
            vars    = local.all_region_vars
          }
        }
      }
      "usage-aws/metrics" = {
        enabled = true
        streams = {
          "aws.usage" = {
            enabled = true
            vars    = local.all_region_vars
          }
        }
      }
      "vpcflow-aws-s3" = {
        enabled = true
        streams = {
          "aws.vpcflow" = {
            enabled = true
            vars = jsonencode({
              queue_url               = module.aws_cloud.vpcflow_queue_url
              collect_s3_logs         = false
              preserve_original_event = false
            })
          }
        }
      }
      "vpn-aws/metrics" = {
        enabled = true
        streams = {
          "aws.vpn" = {
            enabled = true
            vars    = local.all_region_vars
          }
        }
      }
      "waf-aws-cloudwatch" = {
        enabled = true
        streams = {
          "aws.waf" = {
            enabled = true
            vars = jsonencode({
              log_group_name_prefix   = "aws-waf-logs-"
              region_name             = var.aws_region
              preserve_original_event = false
            })
          }
        }
      }
      "route53-aws-cloudwatch" = {
        enabled = true
        streams = {
          "aws.route53_public_logs" = {
            enabled = true
            vars = jsonencode({
              log_group_name_prefix   = "/aws/route53/"
              region_name             = "us-east-1"
              preserve_original_event = false
            })
          }
          "aws.route53_resolver_logs" = {
            enabled = true
            vars = jsonencode({
              log_group_name_prefix   = "/aws/route53resolver/"
              region_name             = var.aws_region
              preserve_original_event = false
            })
          }
        }
      }
      "redshift-aws/metrics" = {
        enabled = true
        streams = {
          "aws.redshift" = {
            enabled = true
            vars    = local.all_region_vars
          }
        }
      }
      "kinesis-aws/metrics" = {
        enabled = true
        streams = {
          "aws.kinesis" = {
            enabled = true
            vars    = local.all_region_vars
          }
        }
      }
      "apigateway-aws/metrics" = {
        enabled = true
        streams = {
          "aws.apigateway_metrics" = {
            enabled = true
            vars    = local.all_region_vars
          }
        }
      }
      "apigateway-aws-cloudwatch" = {
        enabled = true
        streams = {
          "aws.apigateway_logs" = {
            enabled = true
            vars = jsonencode({
              log_group_name_prefix   = "API-Gateway-Execution-Logs_"
              region_name             = var.aws_region
              preserve_original_event = false
            })
          }
        }
      }
      "emr-aws/metrics" = {
        enabled = true
        streams = {
          "aws.emr_metrics" = {
            enabled = true
            vars    = local.all_region_vars
          }
        }
      }
      "emr-aws-cloudwatch" = {
        enabled = true
        streams = {
          "aws.emr_logs" = {
            enabled = true
            vars = jsonencode({
              log_group_name_prefix   = "/aws/elasticmapreduce/"
              region_name             = var.aws_region
              preserve_original_event = false
            })
          }
        }
      }
      "kafka-aws/metrics" = {
        enabled = true
        streams = {
          "aws.kafka_metrics" = {
            enabled = true
            vars    = local.all_region_vars
          }
        }
      }
    },
    var.cloudfront_queue_url != "" ? {
      "cloudfront-aws-s3" = {
        enabled = true
        streams = {
          "aws.cloudfront_logs" = {
            enabled = true
            vars = jsonencode({
              queue_url               = var.cloudfront_queue_url
              collect_s3_logs         = false
              preserve_original_event = false
            })
          }
        }
      }
    } : {},
  )
}

check "required_company_tags" {
  assert {
    condition     = length(local.required_aws_tag_keys_missing) == 0
    error_message = "company_tags is missing required keys: ${join(", ", local.required_aws_tag_keys_missing)}"
  }
}

# The only Elastic environment: one Serverless Observability project.
module "observability" {
  source = "../../modules/elastic-project"

  deployment_mode = "serverless"
  project_kind    = "observability"
  name            = var.elastic_project_name
  region          = var.elastic_region
  product_tier    = var.product_tier
  tags            = local.elastic_tags
}

# Provision the sources needed by agent-only CloudTrail and VPC Flow inputs,
# plus the EC2 instance profile used by the collector.
module "aws_cloud" {
  source = "../../modules/aws-cloud"

  name_prefix          = var.name_prefix
  bucket_name          = var.bucket_name
  enable_cloudtrail    = true
  enable_vpc_flow_logs = true
  enable_sqs           = true
  company_tags         = var.company_tags
  required_tag_keys    = var.required_tag_keys
  additional_tags = {
    Cloud = "aws"
  }
}

# Elastic's managed collector assumes this role through identity federation.
data "aws_iam_policy_document" "elastic_managed_trust" {
  statement {
    sid     = "ElasticManagedCollector"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [var.elastic_managed_collector_role_arn]
    }
  }
}

resource "aws_iam_role" "elastic_managed" {
  name               = "${var.name_prefix}-managed-observability"
  assume_role_policy = data.aws_iam_policy_document.elastic_managed_trust.json
  tags               = merge(var.company_tags, { Name = "${var.name_prefix}-managed-observability" })
}

data "aws_iam_policy_document" "elastic_managed" {
  statement {
    sid    = "DiscoverAccountAndRegions"
    effect = "Allow"
    actions = [
      "ec2:DescribeRegions",
      "iam:ListAccountAliases",
      "sts:GetCallerIdentity",
      "tag:GetResources",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "CollectObservabilityMetrics"
    effect = "Allow"
    actions = [
      "cloudwatch:GetMetricData",
      "cloudwatch:ListMetrics",
      "dynamodb:DescribeTable",
      "dynamodb:ListTables",
      "ec2:DescribeInstanceStatus",
      "ec2:DescribeInstances",
      "ec2:DescribeTransitGatewayAttachments",
      "ec2:DescribeTransitGateways",
      "ec2:DescribeVolumes",
      "ecs:DescribeClusters",
      "ecs:DescribeServices",
      "ecs:ListClusters",
      "ecs:ListServices",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeTags",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeTargetHealth",
      "lambda:GetFunction",
      "lambda:ListFunctions",
      "rds:DescribeDBClusters",
      "rds:DescribeDBInstances",
      "rds:ListTagsForResource",
      "s3:GetBucketLocation",
      "s3:ListAllMyBuckets",
      "s3:ListBucket",
      "sns:GetTopicAttributes",
      "sns:ListTopics",
      "sqs:GetQueueAttributes",
      "sqs:ListQueues",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "CollectGlobalObservabilityData"
    effect = "Allow"
    actions = [
      "ce:GetCostAndUsage",
      "health:DescribeAffectedEntities",
      "health:DescribeEventDetails",
      "health:DescribeEvents",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "elastic_managed" {
  name   = "${var.name_prefix}-managed-observability"
  role   = aws_iam_role.elastic_managed.id
  policy = data.aws_iam_policy_document.elastic_managed.json
}

# Elastic-managed collection handles every supported observability input. A
# separate Fleet policy contains only the inputs that still require an agent.
module "stack" {
  source = "../../modules/elastic-stack"

  kibana_endpoint        = module.observability.kibana_endpoint
  elasticsearch_endpoint = module.observability.elasticsearch_endpoint
  elasticsearch_username = module.observability.username
  elasticsearch_password = module.observability.password
  enable_detection_rules = false

  integrations = [
    {
      name            = "aws-observability-all-regions"
      description     = "Elastic-managed AWS observability collection across all regions"
      package_name    = "aws"
      managed         = true
      agent_policy    = false
      prerelease      = false
      package_version = null
      policy_template = null
      vars_json = jsonencode({
        default_region               = var.aws_region
        role_arn                     = aws_iam_role.elastic_managed.arn
        supports_identity_federation = true
      })
      var_group_selections = {
        credential_type = "identity_federation"
      }
      cloud_connector = {
        enabled            = true
        cloud_connector_id = null
        name               = "${var.name_prefix}-aws-observability"
        target_csp         = "aws"
      }
      inputs = local.managed_inputs
    },
    {
      name            = "aws-agent-only-integrations"
      description     = "AWS integrations and log inputs unavailable in Elastic-managed mode"
      package_name    = "aws"
      managed         = false
      agent_policy    = true
      prerelease      = false
      package_version = null
      policy_template = null
      vars_json = jsonencode({
        default_region = var.aws_region
      })
      var_group_selections = {
        credential_type = "default_credentials"
      }
      cloud_connector = null
      inputs          = local.agent_inputs
    },
  ]

  depends_on = [module.observability, module.aws_cloud, aws_iam_role_policy.elastic_managed]
}

# One customer-managed agent handles only the inputs unavailable in managed
# mode. Its instance profile supplies credentials through IMDS.
module "elastic_agent" {
  source = "../../modules/elastic-agent-ec2"

  name                 = "${var.name_prefix}-agent"
  instance_type        = var.elastic_agent_instance_type
  company_tags         = merge(var.company_tags, { Role = "elastic-agent-observability" })
  fleet_url            = module.observability.fleet_endpoint
  enrollment_token     = module.stack.enrollment_token
  agent_version        = var.elastic_agent_version
  iam_instance_profile = module.aws_cloud.agent_instance_profile_name

  depends_on = [module.stack]
}

# Keep the curated AWS cockpit in the same Observability project as the data.
module "cockpit" {
  count  = var.enable_cockpit_dashboard ? 1 : 0
  source = "../../modules/cockpit-dashboard"

  kibana_endpoint        = module.observability.kibana_endpoint
  elasticsearch_username = module.observability.username
  elasticsearch_password = module.observability.password
  title                  = "AWS Observability Cockpit"
  description            = "AWS service health and metrics collected across all regions."
  dashboard_id           = "a1b2c3d4-e5f6-4789-a012-3456789abcde"
  ndjson_path            = "${path.module}/../../modules/cockpit-dashboard/cockpit-aws.ndjson"

  depends_on = [module.stack]
}

# Deploy every pinned workflow definition in examples/aws/workflows into the
# Observability project. The directory remains the source of truth.
module "workflows" {
  count  = var.enable_workflows ? 1 : 0
  source = "../../modules/kibana-workflows"

  kibana_endpoint        = module.observability.kibana_endpoint
  elasticsearch_username = module.observability.username
  elasticsearch_password = module.observability.password
  workflows_dir          = "${path.module}/workflows"
  execute_on_apply       = var.execute_workflows_on_apply

  depends_on = [module.stack, module.cockpit]
}
