output "deployment_mode" {
  value = var.deployment_mode
}

output "project_kind" {
  value = var.project_kind
}

output "id" {
  description = "Project or deployment id."
  value = local.is_hosted ? ec_deployment.this[0].id : (
    local.is_security ? ec_security_project.this[0].id : ec_observability_project.this[0].id
  )
}

output "name" {
  value = var.name
}

output "cloud_id" {
  value = local.is_hosted ? ec_deployment.this[0].elasticsearch.cloud_id : (
    local.is_security ? ec_security_project.this[0].cloud_id : ec_observability_project.this[0].cloud_id
  )
}

output "kibana_endpoint" {
  value = local.is_hosted ? ec_deployment.this[0].kibana.https_endpoint : (
    local.is_security ? ec_security_project.this[0].endpoints.kibana : ec_observability_project.this[0].endpoints.kibana
  )
}

output "elasticsearch_endpoint" {
  value = local.is_hosted ? ec_deployment.this[0].elasticsearch.https_endpoint : (
    local.is_security ? ec_security_project.this[0].endpoints.elasticsearch : ec_observability_project.this[0].endpoints.elasticsearch
  )
}

output "username" {
  value = local.is_hosted ? ec_deployment.this[0].elasticsearch_username : (
    local.is_security ? ec_security_project.this[0].credentials.username : ec_observability_project.this[0].credentials.username
  )
}

output "password" {
  sensitive = true
  value = local.is_hosted ? ec_deployment.this[0].elasticsearch_password : (
    local.is_security ? ec_security_project.this[0].credentials.password : ec_observability_project.this[0].credentials.password
  )
}

output "project_type" {
  description = "Serverless project type string for CPS linking (security|observability)."
  value       = local.is_serverless ? var.project_kind : null
}

output "fleet_endpoint" {
  description = "Fleet Server URL for Elastic Agent enrollment."
  value       = local.is_serverless ? local.serverless_fleet_url : local.hosted_fleet_url
}

output "linked_statuses" {
  description = "CPS link statuses keyed by project id (serverless only)."
  value = local.is_serverless ? (
    local.is_security ? try(ec_security_project.this[0].linked.statuses, {}) : try(ec_observability_project.this[0].linked.statuses, {})
  ) : {}
}
