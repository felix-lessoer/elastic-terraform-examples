output "kibana_url" {
  value = module.elastic.kibana_endpoint
}

output "project_id" {
  value = module.elastic.id
}

output "cloud_id" {
  value = module.elastic.cloud_id
}

output "elasticsearch_endpoint" {
  value = module.elastic.elasticsearch_endpoint
}

output "username" {
  value = module.elastic.username
}

output "password" {
  sensitive = true
  value     = module.elastic.password
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

output "next_steps" {
  value = <<-EOT
    Open Kibana: ${module.elastic.kibana_endpoint}
    - Security > Cloud Security Posture for CSPM findings
    - Discover / Dashboards for AWS integrations
    - Security > Rules for enabled AWS detection rules
  EOT
}
