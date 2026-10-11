param(
  [string]$EnvFile = "$PSScriptRoot\env.ps1",
  [string]$ImageRef = ""
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


Write-Host "=== Phase9 Client Jobs: 4) Deploy Cloud Run Job (Phase 8.2 sync) ==="

$ProjectId = Get-ConfigValue $CONFIG_PATH "d.get('client',{}).get('project_id','')"
$Region    = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('region', d.get('client',{}).get('bq_location','asia-southeast1'))"
$Deployer  = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('chatbot_deployer_sa','')"
$RuntimeSA = Get-ConfigValue $CONFIG_PATH "d.get('gcp',{}).get('chatbot_access_sa','')"
Require-NonEmpty "client.project_id" $ProjectId
Require-NonEmpty "gcp.chatbot_deployer_sa" $Deployer
Require-NonEmpty "gcp.chatbot_access_sa" $RuntimeSA

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

if (-not [string]::IsNullOrWhiteSpace($ImageRef)) {
  Write-Host "Deploying Cloud Run Job from pre-built image: $ImageRef"
  gcloud run jobs deploy $JOB_NAME `
    --region $Region `
    --image $ImageRef `
    --service-account $RuntimeSA `
    --command python `
    --args "scripts/phase8/8_2_sync_docs_to_pinecone.py"
} else {
  Write-Host "Deploying Cloud Run Job from source (Cloud Build)..."
  gcloud run jobs deploy $JOB_NAME `
    --region $Region `
    --source $SOURCE_DIR `
    --service-account $RuntimeSA `
    --command python `
    --args "scripts/phase8/8_2_sync_docs_to_pinecone.py","--config",$CONFIG_PATH
}

Write-Host "`n✅ Job deployed."
Write-Host "Run now:"
Write-Host "  gcloud run jobs execute $JOB_NAME --project $ProjectId --region $Region"
