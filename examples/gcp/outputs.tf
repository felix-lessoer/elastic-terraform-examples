output "kibana_url" {
  value = module.elastic.kibana_endpoint
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
  value = module.stack.agent_policy_id
}

output "enrollment_token" {
  sensitive = true
  value     = module.stack.enrollment_token
}

output "fleet_url" {
  value = module.elastic.fleet_endpoint
}

output "elastic_agent_instance" {
  value = try(module.elastic_agent[0].instance_name, null)
}

output "elastic_agent_external_ip" {
  value = try(module.elastic_agent[0].external_ip, null)
}

output "next_steps" {
  value = <<-EOT
    Open Kibana: ${module.elastic.kibana_endpoint}
    - Fleet > Agents: confirm ${try(module.elastic_agent[0].instance_name, "elastic-agent")} is Healthy on policy gcp-observe-protect
    - Security > Cloud Security Posture for GCP CSPM
    - Discover for gcp.* data streams from Pub/Sub sinks
    - Security > Rules for Google Cloud detection rules
  EOT
}
