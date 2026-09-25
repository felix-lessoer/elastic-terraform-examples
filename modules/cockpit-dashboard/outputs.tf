output "dashboard_id" {
  value = local.dashboard_id
}

output "title" {
  value = var.title
}

output "dashboard_url" {
  value = "${local.kibana_url}/app/dashboards#/view/${local.dashboard_id}"
}

output "import_success" {
  value = elasticstack_kibana_import_saved_objects.cockpit.success
}

output "import_success_count" {
  value = elasticstack_kibana_import_saved_objects.cockpit.success_count
}
