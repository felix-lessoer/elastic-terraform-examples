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
