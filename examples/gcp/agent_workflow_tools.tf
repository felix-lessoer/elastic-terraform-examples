# Bounded read-only tools for GCP Insight Engine evidence. These fixed ES|QL
# queries cannot mutate state or escape into arbitrary indices.
locals {
  # Deployment code must use these requirements to select workflow files.
  # Keeping the contract next to the tools makes a disabled metric stream
  # impossible to describe as supported without an explicit mapping update.
  gcp_workflow_telemetry_requirements = {
    "gcp-cockpit-host-recommendations"          = ["compute-gcp/metrics"]
    "gcp-cockpit-assets"                        = ["compute-gcp/metrics", "storage-gcp/metrics"]
    "gcp-cockpit-storage-recommendations"       = ["storage-gcp/metrics"]
    "gcp-cockpit-loadbalancing-recommendations" = ["loadbalancing-gcp/metrics"]
    "gcp-cockpit-pubsub-recommendations"        = ["pubsub-gcp/metrics"]
    "gcp-cockpit-gke-recommendations"           = ["gke-gcp/metrics"]
    "gcp-cockpit-cloudrun-recommendations"      = ["cloudrun-gcp/metrics"]
    "gcp-cockpit-cloudsql-recommendations"      = ["cloudsql-gcp/metrics"]
  }

  gcp_metric_input_enabled = {
    "compute-gcp/metrics"       = true
    "storage-gcp/metrics"       = true
    "loadbalancing-gcp/metrics" = true
    "gke-gcp/metrics"           = var.enable_gke_metrics
    "cloudrun-gcp/metrics"      = var.enable_cloudrun_metrics
    "cloudsql-gcp/metrics"      = var.enable_cloudsql_metrics
    "pubsub-gcp/metrics"        = var.enable_pubsub_metrics
  }

  gcp_service_workflow_ids = setunion(
    toset([
      "gcp-cockpit-assets",
      "gcp-cockpit-coverage",
      "gcp-cockpit-host-recommendations",
    ]),
    toset([
      for workflow_id, requirements in local.gcp_workflow_telemetry_requirements :
      workflow_id
      if alltrue([
        for requirement in requirements :
        lookup(local.gcp_metric_input_enabled, requirement, false)
      ])
    ]),
    var.enable_ml_jobs ? toset(["gcp-ml-datafeed-keeper"]) : toset([]),
  )

  gcp_read_tool_specs = var.enable_ai_agents && length(module.observability) > 0 ? {
    "gcp-insight-current-findings" = {
      description = "Read at most 50 current GCP findings, with stable resource keys and evidence."
      query       = "FROM gcp-cockpit-recommendations | WHERE @timestamp > NOW() - 7 days | KEEP @timestamp, resource.key, resource.type, resource.name, category, severity, confidence, activity_status, lookback_days, evidence_refs, contradictory_evidence, missing_telemetry, expected_value, safe_next_action | SORT @timestamp DESC | LIMIT 50"
    }
    "gcp-insight-coverage-gaps" = {
      description = "Read at most 50 GCP telemetry coverage gaps; dataset presence is not resource coverage."
      query       = "FROM gcp-cockpit-coverage | WHERE status != \"healthy\" | KEEP @timestamp, service, status, detail, coverage_scope, docs_24h, last_seen | SORT @timestamp DESC | LIMIT 50"
    }
    "gcp-insight-current-summary" = {
      description = "Read the single current GCP Insight Engine agent summary."
      query       = "FROM gcp-cockpit-insight-summary | WHERE lookup.key == \"latest\" | KEEP @timestamp, priority, headline, summary, action_1, action_2, action_3 | SORT @timestamp DESC | LIMIT 1"
    }
  } : {}
}

resource "elasticstack_kibana_agentbuilder_tool" "gcp_insight_read" {
  for_each = local.gcp_read_tool_specs

  tool_id     = each.key
  type        = "esql"
  description = each.value.description
  tags        = ["gcp", "cockpit", "insight", "read-only", "bounded"]
  space_id    = "default"
  configuration = jsonencode({
    query  = each.value.query
    params = {}
  })

  kibana_connection {
    endpoints = [module.observability[0].kibana_endpoint]
    username  = module.observability[0].username
    password  = module.observability[0].password
  }
}
