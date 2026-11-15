terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  # Remote state bucket created manually once; pass via -backend-config. No hardcoded project.
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" { type = string } # via TF_VAR_project_id, never committed
variable "region" {
  type    = string
  default = "asia-south1"
}
variable "env" {
  type    = string
  default = "staging"
}
variable "api_image" { type = string }
variable "frontend_image" { type = string }

locals { p = "physio-${var.env}" }

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com", "sqladmin.googleapis.com", "cloudtasks.googleapis.com",
    "cloudscheduler.googleapis.com", "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com", "monitoring.googleapis.com", "logging.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = local.p
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

resource "google_service_account" "api" {
  account_id = "${local.p}-api"
}
resource "google_service_account" "worker" {
  account_id = "${local.p}-worker"
}

resource "google_project_iam_member" "api_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}
resource "google_project_iam_member" "api_tasks" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.api.email}"
}
resource "google_project_iam_member" "worker_run" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# Secret values are added out-of-band; never via Terraform variables/state.
resource "google_secret_manager_secret" "s" {
  for_each  = toset(["db-password", "app-secret", "jwt-secret", "worker-token", "whatsapp-token", "whatsapp-app-secret", "llm-key"])
  secret_id = "${local.p}-${each.value}"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_iam_member" "api_read" {
  for_each  = google_secret_manager_secret.s
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# Cloud SQL: no public IP (Cloud Run connects via socket volume), smallest staging tier.
resource "google_sql_database_instance" "pg" {
  name                = "${local.p}-pg"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = false
  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_size         = 10
    ip_configuration {
      ipv4_enabled = false
    }
    backup_configuration {
      enabled = true
    }
  }
  depends_on = [google_project_service.apis]
}
resource "google_sql_database" "db" {
  instance = google_sql_database_instance.pg.name
  name     = "physio_one_staging"
}
# pgvector is enabled by migration 001 (CREATE EXTENSION vector).

resource "google_cloud_tasks_queue" "q" {
  for_each = toset(["inbound", "automation", "campaigns"])
  name     = "${local.p}-${each.value}"
  location = var.region
  retry_config {
    max_attempts = 5
    min_backoff  = "10s"
    max_backoff  = "300s"
  }
  rate_limits {
    max_concurrent_dispatches = 10
    max_dispatches_per_second = 5
  }
}

resource "google_cloud_run_v2_service" "api" {
  name     = "${local.p}-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL" # webhooks are public; protected by Meta/YCloud signature checks + app auth
  template {
    service_account = google_service_account.api.email
    scaling {
      min_instance_count = 0 # cost control: scale to zero in staging
      max_instance_count = 3
    }
    containers {
      image = var.api_image
      ports { container_port = 8000 }
      resources {
        limits = { cpu = "1", memory = "1Gi" }
      }
      env {
        name  = "ENVIRONMENT"
        value = "staging"
      }
      env {
        name  = "AUTOMATION_OUTBOUND_ENABLED"
        value = "false" # mandatory kill-switch default
      }
      env {
        name  = "REQUIRE_OIDC_IN_PRODUCTION"
        value = "true"
      }
      env {
        name  = "CLOUD_TASKS_ENABLED"
        value = "true"
      }
      env {
        name  = "WORKER_SERVICE_ACCOUNT_EMAIL"
        value = google_service_account.worker.email
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.pg.connection_name]
      }
    }
  }
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "${local.p}-web"
  location = var.region
  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.frontend_image
      ports { container_port = 3000 }
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
    }
  }
}

# Bounded worker execution (Cloud Run Job) — never a polling Cloud Run service.
resource "google_cloud_run_v2_job" "worker_once" {
  name     = "${local.p}-worker-once"
  location = var.region
  template {
    template {
      service_account = google_service_account.api.email
      containers {
        image   = var.api_image
        command = ["python", "-m", "app.workers.runner", "--once"]
        env {
          name  = "AUTOMATION_OUTBOUND_ENABLED"
          value = "false"
        }
      }
    }
  }
}

resource "google_cloud_scheduler_job" "jobs" {
  for_each = {
    process-due     = { schedule = "*/5 * * * *", uri_path = "/api/v1/automations/process-due" }
    scan-inactivity = { schedule = "*/15 * * * *", uri_path = "/api/v1/automations/scan-inactivity" }
    campaigns       = { schedule = "*/30 9-20 * * *", uri_path = "/api/v1/campaigns/worker/run" }
    inbound         = { schedule = "*/2 * * * *", uri_path = "/api/v1/ai-inbound/process-due" }
  }
  name      = "${local.p}-${each.key}"
  schedule  = each.value.schedule
  time_zone = "Asia/Kolkata"
  region    = var.region
  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.api.uri}${each.value.uri_path}"
    oidc_token {
      service_account_email = google_service_account.worker.email
      audience              = google_cloud_run_v2_service.api.uri
    }
  }
  retry_config { retry_count = 3 }
}

output "api_url" { value = google_cloud_run_v2_service.api.uri }
output "cost_note" {
  value = "Estimate only: Cloud SQL db-f1-micro + scale-to-zero Cloud Run + low-volume Tasks/Scheduler approx USD 15-35/month. Verify in GCP pricing calculator; set a billing budget alert before apply (budgets are billing-account scoped)."
}
