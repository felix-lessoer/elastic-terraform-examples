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

output "pubsub_subscriptions" {
  value = module.gcp_cloud.subscription_names
}

output "logging_sinks" {
  value = module.gcp_cloud.sink_names
}

output "collection_ownership" {
  description = "Whether each collection path is Terraform-managed or attached as customer-owned."
  value       = module.gcp_cloud.collection_ownership
}

output "discovery_manifest_sha256" {
  description = "Hash of the local brownfield manifest; the manifest itself is not stored in Terraform state."
  value       = var.gcp_discovery_manifest_path == "" ? null : filesha256(var.gcp_discovery_manifest_path)
}

output "discovery_summary" {
  description = "Non-sensitive resource/error counts from the local brownfield manifest."
  value       = var.gcp_discovery_manifest_path == "" ? null : try(jsondecode(file(var.gcp_discovery_manifest_path)).summary, null)
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

output "workflow_ids" {
  description = "Pinned Kibana workflow ids deployed to Observability (and Security when enabled)."
  value = distinct(concat(
    try(module.workflows_obs[0].workflow_ids, []),
    try(module.workflow_summary_obs[0].workflow_ids, []),
    try(module.workflows_security[0].workflow_ids, []),
  ))
}

output "workflow_telemetry_status" {
  description = "Required Fleet inputs and whether each GCP workflow is eligible to deploy."
  value = {
    for workflow_id, requirements in local.gcp_workflow_telemetry_requirements :
    workflow_id => {
      required_inputs = requirements
      enabled = alltrue([
        for requirement in requirements :
        lookup(local.gcp_metric_input_enabled, requirement, false)
      ])
      status = alltrue([
        for requirement in requirements :
        lookup(local.gcp_metric_input_enabled, requirement, false)
      ]) ? "enabled" : "skipped_missing_telemetry"
    }
  }
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
    - Workflows: ${join(", ", distinct(concat(try(module.workflows_obs[0].workflow_ids, []), try(module.workflow_summary_obs[0].workflow_ids, []), try(module.workflows_security[0].workflow_ids, []))))}
    - Workflow telemetry eligibility: inspect output workflow_telemetry_status
  EOT
}
