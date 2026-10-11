param(
  [string]$EnvFile = "$PSScriptRoot\env.ps1"
)
$ErrorActionPreference = "Stop"
. $EnvFile
function Get-ConfigValue {
  param([string]$ConfigPath, [string]$Expr)
  $v = python -c "import json; d=json.load(open(r'$ConfigPath','r',encoding='utf-8')); print($Expr)"
  return $v.Trim()
}

function Require-NonEmpty {
  param([string]$Name, [string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value)) { throw "Missing required config value: $Name" }
}


Write-Host "=== Phase9 Client Jobs: 1) Bootstrap Project ==="

$ProjectId = Get-ConfigValue $CONFIG_PATH "d.get('client',{}).get('project_id','')"
$Region    = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('region', d.get('client',{}).get('bq_location','asia-southeast1'))"
$Deployer  = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('chatbot_deployer_sa','')"
$RuntimeSA = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('chatbot_access_sa','')"

Require-NonEmpty "client.project_id" $ProjectId
Require-NonEmpty "gcp.chatbot_deployer_sa" $Deployer
Require-NonEmpty "gcp.chatbot_access_sa" $RuntimeSA

gcloud config set project $ProjectId | Out-Null
gcloud config set run/region $Region | Out-Null

$KeyFile = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('key_file','')"
if ([string]::IsNullOrWhiteSpace($KeyFile)) {
  $KeyFile = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('service_account_key_path','')"
}

if (-not [string]::IsNullOrWhiteSpace($KeyFile) -and (Test-Path $KeyFile)) {
  Write-Host "Activating service account key: $KeyFile"
  gcloud auth activate-service-account $Deployer --key-file=$KeyFile | Out-Null
} else {
  # Fallback to impersonation if no key file
  $env:CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT = $Deployer
}

Write-Host "Project:  $ProjectId"
Write-Host "Region:   $Region"
Write-Host "Deployer: $Deployer"
Write-Host "Runtime:  $RuntimeSA"

Write-Host "`nEnabling required APIs (idempotent)..."
gcloud services enable `
  run.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com `
  secretmanager.googleapis.com `
  cloudscheduler.googleapis.com `
  iam.googleapis.com `
  iamcredentials.googleapis.com | Out-Null

# Temporarily disable Stop preference for exit code checking
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"

Write-Host "`nEnsuring Artifact Registry repo exists: $AR_REPO"
& gcloud artifacts repositories describe $AR_REPO --location=$Region 2>$null | Out-Null
$repoExists = ($LASTEXITCODE -eq 0)

if (-not $repoExists) {
  $ErrorActionPreference = $oldEAP
  & gcloud artifacts repositories create $AR_REPO `
    --repository-format=docker `
    --location=$Region `
    --description="DIAD jobs images" | Out-Null
  $ErrorActionPreference = "SilentlyContinue"
}

$ChatbotRepo = "cloud-run-source-deploy"
Write-Host "Ensuring Artifact Registry repo exists: $ChatbotRepo"
& gcloud artifacts repositories describe $ChatbotRepo --location=$Region 2>$null | Out-Null
$chatbotExists = ($LASTEXITCODE -eq 0)

if (-not $chatbotExists) {
  $ErrorActionPreference = $oldEAP
  & gcloud artifacts repositories create $ChatbotRepo `
    --repository-format=docker `
    --location=$Region `
    --description="DIAD chatbot images" | Out-Null
  $ErrorActionPreference = "SilentlyContinue"
}

# Restore Stop preference
$ErrorActionPreference = $oldEAP

# Ensure scheduler SA exists
$SchedulerSA = "diad-scheduler@$ProjectId.iam.gserviceaccount.com"
$exists = $true
try { gcloud iam service-accounts describe $SchedulerSA --project $ProjectId | Out-Null } catch { $exists = $false }
if (-not $exists) {
  Write-Host "Creating scheduler SA: $SchedulerSA"
  gcloud iam service-accounts create diad-scheduler --project $ProjectId --display-name="DIAD Cloud Scheduler SA" | Out-Null
}

# Minimal IAM for runtime SA: secret accessor + logs
Write-Host "`nGranting runtime SA access (secret accessor, logWriter)..."
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"

& gcloud projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:$RuntimeSA" `
  --role="roles/secretmanager.secretAccessor" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "⚠️ Warning: Failed to grant roles/secretmanager.secretAccessor. Ensure runtime SA has this role manually."
}

& gcloud projects add-iam-policy-binding $ProjectId `
  --member="serviceAccount:$RuntimeSA" `
  --role="roles/logging.logWriter" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "⚠️ Warning: Failed to grant roles/logging.logWriter. Ensure runtime SA has this role manually."
}

$ErrorActionPreference = $oldEAP

Write-Host "`n✅ Bootstrap complete."
