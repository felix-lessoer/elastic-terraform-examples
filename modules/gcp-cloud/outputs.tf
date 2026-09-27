output "project_id" {
  value = var.project_id
}

output "project_number" {
  value = try(data.google_project.current[0].number, null)
}

output "region" {
  value = var.region
}

output "service_account_email" {
  value = google_service_account.elastic.email
}

output "credentials_json" {
  sensitive = true
  value     = base64decode(google_service_account_key.elastic.private_key)
}

output "topic_names" {
  value = { for k, t in google_pubsub_topic.logs : k => t.name }
}

output "subscription_names" {
  value = { for k, s in google_pubsub_subscription.logs : k => s.name }
}

output "applied_labels" {
  description = "Normalized labels applied to GCP resources."
  value       = local.base_labels
}

