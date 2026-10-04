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
  description = "Pub/Sub topics selected for each stream, including customer-owned topics."
  value       = local.topic_names
}

output "subscription_names" {
  description = "Pub/Sub subscriptions selected for each stream, including customer-owned subscriptions."
  value       = local.subscription_names
}

output "sink_names" {
  description = "Logging sinks selected for each stream, including customer-owned sinks."
  value       = local.sink_names
}

output "collection_ownership" {
  description = "Whether each selected collection resource is managed by this module or attached as customer-owned."
  value = {
    for key in keys(local.topics) : key => {
      topic        = contains(keys(var.existing_topic_names), key) ? "customer" : "module"
      sink         = contains(keys(var.existing_sink_names), key) ? "customer" : "module"
      subscription = contains(keys(var.existing_subscription_names), key) ? "customer" : "module"
    }
  }
}

output "applied_labels" {
  description = "Normalized labels applied to GCP resources."
  value       = local.base_labels
}

