# Phase 9 – Client Jobs (repeatable)

This folder makes Phase 8.2 daily sync (and future jobs) repeatable for a client project.

**Only edit:** `env.ps1` for a new client folder/repo.

Typical flow (PowerShell):
1. `1_bootstrap_project.ps1`   – enable APIs, ensure AR repo, ensure scheduler SA, grant basic IAM
2. `2_upsert_secrets.ps1`      – upsert Secret Manager values (interactive prompt)
3. `3_build_image.ps1`         – build & push jobs image (Cloud Build)
4. `4_deploy_job.ps1`          – deploy Cloud Run Job for Phase 8.2 sync
5. `5_schedule_job.ps1`        – schedule job daily via Cloud Scheduler
6. `9_run_all.ps1`             – runs steps 1 → 5 in order

Notes:
- Uses config file: `config/client_rawdata.json`
- Deployer SA is impersonated via `CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT` (from config).
- Runtime SA (Cloud Run execution identity) is `gcp.chatbot_access_sa` (from config).
