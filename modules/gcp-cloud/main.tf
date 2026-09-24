data "google_project" "current" {
  project_id = var.project_id
}

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  suffix = random_id.suffix.hex
  labels = merge({ project = "elastic-cloud-poc", managed-by = "terraform" }, var.labels)
  sa_id  = substr(lower(replace("${var.name_prefix}-collector-${local.suffix}", "_", "-")), 0, 30)

  topics = {
    audit    = { filter = var.audit_filter }
    firewall = { filter = var.firewall_filter }
    vpcflow  = { filter = var.vpcflow_filter }
    dns      = { filter = var.dns_filter }
    lb       = { filter = var.lb_filter }
  }
}

resource "google_service_account" "elastic" {
  account_id   = local.sa_id
  display_name = "Elastic Cloud PoC collector"
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

resource "google_service_account_key" "elastic" {
  service_account_id = google_service_account.elastic.name
}

resource "google_pubsub_topic" "logs" {
  for_each = local.topics

  name    = "${var.name_prefix}-${each.key}-${local.suffix}"
  project = var.project_id
  labels  = merge(local.labels, { "elastic-log" = each.key })
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
  labels  = local.labels
}
