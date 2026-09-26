output "kibana_url" {
  description = "Security project Kibana (Fleet, CSPM, detection rules)."
  value       = module.elastic.kibana_endpoint
}

output "project_id" {
  value = module.elastic.id
}

output "cloud_id" {
  value = module.elastic.cloud_id
}

output "username" {
  value = module.elastic.username
}

output "password" {
  sensitive = true
  value     = module.elastic.password
}

output "observability_kibana_url" {
  description = "Observability hub Kibana (cockpit dashboard)."
  value       = try(module.observability[0].kibana_endpoint, null)
}

output "observability_project_id" {
  value = try(module.observability[0].id, null)
}

output "observability_password" {
  sensitive = true
  value     = try(module.observability[0].password, null)
}

output "cockpit_dashboard_url" {
  value = try(module.cockpit[0].dashboard_url, null)
}

output "cps_link_statuses" {
  value = try(module.observability[0].linked_statuses, null)
}

output "aws_account_id" {
  value = module.aws_cloud.account_id
}

output "aws_logs_bucket" {
  value = module.aws_cloud.logs_bucket_name
}

output "aws_elastic_role_arn" {
  value = module.aws_cloud.elastic_role_arn
}

output "fleet_agent_policy_id" {
  value = module.stack.agent_policy_id
}

output "enrollment_token" {
  sensitive = true
  value     = module.stack.enrollment_token
}

output "observability_fleet_agent_policy_id" {
  value = try(module.stack_obs[0].agent_policy_id, null)
}

output "elastic_agent_instance" {
  value = try(module.elastic_agent[0].instance_name, null)
}

output "elastic_agent_public_ip" {
  value = try(module.elastic_agent[0].public_ip, null)
}

output "observability_agent_instance" {
  value = try(module.elastic_agent_obs[0].instance_name, null)
}

output "observability_agent_public_ip" {
  value = try(module.elastic_agent_obs[0].public_ip, null)
}

output "ml_job_ids" {
  value = try(module.observability_seed[0].ml_job_ids, [])
}

output "ai_agent_ids" {
  value = try(module.observability_seed[0].ai_agent_ids, [])
}

output "workflow_ids" {
  description = "Pinned Kibana workflow ids deployed to Observability (and Security when enabled)."
  value = distinct(concat(
    try(module.workflows_obs[0].workflow_ids, []),
    try(module.workflows_security[0].workflow_ids, []),
  ))
}

output "applied_tags" {
  value = module.aws_cloud.applied_tags
}

output "next_steps" {
  value = <<-EOT
    Security Kibana: ${module.elastic.kibana_endpoint}
    - Fleet > Agents: confirm ${try(module.elastic_agent[0].instance_name, "elastic-poc-agent")} is Healthy (CloudTrail + Security Hub + GuardDuty + Health)
    - Security > Cloud Security Posture for agentless CSPM / CNVM
    - Discover: logs-aws.securityhub_*, logs-aws.guardduty, metrics-aws.awshealth
    - Security > Rules for AWS detection rules

    Observability Kibana: ${try(module.observability[0].kibana_endpoint, "(disabled)")}
    - Fleet > Agents: confirm ${try(module.elastic_agent_obs[0].instance_name, "elastic-poc-obs-agent")} is Healthy (vpcflow + metrics + Trusted Advisor)
    - Discover: metrics-aws.cloudwatch_metrics (AWS/TrustedAdvisor)
    - Cockpit dashboard: ${try(module.cockpit[0].dashboard_url, "(pending)")}
    - Agent Builder: aws-security-analyst, aws-obs-triage
    - ML jobs: aws-event-rate, aws-cspm-findings-rate
    - Workflows: ${join(", ", distinct(concat(try(module.workflows_obs[0].workflow_ids, []), try(module.workflows_security[0].workflow_ids, []))))}
  EOT
}
