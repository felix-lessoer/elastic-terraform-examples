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
  elasticsearch {
    autoscale = "true"

    dynamic "remote_cluster" {
      for_each = var.elastic_remotes
      content {
        deployment_id = remote_cluster.value["id"]
        alias         = remote_cluster.value["alias"]
      }
    }
  }
  kibana {}
  integrations_server {}
}

output "elastic_cluster_id_aws" {
  value = ec_deployment.elastic_deployment.id
}

output "elastic_cluster_alias_aws" {
  value = ec_deployment.elastic_deployment.name
}

output "elastic_endpoint_aws" {
  value = ec_deployment.elastic_deployment.kibana.https_endpoint
}

output "elastic_cloud_id_aws" {
  value = ec_deployment.elastic_deployment.elasticsearch.cloud_id
}

output "elastic_username_aws" {
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
    elastic_json_body = templatefile("${path.module}/../json_templates/default-policy.json", {"policy_name": "EKS"})
  }
  program = ["sh", "${path.module}/../../lib/elastic_api/kb_create_agent_policy.sh" ]
  depends_on = [ec_deployment.elastic_deployment]
}

# -------------------------------------------------------------
#  Load Rules
# -------------------------------------------------------------

data "external" "elastic_load_rules" {
  query = {
    kibana_endpoint  = ec_deployment.elastic_deployment.kibana.https_endpoint
    elastic_username  = ec_deployment.elastic_deployment.elasticsearch_username
    elastic_password  = ec_deployment.elastic_deployment.elasticsearch_password
  }
  program = ["sh", "${path.module}/../../lib/elastic_api/kb_load_detection_rules.sh" ]
  depends_on = [ec_deployment.elastic_deployment]
}

# data "external" "elastic_enable_rules" {
#   query = {
#     kibana_endpoint  = ec_deployment.elastic_deployment.kibana.https_endpoint
#     elastic_username  = ec_deployment.elastic_deployment.elasticsearch_username
#     elastic_password  = ec_deployment.elastic_deployment.elasticsearch_password
#     elastic_json_body = templatefile("${path.module}/../json_templates/aws_rule_activation.json",{})
#   }
#   program = ["sh", "${path.module}/../../lib/elastic_api/kb_enable_detection_rules.sh" ]
#   depends_on = [data.external.elastic_load_rules]
# }

# output "elastic_enable_aws_rules" {
#   value = data.external.elastic_enable_rules.result
#   depends_on = [
#     data.external.elastic_enable_rules
#   ] 
# }

# -------------------------------------------------------------
#  Create and Start transforms
# -------------------------------------------------------------

# -------------------------------------------------------------
#  Load Dashboards
# -------------------------------------------------------------
