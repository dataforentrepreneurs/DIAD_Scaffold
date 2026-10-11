param(
  [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
  [string]$Region = "asia-southeast1",
  [string]$InternalService = "diad-internal-chat",
  [string]$ExternalService = "diad-external-chat",
  [string]$ConfigPath = "config/client_rawdata.json"
)

if ([string]::IsNullOrWhiteSpace($ProjectId) -and (Test-Path $ConfigPath)) {
  try {
    $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
    $ProjectId = $cfg.client.project_id
    if ($cfg.gcp.region) { $Region = $cfg.gcp.region }
  } catch {}
}

$ErrorActionPreference = "Stop"

Write-Host "=== Phase 9.3 Smoke Test ==="
Write-Host "Project: $ProjectId"
Write-Host "Region:  $Region"

$internalUrl = (gcloud run services describe $InternalService --project $ProjectId --region $Region --format="value(status.url)")
$externalUrl = (gcloud run services describe $ExternalService --project $ProjectId --region $Region --format="value(status.url)")

Write-Host "Internal URL: $internalUrl"
Write-Host "External URL: $externalUrl"

Write-Host "`n[1/2] External health..."
try {
  irm "$externalUrl/" -TimeoutSec 30 | Out-Host
  Write-Host "External OK"
} catch {
  Write-Host "External health failed"
  throw
}

Write-Host "`n[2/2] Internal health..."
Write-Host "Internal is typically private. If you have IAP/auth, test with an authenticated request."
Write-Host "Basic unauthenticated call may fail (expected)."
try {
  irm "$internalUrl/" -TimeoutSec 15 | Out-Host
  Write-Host "Internal responded (service may be public or your shell has auth)"
} catch {
  Write-Host "Internal call failed (often expected if private)."
}

Write-Host "Done"
