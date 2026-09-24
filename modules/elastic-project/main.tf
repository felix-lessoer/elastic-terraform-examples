locals {
  is_serverless = var.deployment_mode == "serverless"
  is_hosted     = var.deployment_mode == "hosted"

  product_types = [
    for line in var.product_lines : {
      product_line = line
      product_tier = var.product_tier
    }
  ]
}

# -----------------------------------------------------------------------------
# Serverless Security project (default)
# -----------------------------------------------------------------------------

resource "ec_security_project" "this" {
  count = local.is_serverless ? 1 : 0

  name          = var.name
  region_id     = var.region
  product_types = local.product_types

  metadata = length(var.tags) > 0 ? { tags = var.tags } : null

  linked = length(var.linked_projects) > 0 ? {
    projects = {
      for id, cfg in var.linked_projects : id => {
        type = cfg.type
      }
    }
  } : null
}

# -----------------------------------------------------------------------------
# Hosted deployment fallback
# -----------------------------------------------------------------------------

data "ec_stack" "latest" {
  count = local.is_hosted && var.elastic_version == "latest" ? 1 : 0

  version_regex = "latest"
  region        = var.region
}

resource "ec_deployment" "this" {
  count = local.is_hosted ? 1 : 0

  name                   = var.name
  region                 = var.region
  version                = var.elastic_version == "latest" ? data.ec_stack.latest[0].version : var.elastic_version
  deployment_template_id = var.deployment_template_id

  elasticsearch = {
    hot = {
      autoscaling = {}
    }

    remote_cluster = [
      for remote in var.remote_clusters : {
        deployment_id = remote.id
        alias         = remote.alias
      }
    ]
  }

  kibana              = {}
  integrations_server = {}
}
