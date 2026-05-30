# RACEJUDGE Infrastructure — Terraform
# Provisions: Cloudflare R2 buckets, Fly.io app secrets
#
# Prerequisites:
#   terraform init
#   export CLOUDFLARE_API_TOKEN=...
#   export FLY_API_TOKEN=...
#
# Apply:
#   terraform plan -var-file=terraform.tfvars
#   terraform apply -var-file=terraform.tfvars

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
    fly = {
      source  = "fly-apps/fly"
      version = "~> 0.0.23"
    }
  }

  backend "s3" {
    # Use Cloudflare R2 as Terraform state backend
    # bucket = "racejudge-tf-state"
    # key    = "terraform.tfstate"
    # endpoint = "https://<account_id>.r2.cloudflarestorage.com"
    # Configure via TF_BACKEND_CONFIG env vars
    # Uncomment after R2 bucket is created manually
  }
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "Neon PostgreSQL connection string"
  type        = string
  sensitive   = true
}

variable "redis_url" {
  description = "Upstash Redis connection string"
  type        = string
  sensitive   = true
  default     = ""
}

variable "clerk_secret_key" {
  description = "Clerk secret key for authentication"
  type        = string
  sensitive   = true
}

variable "hf_token" {
  description = "HuggingFace token for pyannote models"
  type        = string
  sensitive   = true
  default     = ""
}

# ---------------------------------------------------------------------------
# Cloudflare R2 Buckets
# ---------------------------------------------------------------------------

resource "cloudflare_r2_bucket" "raw_pdfs" {
  account_id = var.cloudflare_account_id
  name       = "racejudge-raw"
  location   = "ENAM"  # Eastern North America
}

resource "cloudflare_r2_bucket" "audio" {
  account_id = var.cloudflare_account_id
  name       = "racejudge-audio"
  location   = "ENAM"
}

resource "cloudflare_r2_bucket" "telemetry" {
  account_id = var.cloudflare_account_id
  name       = "racejudge-telemetry"
  location   = "ENAM"
}

# ---------------------------------------------------------------------------
# Fly.io App Secrets
# ---------------------------------------------------------------------------

resource "fly_app" "api" {
  name = "racejudge-api"
  org  = "racejudge-hq"
}

resource "fly_secret" "database_url" {
  app   = fly_app.api.name
  name  = "DATABASE_URL"
  value = var.database_url
}

resource "fly_secret" "redis_url" {
  count = var.redis_url != "" ? 1 : 0
  app   = fly_app.api.name
  name  = "REDIS_URL"
  value = var.redis_url
}

resource "fly_secret" "clerk_secret_key" {
  app   = fly_app.api.name
  name  = "CLERK_SECRET_KEY"
  value = var.clerk_secret_key
}

resource "fly_secret" "hf_token" {
  count = var.hf_token != "" ? 1 : 0
  app   = fly_app.api.name
  name  = "HF_TOKEN"
  value = var.hf_token
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "r2_raw_bucket" {
  value = cloudflare_r2_bucket.raw_pdfs.name
}

output "r2_audio_bucket" {
  value = cloudflare_r2_bucket.audio.name
}

output "fly_app_name" {
  value = fly_app.api.name
}
