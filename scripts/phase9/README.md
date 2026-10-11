# DIAD Phase 9 — Productionize Chatbots (Internal + External) on Client Project

This phase deploys your **internal** and **external** FastAPI chatbots to **Cloud Run in the client project** using:
- **Deployer SA** (impersonated by `gcloud`): `chatbot-deploy-clientside@diamante-diad3.iam.gserviceaccount.com`
- **Runtime SA** (Cloud Run execution identity): `chatbot-access-sources-clients@diamante-diad3.iam.gserviceaccount.com`

Config source of truth: `config/client_rawdata.json` (you uploaded/maintain this per client). fileciteturn0file0

---

## Folder structure

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

Checks BigQuery + optionally Pinecone.

```powershell
python scripts/phase9/9_0_preflight.py --config config/client_rawdata.json
```

**Auth options**
- Recommended: `gcloud auth application-default login`
- Or set `GOOGLE_APPLICATION_CREDENTIALS` to a keyfile

---

## 9.1 Run locally (optional)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase9/9_1_run_local.ps1 -ConfigPath config/client_rawdata.json
```

---

## 9.2 Deploy to Cloud Run (client project)

This script:
- targets client project `diamante-diad3`
- impersonates deployer SA `chatbot-deploy-clientside@diamante-diad3.iam.gserviceaccount.com`
- deploys 2 services: `diad-internal-chat`, `diad-external-chat`
- sets Cloud Run runtime identity to `chatbot-access-sources-clients@diamante-diad3.iam.gserviceaccount.com`

```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase9/9_2_deploy_cloud_run.ps1 -ConfigPath config/client_rawdata.json
```

---

## 9.3 Smoke tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts/phase9/9_3_smoke_test.ps1
```

Notes:
- External should return health response (200).
- Internal is typically private, so unauthenticated smoke test may fail (expected).

---

## Troubleshooting

### Permission denied: run.services.get
You are not impersonating the deployer SA or targeting the wrong project.

Fix:
- Ensure `gcloud config set project diamante-diad3`
- Ensure `CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT` is set to `chatbot-deploy-clientside@diamante-diad3.iam.gserviceaccount.com` (the deploy script does this)

### Runtime errors accessing BigQuery / secrets
Ensure runtime SA `chatbot-access-sources-clients@diamante-diad3.iam.gserviceaccount.com` has:
- `roles/bigquery.jobUser`
- `roles/bigquery.dataViewer` (or dataset-level)
- `roles/secretmanager.secretAccessor`
- `roles/logging.logWriter`
