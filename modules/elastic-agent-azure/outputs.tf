output "instance_id" {
  value = azurerm_linux_virtual_machine.agent.id
}

output "instance_name" {
  value = azurerm_linux_virtual_machine.agent.name
}

output "private_ip" {
  value = azurerm_network_interface.agent.private_ip_address
}

output "public_ip" {
  value = azurerm_public_ip.agent.ip_address
}

output "network_security_group_id" {
  value = azurerm_network_security_group.agent.id
}
