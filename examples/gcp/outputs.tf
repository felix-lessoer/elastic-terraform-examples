output "kibana_url" {
  description = "Security project Kibana (Fleet, CSPM, detection rules)."
  value       = module.elastic.kibana_endpoint
}

output "project_id" {
  description = "Security project id."
  value       = module.elastic.id
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
  description = "Cross-Project Search link statuses from the Observability hub."
  value       = try(module.observability[0].linked_statuses, {})
}

output "ai_agent_ids" {
  value = try(module.observability_seed[0].ai_agent_ids, [])
}

output "ml_job_ids" {
  value = try(module.observability_seed[0].ml_job_ids, [])
}

output "gcp_project_id" {
  value = module.gcp_cloud.project_id
}

output "pubsub_topics" {
  value = module.gcp_cloud.topic_names
}

output "applied_labels" {
  value = module.gcp_cloud.applied_labels
}

output "fleet_agent_policy_id" {
  description = "Security Fleet agent policy id."
  value       = module.stack.agent_policy_id
}

output "observability_fleet_agent_policy_id" {
  description = "Observability Fleet agent policy id."
  value       = try(module.stack_obs[0].agent_policy_id, null)
}

output "enrollment_token" {
  sensitive = true
  value     = module.stack.enrollment_token
}

output "fleet_url" {
  value = module.elastic.fleet_endpoint
}

output "observability_fleet_url" {
  value = try(module.observability[0].fleet_endpoint, null)
}

output "elastic_agent_instance" {
  description = "Security Fleet GCE agent instance."
  value       = try(module.elastic_agent[0].instance_name, null)
}

output "elastic_agent_external_ip" {
  value = try(module.elastic_agent[0].external_ip, null)
}

output "observability_agent_instance" {
  description = "Observability Fleet GCE agent instance."
  value       = try(module.elastic_agent_obs[0].instance_name, null)
}

output "observability_agent_external_ip" {
  value = try(module.elastic_agent_obs[0].external_ip, null)
}

output "next_steps" {
  value = <<-EOT
    Security Kibana: ${module.elastic.kibana_endpoint}
    - Fleet > Agents: confirm ${try(module.elastic_agent[0].instance_name, "elastic-poc-agent")} is Healthy (audit/firewall + CSPM)
    - Security > Cloud Security Posture for GCP CSPM
    - Security > Rules for Google Cloud detection rules

    Observability Kibana: ${try(module.observability[0].kibana_endpoint, "(disabled)")}
    - Fleet > Agents: confirm ${try(module.elastic_agent_obs[0].instance_name, "elastic-poc-obs-agent")} is Healthy (metrics + vpcflow/dns/lb)
    - Cockpit dashboard: ${try(module.cockpit[0].dashboard_url, "(pending)")}
    - Agent Builder: gcp-security-analyst, gcp-obs-triage
    - ML jobs: gcp-event-rate, gcp-cspm-findings-rate
  EOT
}
