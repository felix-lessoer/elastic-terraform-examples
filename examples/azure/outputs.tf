output "kibana_url" {
  value = module.elastic.kibana_endpoint
}

output "project_id" {
  value = module.elastic.id
}

output "cloud_id" {
  value = module.elastic.cloud_id
}

output "password" {
  sensitive = true
  value     = module.elastic.password
}

output "username" {
  value = module.elastic.username
}

output "eventhub_name" {
  value = module.azure_cloud.eventhub_name
}

output "fleet_agent_policy_id" {
  value = module.stack.agent_policy_id
}

output "enrollment_token" {
  sensitive = true
  value     = module.stack.enrollment_token
}

output "next_steps" {
  value = <<-EOT
    Open Kibana: ${module.elastic.kibana_endpoint}
    - Security > Cloud Security Posture for Azure CSPM
    - Discover for azure.* data streams
    - Security > Rules for Azure detection rules
  EOT
}
