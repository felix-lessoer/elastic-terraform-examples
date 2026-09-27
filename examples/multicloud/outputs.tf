output "hub_kibana_url" {
  value = try(local.hub.kibana_endpoint, null)
}

output "hub_project_id" {
  value = try(local.hub.id, null)
}

output "cps_hub" {
  value = var.cps_hub
}

output "aws" {
  sensitive = true
  value = local.deploy_aws ? {
    project_id   = local.elastic_aws.id
    kibana_url   = local.elastic_aws.kibana_endpoint
    cloud_id     = local.elastic_aws.cloud_id
    username     = local.elastic_aws.username
    password     = local.elastic_aws.password
    role_arn     = module.aws_cloud[0].elastic_role_arn
    logs_bucket  = module.aws_cloud[0].logs_bucket_name
    agent_policy = module.stack_aws[0].agent_policy_id
  } : null
}

output "azure" {
  sensitive = true
  value = local.deploy_azure ? {
    project_id   = local.elastic_azure.id
    kibana_url   = local.elastic_azure.kibana_endpoint
    cloud_id     = local.elastic_azure.cloud_id
    username     = local.elastic_azure.username
    password     = local.elastic_azure.password
    eventhub     = module.azure_cloud[0].eventhub_name
    agent_policy = module.stack_azure[0].agent_policy_id
  } : null
}

output "gcp" {
  sensitive = true
  value = local.deploy_gcp ? {
    project_id   = local.elastic_gcp.id
    kibana_url   = local.elastic_gcp.kibana_endpoint
    cloud_id     = local.elastic_gcp.cloud_id
    username     = local.elastic_gcp.username
    password     = local.elastic_gcp.password
    topics       = module.gcp_cloud[0].topic_names
    agent_policy = module.stack_gcp[0].agent_policy_id
  } : null
}

output "next_steps" {
  value = <<-EOT
    Hub Kibana (${var.cps_hub}): ${try(local.hub.kibana_endpoint, "n/a")}
    Mode: ${var.deployment_mode}
    Cross-project search / CCS is configured on the hub toward the other enabled clouds.
    Enroll an Elastic Agent into each cloud's Fleet policy to start log pipelines that are not yet agentless.
  EOT
}
