locals {
  kibana_url   = trimsuffix(var.kibana_endpoint, "/")
  dashboard_id = var.dashboard_id
  ndjson_path  = var.ndjson_path != "" ? var.ndjson_path : "${path.module}/cockpit.ndjson"
}

# Source of truth: NDJSON export of the live Kibana cockpit dashboard.
# Chart panels use type "vis" with embedded Lens attributes (ES|QL textBased).
# To refresh after UI edits:
#   1. Export from Kibana Saved Objects, or POST /api/saved_objects/_export
#      with objects=[{type:dashboard,id:<id>}], includeReferencesDeep=true,
#      excludeExportDetails=true
#   2. Replace the NDJSON file referenced by ndjson_path
#   3. terraform apply
resource "elasticstack_kibana_import_saved_objects" "cockpit" {
  space_id      = var.space_id
  overwrite     = true
  file_contents = file(local.ndjson_path)

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

resource "elasticstack_kibana_import_saved_objects" "additional" {
  for_each = var.additional_ndjson_paths

  space_id      = var.space_id
  overwrite     = true
  file_contents = file(each.value)

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

# Kibana's defaultRoute is a space-scoped Advanced Setting. The provider does
# not expose it directly. Serverless does expose the versioned config object
# through Saved Objects export/import, so round-trip that object to preserve
# every other Advanced Setting while updating only defaultRoute.
resource "terraform_data" "default_route" {
  count = var.set_as_default_route ? 1 : 0

  triggers_replace = [
    var.dashboard_id,
    var.space_id,
    filesha256("${path.module}/scripts/set_kibana_default_route.py"),
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    environment = {
      KIBANA_URL   = local.kibana_url
      KIBANA_USER  = var.elasticsearch_username
      KIBANA_PASS  = var.elasticsearch_password
      DASHBOARD_ID = var.dashboard_id
      SPACE_ID     = var.space_id
    }
    command = <<-EOT
      python3 "${path.module}/scripts/set_kibana_default_route.py" \
        --kibana-url "$KIBANA_URL" \
        --user "$KIBANA_USER" \
        --password "$KIBANA_PASS" \
        --dashboard-id "$DASHBOARD_ID" \
        --space-id "$SPACE_ID"
    EOT
  }

  depends_on = [
    elasticstack_kibana_import_saved_objects.cockpit,
    elasticstack_kibana_import_saved_objects.additional,
  ]
}
