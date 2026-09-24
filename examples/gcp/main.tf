terraform {
  required_version = ">= 1.2.7"

  required_providers {
    ec = {
      source  = "elastic/ec"
      version = "~> 0.13"
    }
    elasticstack = {
      source  = "elastic/elasticstack"
      version = "~> 0.16"
    }
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5"
    }
  }
}

provider "ec" {}

provider "google" {
  project     = var.google_cloud_project
  region      = var.google_cloud_region
  credentials = var.google_cloud_credentials_file != "" ? file(var.google_cloud_credentials_file) : null
}

provider "elasticstack" {}

module "elastic" {
  source = "../../modules/elastic-project"

  deployment_mode        = var.deployment_mode
  name                   = var.elastic_project_name
  region                 = var.elastic_region
  product_tier           = var.product_tier
  elastic_version        = var.elastic_version
  deployment_template_id = var.deployment_template_id
  # Elastic Cloud metadata tags: lowercase, [a-z0-9_-], key ≤ 32 chars
  tags = {
    for k, v in var.company_labels :
    substr(regexreplace(regexreplace(lower(k), "[^a-z0-9_-]", "-"), "^[^a-z]+", "x"), 0, 32) =>
    substr(regexreplace(lower(tostring(v)), "[^a-z0-9_-]", "-"), 0, 32)
  }
}

module "gcp_cloud" {
  source = "../../modules/gcp-cloud"

  project_id          = var.google_cloud_project
  name_prefix         = var.name_prefix
  region              = var.google_cloud_region
  company_labels      = var.company_labels
  required_label_keys = var.required_label_keys
  additional_labels = {
    cloud = "gcp"
  }
}

locals {
  gcp_integrations = concat(
    var.enable_cspm ? [
      {
        name            = "cspm-gcp"
        description     = "Agentless CSPM for GCP"
        package_name    = "cloud_security_posture"
        managed         = true
        agent_policy    = false
        policy_template = "cspm"
        vars_json = jsonencode({
          posture    = "cspm"
          deployment = "gcp"
        })
        var_group_selections = {
          deployment = "gcp"
        }
        inputs = {
          "cspm-cloudbeat/cis_gcp" = {
            enabled = true
            streams = {
              "cloud_security_posture.findings" = {
                enabled = true
                vars = jsonencode({
                  "gcp.project_id"       = module.gcp_cloud.project_id
                  "gcp.credentials.type" = "credentials-json"
                  "gcp.credentials.json" = module.gcp_cloud.credentials_json
                })
              }
            }
          }
        }
      }
    ] : [],
    [
      {
        name         = "gcp-observe"
        description  = "GCP audit/firewall/vpcflow/dns/lb logs + metrics via Pub/Sub"
        package_name = "gcp"
        managed      = false
        agent_policy = true
        inputs = {
          "gcp-pubsub" = {
            enabled = true
            vars = jsonencode({
              credentials_json = module.gcp_cloud.credentials_json
              project_id       = module.gcp_cloud.project_id
            })
            streams = {
              "gcp.audit" = {
                enabled = true
                vars = jsonencode({
                  topic = module.gcp_cloud.topic_names["audit"]
                })
              }
              "gcp.firewall" = {
                enabled = true
                vars = jsonencode({
                  topic = module.gcp_cloud.topic_names["firewall"]
                })
              }
              "gcp.vpcflow" = {
                enabled = true
                vars = jsonencode({
                  topic = module.gcp_cloud.topic_names["vpcflow"]
                })
              }
              "gcp.dns" = {
                enabled = true
                vars = jsonencode({
                  topic = module.gcp_cloud.topic_names["dns"]
                })
              }
              "gcp.loadbalancing_logs" = {
                enabled = true
                vars = jsonencode({
                  topic = module.gcp_cloud.topic_names["lb"]
                })
              }
            }
          }
          "gcp/metrics" = {
            enabled = true
            vars = jsonencode({
              credentials_json = module.gcp_cloud.credentials_json
              project_id       = module.gcp_cloud.project_id
            })
            streams = {
              "gcp.compute" = {
                enabled = true
                vars    = jsonencode({ period = "5m" })
              }
              "gcp.loadbalancing" = {
                enabled = true
                vars    = jsonencode({ period = "5m" })
              }
              "gcp.storage" = {
                enabled = true
                vars    = jsonencode({ period = "15m" })
              }
              "gcp.billing" = {
                enabled = var.enable_billing_metrics
                vars    = jsonencode({ period = "24h" })
              }
            }
          }
        }
      }
    ]
  )
}

module "stack" {
  source = "../../modules/elastic-stack"

  kibana_endpoint        = module.elastic.kibana_endpoint
  elasticsearch_endpoint = module.elastic.elasticsearch_endpoint
  elasticsearch_username = module.elastic.username
  elasticsearch_password = module.elastic.password
  policy_name            = "gcp-observe-protect"
  enable_detection_rules = var.enable_detection_rules
  detection_rule_tags    = var.detection_rule_tags
  integrations           = local.gcp_integrations

  depends_on = [module.elastic, module.gcp_cloud]
}
