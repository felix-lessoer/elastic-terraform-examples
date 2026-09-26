output "workflow_ids" {
  description = "Deployed workflow ids (stable filenames)."
  value       = [for w in elasticstack_kibana_agentbuilder_workflow.this : w.workflow_id]
}

output "workflows" {
  description = "Deployed workflow inventory."
  value = [
    for w in elasticstack_kibana_agentbuilder_workflow.this : {
      id          = w.workflow_id
      name        = w.name
      description = w.description
      enabled     = w.enabled
      valid       = w.valid
    }
  ]
}
