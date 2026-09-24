locals {
  deploy_aws   = var.deploy_aws
  deploy_azure = var.deploy_azure
  deploy_gcp   = var.deploy_gcp

  # Elastic Cloud metadata tags: lowercase, [a-z0-9_-], key ≤ 32 chars
  elastic_tags = {
    for k, v in var.company_tags :
    substr(regexreplace(regexreplace(lower(k), "[^a-z0-9_-]", "-"), "^[^a-z]+", "x"), 0, 32) =>
    substr(regexreplace(lower(tostring(v)), "[^a-z0-9_-]", "-"), 0, 32)
  }
}

# -----------------------------------------------------------------------------
# Spoke projects (never the CPS/CCS hub) — created first, no cross-links
# -----------------------------------------------------------------------------

module "elastic_aws" {
  source = "../../modules/elastic-project"
  count  = local.deploy_aws && var.cps_hub != "aws" ? 1 : 0

  deployment_mode        = var.deployment_mode
  name                   = var.elastic_aws_project_name
  region                 = var.elastic_aws_region
  product_tier           = var.product_tier
  elastic_version        = var.elastic_version
  deployment_template_id = var.aws_deployment_template_id
  tags                   = local.elastic_tags
}

module "elastic_azure" {
  source = "../../modules/elastic-project"
  count  = local.deploy_azure && var.cps_hub != "azure" ? 1 : 0

  deployment_mode        = var.deployment_mode
  name                   = var.elastic_azure_project_name
  region                 = var.elastic_azure_region
  product_tier           = var.product_tier
  elastic_version        = var.elastic_version
  deployment_template_id = var.azure_deployment_template_id
  tags                   = local.elastic_tags
}

module "elastic_gcp" {
  source = "../../modules/elastic-project"
  count  = local.deploy_gcp && var.cps_hub != "gcp" ? 1 : 0

  deployment_mode        = var.deployment_mode
  name                   = var.elastic_gcp_project_name
  region                 = var.elastic_gcp_region
  product_tier           = var.product_tier
  elastic_version        = var.elastic_version
  deployment_template_id = var.gcp_deployment_template_id
  tags                   = local.elastic_tags
}

# -----------------------------------------------------------------------------
# Hub project with Cross-Project Search (serverless) or CCS remotes (hosted)
# -----------------------------------------------------------------------------

locals {
  hub_linked_projects = var.deployment_mode != "serverless" ? {} : merge(
    local.deploy_aws && var.cps_hub != "aws" ? { (module.elastic_aws[0].id) = { type = "security" } } : {},
    local.deploy_azure && var.cps_hub != "azure" ? { (module.elastic_azure[0].id) = { type = "security" } } : {},
    local.deploy_gcp && var.cps_hub != "gcp" ? { (module.elastic_gcp[0].id) = { type = "security" } } : {}
  )

  hub_remote_clusters = var.deployment_mode != "hosted" ? [] : concat(
    local.deploy_aws && var.cps_hub != "aws" ? [{ id = module.elastic_aws[0].id, alias = "aws-data" }] : [],
    local.deploy_azure && var.cps_hub != "azure" ? [{ id = module.elastic_azure[0].id, alias = "azure-data" }] : [],
    local.deploy_gcp && var.cps_hub != "gcp" ? [{ id = module.elastic_gcp[0].id, alias = "gcp-data" }] : []
  )
}

module "elastic_hub_aws" {
  source = "../../modules/elastic-project"
  count  = local.deploy_aws && var.cps_hub == "aws" ? 1 : 0

  deployment_mode        = var.deployment_mode
  name                   = var.elastic_aws_project_name
  region                 = var.elastic_aws_region
  product_tier           = var.product_tier
  elastic_version        = var.elastic_version
  deployment_template_id = var.aws_deployment_template_id
  linked_projects        = local.hub_linked_projects
  remote_clusters        = local.hub_remote_clusters
  tags                   = local.elastic_tags

  depends_on = [module.elastic_azure, module.elastic_gcp]
}

module "elastic_hub_azure" {
  source = "../../modules/elastic-project"
  count  = local.deploy_azure && var.cps_hub == "azure" ? 1 : 0

  deployment_mode        = var.deployment_mode
  name                   = var.elastic_azure_project_name
  region                 = var.elastic_azure_region
  product_tier           = var.product_tier
  elastic_version        = var.elastic_version
  deployment_template_id = var.azure_deployment_template_id
  linked_projects        = local.hub_linked_projects
  remote_clusters        = local.hub_remote_clusters
  tags                   = local.elastic_tags

  depends_on = [module.elastic_aws, module.elastic_gcp]
}

module "elastic_hub_gcp" {
  source = "../../modules/elastic-project"
  count  = local.deploy_gcp && var.cps_hub == "gcp" ? 1 : 0

  deployment_mode        = var.deployment_mode
  name                   = var.elastic_gcp_project_name
  region                 = var.elastic_gcp_region
  product_tier           = var.product_tier
  elastic_version        = var.elastic_version
  deployment_template_id = var.gcp_deployment_template_id
  linked_projects        = local.hub_linked_projects
  remote_clusters        = local.hub_remote_clusters
  tags                   = local.elastic_tags

  depends_on = [module.elastic_aws, module.elastic_azure]
}

locals {
  elastic_aws = local.deploy_aws ? (
    var.cps_hub == "aws" ? module.elastic_hub_aws[0] : module.elastic_aws[0]
  ) : null

  elastic_azure = local.deploy_azure ? (
    var.cps_hub == "azure" ? module.elastic_hub_azure[0] : module.elastic_azure[0]
  ) : null

  elastic_gcp = local.deploy_gcp ? (
    var.cps_hub == "gcp" ? module.elastic_hub_gcp[0] : module.elastic_gcp[0]
  ) : null

  hub = (
    var.cps_hub == "aws" ? local.elastic_aws : (
      var.cps_hub == "azure" ? local.elastic_azure : local.elastic_gcp
    )
  )
}
