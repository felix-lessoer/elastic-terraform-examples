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

  ml_anomalies_ds = jsonencode({
    type          = "data_view_spec"
    index_pattern = ".ml-anomalies-shared,*:ml-anomalies-shared"
    time_field    = "@timestamp"
  })

  ml_jobs_markdown = length(var.ml_jobs) == 0 ? "| _(none provisioned)_ | — | — |" : join(
    "\n",
    [for j in var.ml_jobs : "| **${j.id}** | ${j.description} | ${j.state} |"]
  )

  ai_agents_markdown = length(var.ai_agents) == 0 ? "| _(none provisioned)_ | — | — |" : join(
    "\n",
    [for a in var.ai_agents : "| **${a.id}** | ${a.role} | ${a.state} |"]
  )
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

  panels = [
    # -------------------------------------------------------------------------
    # Mission control
    # -------------------------------------------------------------------------
    {
      type = "markdown"
      grid = { x = 0, y = 0, w = 48, h = 6 }
      markdown_config = {
        by_value = {
          title = "GCP Observe & Protect"
          content = <<-MD
            ### Elastic cockpit
            **${var.observability_project_name}** (Observability hub) · linked to **${var.security_project_name}** via Cross-Project Search

            Security Fleet collects CSPM + audit/firewall. Observability Fleet collects metrics + network/LB logs. This view aggregates both.

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
            description           = "Detection alerts from the Security project (CPS)"
            data_source_json      = local.alerts_security_ds
            query                 = { expression = "" }
            ignore_global_filters = false
            sampling              = 1
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
            description           = "Threshold alerts in the Observability hub"
            data_source_json      = local.alerts_obs_ds
            query                 = { expression = "" }
            ignore_global_filters = false
            sampling              = 1
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
            description           = "Combined logs + metrics across linked projects"
            data_source_json      = local.events_data_source
            query                 = { expression = "" }
            ignore_global_filters = false
            sampling              = 1
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
      grid = { x = 36, y = 6, w = 12, h = 8 }
      vis_config = {
        by_value = {
          metric_chart_config = {
            title                 = "CSPM findings (24h)"
            description           = "Cloud security posture findings (GCP)"
            data_source_json      = local.findings_data_source
            query                 = { expression = "" }
            ignore_global_filters = false
            sampling              = 1
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

    # -------------------------------------------------------------------------
    # Data flow
    # -------------------------------------------------------------------------
    {
      type = "markdown"
      grid = { x = 0, y = 14, w = 48, h = 3 }
      markdown_config = {
        by_value = {
          title   = "Data flow"
          content = "### Data flow — what is delivering?\nDatasets and hosts with traffic in the selected window. Empty charts mean a configured integration is **not** shipping yet."
          settings = {
            hide_title  = true
            hide_border = true
          }
        }
      }
    },
    {
      type = "vis"
      grid = { x = 0, y = 17, w = 24, h = 14 }
      vis_config = {
        by_value = {
          xy_chart_config = {
            title = "Active datasets (by volume)"
            axis = {
              y = { domain_json = jsonencode({ type = "fit" }) }
            }
            decorations = {
              minimum_bar_height = 1
              show_value_labels  = false
            }
            fitting = { type = "none" }
            legend  = {}
            query   = { expression = "" }
            layers = [{
              type = "bar_horizontal"
              data_layer = {
                data_source_json = local.events_data_source
                x_json = jsonencode({
                  operation = "terms"
                  fields    = ["data_stream.dataset"]
                  limit     = 15
                  rank_by = {
                    type         = "metric"
                    metric_index = 0
                    direction    = "desc"
                  }
                })
                y = [{
                  config_json = jsonencode({
                    operation     = "count"
                    empty_as_null = true
                  })
                }]
              }
            }]
          }
        }
      }
    },
    {
      type = "vis"
      grid = { x = 24, y = 17, w = 24, h = 14 }
      vis_config = {
        by_value = {
          xy_chart_config = {
            title = "Hosts / agents delivering"
            axis = {
              y = { domain_json = jsonencode({ type = "fit" }) }
            }
            decorations = {
              minimum_bar_height = 1
              show_value_labels  = false
            }
            fitting = { type = "none" }
            legend  = {}
            query   = { expression = "" }
            layers = [{
              type = "bar_horizontal"
              data_layer = {
                data_source_json = local.events_data_source
                x_json = jsonencode({
                  operation = "terms"
                  fields    = ["host.name"]
                  limit     = 15
                  rank_by = {
                    type         = "metric"
                    metric_index = 0
                    direction    = "desc"
                  }
                })
                y = [{
                  config_json = jsonencode({
                    operation     = "count"
                    empty_as_null = true
                  })
                }]
              }
            }]
          }
        }
      }
    },
    {
      type = "vis"
      grid = { x = 0, y = 31, w = 48, h = 12 }
      vis_config = {
        by_value = {
          xy_chart_config = {
            title = "Telemetry volume over time"
            axis = {
              y = {
                domain_json = jsonencode({ type = "fit" })
                title       = { value = "Events", visible = true }
              }
              x = {
                title = { value = "@timestamp", visible = true }
              }
            }
            decorations = {}
            fitting     = { type = "none" }
            legend      = {}
            query       = { expression = "" }
            layers = [{
              type = "line"
              data_layer = {
                data_source_json = local.events_data_source
                x_json = jsonencode({
                  operation               = "date_histogram"
                  field                   = "@timestamp"
                  suggested_interval      = "auto"
                  use_original_time_range = false
                  include_empty_rows      = true
                  drop_partial_intervals  = false
                })
                y = [{
                  config_json = jsonencode({
                    operation     = "count"
                    empty_as_null = true
                  })
                }]
              }
            }]
          }
        }
      }
    },

    # -------------------------------------------------------------------------
    # ML & AI agents
    # -------------------------------------------------------------------------
    {
      type = "markdown"
      grid = { x = 0, y = 43, w = 48, h = 3 }
      markdown_config = {
        by_value = {
          title   = "Detection intelligence"
          content = "### Detection intelligence — ML & AI agents\nProvisioned automation for this PoC. Live anomaly volume appears when ML jobs have produced records."
          settings = {
            hide_title  = true
            hide_border = true
          }
        }
      }
    },
    {
      type = "markdown"
      grid = { x = 0, y = 46, w = 24, h = 10 }
      markdown_config = {
        by_value = {
          title = "ML jobs (provisioned)"
          content = <<-MD
            | Job | Purpose | State |
            | --- | --- | --- |
            ${local.ml_jobs_markdown}
          MD
          settings = {
            hide_border = false
          }
        }
      }
    },
    {
      type = "markdown"
      grid = { x = 24, y = 46, w = 24, h = 10 }
      markdown_config = {
        by_value = {
          title = "AI agents (provisioned)"
          content = <<-MD
            | Agent | Role | State |
            | --- | --- | --- |
            ${local.ai_agents_markdown}

            Open **Agent Builder** in this Observability project to chat with them.
          MD
          settings = {
            hide_border = false
          }
        }
      }
    },
    {
      type = "vis"
      grid = { x = 0, y = 56, w = 48, h = 12 }
      vis_config = {
        by_value = {
          xy_chart_config = {
            title = "ML anomaly records by job"
            axis = {
              y = { domain_json = jsonencode({ type = "fit" }) }
            }
            decorations = {
              minimum_bar_height = 1
              show_value_labels  = true
            }
            fitting = { type = "none" }
            legend  = {}
            query   = { expression = "" }
            layers = [{
              type = "bar_horizontal"
              data_layer = {
                data_source_json = local.ml_anomalies_ds
                x_json = jsonencode({
                  operation = "terms"
                  fields    = ["job_id"]
                  limit     = 15
                  rank_by = {
                    type         = "metric"
                    metric_index = 0
                    direction    = "desc"
                  }
                })
                y = [{
                  config_json = jsonencode({
                    operation     = "count"
                    empty_as_null = true
                  })
                }]
              }
            }]
          }
        }
      }
    },

    # -------------------------------------------------------------------------
    # GCP inventory
    # -------------------------------------------------------------------------
    {
      type = "markdown"
      grid = { x = 0, y = 68, w = 48, h = 3 }
      markdown_config = {
        by_value = {
          title   = "GCP inventory"
          content = "### GCP inventory\nObserved GCP resources from CSPM findings (aggregated counts — not raw documents)."
          settings = {
            hide_title  = true
            hide_border = true
          }
        }
      }
    },
    {
      type = "vis"
      grid = { x = 0, y = 71, w = 16, h = 14 }
      vis_config = {
        by_value = {
          xy_chart_config = {
            title = "Assets by type"
            axis = {
              y = { domain_json = jsonencode({ type = "fit" }) }
            }
            decorations = {
              minimum_bar_height = 1
              show_value_labels  = false
            }
            fitting = { type = "none" }
            legend  = {}
            query   = { expression = "" }
            layers = [{
              type = "bar_horizontal"
              data_layer = {
                data_source_json = local.findings_data_source
                x_json = jsonencode({
                  operation = "terms"
                  fields    = ["resource.type"]
                  limit     = 15
                  rank_by = {
                    type         = "metric"
                    metric_index = 0
                    direction    = "desc"
                  }
                })
                y = [{
                  config_json = jsonencode({
                    operation     = "count"
                    empty_as_null = true
                  })
                }]
              }
            }]
          }
        }
      }
    },
    {
      type = "vis"
      grid = { x = 16, y = 71, w = 16, h = 14 }
      vis_config = {
        by_value = {
          xy_chart_config = {
            title = "Top assets by name"
            axis = {
              y = { domain_json = jsonencode({ type = "fit" }) }
            }
            decorations = {
              minimum_bar_height = 1
              show_value_labels  = false
            }
            fitting = { type = "none" }
            legend  = {}
            query   = { expression = "" }
            layers = [{
              type = "bar_horizontal"
              data_layer = {
                data_source_json = local.findings_data_source
                x_json = jsonencode({
                  operation = "terms"
                  fields    = ["resource.name"]
                  limit     = 15
                  rank_by = {
                    type         = "metric"
                    metric_index = 0
                    direction    = "desc"
                  }
                })
                y = [{
                  config_json = jsonencode({
                    operation     = "count"
                    empty_as_null = true
                  })
                }]
              }
            }]
          }
        }
      }
    },
    {
      type = "vis"
      grid = { x = 32, y = 71, w = 16, h = 14 }
      vis_config = {
        by_value = {
          pie_chart_config = {
            title                 = "Findings by evaluation"
            donut_hole            = "s"
            label_position        = "outside"
            data_source_json      = local.findings_data_source
            ignore_global_filters = false
            sampling              = 1
            query                 = { expression = "" }
            metrics = [{
              config_json = jsonencode({
                operation = "count"
                format    = { type = "number" }
              })
            }]
            group_by = [{
              config_json = jsonencode({
                operation = "terms"
                fields    = ["result.evaluation"]
                limit     = 10
                rank_by = {
                  type         = "metric"
                  metric_index = 0
                  direction    = "desc"
                }
              })
            }]
          }
        }
      }
    }
  ]

  kibana_connection {
    endpoints = [local.kibana_url]
    username  = var.elasticsearch_username
    password  = var.elasticsearch_password
  }
}
