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
}

check "required_company_labels" {
  assert {
    condition     = length(local.missing_required_keys) == 0
    error_message = "company_labels is missing required keys: ${join(", ", local.missing_required_keys)}"
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

resource "google_project_iam_member" "pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
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

resource "google_pubsub_topic" "logs" {
  for_each = local.topics

  name    = "${var.name_prefix}-${each.key}-${local.suffix}"
  project = var.project_id
  labels  = merge(local.base_labels, { "elastic-log" = each.key })
}

resource "google_logging_project_sink" "logs" {
  for_each = local.topics

  name                   = "${var.name_prefix}-${each.key}-${local.suffix}"
  project                = var.project_id
  destination            = "pubsub.googleapis.com/${google_pubsub_topic.logs[each.key].id}"
  filter                 = each.value.filter
  unique_writer_identity = true

  depends_on = [google_pubsub_topic.logs]
}

resource "google_pubsub_topic_iam_member" "sink_writer" {
  for_each = local.topics

  project = var.project_id
  topic   = google_pubsub_topic.logs[each.key].name
  role    = "roles/pubsub.publisher"
  member  = google_logging_project_sink.logs[each.key].writer_identity
}

resource "google_pubsub_subscription" "logs" {
  for_each = local.topics

  name    = "${var.name_prefix}-${each.key}-sub-${local.suffix}"
  project = var.project_id
  topic   = google_pubsub_topic.logs[each.key].name
  labels  = local.base_labels
}
