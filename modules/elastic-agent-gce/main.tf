locals {
  labels = {
    for k, v in merge(
      {
        "managed-by" = "terraform"
        "stack"      = "elastic-cloud-poc"
        "role"       = "elastic-agent"
      },
      var.company_labels
    ) :
    substr(lower(replace(replace(replace(replace(k, " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 63) =>
    substr(lower(replace(replace(replace(replace(tostring(v), " ", "-"), "/", "-"), ".", "-"), ":", "-")), 0, 63)
  }
}

resource "google_compute_instance" "agent" {
  name         = var.name
  project      = var.project_id
  zone         = var.zone
  machine_type = var.machine_type
  tags         = ["elastic-agent", "terraformed"]

  labels = local.labels

  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30
      type  = "pd-balanced"
      labels = local.labels
    }
  }

  network_interface {
    network    = var.network
    subnetwork = var.subnetwork != "" ? var.subnetwork : null

    access_config {
      // Ephemeral public IP for Fleet + artifact downloads
    }
  }

  dynamic "service_account" {
    for_each = var.service_account_email != "" ? [var.service_account_email] : []
    content {
      email  = service_account.value
      scopes = ["cloud-platform"]
    }
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = templatefile("${path.module}/templates/install_agent.sh.tftpl", {
    fleet_url         = var.fleet_url
    enrollment_token  = var.enrollment_token
    agent_version     = var.agent_version
  })

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
  }
}
