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
  project_kind           = "security"
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

# Observability hub with Cross-Project Search into the Security project.
module "observability" {
  count  = var.enable_observability_project && var.deployment_mode == "serverless" ? 1 : 0
  source = "../../modules/elastic-project"

  deployment_mode = "serverless"
  project_kind    = "observability"
  name            = var.observability_project_name
  region          = var.elastic_region
  product_tier    = var.product_tier
  linked_projects = {
    (module.elastic.id) = { type = "security" }
  }
  tags = {
    for k, v in var.company_labels :
    substr(lower(replace(replace(replace(replace(k, " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32) =>
    substr(lower(replace(replace(replace(replace(tostring(v), " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 32)
  }

  depends_on = [module.elastic]
}

module "observability_seed" {
  count  = length(module.observability) > 0 ? 1 : 0
  source = "../../modules/observability-seed"

  kibana_endpoint               = module.observability[0].kibana_endpoint
  elasticsearch_endpoint        = module.observability[0].elasticsearch_endpoint
  elasticsearch_username        = module.observability[0].username
  elasticsearch_password        = module.observability[0].password
  enable_ml_jobs                = var.enable_ml_jobs
  enable_ai_agents              = var.enable_ai_agents
  enable_observability_alerts   = var.enable_observability_alerts

  depends_on = [module.observability]
}

module "cockpit" {
  count  = length(module.observability) > 0 ? 1 : 0
  source = "../../modules/cockpit-dashboard"

  kibana_endpoint            = module.observability[0].kibana_endpoint
  elasticsearch_username     = module.observability[0].username
  elasticsearch_password     = module.observability[0].password
  security_project_name      = module.elastic.name
  observability_project_name = module.observability[0].name
  ml_jobs                    = try(module.observability_seed[0].ml_jobs, [])
  ai_agents                  = try(module.observability_seed[0].ai_agents, [])

  depends_on = [module.observability, module.observability_seed]
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
  # elasticstack input map keys are "{policy_template}-{input_type}"
  # (e.g. audit-gcp-pubsub). Required stream vars must be set explicitly;
  # the provider does not merge package defaults into the create payload.
  gcp_pubsub_stream = {
    for k, topic in module.gcp_cloud.topic_names : k => {
      topic                   = topic
      subscription_name       = module.gcp_cloud.subscription_names[k]
      subscription_create     = false
      tags                    = ["forwarded", "gcp-${k}"]
      preserve_original_event = false
      keep_json               = false
    }
  }

  # Metrics templates the GCP package enables by default unless declared.
  gcp_extra_metrics_disabled = {
    "firestore-gcp/metrics" = {
      enabled = false
      streams = {
        "gcp.firestore" = {
          enabled = false
          vars    = jsonencode({ period = "10m", tags = ["gcp-firestore"] })
        }
      }
    }
    "gke-gcp/metrics" = {
      enabled = false
      streams = {
        "gcp.gke" = {
          enabled = false
          vars    = jsonencode({ period = "10m", tags = ["gcp-gke"] })
        }
      }
    }
    "dataproc-gcp/metrics" = {
      enabled = false
      streams = {
        "gcp.dataproc" = {
          enabled = false
          vars    = jsonencode({ period = "10m", tags = ["gcp-dataproc"] })
        }
      }
    }
    "pubsub-gcp/metrics" = {
      enabled = false
      streams = {
        "gcp.pubsub" = {
          enabled = false
          vars    = jsonencode({ period = "5m", tags = ["gcp-pubsub"] })
        }
      }
    }
    "redis-gcp/metrics" = {
      enabled = false
      streams = {
        "gcp.redis" = {
          enabled = false
          vars    = jsonencode({ period = "10m", tags = ["gcp-redis"] })
        }
      }
    }
    "cloudrun-gcp/metrics" = {
      enabled = false
      streams = {
        "gcp.cloudrun_metrics" = {
          enabled = false
          vars    = jsonencode({ period = "10m", tags = ["gcp-cloudrun"] })
        }
      }
    }
    "cloudsql-gcp/metrics" = {
      enabled = false
      streams = {
        "gcp.cloudsql_mysql" = {
          enabled = false
          vars    = jsonencode({ period = "10m", tags = ["gcp-cloudsql-mysql"] })
        }
        "gcp.cloudsql_postgresql" = {
          enabled = false
          vars    = jsonencode({ period = "10m", tags = ["gcp-cloudsql-postgresql"] })
        }
        "gcp.cloudsql_sqlserver" = {
          enabled = false
          vars    = jsonencode({ period = "10m", tags = ["gcp-cloudsql-sqlserver"] })
        }
      }
    }
  }

  # Security Fleet: CSPM (agentless) + security-relevant GCP logs (audit, firewall).
  security_integrations = concat(
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
        name                 = "gcp-security"
        description          = "GCP security logs (audit + firewall) via Pub/Sub"
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
        inputs = merge({
          "audit-gcp-pubsub" = {
            enabled = true
            streams = {
              "gcp.audit" = {
                enabled = true
                vars    = jsonencode(merge(local.gcp_pubsub_stream["audit"], { tags = ["forwarded", "gcp-audit"] }))
              }
            }
          }
          "firewall-gcp-pubsub" = {
            enabled = true
            streams = {
              "gcp.firewall" = {
                enabled = true
                vars    = jsonencode(merge(local.gcp_pubsub_stream["firewall"], { tags = ["forwarded", "gcp-firewall"] }))
              }
            }
          }
          # Declared disabled so Fleet package schema stays complete if the UI expects them.
          "vpcflow-gcp-pubsub" = {
            enabled = false
            streams = {
              "gcp.vpcflow" = {
                enabled = false
                vars    = jsonencode(merge(local.gcp_pubsub_stream["vpcflow"], { tags = ["forwarded", "gcp-vpcflow"] }))
              }
            }
          }
          "dns-gcp-pubsub" = {
            enabled = false
            streams = {
              "gcp.dns" = {
                enabled = false
                vars    = jsonencode(merge(local.gcp_pubsub_stream["dns"], { tags = ["forwarded", "gcp-dns"] }))
              }
            }
          }
          "loadbalancing-gcp-pubsub" = {
            enabled = false
            streams = {
              "gcp.loadbalancing_logs" = {
                enabled = false
                vars = jsonencode({
                  topic                   = module.gcp_cloud.topic_names["lb"]
                  subscription_name       = module.gcp_cloud.subscription_names["lb"]
                  subscription_create     = false
                  tags                    = ["forwarded", "gcp-loadbalancing_logs"]
                  preserve_original_event = false
                })
              }
            }
          }
          "compute-gcp/metrics" = {
            enabled = false
            streams = {
              "gcp.compute" = {
                enabled = false
                vars    = jsonencode({ period = "5m", tags = ["gcp-compute"] })
              }
            }
          }
          "loadbalancing-gcp/metrics" = {
            enabled = false
            streams = {
              "gcp.loadbalancing_metrics" = {
                enabled = false
                vars    = jsonencode({ period = "5m", tags = ["gcp-loadbalancing-metrics"] })
              }
            }
          }
          "storage-gcp/metrics" = {
            enabled = false
            streams = {
              "gcp.storage" = {
                enabled = false
                vars    = jsonencode({ period = "15m", tags = ["gcp-storage"] })
              }
            }
          }
          "billing-gcp/metrics" = {
            enabled = false
            streams = {
              "gcp.billing" = {
                enabled = false
                vars = jsonencode({
                  period        = "24h"
                  dataset_id    = "unused"
                  table_pattern = "gcp_billing_export_v1"
                  cost_type     = "regular"
                  tags          = ["gcp-billing"]
                })
              }
            }
          }
        }, local.gcp_extra_metrics_disabled)
      }
    ]
  )

  # Observability Fleet: network/LB logs + platform metrics.
  observability_integrations = [
    {
      name                 = "gcp-observe"
      description          = "GCP observability (vpcflow/dns/lb logs + compute/storage/lb metrics)"
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
        "audit-gcp-pubsub" = {
          enabled = false
          streams = {
            "gcp.audit" = {
              enabled = false
              vars    = jsonencode(merge(local.gcp_pubsub_stream["audit"], { tags = ["forwarded", "gcp-audit"] }))
            }
          }
        }
        "firewall-gcp-pubsub" = {
          enabled = false
          streams = {
            "gcp.firewall" = {
              enabled = false
              vars    = jsonencode(merge(local.gcp_pubsub_stream["firewall"], { tags = ["forwarded", "gcp-firewall"] }))
            }
          }
        }
        "vpcflow-gcp-pubsub" = {
          enabled = true
          streams = {
            "gcp.vpcflow" = {
              enabled = true
              vars    = jsonencode(merge(local.gcp_pubsub_stream["vpcflow"], { tags = ["forwarded", "gcp-vpcflow"] }))
            }
          }
        }
        "dns-gcp-pubsub" = {
          enabled = true
          streams = {
            "gcp.dns" = {
              enabled = true
              vars    = jsonencode(merge(local.gcp_pubsub_stream["dns"], { tags = ["forwarded", "gcp-dns"] }))
            }
          }
        }
        "loadbalancing-gcp-pubsub" = {
          enabled = true
          streams = {
            "gcp.loadbalancing_logs" = {
              enabled = true
              vars = jsonencode({
                topic                   = module.gcp_cloud.topic_names["lb"]
                subscription_name       = module.gcp_cloud.subscription_names["lb"]
                subscription_create     = false
                tags                    = ["forwarded", "gcp-loadbalancing_logs"]
                preserve_original_event = false
              })
            }
          }
        }
        "compute-gcp/metrics" = {
          enabled = true
          streams = {
            "gcp.compute" = {
              enabled = true
              vars    = jsonencode({ period = "5m", tags = ["gcp-compute"] })
            }
          }
        }
        "loadbalancing-gcp/metrics" = {
          enabled = true
          streams = {
            "gcp.loadbalancing_metrics" = {
              enabled = true
              vars    = jsonencode({ period = "5m", tags = ["gcp-loadbalancing-metrics"] })
            }
          }
        }
        "storage-gcp/metrics" = {
          enabled = true
          streams = {
            "gcp.storage" = {
              enabled = true
              vars    = jsonencode({ period = "15m", tags = ["gcp-storage"] })
            }
          }
        }
        "billing-gcp/metrics" = {
          enabled = var.enable_billing_metrics
          streams = {
            "gcp.billing" = {
              enabled = var.enable_billing_metrics
              vars = jsonencode({
                period        = "24h"
                dataset_id    = var.enable_billing_metrics ? var.billing_dataset_id : "unused"
                table_pattern = "gcp_billing_export_v1"
                cost_type     = "regular"
                tags          = ["gcp-billing"]
              })
            }
          }
        }
      }
    }
  ]
}

# Security project Fleet: CSPM + audit/firewall + detection rules + security agent.
module "stack" {
  source = "../../modules/elastic-stack"

  kibana_endpoint        = module.elastic.kibana_endpoint
  elasticsearch_endpoint = module.elastic.elasticsearch_endpoint
  elasticsearch_username = module.elastic.username
  elasticsearch_password = module.elastic.password
  policy_name            = "gcp-observe-protect"
  enable_detection_rules = var.enable_detection_rules
  detection_rule_tags    = var.detection_rule_tags
  integrations           = local.security_integrations

  depends_on = [module.elastic, module.gcp_cloud]
}

# Observability project Fleet: metrics + network/LB logs + observability agent.
module "stack_obs" {
  count  = length(module.observability) > 0 ? 1 : 0
  source = "../../modules/elastic-stack"

  kibana_endpoint        = module.observability[0].kibana_endpoint
  elasticsearch_endpoint = module.observability[0].elasticsearch_endpoint
  elasticsearch_username = module.observability[0].username
  elasticsearch_password = module.observability[0].password
  policy_name            = "gcp-observability"
  enable_detection_rules = false
  integrations           = local.observability_integrations

  depends_on = [module.observability, module.gcp_cloud]
}

module "elastic_agent" {
  count  = var.enable_elastic_agent ? 1 : 0
  source = "../../modules/elastic-agent-gce"

  project_id       = var.google_cloud_project
  name             = "${var.name_prefix}-agent"
  zone             = var.elastic_agent_zone != "" ? var.elastic_agent_zone : "${var.google_cloud_region}-b"
  machine_type     = var.elastic_agent_machine_type
  network          = var.elastic_agent_network
  company_labels   = merge(module.gcp_cloud.applied_labels, { role = "elastic-agent-security" })
  fleet_url        = module.elastic.fleet_endpoint
  enrollment_token = module.stack.enrollment_token
  agent_version    = var.elastic_agent_version

  depends_on = [module.stack]
}

module "elastic_agent_obs" {
  count  = var.enable_elastic_agent && length(module.stack_obs) > 0 ? 1 : 0
  source = "../../modules/elastic-agent-gce"

  project_id       = var.google_cloud_project
  name             = "${var.name_prefix}-obs-agent"
  zone             = var.elastic_agent_zone != "" ? var.elastic_agent_zone : "${var.google_cloud_region}-b"
  machine_type     = var.elastic_agent_machine_type
  network          = var.elastic_agent_network
  company_labels   = merge(module.gcp_cloud.applied_labels, { role = "elastic-agent-observability" })
  fleet_url        = module.observability[0].fleet_endpoint
  enrollment_token = module.stack_obs[0].enrollment_token
  agent_version    = var.elastic_agent_version

  depends_on = [module.stack_obs]
}
