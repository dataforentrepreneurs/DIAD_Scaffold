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


Write-Host "=== Phase9 Client Jobs: 2) Upsert Secrets ==="

$ProjectId = Get-ConfigValue $CONFIG_PATH "d.get('client',{}).get('project_id','')"
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

foreach ($name in $SECRETS) {
  $val = Read-Host -Prompt "Enter value for secret $name (will create new version)"
  if ([string]::IsNullOrWhiteSpace($val)) {
    Write-Host "Skipping $name (empty)"
    continue
  }
  Write-Host "Upserting secret: $name"
  $val | gcloud secrets create $name --data-file=- 2>$null | Out-Null
  $val | gcloud secrets versions add $name --data-file=- | Out-Null
}

Write-Host "`n✅ Secrets upsert complete."
