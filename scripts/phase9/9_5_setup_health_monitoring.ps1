param(
  [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
  [string]$Region = "asia-southeast1",
  [string]$ServiceName = "diad-external-chat",
  [string]$ServiceUrl = "",
  [string]$AlertEmail = "",
  [string]$ConfigPath = "config/client_rawdata.json"
)

# 1. Resolve Project ID & Region from config if not provided
if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "Not Configured") {
  if (Test-Path $ConfigPath) {
    try {
      $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
      if ($cfg.client.project_id -and $cfg.client.project_id -ne "Not Configured") {
        $ProjectId = $cfg.client.project_id
      }
      if ($cfg.gcp.region) { $Region = $cfg.gcp.region }
      if ($cfg.client.business_email -and [string]::IsNullOrWhiteSpace($AlertEmail)) {
        $AlertEmail = $cfg.client.business_email
      }
    } catch {}
  }
}

if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "Not Configured") {
  $ProjectId = (gcloud config get-value project 2>$null)
}

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
  Write-Error "Could not determine Google Cloud Project ID. Please specify -ProjectId."
  exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  DIAD Gate 6: Cloud Monitoring Uptime & Health Check Setup" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Project:           $ProjectId" -ForegroundColor Yellow
Write-Host "Region:            $Region" -ForegroundColor Yellow
Write-Host "Target Service:    $ServiceName" -ForegroundColor Yellow
if ($AlertEmail) {
  Write-Host "Alert Email:       $AlertEmail" -ForegroundColor Yellow
}
Write-Host ""

# 2. Query Cloud Run Service URL
if ([string]::IsNullOrWhiteSpace($ServiceUrl)) {
  Write-Host "Querying Cloud Run endpoint for service '$ServiceName'..." -ForegroundColor Gray
  $serviceUrl = (gcloud run services describe $ServiceName --project $ProjectId --region $Region --quiet --format="value(status.url)" 2>$null)
  
  if ([string]::IsNullOrWhiteSpace($serviceUrl)) {
    # Fallback query for common naming variations
    $altServiceName = "diad-chatbot-external"
    $serviceUrl = (gcloud run services describe $altServiceName --project $ProjectId --region $Region --quiet --format="value(status.url)" 2>$null)
    if (-not [string]::IsNullOrWhiteSpace($serviceUrl)) {
      $ServiceName = $altServiceName
    }
  }
} else {
  $serviceUrl = $ServiceUrl
}

if ([string]::IsNullOrWhiteSpace($serviceUrl)) {
  Write-Host "Notice: No active Cloud Run service found for '$ServiceName' in region '$Region'." -ForegroundColor Yellow
  Write-Host "This is normal if the sandbox was recently reset or Cloud Run has not been deployed yet." -ForegroundColor Gray
  Write-Host "Once you deploy via scripts/phase9/9_2_deploy_cloud_run.ps1, re-run this script to automatically configure the 1-minute Uptime Check." -ForegroundColor Gray
  Write-Host "`nYou can also configure it directly in the GCP Console at:" -ForegroundColor Cyan
  Write-Host "https://console.cloud.google.com/monitoring/uptime?project=$ProjectId" -ForegroundColor White -BackgroundColor Black
  exit 0
}

Write-Host "Found Service Endpoint: $serviceUrl" -ForegroundColor Green
$healthUrl = "$serviceUrl/health"

# 3. Test Endpoint Live Response
Write-Host "Testing health endpoint live: $healthUrl..." -ForegroundColor Gray
try {
  $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 10
  Write-Host "Live Health Check Result: OK ($($response | ConvertTo-Json -Compress))" -ForegroundColor Green
} catch {
  Write-Warning "Live check returned error: $_. Please verify service is running."
}

# 4. Enable Google Cloud Monitoring API
Write-Host "`nEnsuring Google Cloud Monitoring API is enabled..." -ForegroundColor Gray
gcloud services enable monitoring.googleapis.com --project $ProjectId 2>$null

# 5. Extract Hostname for Uptime Check
$uri = [System.Uri]$serviceUrl
$hostName = $uri.Host

$checkDisplayName = "DIAD-Health-Check-$ServiceName"
Write-Host "Setting up 1-minute HTTPS Uptime Check for '$hostName/health'..." -ForegroundColor Gray

# Create Cloud Monitoring Notification Channel (Email) if provided
$channelId = $null
if (-not [string]::IsNullOrWhiteSpace($AlertEmail)) {
  Write-Host "Ensuring notification channel exists for '$AlertEmail'..." -ForegroundColor Gray
  $channelList = (gcloud beta monitoring channels list --project $ProjectId --filter="type=email AND labels.email_address=$AlertEmail" --format="value(name)" 2>$null)
  if ($channelList) {
    $channelId = $channelList | Select-Object -First 1
    Write-Host "Using existing email channel: $channelId" -ForegroundColor Gray
  } else {
    $channelJson = @"
{
  "type": "email",
  "displayName": "DIAD Admin Alerts ($AlertEmail)",
  "labels": {
    "email_address": "$AlertEmail"
  }
}
"@
    $tempChannelFile = [System.IO.Path]::GetTempFileName() + ".json"
    $channelJson | Set-Content $tempChannelFile -Encoding UTF8
    $channelId = (gcloud beta monitoring channels create --project $ProjectId --channel-content-from-file=$tempChannelFile --format="value(name)" 2>$null)
    Remove-Item $tempChannelFile -Force 2>$null
    if ($channelId) {
      Write-Host "Created email notification channel: $channelId" -ForegroundColor Green
    }
  }
}

# 6. Create Uptime Check Configuration via Monitoring Config
$uptimeConfigJson = @"
{
  "displayName": "$checkDisplayName",
  "monitoredResource": {
    "type": "uptime_url",
    "labels": {
      "host": "$hostName",
      "project_id": "$ProjectId"
    }
  },
  "httpCheck": {
    "path": "/health",
    "port": 443,
    "useSsl": true,
    "validateSsl": true,
    "requestMethod": "GET"
  },
  "period": "60s",
  "timeout": "10s",
  "selectedRegions": []
}
"@

$tempUptimeFile = [System.IO.Path]::GetTempFileName() + ".json"
$uptimeConfigJson | Set-Content $tempUptimeFile -Encoding UTF8

$uptimeCreated = $false
try {
  $createResult = (gcloud monitoring uptime-checks create "$checkDisplayName" `
    --project=$ProjectId `
    --config-from-file=$tempUptimeFile `
    --format="value(name)" 2>&1)
  if ($LASTEXITCODE -eq 0 -and $createResult) {
    $uptimeCreated = $true
    Write-Host "`n✅ SUCCESS: Automated 1-minute Uptime Check created in Google Cloud Monitoring!" -ForegroundColor Green
    Write-Host "Check ID: $createResult" -ForegroundColor Gray
  }
} catch {}
Remove-Item $tempUptimeFile -Force 2>$null

# 7. GCP Console Direct Link & Summary
$consoleMonitoringUrl = "https://console.cloud.google.com/monitoring/uptime?project=$ProjectId"
Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  MONITORING VERIFICATION & GCP CONSOLE LINK" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Uptime Check Target: https://$hostName/health" -ForegroundColor White
Write-Host "Check Frequency:     Every 60 seconds (1 minute)" -ForegroundColor White
Write-Host "Failure Threshold:   2 consecutive failed checks" -ForegroundColor White
Write-Host ""
Write-Host "View live uptime status & response times in GCP Console:" -ForegroundColor Cyan
Write-Host "$consoleMonitoringUrl" -ForegroundColor White -BackgroundColor Black
Write-Host "==========================================================" -ForegroundColor Cyan
