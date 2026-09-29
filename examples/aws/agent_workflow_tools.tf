# Expose recommendation / coverage workflows as Agent Builder tools so the next
# greenfield deploy can attach them in the UI. Created after module.workflows.

locals {
  aws_workflow_tool_specs = var.enable_ai_agents && var.enable_workflows && length(module.workflows) > 0 ? {
    "aws-wf-ec2-recommendations" = {
      workflow_id = "aws-cockpit-ec2-recommendations"
      description = "Run the AWS EC2 recommendations workflow (writes aws-cockpit-recommendations)."
    }
    "aws-wf-s3-recommendations" = {
      workflow_id = "aws-cockpit-s3-recommendations"
      description = "Run the AWS S3 recommendations workflow (writes aws-cockpit-recommendations)."
    }
    "aws-wf-lambda-insights" = {
      workflow_id = "aws-cockpit-lambda-insights"
      description = "Run the AWS Lambda reliability and latency insight workflow."
    }
    "aws-wf-rds-insights" = {
      workflow_id = "aws-cockpit-rds-insights"
      description = "Run the AWS RDS capacity and performance insight workflow."
    }
    "aws-wf-elb-insights" = {
      workflow_id = "aws-cockpit-elb-insights"
      description = "Run the AWS ELB target health, error, and latency insight workflow."
    }
    "aws-wf-dynamodb-insights" = {
      workflow_id = "aws-cockpit-dynamodb-insights"
      description = "Run the AWS DynamoDB throttling, error, and latency insight workflow."
    }
    "aws-wf-ecs-insights" = {
      workflow_id = "aws-cockpit-ecs-insights"
      description = "Run the AWS ECS utilization and sizing insight workflow."
    }
    "aws-wf-ebs-insights" = {
      workflow_id = "aws-cockpit-ebs-insights"
      description = "Run the AWS EBS queue depth and burst balance insight workflow."
    }
    "aws-wf-coverage" = {
      workflow_id = "aws-cockpit-coverage"
      description = "Run the AWS cockpit coverage scout workflow."
    }
    "aws-wf-assets" = {
      workflow_id = "aws-cockpit-assets"
      description = "Run the AWS cockpit asset inventory workflow."
    }
    "aws-wf-ml-datafeed-keeper" = {
      workflow_id = "aws-ml-datafeed-keeper"
      description = "Open AWS ML jobs and start their datafeeds once source indices exist."
    }
  } : {}
}

resource "elasticstack_kibana_agentbuilder_tool" "aws_workflow" {
  for_each = local.aws_workflow_tool_specs

  tool_id     = each.key
  type        = "workflow"
  description = each.value.description
  tags        = ["aws", "cockpit", "workflow", "recommendations"]
  space_id    = "default"
  configuration = jsonencode({
    workflow_id = each.value.workflow_id
  })

  kibana_connection {
    endpoints = [module.observability.kibana_endpoint]
    username  = module.observability.username
    password  = module.observability.password
  }

  depends_on = [module.workflows]
}
