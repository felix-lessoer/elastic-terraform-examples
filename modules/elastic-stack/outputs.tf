output "agent_policy_id" {
  value = elasticstack_fleet_agent_policy.cloud.policy_id
}

output "enrollment_token" {
  sensitive = true
  value = try(
    [for t in data.elasticstack_fleet_enrollment_tokens.cloud.tokens : t.api_key if t.active][0],
    null
  )
}

output "fleet_integration_policy_ids" {
  value = { for k, v in elasticstack_fleet_integration_policy.agent : k => v.id }
}

output "managed_integration_ids" {
  value = { for k, v in elasticstack_fleet_managed_integration.this : k => v.id }
}

output "rules_installed" {
  value = try(elasticstack_kibana_install_prebuilt_rules.this[0].rules_installed, 0)
}
