output "dashboard_id" {
  value = elasticstack_kibana_dashboard.cockpit.dashboard_id
}

output "title" {
  value = elasticstack_kibana_dashboard.cockpit.title
}

output "dashboard_url" {
  value = "${trimsuffix(var.kibana_endpoint, "/")}/app/dashboards#/view/${elasticstack_kibana_dashboard.cockpit.dashboard_id}"
}
