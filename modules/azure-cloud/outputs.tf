output "subscription_id" {
  value = data.azurerm_subscription.current.subscription_id
}

output "tenant_id" {
  value = data.azurerm_client_config.current.tenant_id
}

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "location" {
  value = azurerm_resource_group.main.location
}

output "eventhub_namespace" {
  value = azurerm_eventhub_namespace.elastic.name
}

output "eventhub_name" {
  value = azurerm_eventhub.elastic.name
}

output "eventhub_connection_string" {
  sensitive = true
  value     = azurerm_eventhub_authorization_rule.listen.primary_connection_string
}

output "storage_account_name" {
  value = azurerm_storage_account.elastic.name
}

output "client_id" {
  value = azuread_application.elastic.client_id
}

output "client_secret" {
  sensitive = true
  value     = azuread_application_password.elastic.value
}

output "applied_tags" {
  description = "Tags applied to Azure resources."
  value       = local.common_tags
}

output "agent_subnet_id" {
  description = "Subnet id for Elastic Agent VMs (null when enable_agent_network is false)."
  value       = try(azurerm_subnet.agents[0].id, null)
}

output "agent_vnet_name" {
  value = try(azurerm_virtual_network.agents[0].name, null)
}
