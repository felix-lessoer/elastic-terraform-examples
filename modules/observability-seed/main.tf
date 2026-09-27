locals {
  kibana_url = trimsuffix(var.kibana_endpoint, "/")
  es_url     = trimsuffix(var.elasticsearch_endpoint, "/")

  # CSPM findings are ingested into the Security project; run that ML job there when credentials are provided.
  cspm_es_url = var.security_elasticsearch_endpoint != "" ? trimsuffix(var.security_elasticsearch_endpoint, "/") : local.es_url
  cspm_es_username = var.security_elasticsearch_username != "" ? var.security_elasticsearch_username : var.elasticsearch_username
  cspm_es_password = var.security_elasticsearch_password != "" ? var.security_elasticsearch_password : var.elasticsearch_password
  cspm_on_security = var.security_elasticsearch_endpoint != ""

  cloud      = var.cloud_slug
  cloud_name = var.cloud_display_name

  insight_prefix        = "${local.cloud}-cockpit"
  insight_tools_enabled = var.enable_ai_agents
  kb_user               = var.elasticsearch_username
  kb_pass               = var.elasticsearch_password
}

# -----------------------------------------------------------------------------
# Observability alerting (aggregated signal for the cockpit)
# -----------------------------------------------------------------------------

resource "elasticstack_kibana_alerting_rule" "log_rate_spike" {
  count = var.enable_observability_alerts ? 1 : 0

  name         = "${local.cloud_name} telemetry volume drop"
  consumer     = "alerts"
  rule_type_id = ".index-threshold"
  interval     = "5m"
  enabled      = true
  tags         = ["cockpit", local.cloud, "observability", "Missing Elastic Cloud API Key"]
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
  tags         = ["cockpit", local.cloud, "security-signal", "Missing Elastic Cloud API Key"]
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
# Machine learning — anomaly detection on cloud telemetry rate
# -----------------------------------------------------------------------------

resource "elasticstack_elasticsearch_ml_anomaly_detection_job" "gcp_event_rate" {
  count = var.enable_ml_jobs ? 1 : 0

  job_id      = "${local.cloud}-event-rate"
  description = "Detect unusual drops/spikes in ${local.cloud_name} observe-and-protect telemetry volume"
  groups      = [local.cloud, "cockpit"]

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

  datafeed_id = "datafeed-${local.cloud}-event-rate"
  job_id      = elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate[0].job_id
  indices     = ["logs-*", "metrics-*"]

  # Greenfield projects have no logs/metrics until agents enroll; allow empty start.
  indices_options = {
    allow_no_indices   = true
    ignore_unavailable = true
    expand_wildcards   = ["open"]
  }

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

  job_id      = "${local.cloud}-cspm-findings-rate"
  description = "Unusual rate of CSPM findings documents"
  groups      = [local.cloud, "cockpit", "cspm"]

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
    endpoints = [local.cspm_es_url]
    username  = local.cspm_es_username
    password  = local.cspm_es_password
  }
}

resource "elasticstack_elasticsearch_ml_datafeed" "gcp_cspm_findings_rate" {
  count = var.enable_ml_jobs ? 1 : 0

  datafeed_id = "datafeed-${local.cloud}-cspm-findings-rate"
  job_id      = elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_cspm_findings_rate[0].job_id
  # CSPM findings may lag; scores land first. Wildcard + allow_no_indices lets the
  # datafeed start before findings indices exist.
  indices = ["logs-cloud_security_posture.*"]

  indices_options = {
    allow_no_indices   = true
    ignore_unavailable = true
    expand_wildcards   = ["open"]
  }

  query = jsonencode({
    bool = {
      filter = [
        { range = { "@timestamp" = { gte = "now-7d" } } }
      ]
    }
  })

  elasticsearch_connection {
    endpoints = [local.cspm_es_url]
    username  = local.cspm_es_username
    password  = local.cspm_es_password
  }

  depends_on = [elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_cspm_findings_rate]
}

# -----------------------------------------------------------------------------
# Start ML jobs + datafeeds after create (open job, then start datafeed)
# -----------------------------------------------------------------------------

resource "elasticstack_elasticsearch_ml_job_state" "gcp_event_rate" {
  count = var.enable_ml_jobs ? 1 : 0

  job_id      = elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate[0].job_id
  state       = "opened"
  job_timeout = "5m"

  timeouts = {
    create = "10m"
    update = "10m"
  }

  elasticsearch_connection {
    endpoints = [local.es_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }

  depends_on = [
    elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate,
    elasticstack_elasticsearch_ml_datafeed.gcp_event_rate,
  ]
}

resource "elasticstack_elasticsearch_ml_datafeed_state" "gcp_event_rate" {
  count = var.enable_ml_jobs ? 1 : 0

  datafeed_id = elasticstack_elasticsearch_ml_datafeed.gcp_event_rate[0].datafeed_id
  # Omit start/end so the datafeed runs real-time (avoids provider start-alignment drift).
  state = "started"

  timeouts = {
    create = "10m"
    update = "10m"
  }

  elasticsearch_connection {
    endpoints = [local.es_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }

  depends_on = [elasticstack_elasticsearch_ml_job_state.gcp_event_rate]
}

resource "elasticstack_elasticsearch_ml_job_state" "gcp_cspm_findings_rate" {
  count = var.enable_ml_jobs ? 1 : 0

  job_id      = elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_cspm_findings_rate[0].job_id
  state       = "opened"
  job_timeout = "5m"

  timeouts = {
    create = "10m"
    update = "10m"
  }

  elasticsearch_connection {
    endpoints = [local.cspm_es_url]
    username  = local.cspm_es_username
    password  = local.cspm_es_password
  }

  depends_on = [
    elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_cspm_findings_rate,
    elasticstack_elasticsearch_ml_datafeed.gcp_cspm_findings_rate,
  ]
}

resource "elasticstack_elasticsearch_ml_datafeed_state" "gcp_cspm_findings_rate" {
  count = var.enable_ml_jobs ? 1 : 0

  datafeed_id = elasticstack_elasticsearch_ml_datafeed.gcp_cspm_findings_rate[0].datafeed_id
  state       = "started"

  timeouts = {
    create = "10m"
    update = "10m"
  }

  elasticsearch_connection {
    endpoints = [local.cspm_es_url]
    username  = local.cspm_es_username
    password  = local.cspm_es_password
  }

  depends_on = [elasticstack_elasticsearch_ml_job_state.gcp_cspm_findings_rate]
}

# -----------------------------------------------------------------------------
# Agent Builder — tools over the cockpit insight fabric indices
# (seeded by modules/cockpit-dashboard/scripts/seed_*_insight_indices.py)
# -----------------------------------------------------------------------------

resource "elasticstack_kibana_agentbuilder_tool" "insight_security_kpi" {
  count = local.insight_tools_enabled ? 1 : 0

  tool_id     = "${local.cloud}-insight-security-kpi"
  type        = "index_search"
  description = "Search ${local.cloud_name} cockpit security KPI summary (${local.insight_prefix}-security-kpi)."
  tags        = [local.cloud, "cockpit", "insight", "security"]
  space_id    = var.space_id
  configuration = jsonencode({
    pattern = "${local.insight_prefix}-security-kpi*"
  })

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = local.kb_user
    password  = local.kb_pass
  }
}

resource "elasticstack_kibana_agentbuilder_tool" "insight_coverage" {
  count = local.insight_tools_enabled ? 1 : 0

  tool_id     = "${local.cloud}-insight-coverage"
  type        = "index_search"
  description = "Search ${local.cloud_name} telemetry coverage matrix (${local.insight_prefix}-coverage)."
  tags        = [local.cloud, "cockpit", "insight", "coverage"]
  space_id    = var.space_id
  configuration = jsonencode({
    pattern = "${local.insight_prefix}-coverage*"
  })

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = local.kb_user
    password  = local.kb_pass
  }
}

resource "elasticstack_kibana_agentbuilder_tool" "insight_assets" {
  count = local.insight_tools_enabled ? 1 : 0

  tool_id     = "${local.cloud}-insight-assets"
  type        = "index_search"
  description = "Search ${local.cloud_name} asset inventory (${local.insight_prefix}-assets)."
  tags        = [local.cloud, "cockpit", "insight", "assets"]
  space_id    = var.space_id
  configuration = jsonencode({
    pattern = "${local.insight_prefix}-assets*"
  })

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = local.kb_user
    password  = local.kb_pass
  }
}

resource "elasticstack_kibana_agentbuilder_tool" "insight_events" {
  count = local.insight_tools_enabled ? 1 : 0

  tool_id     = "${local.cloud}-insight-events"
  type        = "index_search"
  description = "Search ${local.cloud_name} cockpit events / timeline (${local.insight_prefix}-events)."
  tags        = [local.cloud, "cockpit", "insight", "events"]
  space_id    = var.space_id
  configuration = jsonencode({
    pattern = "${local.insight_prefix}-events*"
  })

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = local.kb_user
    password  = local.kb_pass
  }
}

resource "elasticstack_kibana_agentbuilder_tool" "insight_recommendations" {
  count = local.insight_tools_enabled ? 1 : 0

  tool_id     = "${local.cloud}-insight-recommendations"
  type        = "index_search"
  description = "Search ${local.cloud_name} cost/performance recommendations (${local.insight_prefix}-recommendations)."
  tags        = [local.cloud, "cockpit", "insight", "recommendations"]
  space_id    = var.space_id
  configuration = jsonencode({
    pattern = "${local.insight_prefix}-recommendations*"
  })

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = local.kb_user
    password  = local.kb_pass
  }
}

resource "elasticstack_kibana_agentbuilder_tool" "insight_recs_esql" {
  count = local.insight_tools_enabled ? 1 : 0

  tool_id     = "${local.cloud}-insight-recs-esql"
  type        = "esql"
  description = "Aggregate open ${local.cloud_name} recommendations by severity and category."
  tags        = [local.cloud, "cockpit", "insight", "recommendations", "esql"]
  space_id    = var.space_id
  configuration = jsonencode({
    query  = "FROM ${local.insight_prefix}-recommendations | STATS count = COUNT(*) BY severity, category | SORT count DESC | LIMIT 25"
    params = {}
  })

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = local.kb_user
    password  = local.kb_pass
  }
}

locals {
  insight_tool_ids = local.insight_tools_enabled ? compact([
    try(elasticstack_kibana_agentbuilder_tool.insight_security_kpi[0].tool_id, null),
    try(elasticstack_kibana_agentbuilder_tool.insight_coverage[0].tool_id, null),
    try(elasticstack_kibana_agentbuilder_tool.insight_assets[0].tool_id, null),
    try(elasticstack_kibana_agentbuilder_tool.insight_events[0].tool_id, null),
    try(elasticstack_kibana_agentbuilder_tool.insight_recommendations[0].tool_id, null),
    try(elasticstack_kibana_agentbuilder_tool.insight_recs_esql[0].tool_id, null),
  ]) : []

  agent_tool_ids = distinct(concat(local.insight_tool_ids, var.additional_tool_ids))
}

# -----------------------------------------------------------------------------
# Agent Builder — AI agents for triage + recommendations
# -----------------------------------------------------------------------------

resource "elasticstack_kibana_agentbuilder_agent" "security_analyst" {
  count = var.enable_ai_agents ? 1 : 0

  agent_id      = "${local.cloud}-security-analyst"
  name          = "${local.cloud_name} Security Analyst"
  description   = "Triages CSPM findings, Security Hub/GuardDuty posture, and detection alerts using the cockpit insight fabric."
  space_id      = var.space_id
  labels        = [local.cloud, "security", "cockpit", "insight"]
  avatar_color  = "#0B64DD"
  avatar_symbol = "S"
  tools         = local.agent_tool_ids

  instructions = <<-EOT
    You are an Elastic Security analyst for a ${local.cloud_name} observe-and-protect PoC.
    Prefer the cockpit insight indices over raw dumps:
    - ${local.insight_prefix}-security-kpi for rolling security KPIs
    - ${local.insight_prefix}-coverage for dataset / service health
    - ${local.insight_prefix}-events for Health / CloudTrail / finding highlights
    - ${local.insight_prefix}-recommendations when cost or posture actions overlap security
    Summarize: (1) open alerts and severity mix, (2) failed CSPM by resource type,
    (3) GuardDuty / Security Hub posture, (4) concrete next actions with Discover deep-links when present.
    Use Cross-Project Search when Security data lives in the linked Security project.
  EOT

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }

  depends_on = [
    elasticstack_kibana_agentbuilder_tool.insight_security_kpi,
    elasticstack_kibana_agentbuilder_tool.insight_coverage,
    elasticstack_kibana_agentbuilder_tool.insight_assets,
    elasticstack_kibana_agentbuilder_tool.insight_events,
    elasticstack_kibana_agentbuilder_tool.insight_recommendations,
    elasticstack_kibana_agentbuilder_tool.insight_recs_esql,
  ]
}

resource "elasticstack_kibana_agentbuilder_agent" "obs_triage" {
  count = var.enable_ai_agents ? 1 : 0

  agent_id      = "${local.cloud}-obs-triage"
  name          = "${local.cloud_name} Observability Triage"
  description   = "Explains telemetry gaps, coverage holes, alert bursts, and ML anomalies for ${local.cloud_name} pipelines."
  space_id      = var.space_id
  labels        = [local.cloud, "observability", "cockpit", "insight"]
  avatar_color  = "#48EFCF"
  avatar_symbol = "O"
  tools         = local.agent_tool_ids

  instructions = <<-EOT
    You are an Elastic Observability triage assistant for ${local.cloud_name}.
    Use the insight fabric first:
    - ${local.insight_prefix}-coverage for which services/datasets are healthy vs empty
    - ${local.insight_prefix}-assets for EC2/S3 (or equivalent) inventory context
    - ${local.insight_prefix}-events for recent Health / pipeline highlights
    Focus on whether configured pipelines are delivering data, which observability alerts fired,
    and ML job health. Give a cockpit-style briefing with the top gaps and what to fix next.
  EOT

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }

  depends_on = [
    elasticstack_kibana_agentbuilder_tool.insight_security_kpi,
    elasticstack_kibana_agentbuilder_tool.insight_coverage,
    elasticstack_kibana_agentbuilder_tool.insight_assets,
    elasticstack_kibana_agentbuilder_tool.insight_events,
    elasticstack_kibana_agentbuilder_tool.insight_recommendations,
    elasticstack_kibana_agentbuilder_tool.insight_recs_esql,
  ]
}

resource "elasticstack_kibana_agentbuilder_agent" "recs_advisor" {
  count = var.enable_ai_agents ? 1 : 0

  agent_id      = "${local.cloud}-recs-advisor"
  name          = "${local.cloud_name} Recommendations Advisor"
  description   = "Prioritizes cost and performance recommendations from the cockpit insight engine."
  space_id      = var.space_id
  labels        = [local.cloud, "recommendations", "cockpit", "insight"]
  avatar_color  = "#F04E98"
  avatar_symbol = "R"
  tools         = local.agent_tool_ids

  instructions = <<-EOT
    You are a ${local.cloud_name} FinOps / performance advisor for the Observe & Protect cockpit.
    Primary data: ${local.insight_prefix}-recommendations (and the recs ES|QL tool for aggregates).
    Cross-check ${local.insight_prefix}-assets and ${local.insight_prefix}-coverage when a recommendation
    needs inventory or telemetry context. Rank by severity/impact, group by category (cost vs performance),
    and return a short action list owners can execute. Prefer counts and top resources over raw docs.
  EOT

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }

  depends_on = [
    elasticstack_kibana_agentbuilder_tool.insight_security_kpi,
    elasticstack_kibana_agentbuilder_tool.insight_coverage,
    elasticstack_kibana_agentbuilder_tool.insight_assets,
    elasticstack_kibana_agentbuilder_tool.insight_events,
    elasticstack_kibana_agentbuilder_tool.insight_recommendations,
    elasticstack_kibana_agentbuilder_tool.insight_recs_esql,
  ]
}
