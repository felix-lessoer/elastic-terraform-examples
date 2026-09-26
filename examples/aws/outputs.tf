output "kibana_url" {
  description = "Elastic Serverless Observability Kibana URL."
  value       = module.observability.kibana_endpoint
}

output "project_id" {
  description = "Elastic Serverless Observability project ID."
  value       = module.observability.id
}

output "cloud_id" {
  value = module.observability.cloud_id
}

output "username" {
  value = module.observability.username
}

output "password" {
  sensitive = true
  value     = module.observability.password
}

output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "aws_managed_collector_role_arn" {
  description = "AWS role assumed by the Elastic-managed collector."
  value       = aws_iam_role.elastic_managed.arn
}

output "managed_integration_ids" {
  description = "Elastic-managed AWS integration policies."
  value       = module.stack.managed_integration_ids
}

output "regional_security_agent_regions" {
  description = "AWS regions reconciled on the shared EC2 Agent for GuardDuty, Security Hub, Inspector, and Config."
  value       = sort(keys(data.external.enabled_regions.result))
}

output "agent_policy_id" {
  description = "Fleet policy containing only non-managed AWS integrations."
  value       = module.stack.agent_policy_id
}

output "elastic_agent_instance_id" {
  value = module.elastic_agent.instance_id
}

output "elastic_agent_public_ip" {
  value = module.elastic_agent.public_ip
}

output "aws_logs_bucket" {
  value = module.aws_cloud.logs_bucket_name
}

output "cockpit_dashboard_url" {
  description = "Pinned AWS Observability cockpit dashboard."
  value       = try(module.cockpit[0].dashboard_url, null)
}

output "workflow_ids" {
  description = "Pinned Kibana workflows deployed to the Observability project."
  value       = try(module.workflows[0].workflow_ids, [])
}

output "enabled_datasets" {
  description = "AWS observability datasets enabled through managed and EC2 collectors."
  value = sort(distinct(concat(flatten([
    for input in values(local.managed_inputs) : keys(input.streams)
    ]), flatten([
    for input in values(local.agent_inputs) : keys(input.streams)
    ]),
    length(data.external.guardduty_detectors.result) > 0 ? ["aws.guardduty"] : [],
    length(data.external.enabled_regions.result) > 0 ? [
      "aws.config",
      "aws.inspector",
      "aws.securityhub_findings",
      "aws.securityhub_findings_full_posture",
      "aws.securityhub_insights",
    ] : []
  )))
}

output "applied_tags" {
  value = var.company_tags
}

output "next_steps" {
  value = <<-EOT
    Kibana: ${module.observability.kibana_endpoint}
    - Fleet > Managed integrations: confirm all aws-managed-*-all-regions policies are Healthy
    - Fleet > Agents: confirm ${module.elastic_agent.instance_name} is Healthy
    - Infrastructure > Inventory: inspect AWS hosts and services
    - Dashboards: open the AWS integration dashboards
    - Cockpit dashboard: ${try(module.cockpit[0].dashboard_url, "(disabled)")}
    - Workflows: ${join(", ", try(module.workflows[0].workflow_ids, []))}
    - Discover: filter data_stream.dataset by aws.*
  EOT
}
