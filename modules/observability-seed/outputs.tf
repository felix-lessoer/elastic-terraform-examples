output "ai_agent_ids" {
  value = compact([
    try(elasticstack_kibana_agentbuilder_agent.security_analyst[0].agent_id, null),
    try(elasticstack_kibana_agentbuilder_agent.obs_triage[0].agent_id, null),
  ])
}

output "ml_job_ids" {
  value = compact([
    try(elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_event_rate[0].job_id, null),
    try(elasticstack_elasticsearch_ml_anomaly_detection_job.gcp_cspm_findings_rate[0].job_id, null),
  ])
}

output "observability_alert_rule_ids" {
  value = compact([
    try(elasticstack_kibana_alerting_rule.log_rate_spike[0].id, null),
    try(elasticstack_kibana_alerting_rule.cspm_failed_findings[0].id, null),
  ])
}
