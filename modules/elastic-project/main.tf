locals {
  is_serverless     = var.deployment_mode == "serverless"
  is_hosted         = var.deployment_mode == "hosted"
  is_security       = var.project_kind == "security"
  is_observability  = var.project_kind == "observability"

  product_types = [
    for line in var.product_lines : {
      product_line = line
      product_tier = var.product_tier
    }
  ]

  # Elastic Cloud region ids look like gcp-europe-west3 / aws-eu-west-1 / azure-westeurope.
  cloud_provider = (
    substr(var.region, 0, 4) == "aws-" ? "aws" :
    substr(var.region, 0, 6) == "azure-" ? "azure" :
    "gcp"
  )
  cloud_region = (
    local.cloud_provider == "aws" ? trimprefix(var.region, "aws-") :
    local.cloud_provider == "azure" ? trimprefix(var.region, "azure-") :
    trimprefix(var.region, "gcp-")
  )

  linked_block = length(var.linked_projects) > 0 ? {
    projects = {
      for id, cfg in var.linked_projects : id => {
        type = cfg.type
      }
    }
  } : null

  serverless_project_id = local.is_serverless ? (
    local.is_security ? ec_security_project.this[0].id : ec_observability_project.this[0].id
  ) : null

  serverless_fleet_url = local.is_serverless ? format(
    "https://%s.fleet.%s.%s.elastic.cloud:443",
    local.serverless_project_id,
    local.cloud_region,
    local.cloud_provider
  ) : null

  hosted_fleet_url = local.is_hosted ? replace(
    ec_deployment.this[0].integrations_server.https_endpoint,
    "apm",
    "fleet"
  ) : null
}

# -----------------------------------------------------------------------------
# Serverless Security project
# -----------------------------------------------------------------------------

resource "ec_security_project" "this" {
  count = local.is_serverless && local.is_security ? 1 : 0

  name          = var.name
  region_id     = var.region
  product_types = local.product_types

  metadata = length(var.tags) > 0 ? { tags = var.tags } : null
  linked   = local.linked_block
}

# -----------------------------------------------------------------------------
# Serverless Observability project
# -----------------------------------------------------------------------------

resource "ec_observability_project" "this" {
  count = local.is_serverless && local.is_observability ? 1 : 0

  name         = var.name
  region_id    = var.region
  product_tier = var.product_tier

  metadata = length(var.tags) > 0 ? { tags = var.tags } : null
  linked   = local.linked_block
}

# -----------------------------------------------------------------------------
# Hosted deployment fallback (security / general purpose only)
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
