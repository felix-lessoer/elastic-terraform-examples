# -------------------------------------------------------------
#  Deploy Elastic Cloud
# -------------------------------------------------------------
data "ec_stack" "latest" {
  version_regex = "latest"
  region        = var.elastic_region
}

resource "ec_deployment" "elastic_deployment" {
  name                    = var.elastic_deployment_name
  region                  = var.elastic_region
  version                 = var.elastic_version == "latest" ? data.ec_stack.latest.version : var.elastic_version
  deployment_template_id  = var.elastic_deployment_template_id
  elasticsearch = {
    hot = {
      autoscaling = {}
    }
  }
  kibana = {}
  integrations_server = {}
}

output "elastic_cluster_id" {
  value = ec_deployment.elastic_deployment.id
}

output "elastic_cluster_alias" {
  value = ec_deployment.elastic_deployment.name
}

output "elastic_endpoint" {
  value = ec_deployment.elastic_deployment.kibana.https_endpoint
}

output "elastic_cloud_id" {
  value = ec_deployment.elastic_deployment.elasticsearch.cloud_id
}

output "elastic_username" {
  value = ec_deployment.elastic_deployment.elasticsearch_username
}

output "elastic_password" {
  value = ec_deployment.elastic_deployment.elasticsearch_password
  sensitive = true
}


# -------------------------------------------------------------
#  Load Policy
# -------------------------------------------------------------

data "external" "elastic_create_policy" {
  query = {
    kibana_endpoint  = ec_deployment.elastic_deployment.kibana.https_endpoint
    elastic_username  = ec_deployment.elastic_deployment.elasticsearch_username
    elastic_password  = ec_deployment.elastic_deployment.elasticsearch_password
    elastic_json_body = templatefile("${path.module}/../json_templates/default-policy.json", {"policy_name": "AWS"})
  }
  program = ["sh", "${path.module}/../../lib/elastic_api/kb_create_agent_policy.sh" ]
  depends_on = [ec_deployment.elastic_deployment]
}
