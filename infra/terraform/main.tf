terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
  }
  # Wire to a real backend once GCS bucket exists:
  # backend "gcs" {
  #   bucket = "trade-tfstate-<your-project-id>"
  #   prefix = "infra/"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# ---- Networking ----

resource "google_compute_network" "trade" {
  name                    = "trade-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "trade" {
  name          = "trade-subnet"
  ip_cidr_range = "10.10.0.0/24"
  region        = var.region
  network       = google_compute_network.trade.id
}

resource "google_compute_address" "trade_static" {
  name   = "trade-static-ip"
  region = var.region
}

resource "google_compute_firewall" "iap_ssh" {
  name      = "trade-allow-iap-ssh"
  network   = google_compute_network.trade.id
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # IAP TCP forwarding source range.
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["trade-vm"]
}

resource "google_compute_firewall" "monitoring_scrape" {
  name      = "trade-allow-monitoring"
  network   = google_compute_network.trade.id
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["7070"]  # ws-gateway behind Cloud Load Balancer if exposed
  }

  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]
  target_tags   = ["trade-vm"]
}

# ---- Service account for the VM ----

resource "google_service_account" "vm" {
  account_id   = "trade-vm-sa"
  display_name = "trade VM service account"
}

resource "google_project_iam_member" "vm_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_artifact_registry" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# ---- The VM ----

resource "google_compute_instance" "trade" {
  name         = "trade"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["trade-vm"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 200
      type  = "pd-balanced"
    }
  }

  network_interface {
    network    = google_compute_network.trade.id
    subnetwork = google_compute_subnetwork.trade.id
    access_config {
      nat_ip = google_compute_address.trade_static.address
    }
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  # Provisioning script: installs Docker, Ops Agent, and lays down the
  # systemd unit. The trading-stack.service starts only after secrets are
  # delivered (deploy-vm.yml CI job does this).
  metadata_startup_script = file("${path.module}/startup.sh")

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }
}

# ---- Pub/Sub topics for VM ↔ Cloud Run fanout ----

resource "google_pubsub_topic" "news_classified" {
  name = "trade-news-classified"
}

resource "google_pubsub_topic" "pair_registry" {
  name = "trade-pair-registry"
}

resource "google_pubsub_topic" "risk_alerts" {
  name = "trade-risk-alerts"
}

# ---- Secret Manager placeholders (populate values out-of-band) ----

resource "google_secret_manager_secret" "kalshi_private_key" {
  secret_id = "kalshi-private-key"
  replication { auto {} }
}

resource "google_secret_manager_secret" "poly_us_secret" {
  secret_id = "poly-us-secret"
  replication { auto {} }
}

resource "google_secret_manager_secret" "clickhouse_password" {
  secret_id = "clickhouse-password"
  replication { auto {} }
}

# ---- Artifact Registry for Docker images ----

resource "google_artifact_registry_repository" "trade" {
  location      = var.region
  repository_id = "trade"
  description   = "Container images for the trade stack"
  format        = "DOCKER"
}
