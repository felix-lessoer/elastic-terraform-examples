# Project number is optional — many collector SAs lack resourcemanager.projects.get.
data "google_project" "current" {
  count      = var.fetch_project_number ? 1 : 0
  project_id = var.project_id
}

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  suffix = random_id.suffix.hex
  sa_id  = substr(lower(replace("${var.name_prefix}-collector-${local.suffix}", "_", "-")), 0, 30)

  # Normalize labels with replace()/lower() (no regexreplace — not available in all Terraform builds).
  # Prefer already-valid GCP labels: lowercase [a-z0-9_-], key starts with a letter.
  raw_labels = merge(var.company_labels, var.additional_labels)
  normalize = {
    for k, v in local.raw_labels :
    substr(lower(replace(replace(replace(replace(k, " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 63) =>
    substr(lower(replace(replace(replace(replace(tostring(v), " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 63)
  }

  base_labels = merge(
    {
      "managed-by" = "terraform"
      "stack"      = "elastic-cloud-poc"
    },
    local.normalize
  )

  required_normalized = [
    for key in var.required_label_keys :
    substr(lower(replace(replace(replace(replace(key, " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 63)
  ]

  missing_required_keys = [
    for key in local.required_normalized : key
    if !contains(keys(local.normalize), key)
  ]

  topics = {
    audit    = { filter = var.audit_filter }
    firewall = { filter = var.firewall_filter }
    vpcflow  = { filter = var.vpcflow_filter }
    dns      = { filter = var.dns_filter }
    lb       = { filter = var.lb_filter }
  }

  managed_topics = {
    for key, value in local.topics : key => value
    if !contains(keys(var.existing_topic_names), key)
  }
  managed_sinks = {
    for key, value in local.topics : key => value
    if !contains(keys(var.existing_sink_names), key)
  }
  managed_subscriptions = {
    for key, value in local.topics : key => value
    if !contains(keys(var.existing_subscription_names), key)
  }

  topic_names = merge(
    { for key, topic in google_pubsub_topic.logs : key => topic.name },
    { for key, topic in data.google_pubsub_topic.existing : key => topic.name }
  )
  topic_ids = merge(
    { for key, topic in google_pubsub_topic.logs : key => topic.id },
    { for key, topic in data.google_pubsub_topic.existing : key => topic.id }
  )
  sink_names = merge(
    { for key, sink in google_logging_project_sink.logs : key => sink.name },
    { for key, sink in data.google_logging_sink.existing : key => sink.name }
  )
  subscription_names = merge(
    { for key, subscription in google_pubsub_subscription.logs : key => subscription.name },
    { for key, subscription in data.google_pubsub_subscription.existing : key => subscription.name }
  )
  subscription_access = merge(
    { for key, subscription in google_pubsub_subscription.logs : key => subscription.name },
    var.grant_existing_subscription_access ? {
      for key, subscription in data.google_pubsub_subscription.existing : key => subscription.name
    } : {}
  )
}

check "required_company_labels" {
  assert {
    condition     = length(local.missing_required_keys) == 0
    error_message = "company_labels is missing required keys: ${join(", ", local.missing_required_keys)}"
  }
}

check "existing_path_dependencies" {
  assert {
    condition = alltrue([
      for key in setunion(
        toset(keys(var.existing_sink_names)),
        toset(keys(var.existing_subscription_names))
      ) : contains(keys(var.existing_topic_names), key)
    ])
    error_message = "Every reused sink or subscription requires an existing_topic_names entry for the same stream key."
  }
}

check "existing_path_uniqueness" {
  assert {
    condition = (
      length(distinct(values(var.existing_topic_names))) == length(var.existing_topic_names) &&
      length(distinct(values(var.existing_sink_names))) == length(var.existing_sink_names) &&
      length(distinct(values(var.existing_subscription_names))) == length(var.existing_subscription_names)
    )
    error_message = "One existing topic, sink, or subscription cannot be assigned to multiple stream keys."
  }
}

resource "google_service_account" "elastic" {
  account_id   = local.sa_id
  display_name = "Elastic Cloud PoC collector"
  description  = "Collector SA for Elastic observe-and-protect PoC"
  project      = var.project_id
}

resource "google_project_iam_member" "viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.elastic.email}"
}

resource "google_project_iam_member" "monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.elastic.email}"
}

# Extra read roles commonly required for agentless GCP CSPM (CIS) asset inventory.
resource "google_project_iam_member" "cloudasset_viewer" {
  project = var.project_id
  role    = "roles/cloudasset.viewer"
  member  = "serviceAccount:${google_service_account.elastic.email}"
}

resource "google_project_iam_member" "iam_security_reviewer" {
  project = var.project_id
  role    = "roles/iam.securityReviewer"
  member  = "serviceAccount:${google_service_account.elastic.email}"
}

resource "google_service_account_key" "elastic" {
  service_account_id = google_service_account.elastic.name
}

data "google_pubsub_topic" "existing" {
  for_each = var.existing_topic_names

  name    = each.value
  project = var.project_id
}

data "google_logging_sink" "existing" {
  for_each = var.existing_sink_names

  id = "projects/${var.project_id}/sinks/${each.value}"
}

data "google_pubsub_subscription" "existing" {
  for_each = var.existing_subscription_names

  name    = each.value
  project = var.project_id
}

resource "google_pubsub_topic" "logs" {
  for_each = local.managed_topics

  name    = "${var.name_prefix}-${each.key}-${local.suffix}"
  project = var.project_id
  labels  = merge(local.base_labels, { "elastic-log" = each.key })
}

resource "google_logging_project_sink" "logs" {
  for_each = local.managed_sinks

  name                   = "${var.name_prefix}-${each.key}-${local.suffix}"
  project                = var.project_id
  destination            = "pubsub.googleapis.com/${local.topic_ids[each.key]}"
  filter                 = each.value.filter
  unique_writer_identity = true

  depends_on = [google_pubsub_topic.logs, data.google_pubsub_topic.existing]
}

resource "google_pubsub_topic_iam_member" "sink_writer" {
  for_each = local.managed_sinks

  project = var.project_id
  topic   = local.topic_names[each.key]
  role    = "roles/pubsub.publisher"
  member  = google_logging_project_sink.logs[each.key].writer_identity
}

resource "google_pubsub_subscription" "logs" {
  for_each = local.managed_subscriptions

  name    = "${var.name_prefix}-${each.key}-sub-${local.suffix}"
  project = var.project_id
  topic   = local.topic_names[each.key]
  labels  = local.base_labels
}

resource "google_pubsub_subscription_iam_member" "collector" {
  for_each = local.subscription_access

  project      = var.project_id
  subscription = each.value
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.elastic.email}"
}

check "existing_sink_destinations" {
  assert {
    condition = alltrue([
      for key, sink in data.google_logging_sink.existing :
      !contains(keys(var.existing_topic_names), key) ||
      sink.destination == "pubsub.googleapis.com/${local.topic_ids[key]}"
    ])
    error_message = "A reused Logging sink destination does not match its reused Pub/Sub topic."
  }
}

check "existing_subscription_topics" {
  assert {
    condition = alltrue([
      for key, subscription in data.google_pubsub_subscription.existing :
      !contains(keys(var.existing_topic_names), key) ||
      subscription.topic == local.topic_ids[key]
    ])
    error_message = "A reused Pub/Sub subscription does not consume from its reused topic."
  }
}
