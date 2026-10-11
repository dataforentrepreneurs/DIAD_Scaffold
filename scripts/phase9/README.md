# DIAD Phase 9 — Productionize Chatbots (Internal + External) on Client Project

This phase deploys the **internal** and **external** chatbots to **Cloud Run in the client GCP project** using the pre-built DIAD Engine container (`ghcr.io/dataforentrepreneurs/diad-engine:v1.0.0`):
- **Deployer SA** (impersonated by `gcloud`): `<DEPLOYER_SA>@<PROJECT_ID>.iam.gserviceaccount.com`
- **Runtime SA** (Cloud Run execution identity): `<RUNTIME_SA>@<PROJECT_ID>.iam.gserviceaccount.com`

Config source of truth: `config/client_rawdata.json`

---

## Folder Structure

```
scripts/
  phase9/
    9_0_preflight.py
    9_1_run_local.ps1
    9_2_deploy_cloud_run.ps1
    9_3_smoke_test.ps1
    README.md
```

---

## 9.0 Preflight (local)

Validates BigQuery datasets, tables, and optional external services.

```powershell
python scripts/phase9/9_0_preflight.py --config config/client_rawdata.json
```

**Auth options:**
- Recommended: `gcloud auth application-default login`
- Or provide a Service Account key in `keys/`

---

## 9.1 Run locally (Docker)

Runs the pre-built DIAD engine container locally for smoke testing:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase9/9_1_run_local.ps1 -ConfigPath config/client_rawdata.json
```

---

## 9.2 Deploy to Cloud Run (Client Project)

This script:
- Targets the client project defined in `config/client_rawdata.json`
- Impersonates the deployer Service Account
- Deploys both services: `diad-internal-chat` and `diad-external-chat`
- Pulls the pre-built engine container from GitHub Packages
- Sets the Cloud Run runtime identity to the runtime Service Account
- Injects required Secret Manager secrets as environment variables

```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase9/9_2_deploy_cloud_run.ps1 -ConfigPath config/client_rawdata.json
```

---

## 9.3 Smoke tests

Tests connectivity and health check endpoints on deployed Cloud Run services:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase9/9_3_smoke_test.ps1
```

Notes:
- External service returns a 200 OK health response on `/healthz`.
- Internal service is typically configured as private/IAM-authenticated, so unauthenticated smoke tests will report status code 401/403 as expected.

---

## Troubleshooting

### Permission denied: run.services.get
You are not impersonating the deployer SA or targeting the wrong project.

Fix:
- Ensure `gcloud config set project <PROJECT_ID>`
- Ensure `CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT` is set to `<DEPLOYER_SA>@<PROJECT_ID>.iam.gserviceaccount.com` (the deploy script handles this automatically if configured)

### Runtime errors accessing BigQuery / secrets
Ensure the runtime SA has:
- `roles/bigquery.jobUser`
- `roles/bigquery.dataViewer` (or dataset-level)
- `roles/secretmanager.secretAccessor`
- `roles/logging.logWriter`
