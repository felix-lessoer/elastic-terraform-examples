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

output "eventhub_name" {
  value = module.azure_cloud.eventhub_name
}

output "azure_subscription_id" {
  value = module.azure_cloud.subscription_id
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
  value = module.azure_cloud.applied_tags
}

output "next_steps" {
  value = <<-EOT
    Security Kibana: ${module.elastic.kibana_endpoint}
    - Fleet > Agents: confirm ${try(module.elastic_agent[0].instance_name, "elastic-poc-agent")} is Healthy (activity/platform logs)
    - Security > Cloud Security Posture for agentless CSPM
    - Discover: logs-azure.activitylogs-*, logs-azure.platformlogs-*
    - Security > Rules for Azure detection rules

    Observability Kibana: ${try(module.observability[0].kibana_endpoint, "(disabled)")}
    - Fleet > Agents: confirm ${try(module.elastic_agent_obs[0].instance_name, "elastic-poc-obs-agent")} is Healthy (metrics + billing)
    - Discover: metrics-azure.compute_vm-*, metrics-azure.storage_account-*, metrics-azure.billing-*
    - Cockpit dashboard: ${try(module.cockpit[0].dashboard_url, "(pending)")}
    - Agent Builder: azure-security-analyst, azure-obs-triage
    - ML jobs: azure-event-rate, azure-cspm-findings-rate
    - Workflows: ${join(", ", distinct(concat(try(module.workflows_obs[0].workflow_ids, []), try(module.workflows_security[0].workflow_ids, []))))}
  EOT
}
