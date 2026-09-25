output "ai_agent_ids" {
  value = concat(
    length(elasticstack_kibana_agentbuilder_agent.security_analyst) > 0 ? [elasticstack_kibana_agentbuilder_agent.security_analyst[0].agent_id] : [],
    length(elasticstack_kibana_agentbuilder_agent.obs_triage) > 0 ? [elasticstack_kibana_agentbuilder_agent.obs_triage[0].agent_id] : [],
  )
}

output "ai_agents" {
  description = "Structured Agent Builder inventory for the cockpit dashboard."
  value = concat(
    length(elasticstack_kibana_agentbuilder_agent.security_analyst) > 0 ? [{
      id    = elasticstack_kibana_agentbuilder_agent.security_analyst[0].agent_id
      role  = "Triage CSPM + detection alerts across CPS"
      state = "Ready in Agent Builder"
    }] : [],
    length(elasticstack_kibana_agentbuilder_agent.obs_triage) > 0 ? [{
      id    = elasticstack_kibana_agentbuilder_agent.obs_triage[0].agent_id
      role  = "Explain telemetry gaps and alert bursts"
      state = "Ready in Agent Builder"
    }] : [],
  )
}

output "ml_job_ids" {
  value = concat(
    length(elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate) > 0 ? [elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate[0].job_id] : [],
    length(elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_cspm_findings_rate) > 0 ? [elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_cspm_findings_rate[0].job_id] : [],
  )
}

output "ml_jobs" {
  description = "Structured ML job inventory for the cockpit dashboard."
  value = concat(
    length(elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate) > 0 ? [{
      id          = elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate[0].job_id
      description = "Unusual drops/spikes in GCP telemetry volume"
      state       = try(elasticstack_elasticsearch_ml_job_state.gcp_event_rate[0].state, "configured")
    }] : [],
    length(elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_cspm_findings_rate) > 0 ? [{
      id          = elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_cspm_findings_rate[0].job_id
      description = "Unusual rate of CSPM findings documents"
      state       = try(elasticstack_elasticsearch_ml_job_state.gcp_cspm_findings_rate[0].state, "configured")
    }] : [],
  )
}

output "ml_datafeed_ids" {
  value = concat(
    length(elasticstack_elasticsearch_ml_datafeed.gcp_event_rate) > 0 ? [elasticstack_elasticsearch_ml_datafeed.gcp_event_rate[0].datafeed_id] : [],
    length(elasticstack_elasticsearch_ml_datafeed.gcp_cspm_findings_rate) > 0 ? [elasticstack_elasticsearch_ml_datafeed.gcp_cspm_findings_rate[0].datafeed_id] : [],
  )
}

output "ml_datafeed_states" {
  value = concat(
    length(elasticstack_elasticsearch_ml_datafeed_state.gcp_event_rate) > 0 ? [{
      id    = elasticstack_elasticsearch_ml_datafeed.gcp_event_rate[0].datafeed_id
      state = elasticstack_elasticsearch_ml_datafeed_state.gcp_event_rate[0].state
    }] : [],
    length(elasticstack_elasticsearch_ml_datafeed_state.gcp_cspm_findings_rate) > 0 ? [{
      id    = elasticstack_elasticsearch_ml_datafeed.gcp_cspm_findings_rate[0].datafeed_id
      state = elasticstack_elasticsearch_ml_datafeed_state.gcp_cspm_findings_rate[0].state
    }] : [],
  )
}

output "observability_alert_rule_ids" {
  value = concat(
    length(elasticstack_kibana_alerting_rule.log_rate_spike) > 0 ? [elasticstack_kibana_alerting_rule.log_rate_spike[0].id] : [],
    length(elasticstack_kibana_alerting_rule.cspm_failed_findings) > 0 ? [elasticstack_kibana_alerting_rule.cspm_failed_findings[0].id] : [],
  )
}
