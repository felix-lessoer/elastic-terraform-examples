output "deployment_mode" {
  value = var.deployment_mode
}

output "id" {
  description = "Project or deployment id."
  value       = local.is_serverless ? ec_security_project.this[0].id : ec_deployment.this[0].id
}

output "name" {
  value = var.name
}

output "cloud_id" {
  value = local.is_serverless ? ec_security_project.this[0].cloud_id : ec_deployment.this[0].elasticsearch.cloud_id
}

output "kibana_endpoint" {
  value = local.is_serverless ? ec_security_project.this[0].endpoints.kibana : ec_deployment.this[0].kibana.https_endpoint
}

output "elasticsearch_endpoint" {
  value = local.is_serverless ? ec_security_project.this[0].endpoints.elasticsearch : ec_deployment.this[0].elasticsearch.https_endpoint
}

output "username" {
  value = local.is_serverless ? ec_security_project.this[0].credentials.username : ec_deployment.this[0].elasticsearch_username
}

output "password" {
  sensitive = true
  value     = local.is_serverless ? ec_security_project.this[0].credentials.password : ec_deployment.this[0].elasticsearch_password
}

output "project_type" {
  description = "Serverless project type string for CPS linking (security)."
  value       = local.is_serverless ? "security" : null
}

output "fleet_endpoint" {
  description = "Fleet Server URL for Elastic Agent enrollment."
  value       = local.is_serverless ? local.serverless_fleet_url : local.hosted_fleet_url
}
