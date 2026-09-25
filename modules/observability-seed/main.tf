locals {
  kibana_url = trimsuffix(var.kibana_endpoint, "/")
  es_url     = trimsuffix(var.elasticsearch_endpoint, "/")
}

# -----------------------------------------------------------------------------
# Observability alerting (aggregated signal for the cockpit)
# -----------------------------------------------------------------------------

resource "elasticstack_kibana_alerting_rule" "log_rate_spike" {
  count = var.enable_observability_alerts ? 1 : 0

  name         = "GCP telemetry volume drop"
  consumer     = "alerts"
  rule_type_id = ".index-threshold"
  interval     = "5m"
  enabled      = true
  tags         = ["cockpit", "gcp", "observability", "Missing Elastic Cloud API Key"]
  space_id     = var.space_id

  params = jsonencode({
    index               = ["logs-*", "metrics-*"]
    timeField           = "@timestamp"
    aggType             = "count"
    groupBy             = "all"
    termSize            = 5
    thresholdComparator = "<"
    threshold           = [1]
    timeWindowSize      = 30
    timeWindowUnit      = "m"
  })

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

resource "elasticstack_kibana_alerting_rule" "cspm_failed_findings" {
  count = var.enable_observability_alerts ? 1 : 0

  name         = "CSPM findings activity"
  consumer     = "alerts"
  rule_type_id = ".index-threshold"
  interval     = "15m"
  enabled      = true
  tags         = ["cockpit", "gcp", "security-signal", "Missing Elastic Cloud API Key"]
  space_id     = var.space_id

  params = jsonencode({
    index               = ["logs-cloud_security_posture.findings-*", "*:logs-cloud_security_posture.findings-*"]
    timeField           = "@timestamp"
    aggType             = "count"
    groupBy             = "all"
    termSize            = 5
    thresholdComparator = ">"
    threshold           = [0]
    timeWindowSize      = 1
    timeWindowUnit      = "h"
  })

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

# -----------------------------------------------------------------------------
# Machine learning — anomaly detection on GCP telemetry rate
# -----------------------------------------------------------------------------

resource "elasticstack_elasticsearch_ml_anomaly_detection_job" "gcp_event_rate" {
  count = var.enable_ml_jobs ? 1 : 0

  job_id      = "gcp-event-rate"
  description = "Detect unusual drops/spikes in GCP observe-and-protect telemetry volume"
  groups      = ["gcp", "cockpit"]

  analysis_config = {
    bucket_span = "15m"
    detectors = [
      {
        function             = "count"
        detector_description = "event_rate"
      }
    ]
  }

  data_description = {
    time_field  = "@timestamp"
    time_format = "epoch_ms"
  }

  allow_lazy_open = true

  elasticsearch_connection {
    endpoints = [local.es_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

resource "elasticstack_elasticsearch_ml_datafeed" "gcp_event_rate" {
  count = var.enable_ml_jobs ? 1 : 0

  datafeed_id = "datafeed-gcp-event-rate"
  job_id      = elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate[0].job_id
  indices     = ["logs-*", "metrics-*"]

  query = jsonencode({
    bool = {
      filter = [
        { range = { "@timestamp" = { gte = "now-7d" } } }
      ]
    }
  })

  elasticsearch_connection {
    endpoints = [local.es_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }

  depends_on = [elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate]
}

resource "elasticstack_elasticsearch_ml_anomaly_detection_job" "gcp_cspm_findings_rate" {
  count = var.enable_ml_jobs ? 1 : 0

  job_id      = "gcp-cspm-findings-rate"
  description = "Unusual rate of CSPM findings documents"
  groups      = ["gcp", "cockpit", "cspm"]

  analysis_config = {
    bucket_span = "30m"
    detectors = [
      {
        function             = "count"
        detector_description = "findings_rate"
      }
    ]
  }

  data_description = {
    time_field  = "@timestamp"
    time_format = "epoch_ms"
  }

  allow_lazy_open = true

  elasticsearch_connection {
    endpoints = [local.es_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

# -----------------------------------------------------------------------------
# Agent Builder — AI agents for triage
# -----------------------------------------------------------------------------

resource "elasticstack_kibana_agentbuilder_agent" "security_analyst" {
  count = var.enable_ai_agents ? 1 : 0

  agent_id      = "gcp-security-analyst"
  name          = "GCP Security Analyst"
  description   = "Triages CSPM findings and Security detection alerts across CPS-linked projects."
  space_id      = var.space_id
  labels        = ["gcp", "security", "cockpit"]
  avatar_color  = "#0B64DD"
  avatar_symbol = "S"

  instructions = <<-EOT
    You are an Elastic Security analyst for a GCP observe-and-protect PoC.
    Prefer aggregated posture over raw documents. Summarize:
    1) open security alerts and severity mix,
    2) failed CSPM findings by resource type,
    3) recommended next actions.
    Use Cross-Project Search context when Security data lives in the linked Security project.
  EOT

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}

resource "elasticstack_kibana_agentbuilder_agent" "obs_triage" {
  count = var.enable_ai_agents ? 1 : 0

  agent_id      = "gcp-obs-triage"
  name          = "GCP Observability Triage"
  description   = "Explains telemetry gaps, alert bursts, and ML anomalies for GCP pipelines."
  space_id      = var.space_id
  labels        = ["gcp", "observability", "cockpit"]
  avatar_color  = "#48EFCF"
  avatar_symbol = "O"

  instructions = <<-EOT
    You are an Elastic Observability triage assistant for GCP.
    Focus on whether configured pipelines (audit, firewall, vpcflow, dns, lb, metrics, CSPM) are delivering data,
    which observability alerts fired, and ML job health. Give a cockpit-style briefing, not raw event dumps.
  EOT

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}
