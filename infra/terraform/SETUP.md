# Terraform Setup — Step-by-Step

This provisions Cloudflare R2 buckets and Fly.io app secrets.
Run this once after you have accounts on Cloudflare and Fly.io.

---

## Prerequisites (accounts you must create first)

1. [cloudflare.com](https://cloudflare.com) — free account, enable R2 (requires credit card for R2)
2. [fly.io](https://fly.io) — free account, install CLI: `brew install flyctl && fly auth login`
3. [terraform](https://terraform.io) — install: `brew install terraform`

---

## Step 1 — Get your API tokens

### Cloudflare API token

1. Go to [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click **Create Token**
3. Use template: **Edit Cloudflare Workers** (or Custom Token with R2:Edit permission)
4. Copy the token — you'll use it as `CLOUDFLARE_API_TOKEN`
5. Copy your **Account ID** from the right sidebar of any Cloudflare page

### Fly.io API token

```bash
fly auth token
# Copy the printed token — use it as FLY_API_TOKEN
```

---

## Step 2 — Set environment variables

```bash
export CLOUDFLARE_API_TOKEN="your_token_here"
export FLY_API_TOKEN="your_token_here"
```

---

## Step 3 — Fill in terraform.tfvars

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — fill in all values (see comments in the file)
```

---

## Step 4 — Initialize and apply

```bash
cd infra/terraform

# Download providers
terraform init

# Preview what will be created (no changes yet)
terraform plan -var-file=terraform.tfvars

# Apply — creates R2 buckets + Fly.io secrets
terraform apply -var-file=terraform.tfvars
# Type "yes" when prompted
```

Expected output after apply:
```
Apply complete! Resources: 6 added, 0 changed, 0 destroyed.

Outputs:
fly_app_name     = "racejudge-api"
r2_audio_bucket  = "racejudge-audio"
r2_raw_bucket    = "racejudge-raw"
```

---

## Step 5 — Create R2 API keys (manual — cannot be done via Terraform)

Terraform creates the buckets but NOT the R2 API keys. Do this manually:

1. Cloudflare dashboard → R2 → **Manage R2 API tokens**
2. Click **Create API token**
3. Select **Object Read & Write** permission
4. Under **Specify bucket(s)**, select: `racejudge-raw`, `racejudge-audio`, `racejudge-telemetry`
5. Click **Create API Token**
6. Copy **Access Key ID** → `R2_ACCESS_KEY_ID` in `.env`
7. Copy **Secret Access Key** → `R2_SECRET_ACCESS_KEY` in `.env`
8. Copy **Account ID** → `R2_ACCOUNT_ID` in `.env`

---

## Step 6 — Deploy the API to Fly.io

```bash
# From repo root
fly deploy

# First-time only: create the app first
fly apps create racejudge-api --org racejudge-hq

# Then deploy
fly deploy

# Check it's running
fly status
fly logs
```

---

## What Terraform manages vs. what it doesn't

| Resource | Managed by Terraform | Manual |
|---|---|---|
| R2 buckets (3) | ✅ | |
| Fly.io app | ✅ | |
| Fly.io secrets (env vars) | ✅ | |
| R2 API keys | | ✅ Cloudflare dashboard |
| Neon Postgres | | ✅ neon.tech dashboard |
| Clerk application | | ✅ clerk.com dashboard |
| DNS / domain | | ✅ domain registrar |

---

## Destroy everything (if needed)

```bash
cd infra/terraform
terraform destroy -var-file=terraform.tfvars
```
