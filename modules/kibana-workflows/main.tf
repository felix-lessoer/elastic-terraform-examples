locals {
  kibana_url = trimsuffix(var.kibana_endpoint, "/")

  workflow_files = merge(
    {
      for f in fileset(var.workflows_dir, "*.yaml") :
      trimsuffix(f, ".yaml") => abspath("${var.workflows_dir}/${f}")
    },
    {
      for f in fileset(var.workflows_dir, "*.yml") :
      trimsuffix(f, ".yml") => abspath("${var.workflows_dir}/${f}")
    },
  )
}

resource "elasticstack_kibana_agentbuilder_workflow" "this" {
  for_each = local.workflow_files

  space_id           = var.space_id
  workflow_id        = each.key
  configuration_yaml = file(each.value)

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

# Greenfield: fire each enabled workflow once after it is created/updated.
resource "terraform_data" "execute" {
  for_each = var.execute_on_apply ? elasticstack_kibana_agentbuilder_workflow.this : {}

  triggers_replace = [
    each.value.workflow_id,
    each.value.configuration_yaml,
    each.value.valid,
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    environment = {
      WF_ID       = each.value.workflow_id
      WF_ENABLED  = tostring(each.value.enabled)
      WF_VALID    = tostring(each.value.valid)
      KIBANA_URL  = local.kibana_url
      KIBANA_USER = var.elasticsearch_username
      KIBANA_PASS = var.elasticsearch_password
    }
    command = "bash '${path.module}/execute-workflow.sh'"
  }

  depends_on = [elasticstack_kibana_agentbuilder_workflow.this]
}
