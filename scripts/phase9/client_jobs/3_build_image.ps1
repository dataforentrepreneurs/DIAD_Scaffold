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


Write-Host "=== Phase9 Client Jobs: 3) Build Jobs Image ==="

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

$img = "$Region-docker.pkg.dev/$ProjectId/$AR_REPO/$IMAGE_NAME`:$IMAGE_TAG"
Write-Host "Building: $img"

# Copy Dockerfile to root temporarily as gcloud builds submit doesn't support custom Dockerfile path directly
Copy-Item scripts/phase9/jobs/Dockerfile.jobs Dockerfile
try {
  gcloud builds submit --tag $img $SOURCE_DIR
} finally {
  Remove-Item Dockerfile -ErrorAction SilentlyContinue
}

Write-Host "`n✅ Build complete."
