output "instance_name" {
  value = google_compute_instance.agent.name
}

output "instance_id" {
  value = google_compute_instance.agent.instance_id
}

output "zone" {
  value = google_compute_instance.agent.zone
}

output "external_ip" {
  value = try(google_compute_instance.agent.network_interface[0].access_config[0].nat_ip, null)
}

output "self_link" {
  value = google_compute_instance.agent.self_link
}

output "labels" {
  value = google_compute_instance.agent.labels
}
