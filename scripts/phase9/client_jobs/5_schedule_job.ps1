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


Write-Host "=== Phase9 Client Jobs: 5) Schedule Cloud Run Job Daily ==="

$ProjectId = Get-ConfigValue $CONFIG_PATH "d.get('client',{}).get('project_id','')"
$Region    = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('region', d.get('client',{}).get('bq_location','asia-southeast1'))"
$Deployer  = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('chatbot_deployer_sa','')"
Require-NonEmpty "client.project_id" $ProjectId
Require-NonEmpty "gcp.chatbot_deployer_sa" $Deployer

gcloud config set project $ProjectId | Out-Null

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

$SchedulerSA = "diad-scheduler@$ProjectId.iam.gserviceaccount.com"

# Allow scheduler SA to run jobs (least friction). You can tighten later to run.invoker on the job.
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& gcloud projects add-iam-policy-binding $ProjectId `
  --member "serviceAccount:$SchedulerSA" `
  --role "roles/run.invoker" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "⚠️ Warning: Failed to grant roles/run.invoker to scheduler SA. Ensure it is granted manually."
}
$ErrorActionPreference = $oldEAP

$uri = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs/$JOB_NAME:run"

# Create or update scheduler job
$exists = $true
try { gcloud scheduler jobs describe $SCHEDULER_NAME --location $Region | Out-Null } catch { $exists = $false }

if (-not $exists) {
  gcloud scheduler jobs create http $SCHEDULER_NAME `
    --location $Region `
    --schedule "$CRON" `
    --time-zone "$TIME_ZONE" `
    --uri "$uri" `
    --http-method POST `
    --oauth-service-account-email "$SchedulerSA" `
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
    --message-body "{}" `
    --headers "Content-Type=application/json"
} else {
  gcloud scheduler jobs update http $SCHEDULER_NAME `
    --location $Region `
    --schedule "$CRON" `
    --time-zone "$TIME_ZONE" `
    --uri "$uri" `
    --http-method POST `
    --oauth-service-account-email "$SchedulerSA" `
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
    --message-body "{}" `
    --headers "Content-Type=application/json"
}

Write-Host "`n✅ Scheduler configured ($CRON $TIME_ZONE)."
Write-Host "Trigger now:"
Write-Host "  gcloud scheduler jobs run $SCHEDULER_NAME --project $ProjectId --location $Region"
