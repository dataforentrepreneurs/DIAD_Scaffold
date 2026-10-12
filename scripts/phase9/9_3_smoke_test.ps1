param(
  [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
  [string]$Region = "asia-southeast1",
  [string]$InternalService = "diad-internal-chat",
  [string]$ExternalService = "diad-external-chat",
  [string]$ConfigPath = "config/client_rawdata.json"
)

if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "Not Configured") {
  if (Test-Path $ConfigPath) {
    try {
      $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
      if ($cfg.client.project_id -and $cfg.client.project_id -ne "Not Configured") {
        $ProjectId = $cfg.client.project_id
      }
      if ($cfg.gcp.region) { $Region = $cfg.gcp.region }
    } catch {}
  }
}

if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "Not Configured") {
  $ProjectId = (gcloud config get-value project 2>$null)
}

$ErrorActionPreference = "Stop"

Write-Host "=== Phase 9.3 Smoke Test ==="
Write-Host "Project: $ProjectId"
Write-Host "Region:  $Region"

$projectNum = (gcloud projects describe $ProjectId --format="value(projectNumber)" 2>$null)

$internalUrl = (gcloud run services describe $InternalService --project $ProjectId --region $Region --format="value(status.url)" 2>$null)
$externalUrl = (gcloud run services describe $ExternalService --project $ProjectId --region $Region --format="value(status.url)" 2>$null)

# Fallback to regional deterministic URL if needed
$altExternalUrl = if ($projectNum) { "https://${ExternalService}-${projectNum}.${Region}.run.app" } else { $null }

Write-Host "Internal URL: $internalUrl"
Write-Host "External URL: $externalUrl"
if ($altExternalUrl) { Write-Host "Regional URL: $altExternalUrl" }

Write-Host "`n[1/2] External health check..."
$targetUrl = $null
$urlsToTry = @($externalUrl, $altExternalUrl) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

foreach ($u in $urlsToTry) {
  try {
    Write-Host "Checking: $u"
    $res = irm "$u/" -TimeoutSec 10
    $targetUrl = $u
    Write-Host "External OK ($targetUrl)"
    break
  } catch {
    Write-Host "Failed to reach $u"
  }
}

if (-not $targetUrl) {
  Write-Host "External health check failed on all URLs"
  throw "Unable to connect to external chat service"
}

Write-Host "`n[1.1] Testing live chat query (/external/chat)..."
try {
  $testBody = @{ question = "Hello, what is your return policy?" } | ConvertTo-Json -Compress
  $chatRes = irm -Uri "$targetUrl/external/chat" -Method Post -Body $testBody -ContentType "application/json" -TimeoutSec 15
  Write-Host "Chat Response Received:"
  Write-Host ($chatRes | ConvertTo-Json -Depth 3)
} catch {
  Write-Host "Chat query warning: $_"
}

Write-Host "`n[2/2] Internal health..."
Write-Host "Internal is typically private. If you have IAP/auth, test with an authenticated request."
Write-Host "Basic unauthenticated call may fail (expected)."
try {
  irm "$internalUrl/" -TimeoutSec 10 | Out-Host
  Write-Host "Internal responded (service may be public or your shell has auth)"
} catch {
  Write-Host "Internal call failed (often expected if private)."
}

Write-Host "`nSmoke Test Complete!"
