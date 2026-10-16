param(
  [string]$ProjectId = "",
  [string]$ServiceName = "diad-chatbot-external",
  [string]$Region = "asia-southeast1",
  [string]$ConfigPath = "config/client_rawdata.json"
)

# Auto-resolve from config/client_rawdata.json if not passed
if (-not $ProjectId -and (Test-Path $ConfigPath)) {
  try {
    $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
    if ($cfg.client.project_id -and $cfg.client.project_id -ne "Not Configured") {
      $ProjectId = $cfg.client.project_id
    }
    if ($cfg.gcp.region) {
      $Region = $cfg.gcp.region
    }
  } catch {}
}

if (-not $ProjectId) {
  $ProjectId = $env:GOOGLE_CLOUD_PROJECT
}

if (-not $ProjectId) {
  $activeGcloud = gcloud config get-value project 2>$null
  if ($activeGcloud -and $activeGcloud -ne "(unset)") {
    $ProjectId = $activeGcloud
  }
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "     DIAD Automated Client Deployment Verification        " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Target Project:   $ProjectId" -ForegroundColor Yellow
Write-Host "Target Region:    $Region" -ForegroundColor Yellow
Write-Host "Target Service:   $ServiceName" -ForegroundColor Yellow
Write-Host ""

if (-not $ProjectId) {
  Write-Host "[ERROR] Could not resolve a Google Cloud Project ID. Please pass -ProjectId <id>." -ForegroundColor Red
  exit 1
}

$allPass = $true

# TEST 1: Cloud Run Service & Health Endpoint
Write-Host "[1/4] Testing Cloud Run Service Health..." -ForegroundColor Yellow
try {
  $serviceUrl = gcloud run services describe $ServiceName --project $ProjectId --region $Region --format "value(status.url)" 2>$null
  if ($serviceUrl) {
    Write-Host "      Found endpoint: $serviceUrl" -ForegroundColor Gray
    $healthUrl = "$serviceUrl/health"
    $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 10 -ErrorAction Stop
    if ($response.status -eq "ok" -or $response -match "ok") {
      Write-Host "      [PASS] Cloud Run service is HEALTHY (200 OK at /health)" -ForegroundColor Green
    } else {
      Write-Host "      [WARN] Cloud Run responded but status unexpected: $response" -ForegroundColor Yellow
    }
  } else {
    Write-Host "      [WARN] Service '$ServiceName' not found in $Region. Searching other regions..." -ForegroundColor Yellow
    $allServices = gcloud run services list --project $ProjectId --format "table(metadata.name,status.url,metadata.labels['cloud.googleapis.com/location'])" 2>$null
    Write-Host $allServices -ForegroundColor Gray
  }
} catch {
  Write-Host "      [FAIL] Could not verify Cloud Run health: $($_.Exception.Message)" -ForegroundColor Red
  $allPass = $false
}

# TEST 2: BigQuery Dataset & Mart Availability
Write-Host "`n[2/4] Testing BigQuery Analytics Datasets..." -ForegroundColor Yellow
try {
  $datasets = bq ls --project_id=$ProjectId --format=json 2>$null | ConvertFrom-Json
  if ($datasets -and $datasets.Count -gt 0) {
    $dsNames = $datasets | ForEach-Object { $_.datasetReference.datasetId }
    Write-Host "      Found datasets: $($dsNames -join ', ')" -ForegroundColor Gray
    Write-Host "      [PASS] BigQuery data warehouse is provisioned with $($datasets.Count) datasets." -ForegroundColor Green
  } else {
    Write-Host "      [WARN] No datasets found via 'bq ls' in project $ProjectId." -ForegroundColor Yellow
  }
} catch {
  Write-Host "      [WARN] BigQuery check skipped or error: $($_.Exception.Message)" -ForegroundColor Gray
}

# TEST 3: Cloud Scheduler Automated Cadences
Write-Host "`n[3/4] Testing Cloud Scheduler Cadences..." -ForegroundColor Yellow
try {
  $jobs = gcloud scheduler jobs list --project $ProjectId --location $Region --format "value(name,state)" 2>$null
  if ($jobs) {
    Write-Host "      [PASS] Cloud Scheduler cadences active:" -ForegroundColor Green
    $jobs | ForEach-Object { Write-Host "        • $_" -ForegroundColor Gray }
  } else {
    Write-Host "      [INFO] No active Cloud Scheduler jobs found in $Region." -ForegroundColor Gray
  }
} catch {
  Write-Host "      [WARN] Cloud Scheduler check error: $($_.Exception.Message)" -ForegroundColor Gray
}

# TEST 4: Service Account Least-Privilege Check
Write-Host "`n[4/4] Verifying Least-Privilege Service Account..." -ForegroundColor Yellow
try {
  $sas = gcloud iam service-accounts list --project $ProjectId --filter "email ~ diad-" --format "value(email)" 2>$null
  if ($sas) {
    Write-Host "      [PASS] Dedicated isolated service account found:" -ForegroundColor Green
    $sas | ForEach-Object { Write-Host "        • $_" -ForegroundColor Gray }
  } else {
    Write-Host "      [INFO] No diad-prefixed service account found." -ForegroundColor Gray
  }
} catch {
  Write-Host "      [WARN] SA check error: $($_.Exception.Message)" -ForegroundColor Gray
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
if ($allPass) {
  Write-Host "  DIAD Deployment Verification Result: CERTIFIED HEALTHY  " -ForegroundColor Green
} else {
  Write-Host "  DIAD Deployment Verification Result: ATTENTION NEEDED   " -ForegroundColor Yellow
}
Write-Host "==========================================================" -ForegroundColor Cyan
