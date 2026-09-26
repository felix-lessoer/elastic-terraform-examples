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
    external = {
      source  = "hashicorp/external"
      version = ">= 2.3"
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

data "external" "guardduty_detectors" {
  program = ["python3", "${path.module}/scripts/discover_guardduty.py"]

  query = {
    bootstrap_region = var.aws_region
  }
}

data "external" "enabled_regions" {
  program = ["python3", "${path.module}/scripts/discover_enabled_regions.py"]

  query = {
    bootstrap_region = var.aws_region
  }
}

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

  # Mixed templates default their log inputs on the server. Disable log
  # transports that managed mode cannot run or that need a concrete source.
  managed_disabled_inputs = {
    cloudwatch = {
      "cloudwatch-aws-cloudwatch" = {
        enabled = false
        streams = { "aws.cloudwatch_logs" = { enabled = false } }
      }
    }
    ec2 = {
      "ec2-aws-s3" = {
        enabled = false
        streams = { "aws.ec2_logs" = { enabled = false } }
      }
      "ec2-aws-cloudwatch" = {
        enabled = false
        streams = { "aws.ec2_logs" = { enabled = false } }
      }
    }
    elb = {
      "elb-aws-s3" = {
        enabled = false
        streams = { "aws.elb_logs" = { enabled = false } }
      }
      "elb-aws-cloudwatch" = {
        enabled = false
        streams = { "aws.elb_logs" = { enabled = false } }
      }
    }
    lambda = {
      "lambda-aws-cloudwatch" = {
        enabled = false
        streams = { "aws.lambda_logs" = { enabled = false } }
      }
    }
    firewall = {
      "firewall-aws-s3" = {
        enabled = false
        streams = { "aws.firewall_logs" = { enabled = false } }
      }
      "firewall-aws-cloudwatch" = {
        enabled = false
        streams = { "aws.firewall_logs" = { enabled = false } }
      }
    }
    s3 = {
      "s3-aws-s3" = {
        enabled = false
        streams = { "aws.s3access" = { enabled = false } }
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
            vars = var.existing_cloudtrail_bucket_name != "" ? jsonencode({
              bucket_arn              = "arn:${data.aws_partition.current.partition}:s3:::${var.existing_cloudtrail_bucket_name}"
              bucket_list_prefix      = "AWSLogs/${data.aws_caller_identity.current.account_id}/CloudTrail/"
              collect_s3_logs         = true
              preserve_original_event = false
              actor_target_mapping    = true
              }) : jsonencode({
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

  # The AWS package adds every input to an aggregate agent policy unless it is
  # explicitly disabled. Keep the EC2 policy limited to agent-only collection
  # and avoid duplicate managed ingestion.
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

  agent_disabled_input_stubs = {
    for input_key, datasets in local.aws_all_input_datasets : input_key => {
      enabled = false
      streams = { for dataset in datasets : dataset => { enabled = false } }
    }
  }

  # Fleet validates required fields on these API streams even while disabled.
  agent_required_disabled_overrides = {
    "config-cel" = {
      enabled = false
      streams = {
        "aws.config" = {
          enabled = false
          vars    = jsonencode({ aws_region = var.aws_region })
        }
      }
    }
    "securityhub-httpjson" = {
      enabled = false
      streams = {
        "aws.securityhub_findings" = {
          enabled = false
          vars    = jsonencode({ aws_region = var.aws_region })
        }
        "aws.securityhub_findings_full_posture" = {
          enabled = false
          vars    = jsonencode({ aws_region = var.aws_region })
        }
        "aws.securityhub_insights" = {
          enabled = false
          vars    = jsonencode({ aws_region = var.aws_region })
        }
      }
    }
    "inspector-httpjson" = {
      enabled = false
      streams = {
        "aws.inspector" = {
          enabled = false
          vars    = jsonencode({ aws_region = var.aws_region })
        }
      }
    }
    "guardduty-httpjson" = {
      enabled = false
      streams = {
        "aws.guardduty" = {
          enabled = false
          vars = jsonencode({
            aws_region  = var.aws_region
            detector_id = "00000000000000000000000000000000"
          })
        }
      }
    }
  }

  agent_policy_inputs = merge(
    local.agent_disabled_input_stubs,
    local.agent_required_disabled_overrides,
    local.agent_inputs,
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
  enable_cloudtrail    = var.existing_cloudtrail_bucket_name == ""
  enable_vpc_flow_logs = true
  enable_sqs           = true
  company_tags         = var.company_tags
  required_tag_keys    = var.required_tag_keys
  additional_read_bucket_arns = var.existing_cloudtrail_bucket_name != "" ? [
    "arn:${data.aws_partition.current.partition}:s3:::${var.existing_cloudtrail_bucket_name}"
  ] : []
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
      "guardduty:GetDetector",
      "guardduty:GetFindings",
      "guardduty:ListDetectors",
      "guardduty:ListFindings",
      "securityhub:DescribeHub",
      "securityhub:GetFindings",
      "securityhub:GetInsights",
      "securityhub:ListEnabledProductsForImport",
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

  integrations = concat(
    [
      for input_key, input_config in local.managed_inputs : {
        name            = "aws-managed-${split("-", input_key)[0]}-all-regions"
        description     = "Elastic-managed ${split("-", input_key)[0]} collection across all regions"
        package_name    = "aws"
        managed         = true
        agent_policy    = false
        prerelease      = false
        package_version = null
        policy_template = split("-", input_key)[0]
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
          name               = "${var.name_prefix}-${split("-", input_key)[0]}"
          target_csp         = "aws"
        }
        inputs = merge(
          lookup(local.managed_disabled_inputs, split("-", input_key)[0], {}),
          { (input_key) = input_config },
        )
      }
    ],
    [{
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
      inputs          = local.agent_policy_inputs
    }],
  )

  depends_on = [module.observability, module.aws_cloud, aws_iam_role_policy.elastic_managed]
}

# GuardDuty, Security Hub, Inspector, and Config are regional API integrations.
# Merge them into one package policy per region on the shared EC2 Agent.
resource "terraform_data" "regional_security_integrations" {
  input = {
    kibana_url      = module.observability.kibana_endpoint
    kibana_username = module.observability.username
    kibana_password = module.observability.password
    agent_policy_id = module.stack.agent_policy_id
    aws_account_id  = data.aws_caller_identity.current.account_id
    regions_json    = jsonencode(sort(keys(data.external.enabled_regions.result)))
    detectors_json  = jsonencode(data.external.guardduty_detectors.result)
  }

  triggers_replace = [
    jsonencode(sort(keys(data.external.enabled_regions.result))),
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "python3 '${path.module}/scripts/sync_regional_security_integrations.py' sync"
    environment = {
      KIBANA_URL      = self.input.kibana_url
      KIBANA_USERNAME = self.input.kibana_username
      KIBANA_PASSWORD = self.input.kibana_password
      AGENT_POLICY_ID = self.input.agent_policy_id
      AWS_ACCOUNT_ID  = self.input.aws_account_id
      REGIONS_JSON    = self.input.regions_json
      DETECTORS_JSON  = self.input.detectors_json
    }
  }

  provisioner "local-exec" {
    when        = destroy
    on_failure  = continue
    interpreter = ["/bin/bash", "-c"]
    command     = "python3 '${path.module}/scripts/sync_regional_security_integrations.py' cleanup"
    environment = {
      KIBANA_URL      = self.input.kibana_url
      KIBANA_USERNAME = self.input.kibana_username
      KIBANA_PASSWORD = self.input.kibana_password
      AGENT_POLICY_ID = self.input.agent_policy_id
      AWS_ACCOUNT_ID  = self.input.aws_account_id
      REGIONS_JSON    = self.input.regions_json
      DETECTORS_JSON  = self.input.detectors_json
    }
  }

  depends_on = [module.stack, module.aws_cloud]
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
