variable "deployment_mode" {
  type    = string
  default = "serverless"
}

variable "elastic_project_name" {
  type    = string
  default = "GCP Observe and Protect"
}

variable "observability_project_name" {
  type    = string
  default = "GCP Observability Cockpit"
}

variable "enable_observability_project" {
  type        = bool
  description = "Create a serverless Observability project linked to Security via Cross-Project Search and deploy the cockpit dashboard."
  default     = true
}

variable "enable_ml_jobs" {
  type    = bool
  default = true
}

variable "enable_ai_agents" {
  type    = bool
  default = true
}

variable "enable_observability_alerts" {
  type    = bool
  default = true
}

variable "elastic_region" {
  type    = string
  default = "gcp-europe-west3"
}

variable "product_tier" {
  type    = string
  default = "complete"
}

variable "elastic_version" {
  type    = string
  default = "latest"
}

variable "deployment_template_id" {
  type    = string
  default = "gcp-general-purpose"
}

variable "google_cloud_project" {
  type = string
}

variable "google_cloud_region" {
  type    = string
  default = "europe-west3"
}

variable "google_cloud_credentials_file" {
  type        = string
  description = "Path to GCP service account JSON used by Terraform. Leave empty to use ADC."
  default     = ""
}

variable "name_prefix" {
  type    = string
  default = "elastic-poc"
}

variable "elastic_labels_required" {
  type        = bool
  description = "Whether organization-specific Elastic labels must be applied to provisioned GCP resources."
  default     = true
}

variable "company_labels" {
  type        = map(string)
  description = "Company-policy labels applied to all GCP resources (and sanitized onto the Elastic project)."

  validation {
    condition     = length(var.company_labels) > 0
    error_message = "Set company_labels according to your company tagging policy."
  }
}

variable "required_label_keys" {
  type        = list(string)
  description = "Optional list of label keys that must appear in company_labels."
  default     = []
}

variable "enable_cspm" {
  type    = bool
  default = true
}

variable "enable_billing_metrics" {
  type        = bool
  description = "Enable GCP billing metrics stream (requires billing_dataset_id)."
  default     = false
}

variable "enable_gke_metrics" {
  type        = bool
  description = "Enable GKE metrics and the GKE insight workflow. May increase Cloud Monitoring and Elastic ingest cost."
  default     = false
}

variable "enable_cloudrun_metrics" {
  type        = bool
  description = "Enable Cloud Run metrics and the Cloud Run insight workflow. May increase Cloud Monitoring and Elastic ingest cost."
  default     = false
}

variable "enable_cloudsql_metrics" {
  type        = bool
  description = "Enable Cloud SQL metrics and the Cloud SQL insight workflow. May increase Cloud Monitoring and Elastic ingest cost."
  default     = false
}

variable "enable_pubsub_metrics" {
  type        = bool
  description = "Enable Pub/Sub metrics for coverage and backlog analysis. May increase Cloud Monitoring and Elastic ingest cost."
  default     = false
}

variable "billing_dataset_id" {
  type        = string
  description = "BigQuery dataset id for GCP billing export (required when enable_billing_metrics is true)."
  default     = ""
}

variable "existing_topic_names" {
  type        = map(string)
  description = "Customer-owned Pub/Sub topics to attach by stream key instead of creating duplicates."
  default     = {}
}

variable "existing_sink_names" {
  type        = map(string)
  description = "Customer-owned Logging sinks to attach by stream key; matching existing topics are required."
  default     = {}
}

variable "existing_subscription_names" {
  type        = map(string)
  description = "Customer-owned Pub/Sub subscriptions to attach by stream key; matching existing topics are required."
  default     = {}
}

variable "grant_existing_subscription_access" {
  type        = bool
  description = "Grant the PoC collector subscriber access to attached customer subscriptions. False preserves customer IAM ownership."
  default     = false
}

variable "gcp_discovery_manifest_path" {
  type        = string
  description = "Optional path to a validated local brownfield manifest. Only its hash and summary are retained by Terraform."
  default     = ""

  validation {
    condition     = var.gcp_discovery_manifest_path == "" || fileexists(var.gcp_discovery_manifest_path)
    error_message = "gcp_discovery_manifest_path must be empty or point to a readable validated manifest."
  }
}

variable "enable_detection_rules" {
  type    = bool
  default = true
}

variable "enable_workflows" {
  type        = bool
  description = "Deploy pinned Kibana Workflow YAML from examples/gcp/workflows/ after greenfield create."
  default     = true
}

variable "execute_workflows_on_apply" {
  type        = bool
  description = "Manually execute each enabled workflow once after Terraform creates/updates it."
  default     = true
}

variable "deploy_workflows_to_security" {
  type        = bool
  description = "Also deploy the same pinned workflows into the Security project Kibana (in addition to Observability)."
  default     = false
}

variable "detection_rule_tags" {
  type = list(object({
    key   = string
    value = string
  }))
  # Prebuilt GCP rules use "Data Source: Google Cloud Platform" / "Data Source: GCP"
  # (not "Google Cloud"). Wrong value installs rules but enables none of them.
  default = [
    { key = "Data Source", value = "Google Cloud Platform" }
  ]
}

variable "enable_elastic_agent" {
  type        = bool
  description = "Deploy a GCE VM with Elastic Agent enrolled into the Fleet policy (required for Pub/Sub/metrics collection)."
  default     = true
}

variable "elastic_agent_zone" {
  type        = string
  description = "GCE zone for the Elastic Agent VM. Empty picks {google_cloud_region}-b."
  default     = ""
}

variable "elastic_agent_machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "elastic_agent_version" {
  type        = string
  description = "Elastic Agent version installed on the GCE VM."
  default     = "9.5.4"
}

variable "elastic_agent_network" {
  type    = string
  default = "default"
}
