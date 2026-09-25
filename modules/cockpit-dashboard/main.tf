locals {
  kibana_url   = trimsuffix(var.kibana_endpoint, "/")
  dashboard_id = "c51727b1-226a-4955-9cb2-fcd59f950d55"
}

# Source of truth: NDJSON export of the live Kibana cockpit dashboard.
# Chart panels must be type "lens" (not "vis") so Saved Objects import
# restores a working dashboard on greenfield applies.
# To refresh after UI edits:
#   1. Export from Kibana Saved Objects, or POST /api/saved_objects/_export
#      with objects=[{type:dashboard,id:<id>}], includeReferencesDeep=true,
#      excludeExportDetails=true
#   2. Replace cockpit.ndjson with the export
#   3. terraform apply
resource "elasticstack_kibana_import_saved_objects" "cockpit" {
  space_id      = var.space_id
  overwrite     = true
  file_contents = file("${path.module}/cockpit.ndjson")

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}
