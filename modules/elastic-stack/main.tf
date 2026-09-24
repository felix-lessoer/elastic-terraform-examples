locals {
  kibana_url = trimsuffix(var.kibana_endpoint, "/")
  es_url     = trimsuffix(var.elasticsearch_endpoint, "/")

  agent_integrations = {
    for idx, i in var.integrations : idx => i
    if try(i.agent_policy, true) && !try(i.managed, false)
  }

  managed_integrations = {
    for idx, i in var.integrations : idx => i
    if try(i.managed, false)
  }

  # Unique package names to install (agent-based path)
  packages = {
    for name in distinct([for i in values(local.agent_integrations) : i.package_name]) :
    name => [
      for i in values(local.agent_integrations) : i
      if i.package_name == name
    ][0]
  }
}

# -----------------------------------------------------------------------------
# Fleet agent policy (for agent-based / hybrid collection)
# -----------------------------------------------------------------------------

resource "elasticstack_fleet_agent_policy" "cloud" {
  name            = var.policy_name
  namespace       = var.policy_namespace
  description     = "PoC cloud observe-and-protect agent policy"
  monitor_logs    = true
  monitor_metrics = true
  sys_monitoring  = true
  space_ids       = [var.space_id]

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

data "elasticstack_fleet_enrollment_tokens" "cloud" {
  policy_id = elasticstack_fleet_agent_policy.cloud.policy_id

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }

  depends_on = [elasticstack_fleet_agent_policy.cloud]
}

# -----------------------------------------------------------------------------
# Install packages at latest (or pinned) version
# -----------------------------------------------------------------------------

data "elasticstack_fleet_integration" "latest" {
  for_each = local.packages

  name       = each.key
  prerelease = try(each.value.prerelease, false)

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

resource "elasticstack_fleet_integration" "packages" {
  for_each = local.packages

  name    = each.key
  version = coalesce(try(each.value.package_version, null), data.elasticstack_fleet_integration.latest[each.key].version)
  force   = true

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

# -----------------------------------------------------------------------------
# Agent-based integration policies
# -----------------------------------------------------------------------------

resource "elasticstack_fleet_integration_policy" "agent" {
  for_each = local.agent_integrations

  name                = each.value.name
  namespace           = var.policy_namespace
  description         = coalesce(try(each.value.description, null), "Terraform-managed ${each.value.package_name} integration")
  agent_policy_id     = elasticstack_fleet_agent_policy.cloud.policy_id
  integration_name    = each.value.package_name
  integration_version = elasticstack_fleet_integration.packages[each.value.package_name].version

  inputs = try(each.value.inputs, {})

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }

  depends_on = [elasticstack_fleet_integration.packages]
}

# -----------------------------------------------------------------------------
# Managed / agentless integrations (CSPM, agentless AWS metrics, etc.)
# -----------------------------------------------------------------------------

data "elasticstack_fleet_integration" "managed_latest" {
  for_each = {
    for idx, i in local.managed_integrations : idx => i.package_name
  }

  name       = each.value
  prerelease = try(local.managed_integrations[each.key].prerelease, false)

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

resource "elasticstack_fleet_managed_integration" "this" {
  for_each = local.managed_integrations

  name            = each.value.name
  description     = coalesce(try(each.value.description, null), "Agentless ${each.value.package_name}")
  policy_template = each.value.policy_template

  package = {
    name    = each.value.package_name
    version = coalesce(try(each.value.package_version, null), data.elasticstack_fleet_integration.managed_latest[each.key].version)
  }

  vars_json            = try(each.value.vars_json, null)
  var_group_selections = try(each.value.var_group_selections, {})
  inputs               = try(each.value.inputs, {})

  cloud_connector = try(each.value.cloud_connector, null) != null ? {
    enabled            = each.value.cloud_connector.enabled
    cloud_connector_id = try(each.value.cloud_connector.cloud_connector_id, null)
    name               = try(each.value.cloud_connector.name, null)
    target_csp         = try(each.value.cloud_connector.target_csp, null)
  } : null

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

# -----------------------------------------------------------------------------
# Security detection rules
# -----------------------------------------------------------------------------

resource "elasticstack_kibana_install_prebuilt_rules" "this" {
  count = var.enable_detection_rules ? 1 : 0

  space_id = var.space_id

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

resource "elasticstack_kibana_security_enable_rule" "by_tag" {
  for_each = var.enable_detection_rules ? {
    for t in var.detection_rule_tags : "${t.key}:${t.value}" => t
  } : {}

  space_id           = var.space_id
  key                = each.value.key
  value              = each.value.value
  disable_on_destroy = false

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }

  depends_on = [elasticstack_kibana_install_prebuilt_rules.this]
}
