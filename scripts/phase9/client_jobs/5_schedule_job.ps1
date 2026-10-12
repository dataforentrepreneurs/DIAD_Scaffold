param(
  [string]$EnvFile = "$PSScriptRoot\env.ps1"
)
$ErrorActionPreference = "Stop"
if (Test-Path $EnvFile) { . $EnvFile }

function Get-ConfigJson {
  param([string]$ConfigPath)
  if (-not (Test-Path $ConfigPath)) {
    if (Test-Path "config/client_rawdata.json") { $ConfigPath = "config/client_rawdata.json" }
    elseif (Test-Path "scaffold/config/client_rawdata.json") { $ConfigPath = "scaffold/config/client_rawdata.json" }
  }
  $raw = Get-Content $ConfigPath -Raw -Encoding UTF8
  return ($raw | ConvertFrom-Json)
}

Write-Host "=== DIAD Multi-Cadence Cloud Scheduler Provisioning ===" -ForegroundColor Cyan

$cfgPath = if ($CONFIG_PATH) { $CONFIG_PATH } else { "config/client_rawdata.json" }
$cfg = Get-ConfigJson $cfgPath

$ProjectId = $cfg.client.project_id
if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "YOUR_PROJECT_ID" -or $ProjectId -eq "Not Configured") {
  if (Test-Path "scaffold/config/client_rawdata.json") {
    $scaffoldCfg = Get-ConfigJson "scaffold/config/client_rawdata.json"
    if ($scaffoldCfg.client.project_id -and $scaffoldCfg.client.project_id -ne "Not Configured") {
      $ProjectId = $scaffoldCfg.client.project_id
    }
  }
  if (-not $ProjectId -or $ProjectId -eq "Not Configured") {
    $ProjectId = (& gcloud config get-value project 2>$null).Trim()
  }
}
if ([string]::IsNullOrWhiteSpace($ProjectId)) {
  throw "client.project_id missing or not configured in $cfgPath"
}

$Region = $cfg.gcp.region
if (-not $Region) { $Region = $cfg.client.bq_location }
if (-not $Region) { $Region = "asia-southeast1" }

gcloud config set project $ProjectId | Out-Null

# Service account for scheduler (use runtime SA or diad-onboarding)
$SchedulerSA = $cfg.gcp.chatbot_access_sa
if (-not $SchedulerSA -or $SchedulerSA -eq "YOUR_RUNTIME_SERVICE_ACCOUNT_EMAIL") {
  $SchedulerSA = "diad-onboarding@$ProjectId.iam.gserviceaccount.com"
}
Write-Host "Using Scheduler Invoker Identity: $SchedulerSA" -ForegroundColor Cyan

# Read cadence schedules
$schedules = $cfg.schedules
$timeZone = if ($schedules.timezone) { $schedules.timezone } else { "Asia/Singapore" }

$jobUriBase = "https://$Region-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$ProjectId/jobs"
$docsJobUri = "$jobUriBase/diad-phase8-sync-docs:run"
$ecomJobUri = "$jobUriBase/diad-phase-jobs:run"

function Sync-SchedulerJob {
  param(
    [string]$JobName,
    [bool]$Enabled,
    [string]$Cron,
    [string]$Tz,
    [string]$Uri,
    [string]$Body = "{}"
  )

  $exists = $false
  try {
    $desc = gcloud scheduler jobs describe $JobName --location $Region --project $ProjectId 2>$null
    if ($desc) { $exists = $true }
  } catch {
    $exists = $false
  }

  if ($Enabled -and -not [string]::IsNullOrWhiteSpace($Cron)) {
    if (-not $exists) {
      Write-Host "Creating Cloud Scheduler job [$JobName] ($Cron $Tz)..." -ForegroundColor Cyan
      gcloud scheduler jobs create http $JobName `
        --location $Region `
        --project $ProjectId `
        --schedule "$Cron" `
        --time-zone "$Tz" `
        --uri "$Uri" `
        --http-method POST `
        --oauth-service-account-email "$SchedulerSA" `
        --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
        --message-body "$Body" `
        --headers "Content-Type=application/json" | Out-Null
    } else {
      Write-Host "Updating Cloud Scheduler job [$JobName] ($Cron $Tz)..." -ForegroundColor Cyan
      gcloud scheduler jobs update http $JobName `
        --location $Region `
        --project $ProjectId `
        --schedule "$Cron" `
        --time-zone "$Tz" `
        --uri "$Uri" `
        --http-method POST `
        --oauth-service-account-email "$SchedulerSA" `
        --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" `
        --message-body "$Body" `
        --update-headers "Content-Type=application/json" | Out-Null
    }
    Write-Host "  ✅ [$JobName] ACTIVE -> Schedule: '$Cron' ($Tz)" -ForegroundColor Green
  } else {
    if ($exists) {
      Write-Host "Removing disabled scheduler job [$JobName]..." -ForegroundColor Yellow
      gcloud scheduler jobs delete $JobName --location $Region --project $ProjectId --quiet | Out-Null
      Write-Host "  🗑️ [$JobName] REMOVED" -ForegroundColor Gray
    } else {
      Write-Host "  ⏸️ [$JobName] DISABLED (Not scheduled)" -ForegroundColor Gray
    }
  }
}

Write-Host "`n--- Configuring Cloud Schedulers for Project: $ProjectId ($Region) ---" -ForegroundColor Yellow

# 1. Ecommerce Data Sync (Daily orders, payments, shipments -> BigQuery)
$ecomCfg = $schedules.ecommerce_pipeline
$ecomEnabled = if ($ecomCfg) { [bool]$ecomCfg.enabled } else { $true }
$ecomCron = if ($ecomCfg.cron) { $ecomCfg.cron } else { "0 2 * * *" }
Sync-SchedulerJob "diad-sched-ecommerce" $ecomEnabled $ecomCron $timeZone $ecomJobUri

# 2. Google Drive Docs Sync (Daily incremental check on modified return policies)
$gdriveCfg = $schedules.knowledge_base.gdrive
$gdriveEnabled = if ($gdriveCfg) { [bool]$gdriveCfg.enabled } else { $true }
$gdriveCron = if ($gdriveCfg.cron) { $gdriveCfg.cron } else { "0 3 * * *" }
Sync-SchedulerJob "diad-sched-docs-gdrive" $gdriveEnabled $gdriveCron $timeZone $docsJobUri

# 3. Confluence Knowledge Base Sync (Weekly company policies & handbooks)
$confCfg = $schedules.knowledge_base.confluence
$confEnabled = if ($confCfg) { [bool]$confCfg.enabled } else { $true }
$confCron = if ($confCfg.cron) { $confCfg.cron } else { "0 3 * * 0" }
Sync-SchedulerJob "diad-sched-docs-confluence" $confEnabled $confCron $timeZone $docsJobUri

# 4. Notion Product Specs Sync (Weekly product catalog rules)
$notionCfg = $schedules.knowledge_base.notion
$notionEnabled = if ($notionCfg) { [bool]$notionCfg.enabled } else { $true }
$notionCron = if ($notionCfg.cron) { $notionCfg.cron } else { "0 4 * * 0" }
Sync-SchedulerJob "diad-sched-docs-notion" $notionEnabled $notionCron $timeZone $docsJobUri

Write-Host "`n=== Cloud Scheduler Configuration Summary ===" -ForegroundColor Green
gcloud scheduler jobs list --location $Region --project $ProjectId
Write-Host ""
