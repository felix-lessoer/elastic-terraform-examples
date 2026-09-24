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
  # Elastic Cloud metadata tags: lowercase, prefer [a-z0-9_-]
  tags = {
    for k, v in var.company_labels :
    substr(lower(replace(replace(replace(replace(k, " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32) =>
    substr(lower(replace(replace(replace(replace(tostring(v), " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32)
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
  # Fleet input keys are "{input_type}-{policy_template}" (e.g. gcp-pubsub-audit).
  # Keep a single object shape so Terraform can type the list.
  gcp_integrations = concat(
    var.enable_cspm ? [
      {
        name                 = "cspm-gcp"
        description          = "Agentless CSPM for GCP"
        package_name         = "cloud_security_posture"
        managed              = true
        agent_policy         = false
        prerelease           = false
        package_version      = null
        policy_template      = "cspm"
        vars_json            = jsonencode({ posture = "cspm", deployment = "gcp" })
        var_group_selections = { deployment = "gcp" }
        cloud_connector      = null
        inputs = {
          "cspm-cloudbeat/cis_gcp" = {
            enabled = true
            streams = {
              "cloud_security_posture.findings" = {
                enabled = true
                vars = jsonencode({
                  "gcp.account_type"      = "single-account"
                  "gcp.project_id"        = module.gcp_cloud.project_id
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
        name                 = "gcp-observe"
        description          = "GCP audit/firewall/vpcflow/dns/lb logs + metrics via Pub/Sub"
        package_name         = "gcp"
        managed              = false
        agent_policy         = true
        prerelease           = false
        package_version      = null
        policy_template      = null
        vars_json = jsonencode({
          project_id       = module.gcp_cloud.project_id
          credentials_json = module.gcp_cloud.credentials_json
        })
        var_group_selections = {}
        cloud_connector      = null
        inputs = {
          "gcp-pubsub-audit" = {
            enabled = true
            streams = {
              "gcp.audit" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud.topic_names["audit"] })
              }
            }
          }
          "gcp-pubsub-firewall" = {
            enabled = true
            streams = {
              "gcp.firewall" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud.topic_names["firewall"] })
              }
            }
          }
          "gcp-pubsub-vpcflow" = {
            enabled = true
            streams = {
              "gcp.vpcflow" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud.topic_names["vpcflow"] })
              }
            }
          }
          "gcp-pubsub-dns" = {
            enabled = true
            streams = {
              "gcp.dns" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud.topic_names["dns"] })
              }
            }
          }
          "gcp-pubsub-loadbalancing" = {
            enabled = true
            streams = {
              "gcp.loadbalancing_logs" = {
                enabled = true
                vars    = jsonencode({ topic = module.gcp_cloud.topic_names["lb"] })
              }
            }
          }
          "gcp/metrics-compute" = {
            enabled = true
            streams = {
              "gcp.compute" = {
                enabled = true
                vars    = jsonencode({ period = "5m" })
              }
            }
          }
          "gcp/metrics-loadbalancing" = {
            enabled = true
            streams = {
              "gcp.loadbalancing_metrics" = {
                enabled = true
                vars    = jsonencode({ period = "5m" })
              }
            }
          }
          "gcp/metrics-storage" = {
            enabled = true
            streams = {
              "gcp.storage" = {
                enabled = true
                vars    = jsonencode({ period = "15m" })
              }
            }
          }
          "gcp/metrics-billing" = {
            enabled = var.enable_billing_metrics
            streams = {
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
