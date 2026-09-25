data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

data "aws_vpc" "default" {
  count   = var.enable_vpc_flow_logs ? 1 : 0
  default = true
}

resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.region
  bucket      = lower("${var.bucket_name}-${local.account_id}-${random_id.suffix.hex}")
  external_id = random_id.suffix.hex

  common_tags = merge(
    {
      Project   = "elastic-cloud-poc"
      ManagedBy = "terraform"
    },
    var.company_tags,
    var.additional_tags
  )

  missing_required_keys = [
    for key in var.required_tag_keys : key
    if !contains(keys(var.company_tags), key)
  ]
}

check "required_company_tags" {
  assert {
    condition     = length(local.missing_required_keys) == 0
    error_message = "company_tags is missing required keys: ${join(", ", local.missing_required_keys)}"
  }
}

# -----------------------------------------------------------------------------
# Log landing bucket + SQS notifications
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "logs" {
  bucket = local.bucket
  tags   = merge(local.common_tags, { Name = local.bucket })
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_sqs_queue" "cloudtrail" {
  count = var.enable_sqs ? 1 : 0

  name                       = "${var.name_prefix}-cloudtrail"
  visibility_timeout_seconds = 900
  tags                       = local.common_tags
}

resource "aws_sqs_queue_policy" "cloudtrail" {
  count = var.enable_sqs ? 1 : 0

  queue_url = aws_sqs_queue.cloudtrail[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.cloudtrail[0].arn
      Condition = {
        ArnEquals = { "aws:SourceArn" = aws_s3_bucket.logs.arn }
      }
    }]
  })
}

resource "aws_sqs_queue" "vpcflow" {
  count = var.enable_sqs && var.enable_vpc_flow_logs ? 1 : 0

  name                       = "${var.name_prefix}-vpcflow"
  visibility_timeout_seconds = 900
  tags                       = local.common_tags
}

resource "aws_sqs_queue_policy" "vpcflow" {
  count = var.enable_sqs && var.enable_vpc_flow_logs ? 1 : 0

  queue_url = aws_sqs_queue.vpcflow[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.vpcflow[0].arn
      Condition = {
        ArnEquals = { "aws:SourceArn" = aws_s3_bucket.logs.arn }
      }
    }]
  })
}

resource "aws_s3_bucket_policy" "logs" {
  bucket = aws_s3_bucket.logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AWSCloudTrailAclCheck"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.logs.arn
      },
      {
        Sid       = "AWSLogDeliveryAclCheck"
        Effect    = "Allow"
        Principal = { Service = "delivery.logs.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.logs.arn
        Condition = {
          StringEquals = { "aws:SourceAccount" = local.account_id }
        }
      },
      {
        Sid    = "AWSLogWrite"
        Effect = "Allow"
        Principal = {
          Service = [
            "cloudtrail.amazonaws.com",
            "vpc-flow-logs.amazonaws.com",
            "delivery.logs.amazonaws.com"
          ]
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.logs.arn}/AWSLogs/${local.account_id}/*"
        Condition = {
          StringEquals = { "s3:x-amz-acl" = "bucket-owner-full-control" }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_notification" "logs" {
  count = var.enable_sqs ? 1 : 0

  bucket = aws_s3_bucket.logs.id

  queue {
    queue_arn     = aws_sqs_queue.cloudtrail[0].arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "AWSLogs/${local.account_id}/CloudTrail/"
  }

  dynamic "queue" {
    for_each = var.enable_vpc_flow_logs ? [1] : []
    content {
      queue_arn     = aws_sqs_queue.vpcflow[0].arn
      events        = ["s3:ObjectCreated:*"]
      filter_prefix = "AWSLogs/${local.account_id}/vpcflowlogs/"
    }
  }

  depends_on = [
    aws_sqs_queue_policy.cloudtrail,
    aws_sqs_queue_policy.vpcflow,
  ]
}

# -----------------------------------------------------------------------------
# CloudTrail
# -----------------------------------------------------------------------------

resource "aws_cloudtrail" "management" {
  count = var.enable_cloudtrail ? 1 : 0

  name                          = "${var.name_prefix}-trail"
  s3_bucket_name                = aws_s3_bucket.logs.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_logging                = true
  tags                          = local.common_tags

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }

  depends_on = [aws_s3_bucket_policy.logs]
}

# -----------------------------------------------------------------------------
# VPC Flow Logs (default VPC when present)
# -----------------------------------------------------------------------------

resource "aws_flow_log" "default_vpc" {
  count = var.enable_vpc_flow_logs && length(data.aws_vpc.default) > 0 ? 1 : 0

  log_destination      = aws_s3_bucket.logs.arn
  log_destination_type = "s3"
  traffic_type         = "ALL"
  vpc_id               = data.aws_vpc.default[0].id
  tags                 = local.common_tags

  depends_on = [aws_s3_bucket_policy.logs]
}

# -----------------------------------------------------------------------------
# IAM role for Elastic (assume-role / cloud connector style)
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "elastic_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${local.account_id}:root"]
    }

    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = [local.external_id]
    }
  }
}

resource "aws_iam_role" "elastic" {
  name               = "${var.name_prefix}-elastic-collector"
  assume_role_policy = data.aws_iam_policy_document.elastic_trust.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "elastic_permissions" {
  statement {
    sid    = "CloudWatchMetrics"
    effect = "Allow"
    actions = [
      "cloudwatch:GetMetricData",
      "cloudwatch:ListMetrics",
      "ec2:Describe*",
      "rds:Describe*",
      "rds:List*",
      "s3:GetBucketLocation",
      "s3:ListAllMyBuckets",
      "s3:ListBucket",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "tag:GetResources",
      "iam:ListAccountAliases",
      "organizations:DescribeOrganization",
      "ce:GetCostAndUsage",
      "ce:GetDimensionValues",
      "config:Describe*",
      "config:Get*",
      "config:List*",
      "securityhub:Get*",
      "securityhub:Describe*",
      "securityhub:List*",
      "guardduty:Get*",
      "guardduty:List*",
      "inspector2:List*",
      "inspector2:Get*",
      # AWS Health (console home widget)
      "health:DescribeEvents",
      "health:DescribeEventDetails",
      "health:DescribeAffectedEntities",
      # Trusted Advisor check metrics land in CloudWatch (AWS/TrustedAdvisor)
      "support:DescribeTrustedAdvisorChecks",
      "support:DescribeTrustedAdvisorCheckResult",
      "support:DescribeTrustedAdvisorCheckSummaries"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ReadLogBucket"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.logs.arn,
      "${aws_s3_bucket.logs.arn}/*"
    ]
  }

  statement {
    sid    = "ReadCloudTrailQueue"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    # When SQS is disabled (org SCP), keep a no-op resource so the policy
    # document does not depend on queue creation.
    resources = length(compact(concat(
      aws_sqs_queue.cloudtrail[*].arn,
      aws_sqs_queue.vpcflow[*].arn,
    ))) > 0 ? compact(concat(
      aws_sqs_queue.cloudtrail[*].arn,
      aws_sqs_queue.vpcflow[*].arn,
    )) : ["arn:${data.aws_partition.current.partition}:sqs:${local.region}:${local.account_id}:elastic-poc-disabled"]
  }
}

resource "aws_iam_role_policy" "elastic" {
  name   = "${var.name_prefix}-elastic-collector"
  role   = aws_iam_role.elastic.id
  policy = data.aws_iam_policy_document.elastic_permissions.json
}

# Broad SecurityAudit for CSPM findings
resource "aws_iam_role_policy_attachment" "security_audit" {
  role       = aws_iam_role.elastic.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/SecurityAudit"
}

resource "aws_iam_role_policy_attachment" "view_only" {
  role       = aws_iam_role.elastic.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/job-function/ViewOnlyAccess"
}

# -----------------------------------------------------------------------------
# EC2 instance profile for Elastic Agents (IMDS credentials — no static keys)
# Same collector permissions; agents use the default AWS credential chain.
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "agent_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "agent" {
  name               = "${var.name_prefix}-elastic-agent"
  assume_role_policy = data.aws_iam_policy_document.agent_trust.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "agent" {
  name   = "${var.name_prefix}-elastic-agent"
  role   = aws_iam_role.agent.id
  policy = data.aws_iam_policy_document.elastic_permissions.json
}

resource "aws_iam_role_policy_attachment" "agent_security_audit" {
  role       = aws_iam_role.agent.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/SecurityAudit"
}

resource "aws_iam_role_policy_attachment" "agent_view_only" {
  role       = aws_iam_role.agent.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/job-function/ViewOnlyAccess"
}

resource "aws_iam_instance_profile" "agent" {
  name = "${var.name_prefix}-elastic-agent"
  role = aws_iam_role.agent.name
  tags = local.common_tags
}
