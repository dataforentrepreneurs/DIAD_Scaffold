<# 
Phase 9.2 Cloud Run Deploy (client project) — BUILD ONCE, DEPLOY TWICE

Usage:
  powershell -ExecutionPolicy Bypass -File scripts/phase9/9_2_deploy_cloud_run.ps1 `
    -key_file keys/client-service-account.json

  - Deploy pre-built versioned image (Recommended for production):
    powershell -ExecutionPolicy Bypass -File scripts/phase9/9_2_deploy_cloud_run.ps1 `
      -SkipBuild -ImageRef "asia-southeast1-docker.pkg.dev/<PROJECT_ID>/diad/diad-engine:v1.0.0"

  - Grant internal chat invoker permission:
    powershell -ExecutionPolicy Bypass -File scripts/phase9/9_2_deploy_cloud_run.ps1 `
      -key_file keys/client-service-account.json `
      -InternalInvokers @("admin@yourcompany.com")

Notes:
- Deploys internal + external from the same image
- Injects secrets from Secret Manager into env vars (OPENAI_API_KEY, GEMINI_API_KEY, PINECONE_API_KEY, etc.)
#>

param(
  [string]$ConfigPath = "config/client_rawdata.json",
  [string]$key_file,
  [string]$InternalService = "diad-internal-chat",
  [string]$ExternalService = "diad-external-chat",
  [bool]$ExternalPublic = $true,
  [string]$InternalIngress = "internal-and-cloud-load-balancing",
  [string[]]$InternalInvokers = @(),
  [string]$SourceDir = ".",
  [switch]$SkipBuild,
  [string]$ImageRef,


  # Artifact Registry repo to push the built image
  # You currently have "cloud-run-source-deploy" in asia-southeast1 (Google-managed) — we reuse it.
  [string]$ArtifactRepo = "cloud-run-source-deploy",

  # Image name in Artifact Registry
  [string]$ImageName = "diad-chatbot",

  # Optional tag override (else timestamp)
  [string]$ImageTag
)

$ErrorActionPreference = "Stop"

# Always use gcloud.cmd on Windows
$GCLOUD = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (-not $GCLOUD) { $GCLOUD = (Get-Command gcloud -ErrorAction SilentlyContinue).Source }
if (-not $GCLOUD) { throw "gcloud not found on PATH" }

Write-Host "=== Phase 9.2 Cloud Run Deploy (client project) [build once, deploy twice] ==="
Write-Host "ConfigPath: $ConfigPath"
Write-Host "SourceDir:  $SourceDir"
Write-Host "gcloud:     $GCLOUD"

function Require([string]$name, [string]$val) {
  if ([string]::IsNullOrWhiteSpace($val)) {
    throw "Required value '$name' is empty/unset. Fix config/client_rawdata.json or script params."
  }
}

if (-not (Test-Path $ConfigPath)) { throw "Config not found: $ConfigPath" }
$cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json

$PROJECT    = $cfg.client.project_id
$REGION     = $cfg.gcp.region
$RUNTIME_SA = $cfg.gcp.chatbot_access_sa

Require "client.project_id" $PROJECT
Require "gcp.region" $REGION
Require "gcp.chatbot_access_sa" $RUNTIME_SA
Require "SourceDir" $SourceDir

# Allow key_file to come from config if not passed
if (-not $key_file) {
  $key_file = $cfg.gcp.key_file
  if (-not $key_file) { $key_file = $cfg.gcp."key-file" }
}

if (-not $key_file -or -not (Test-Path $key_file)) {
  throw "key_file missing. Provide -key_file or set gcp.key_file in config/client_rawdata.json"
}

# Ensure no impersonation is set
try { & $GCLOUD config unset auth/impersonate_service_account | Out-Null } catch {}
Remove-Item Env:CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT -ErrorAction SilentlyContinue

# Auth then set project
& $GCLOUD auth activate-service-account --key-file "$key_file" | Out-Null
& $GCLOUD config set project $PROJECT | Out-Null
& $GCLOUD config set run/region $REGION | Out-Null

Write-Host ""
Write-Host "--- Active identity ---"
& $GCLOUD auth list

Write-Host ""
Write-Host "--- Enable required APIs (idempotent) ---"
& $GCLOUD services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  iam.googleapis.com `
  iamcredentials.googleapis.com `
  secretmanager.googleapis.com | Out-Null

function ConvertTo-IamMember([string]$principal) {
  if ($principal -match "@.*gserviceaccount\.com$") { return "serviceAccount:$principal" }
  if ($principal -match "^(user|serviceAccount|group):") { return $principal }
  return "user:$principal"
}

function Grant-ProjectRole([string]$member, [string]$role) {
  $m = ConvertTo-IamMember $member
  & $GCLOUD projects add-iam-policy-binding $PROJECT `
    --member="$m" --role="$role" | Out-Null
  Write-Host ("Project IAM: {0} -> {1}" -f $m, $role)
}

function Grant-RunInvoker([string]$service, [string]$member) {
  $m = ConvertTo-IamMember $member
  & $GCLOUD run services add-iam-policy-binding $service `
    --project=$PROJECT --region=$REGION `
    --member="$m" --role="roles/run.invoker" | Out-Null
  Write-Host ("Invoker: {0} -> {1}" -f $service, $m)
}

function Remove-AllUsers-Invoker([string]$service) {
  try {
    & $GCLOUD run services remove-iam-policy-binding $service `
      --project=$PROJECT --region=$REGION `
      --member="allUsers" --role="roles/run.invoker" | Out-Null
    Write-Host ("Removed allUsers invoker on {0} (if it existed)" -f $service)
  } catch {
    Write-Host ("allUsers invoker not present on {0} (ok)" -f $service)
  }
}

# Runtime SA minimum permissions
Write-Host ""
Write-Host "--- Ensure runtime SA permissions (idempotent) ---"
Grant-ProjectRole $RUNTIME_SA "roles/bigquery.jobUser"
Grant-ProjectRole $RUNTIME_SA "roles/bigquery.dataViewer"
Grant-ProjectRole $RUNTIME_SA "roles/secretmanager.secretAccessor"

# Common env vars (kept same as your current design)
# NOTE: This assumes config/ is included in the image (Dockerfile copies repo). If not, we can switch to DIAD_CONFIG_JSON.
$commonEnv = @(
  "DIAD_CONFIG=$ConfigPath",
  "DIAD_PROJECT_ID=$PROJECT",
  "DIAD_REGION=$REGION"
) -join ","

# Dynamic Secrets mapping (Secret Manager -> env var)
$gcloudSecrets = (& $GCLOUD secrets list --project $PROJECT --format="value(name)")

$candidateSecrets = @(
  @{ env = "OPENAI_API_KEY"; secret = "OPENAI_API_KEY" },
  @{ env = "GEMINI_API_KEY"; secret = "GEMINI_API_KEY" },
  @{ env = "PINECONE_API_KEY"; secret = "PINECONE_API_KEY" },
  @{ env = "NOTION_API_KEY"; secret = "NOTION_TOKEN" },
  @{ env = "NOTION_API_KEY"; secret = "NOTION_API_KEY" },
  @{ env = "CONFLUENCE_API_TOKEN"; secret = "CONFLUENCE_TOKEN" },
  @{ env = "CONFLUENCE_API_TOKEN"; secret = "CONFLUENCE_API_TOKEN" }
)

$secrets = @()
$seenEnvs = @{}
foreach ($item in $candidateSecrets) {
  $envName = $item.env
  $secName = $item.secret
  if (-not $seenEnvs[$envName] -and ($gcloudSecrets -contains $secName)) {
    $secrets += "$envName=$secName`:latest"
    $seenEnvs[$envName] = $true
  }
}



# -----------------------------
# Build image once (or skip)
# -----------------------------

if ($SkipBuild) {
  if ($ImageRef) {
    $IMAGE = $ImageRef
  } elseif ($ImageTag) {
    $IMAGE = "ghcr.io/dataforentrepreneurs/diad-engine:" + $ImageTag
  } else {
    $IMAGE = "ghcr.io/dataforentrepreneurs/diad-engine:latest"
  }

  Write-Host ""
  Write-Host "--- SkipBuild enabled: reusing existing image ---"
  Write-Host ("Image: {0}" -f $IMAGE)

} else {

  if (-not $ImageTag) {
    $ImageTag = (Get-Date -Format "yyyyMMdd-HHmmss")
  }

  # Ensure Artifact Registry repository exists
  try {
    & $GCLOUD artifacts repositories describe $ArtifactRepo --project $PROJECT --location $REGION | Out-Null
  } catch {
    Write-Host "Creating Artifact Registry repository '$ArtifactRepo' in $REGION..."
    & $GCLOUD artifacts repositories create $ArtifactRepo --repository-format=docker --location $REGION --project $PROJECT | Out-Null
  }

  $IMAGE = "$REGION-docker.pkg.dev/$PROJECT/$ArtifactRepo/$ImageName" + ":" + $ImageTag


  Write-Host ""
  Write-Host "--- Build once (Cloud Build -> Artifact Registry) ---"
  Write-Host ("Image: {0}" -f $IMAGE)

  if (-not (Test-Path $SourceDir)) { throw "SourceDir not found: $SourceDir" }

  # Start build without trying to stream logs
  $buildId = & $GCLOUD builds submit $SourceDir `
    --project $PROJECT `
    --region $REGION `
    --tag $IMAGE `
    --async `
    --format="value(id)"

  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($buildId)) {
    throw "Cloud Build submission failed."
  }

  Write-Host ("Cloud Build started: {0}" -f $buildId)
  Write-Host "Polling build status..."

  while ($true) {
    $status = & $GCLOUD builds describe $buildId `
      --project $PROJECT `
      --region $REGION `
      --format="value(status)"
    Write-Host ("Build status: {0}" -f $status)

    if ($status -eq "SUCCESS") { break }
    if ($status -in @("FAILURE","CANCELLED","TIMEOUT")) {
      throw "Cloud Build ended with status: $status (build id: $buildId)"
    }
    Start-Sleep -Seconds 5
  }
}
# -----------------------------

# Deploy INTERNAL from image
Write-Host ""
Write-Host "Deploying INTERNAL..."
& $GCLOUD run deploy $InternalService `
  --project=$PROJECT `
  --region=$REGION `
  --image $IMAGE `
  --memory=2Gi `
  --cpu=1 `
  --no-allow-unauthenticated `
  --ingress=$InternalIngress `
  --service-account=$RUNTIME_SA `
  --set-env-vars "$commonEnv,APP_MODULE=chatbot.internal_api:app" `
  --set-secrets ($secrets -join ",")

# Ensure internal is not public
Remove-AllUsers-Invoker $InternalService

# Grant invoker to the *currently active* identity (useful for admin/testing)
$ACTIVE = (& $GCLOUD config get-value account).Trim()
if (-not [string]::IsNullOrWhiteSpace($ACTIVE)) {
  Grant-RunInvoker $InternalService $ACTIVE
}

# Grant additional internal invokers (optional)
foreach ($p in $InternalInvokers) {
  if (-not [string]::IsNullOrWhiteSpace($p)) { Grant-RunInvoker $InternalService $p }
}

# Deploy EXTERNAL from same image
Write-Host ""
Write-Host "Deploying EXTERNAL..."
if ($ExternalPublic) {
  & $GCLOUD run deploy $ExternalService `
    --project=$PROJECT `
    --region=$REGION `
    --image $IMAGE `
    --memory=2Gi `
    --cpu=1 `
    --allow-unauthenticated `
    --ingress=all `
    --service-account=$RUNTIME_SA `
    --set-env-vars "$commonEnv,APP_MODULE=chatbot.external_api:app" `
    --set-secrets ($secrets -join ",")
} else {
  & $GCLOUD run deploy $ExternalService `
    --project=$PROJECT `
    --region=$REGION `
    --image $IMAGE `
    --memory=2Gi `
    --cpu=1 `
    --no-allow-unauthenticated `
    --ingress=all `
    --service-account=$RUNTIME_SA `
    --set-env-vars "$commonEnv,APP_MODULE=chatbot.external_api:app" `
    --set-secrets ($secrets -join ",")
}


Write-Host ""
Write-Host "Deploy complete."
Write-Host ("Built image: {0}" -f $IMAGE)

Write-Host ""
Write-Host "Service URLs:"
& $GCLOUD run services describe $InternalService --project=$PROJECT --region=$REGION --format="value(status.url)"
& $GCLOUD run services describe $ExternalService --project=$PROJECT --region=$REGION --format="value(status.url)"
