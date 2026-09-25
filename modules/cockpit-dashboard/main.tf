locals {
  kibana_url = trimsuffix(var.kibana_endpoint, "/")

  # Prefer CPS-friendly wildcards so linked Security data is included when available.
  events_data_source = jsonencode({
    type          = "data_view_spec"
    index_pattern = "logs-*,metrics-*,*:logs-*,*:metrics-*"
    time_field    = "@timestamp"
  })

  findings_data_source = jsonencode({
    type          = "data_view_spec"
    index_pattern = "logs-cloud_security_posture.findings-*,*:logs-cloud_security_posture.findings-*"
    time_field    = "@timestamp"
  })

  alerts_security_ds = jsonencode({
    type          = "data_view_spec"
    index_pattern = ".alerts-security.alerts-*,*:.alerts-security.alerts-*"
    time_field    = "@timestamp"
  })

  alerts_obs_ds = jsonencode({
    type          = "data_view_spec"
    index_pattern = ".alerts-observability.*,.alerts-default.*,*:.alerts-observability.*,*:.alerts-default.*"
    time_field    = "@timestamp"
  })
}

resource "elasticstack_kibana_dashboard" "cockpit" {
  title       = var.title
  description = var.description
  space_id    = var.space_id
  tags        = ["cockpit", "gcp", "observe-and-protect", "cps"]

  time_range = {
    from = "now-24h"
    to   = "now"
  }

  refresh_interval = {
    pause = false
    value = 60000
  }

  query = {
    language = "kql"
    text     = ""
  }

  options = {
    hide_panel_titles  = false
    hide_panel_borders = false
    sync_colors        = true
    sync_cursor        = true
    sync_tooltips      = true
    auto_apply_filters = true
  }

  panels = []

  sections = [
    {
      title     = "Mission control"
      collapsed = false
      grid      = { y = 0 }
      panels = [
        {
          type = "markdown"
          grid = { x = 0, y = 0, w = 48, h = 6 }
          markdown_config = {
            by_value = {
              title = "GCP Observe & Protect"
              content = <<-MD
                ### Elastic cockpit
                **${var.observability_project_name}** (Observability hub) · linked to **${var.security_project_name}** via Cross-Project Search

                Aggregated posture only — not raw events. KPIs refresh every 60s.
                <span style="color:#48EFCF">■</span> healthy signal &nbsp;
                <span style="color:#FEC514">■</span> attention &nbsp;
                <span style="color:#FF957D">■</span> security pressure
              MD
              settings = {
                hide_title  = true
                hide_border = true
              }
            }
          }
        },
        {
          type = "vis"
          grid = { x = 0, y = 6, w = 12, h = 8 }
          vis_config = {
            by_value = {
              metric_chart_config = {
                title                 = "Security alerts (24h)"
                description           = "Open / recent detection alerts from the Security project"
                data_source_json      = local.alerts_security_ds
                query                 = { expression = "" }
                ignore_global_filters = false
                metrics = [{
                  config_json = jsonencode({
                    type      = "primary"
                    operation = "count"
                    format    = { type = "number" }
                  })
                }]
              }
            }
          }
        },
        {
          type = "vis"
          grid = { x = 12, y = 6, w = 12, h = 8 }
          vis_config = {
            by_value = {
              metric_chart_config = {
                title                 = "Observability alerts (24h)"
                description           = "Threshold / log alerts in the Observability hub"
                data_source_json      = local.alerts_obs_ds
                query                 = { expression = "" }
                ignore_global_filters = false
                metrics = [{
                  config_json = jsonencode({
                    type      = "primary"
                    operation = "count"
                    format    = { type = "number" }
                  })
                }]
              }
            }
          }
        },
        {
          type = "vis"
          grid = { x = 24, y = 6, w = 12, h = 8 }
          vis_config = {
            by_value = {
              metric_chart_config = {
                title                 = "Telemetry events (24h)"
                description           = "Combined logs + metrics volume across linked projects"
                data_source_json      = local.events_data_source
                query                 = { expression = "" }
                ignore_global_filters = false
                metrics = [{
                  config_json = jsonencode({
                    type      = "primary"
                    operation = "count"
                    format    = { type = "compactNumber", decimals = 1 }
                  })
                }]
              }
            }
          }
        },
        {
          type = "vis"
          grid = { x = 36, y = 6, w = 12, h = 8 }
          vis_config = {
            by_value = {
              metric_chart_config = {
                title                 = "CSPM findings (24h)"
                description           = "Cloud security posture findings (GCP)"
                data_source_json      = local.findings_data_source
                query                 = { expression = "" }
                ignore_global_filters = false
                metrics = [{
                  config_json = jsonencode({
                    type      = "primary"
                    operation = "count"
                    format    = { type = "number" }
                  })
                }]
              }
            }
          }
        }
      ]
    },
    {
      title     = "Data flow — what is delivering?"
      collapsed = false
      grid      = { y = 16 }
      panels = [
        {
          type = "markdown"
          grid = { x = 0, y = 0, w = 48, h = 3 }
          markdown_config = {
            by_value = {
              title   = "Pipelines"
              content = "Datasets with traffic in the selected window. Empty rows mean a configured integration is **not** shipping yet."
              settings = {
                hide_title  = true
                hide_border = true
              }
            }
          }
        },
        {
          type = "esql"
          grid = { x = 0, y = 3, w = 48, h = 14 }
          esql_config = {
            by_value = {
              title = "Active data streams"
              query = {
                type  = "esql"
                esql   = <<-ESQL
                  FROM logs-*, metrics-*, *:logs-*, *:metrics-*
                  | WHERE @timestamp > NOW() - 24 hours
                  | STATS
                      events = COUNT(*),
                      last_seen = MAX(@timestamp),
                      hosts = COUNT_DISTINCT(host.name)
                    BY data_stream.type, data_stream.dataset
                  | SORT events DESC
                  | LIMIT 50
                ESQL
              }
            }
          }
        }
      ]
    },
    {
      title     = "Detection intelligence — ML & AI agents"
      collapsed = false
      grid      = { y = 36 }
      panels = [
        {
          type = "markdown"
          grid = { x = 0, y = 0, w = 48, h = 3 }
          markdown_config = {
            by_value = {
              title   = "Automation"
              content = "Machine learning jobs and Agent Builder agents provisioned for this PoC. Status reflects the last 24h of results / runs when available."
              settings = {
                hide_title  = true
                hide_border = true
              }
            }
          }
        },
        {
          type = "esql"
          grid = { x = 0, y = 3, w = 24, h = 12 }
          esql_config = {
            by_value = {
              title = "ML jobs"
              query = {
                type = "esql"
                esql = <<-ESQL
                  FROM .ml-anomalies-shared, .ml-notifications-*, *:ml-anomalies-shared
                  | WHERE @timestamp > NOW() - 24 hours
                  | STATS
                      records = COUNT(*),
                      last_record = MAX(@timestamp)
                    BY job_id
                  | SORT records DESC
                  | LIMIT 25
                ESQL
              }
            }
          }
        },
        {
          type = "esql"
          grid = { x = 24, y = 3, w = 24, h = 12 }
          esql_config = {
            by_value = {
              title = "AI agent activity"
              query = {
                type = "esql"
                esql = <<-ESQL
                  FROM logs-elastic_agent*, metrics-elastic_agent*, .kibana-event-log-*, *:.kibana-event-log-*
                  | WHERE @timestamp > NOW() - 24 hours
                  | WHERE event.action LIKE "*agent*" OR kibana.alert.rule.name LIKE "*agent*" OR message LIKE "*Agent Builder*"
                  | STATS events = COUNT(*), last_seen = MAX(@timestamp) BY event.action, kibana.alert.rule.name
                  | SORT events DESC
                  | LIMIT 25
                ESQL
              }
            }
          }
        },
        {
          type = "markdown"
          grid = { x = 0, y = 15, w = 48, h = 5 }
          markdown_config = {
            by_value = {
              title = "Provisioned AI agents"
              content = <<-MD
                | Agent | Role | Expected state |
                | --- | --- | --- |
                | **gcp-security-analyst** | Triage CSPM + detection alerts across CPS | Ready in Agent Builder |
                | **gcp-obs-triage** | Explain telemetry gaps and alert bursts | Ready in Agent Builder |

                Open **Agent Builder** in this Observability project to chat with them. ML jobs are listed above once anomaly records exist.
              MD
              settings = {
                hide_border = false
              }
            }
          }
        }
      ]
    },
    {
      title     = "GCP inventory"
      collapsed = false
      grid      = { y = 60 }
      panels = [
        {
          type = "markdown"
          grid = { x = 0, y = 0, w = 48, h = 3 }
          markdown_config = {
            by_value = {
              title   = "Inventory"
              content = "Observed GCP resources from CSPM findings and cloud telemetry (aggregated, not raw document dump)."
              settings = {
                hide_title  = true
                hide_border = true
              }
            }
          }
        },
        {
          type = "esql"
          grid = { x = 0, y = 3, w = 48, h = 16 }
          esql_config = {
            by_value = {
              title = "Observed GCP assets"
              query = {
                type = "esql"
                esql = <<-ESQL
                  FROM logs-cloud_security_posture.findings-*, *:logs-cloud_security_posture.findings-*, metrics-gcp.*, *:metrics-gcp.*
                  | WHERE @timestamp > NOW() - 7 days
                  | EVAL
                      asset_id = COALESCE(resource.id, cloud.instance.id, host.id, agent.id),
                      asset_name = COALESCE(resource.name, host.name, agent.name, cloud.instance.id),
                      asset_type = COALESCE(resource.type, cloud.service.name, data_stream.dataset),
                      provider = COALESCE(cloud.provider, "gcp")
                  | WHERE asset_id IS NOT NULL
                  | STATS
                      signals = COUNT(*),
                      last_seen = MAX(@timestamp),
                      critical = COUNT(*) WHERE result.evaluation == "failed" OR kibana.alert.severity == "critical"
                    BY provider, asset_type, asset_name, asset_id
                  | SORT signals DESC
                  | LIMIT 100
                ESQL
              }
            }
          }
        }
      ]
    }
  ]

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}
