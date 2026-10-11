# SETUP_GCP.md

## Google Cloud Platform (GCP) Setup for DIAD Agent

This document outlines the steps required to provision the GCP resources needed for the DIAD onboarding pipeline.

### 1️⃣ Create a GCP Project
1. Sign in to the Google Cloud Console: https://console.cloud.google.com/
2. Click **Select a project** → **New Project**.
3. Give it a descriptive name (e.g., `diad-onboarding`).
4. Note the **Project ID** – you will need it for the environment variables.

### 2️⃣ Service Account & Credentials
1. In the Cloud Console, navigate to **IAM & Admin → Service Accounts**.
2. Click **+ CREATE SERVICE ACCOUNT**.
   - Name: `diad-client-sa`
   - Description: Service account for DIAD onboarding scripts.
3. Grant the following roles (adjust as needed):
   - **Editor** (or more granular roles: Cloud Run Admin, Cloud Build Editor, Storage Admin, IAM Service Account User)
4. Click **DONE**.
5. Select the newly created service account and click **KEYS → Add Key → Create new key** (JSON).
6. Download the key file and place it under the repository at `keys/client-service-account.json` (this path is already listed in `.gitignore`).

### 3️⃣ Enable Required APIs
Run the following command (or enable via the console):
```bash
 gcloud services enable \
   cloudbuild.googleapis.com \
   run.googleapis.com \
   iam.googleapis.com \
   storage.googleapis.com \
   compute.googleapis.com
```

### 4️⃣ Configure Environment Variables
Create (or copy) the example environment files and fill in the values:
- `env.sh.example` → `env.sh`
- `env.ps1.example` → `env.ps1`

Set the following variables:
```bash
export GOOGLE_CLOUD_PROJECT="YOUR_GCP_PROJECT_ID"
export GOOGLE_APPLICATION_CREDENTIALS="keys/client-service-account.json"
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"   # if using OpenAI
export PINECONE_API_KEY="YOUR_PINECONE_API_KEY"
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

### 5️⃣ (Optional) Terraform Provisioning
If you prefer IaC, you can create a `terraform/` directory with the following basic configuration:
```hcl
provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_service_account" "diad_sa" {
  account_id   = "diad-client-sa"
  display_name = "DIAD onboarding service account"
}

# Add other resources (Cloud Run services, Cloud Build triggers, etc.) as needed.
```
Run `terraform init && terraform apply` to provision.

### 6️⃣ Verify Setup
1. Source the environment file:
   ```bash
   source env.sh   # or .\env.ps1 on Windows PowerShell
   ```
2. Test the credentials:
   ```bash
   gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS
   gcloud config set project $GOOGLE_CLOUD_PROJECT
   gcloud projects describe $GOOGLE_CLOUD_PROJECT
   ```
   You should see project details without error.
3. Run a quick pipeline sanity check:
   ```bash
   python scripts/onboarding_dashboard.py --dry-run
   ```
   It should complete the pre‑flight checks.

---
**Tip**: Keep the `keys/` directory excluded via `.gitignore` to avoid committing secrets.

Feel free to adjust the steps to match your organizational policies.
