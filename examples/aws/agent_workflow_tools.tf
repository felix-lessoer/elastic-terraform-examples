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
    "aws-wf-coverage" = {
      workflow_id = "aws-cockpit-coverage"
      description = "Run the AWS cockpit coverage scout workflow."
    }
    "aws-wf-assets" = {
      workflow_id = "aws-cockpit-assets"
      description = "Run the AWS cockpit asset inventory workflow."
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
