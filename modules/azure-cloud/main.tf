data "azurerm_client_config" "current" {}
data "azurerm_subscription" "current" {}

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  suffix = random_id.suffix.hex
  common_tags = merge(
    {
      Project   = "elastic-cloud-poc"
      ManagedBy = "terraform"
    },
    var.company_tags,
    var.additional_tags
  )
  # Storage account names: 3-24 lowercase alphanumeric
  storage_name = substr(lower(replace("${var.name_prefix}${local.suffix}", "-", "")), 0, 24)
  eh_ns_name   = substr(lower("${var.name_prefix}-eh-${local.suffix}"), 0, 50)

  missing_required_keys = [
    for key in var.required_tag_keys : key
    if !contains(keys(var.company_tags), key)
  ]
}

check "required_company_tags" {
  assert {
    condition     = length(local.missing_required_keys) == 0
    error_message = "company_tags is missing required keys: ${join(", ", local.missing_required_keys)}"
  }
}

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_eventhub_namespace" "elastic" {
  name                = local.eh_ns_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"
  capacity            = 1
  tags                = local.common_tags
}

resource "azurerm_eventhub" "elastic" {
  name              = "azure-logs-to-elastic"
  namespace_id      = azurerm_eventhub_namespace.elastic.id
  partition_count   = 2
  message_retention = 1
}

resource "azurerm_eventhub_authorization_rule" "listen" {
  name                = "elastic-listen"
  namespace_name      = azurerm_eventhub_namespace.elastic.name
  eventhub_name       = azurerm_eventhub.elastic.name
  resource_group_name = azurerm_resource_group.main.name
  listen              = true
  send                = false
  manage              = false
}

resource "azurerm_eventhub_authorization_rule" "send" {
  name                = "elastic-send"
  namespace_name      = azurerm_eventhub_namespace.elastic.name
  eventhub_name       = azurerm_eventhub.elastic.name
  resource_group_name = azurerm_resource_group.main.name
  listen              = false
  send                = true
  manage              = false
}

resource "azurerm_storage_account" "elastic" {
  name                     = local.storage_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = local.common_tags
}

resource "azurerm_monitor_diagnostic_setting" "subscription" {
  name                           = "AllLogsToElastic"
  target_resource_id             = data.azurerm_subscription.current.id
  eventhub_name                  = azurerm_eventhub.elastic.name
  eventhub_authorization_rule_id = azurerm_eventhub_authorization_rule.send.id

  enabled_log { category = "Administrative" }
  enabled_log { category = "Security" }
  enabled_log { category = "ServiceHealth" }
  enabled_log { category = "Alert" }
  enabled_log { category = "Recommendation" }
  enabled_log { category = "Policy" }
  enabled_log { category = "Autoscale" }
  enabled_log { category = "ResourceHealth" }
}

# App registration / SP for Elastic Azure integrations (metrics + Event Hub)
resource "azuread_application" "elastic" {
  display_name = "${var.name_prefix}-elastic-collector"
}

resource "azuread_service_principal" "elastic" {
  client_id = azuread_application.elastic.client_id
}

resource "azuread_application_password" "elastic" {
  application_id = azuread_application.elastic.id
}

resource "azurerm_role_assignment" "reader" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Reader"
  principal_id         = azuread_service_principal.elastic.object_id
}

resource "azurerm_role_assignment" "monitoring_reader" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Monitoring Reader"
  principal_id         = azuread_service_principal.elastic.object_id
}

resource "azurerm_role_assignment" "billing_reader" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Billing Reader"
  principal_id         = azuread_service_principal.elastic.object_id
}

resource "azurerm_role_assignment" "eventhub_data_receiver" {
  scope                = azurerm_eventhub.elastic.id
  role_definition_name = "Azure Event Hubs Data Receiver"
  principal_id         = azuread_service_principal.elastic.object_id
}

# Shared VNet for dual Elastic Agent VMs (Security + Observability Fleet).
resource "azurerm_virtual_network" "agents" {
  count               = var.enable_agent_network ? 1 : 0
  name                = "${var.name_prefix}-agents-vnet"
  address_space       = [var.agent_vnet_cidr]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_subnet" "agents" {
  count                = var.enable_agent_network ? 1 : 0
  name                 = "agents"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.agents[0].name
  address_prefixes     = [var.agent_subnet_cidr]
}
