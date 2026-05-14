output "vm_name" {
  value = google_compute_instance.trade.name
}

output "vm_external_ip" {
  value = google_compute_address.trade_static.address
}

output "vm_zone" {
  value = google_compute_instance.trade.zone
}

output "artifact_registry_repo" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.trade.repository_id}"
}

output "pubsub_topics" {
  value = {
    news_classified = google_pubsub_topic.news_classified.name
    pair_registry   = google_pubsub_topic.pair_registry.name
    risk_alerts     = google_pubsub_topic.risk_alerts.name
  }
}

output "ssh_via_iap" {
  description = "Command to SSH to the VM through IAP."
  value       = "gcloud compute ssh ${google_compute_instance.trade.name} --zone ${google_compute_instance.trade.zone} --tunnel-through-iap"
}
