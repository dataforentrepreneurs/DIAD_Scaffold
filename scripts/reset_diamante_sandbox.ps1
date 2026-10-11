<#
.SYNOPSIS
    DIAD Sandbox Teardown & Reset Script (The Diamante Collections)
.DESCRIPTION
    Wipes all deployed GCP resources (BigQuery datasets, GCS bucket files, Cloud Run services/jobs, Cloud Scheduler triggers, Secret Manager keys)
    and resets the local configuration file so the Diamante sandbox can be reused repeatedly for pitches & live demos.

    .\scripts\reset_diamante_sandbox.ps1 -Force
#>

param(
    [string]$ProjectId = "diamante-diad",
    [string]$Region = "asia-southeast1",
    [string]$BucketName = "diamante-diad-storage",
    [bool]$ResetLocalConfig = $true,
    [switch]$Force = $false
)

$oldEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "     DIAD Sandbox Teardown Script: The Diamante Collections       " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Target GCP Project: $ProjectId" -ForegroundColor Yellow
Write-Host "Target GCP Region : $Region" -ForegroundColor Yellow
Write-Host ""

if (-not $Force) {
    $confirm = Read-Host "⚠️ WARNING: This will permanently delete test datasets, secrets, and Cloud Run services in '$ProjectId'. Continue? (y/n)"
    if ($confirm -ne 'y' -and $confirm -ne 'Y') {
        Write-Host "Cancelled." -ForegroundColor Red
        exit 0
    }
}

Write-Host "`n[1/5] Setting gcloud active project..." -ForegroundColor Yellow
& gcloud config set project $ProjectId 2>$null | Out-Null

Write-Host "`n[2/5] Deleting Cloud Run Services & Scheduler Jobs..." -ForegroundColor Yellow
& gcloud scheduler jobs delete diad-phase8-sync-quarterly --location Asia/Singapore --quiet 2>$null | Out-Null
& gcloud scheduler jobs delete diad-sync-docs-scheduler --location Asia/Singapore --quiet 2>$null | Out-Null

    $regionsToCheck = @($Region, "us-central1") | Select-Object -Unique
    foreach ($r in $regionsToCheck) {
        & gcloud run services delete diad-external-chat --region $r --quiet 2>$null | Out-Null
        & gcloud run services delete diad-internal-chat --region $r --quiet 2>$null | Out-Null
        & gcloud run jobs delete diad-phase8-sync-docs --region $r --quiet 2>$null | Out-Null
        & gcloud run jobs delete diad-sync-docs-job --region $r --quiet 2>$null | Out-Null
    }
    Write-Host "  ✅ Cloud Run & Scheduler jobs cleaned up." -ForegroundColor Green

Write-Host "`n[3/5] Deleting Secret Manager Secrets..." -ForegroundColor Yellow
$secrets = @("OPENAI_API_KEY", "PINECONE_API_KEY", "NOTION_TOKEN", "CONFLUENCE_TOKEN", "GEMINI_API_KEY", "NOTION_API_KEY")
foreach ($s in $secrets) {
    & gcloud secrets delete $s --quiet 2>$null | Out-Null
}
Write-Host "  ✅ GCP Secrets cleaned up." -ForegroundColor Green

Write-Host "`n[4/5] Deleting BigQuery Datasets & GCS Objects..." -ForegroundColor Yellow
$datasets = @("ecommerce_raw", "ecommerce_canonical", "ecommerce_mart", "firestore_export", "firebase_auth_export", "firebase_consolidated", "google_analytics_export")
foreach ($ds in $datasets) {
    & bq rm -r -f -d "$($ProjectId):$ds" 2>$null | Out-Null
}
Write-Host "  ✅ BigQuery datasets deleted." -ForegroundColor Green

if ($BucketName) {
    & gcloud storage rm "gs://$BucketName/**" --quiet 2>$null | Out-Null
    Write-Host "  ✅ GCS bucket objects cleared." -ForegroundColor Green
}

if ($ResetLocalConfig) {
    Write-Host "`n[5/5] Resetting Local DIAD Configuration & Keys..." -ForegroundColor Yellow
    $scriptDir = $PSScriptRoot
    $repoRoot = (Get-Item $scriptDir).Parent.FullName
    $configPath = Join-Path $repoRoot "config\client_rawdata.json"
    $examplePath = Join-Path $repoRoot "config\client_rawdata.json.example"

    if (Test-Path $examplePath) {
        Copy-Item $examplePath $configPath -Force
        Write-Host "  ✅ Reset config/client_rawdata.json to initial template." -ForegroundColor Green
    }

    $secretsFlag = Join-Path $repoRoot "config\.secrets_synced"
    if (Test-Path $secretsFlag) {
        Remove-Item $secretsFlag -Force 2>$null
        Write-Host "  ✅ Removed config\.secrets_synced flag." -ForegroundColor Green
    }

    $keysDir = Join-Path $repoRoot "keys"
    if (Test-Path $keysDir) {
        Get-ChildItem -Path $keysDir -Filter "*.json" | ForEach-Object {
            Remove-Item $_.FullName -Force 2>$null
            Write-Host "  ✅ Removed local key file: $($_.Name)" -ForegroundColor Green
        }
    }

    $pkgDir = Join-Path $repoRoot "client_site_package"
    if (Test-Path $pkgDir) {
        Get-ChildItem -Path $pkgDir -Filter "*.zip" | ForEach-Object {
            Remove-Item $_.FullName -Force 2>$null
            Write-Host "  ✅ Removed generated package: $($_.Name)" -ForegroundColor Green
        }
    }

    $logsDir = Join-Path $repoRoot "logs"
    if (Test-Path $logsDir) {
        Get-ChildItem -Path $logsDir -Filter "*.log" | ForEach-Object {
            Remove-Item $_.FullName -Force 2>$null
        }
        Write-Host "  ✅ Cleared execution logs in logs/." -ForegroundColor Green
    }

    $dbtTarget = Join-Path $repoRoot "dbt\diad_dbt\target"
    if (Test-Path $dbtTarget) {
        Remove-Item $dbtTarget -Recurse -Force 2>$null
    }

    # Also reset $env:USERPROFILE\DIAD if it exists (where setup.bat installs to)
    $homeDiad = Join-Path $env:USERPROFILE "DIAD"
    if (Test-Path $homeDiad) {
        if (Test-Path $examplePath) {
            Copy-Item $examplePath (Join-Path $homeDiad "config\client_rawdata.json") -Force 2>$null
            Write-Host "  ✅ Reset $homeDiad\config\client_rawdata.json to initial template." -ForegroundColor Green
        }
        $homeFlag = Join-Path $homeDiad "config\.secrets_synced"
        if (Test-Path $homeFlag) {
            Remove-Item $homeFlag -Force 2>$null
        }
        $homeKeys = Join-Path $homeDiad "keys"
        if (Test-Path $homeKeys) {
            Get-ChildItem -Path $homeKeys -Filter "*.json" | ForEach-Object {
                Remove-Item $_.FullName -Force 2>$null
                Write-Host "  ✅ Removed $homeDiad key file: $($_.Name)" -ForegroundColor Green
            }
        }
        $homePkg = Join-Path $homeDiad "client_site_package"
        if (Test-Path $homePkg) {
            Get-ChildItem -Path $homePkg -Filter "*.zip" | ForEach-Object {
                Remove-Item $_.FullName -Force 2>$null
            }
        }
        $homeLogs = Join-Path $homeDiad "logs"
        if (Test-Path $homeLogs) {
            Get-ChildItem -Path $homeLogs -Filter "*.log" | ForEach-Object {
                Remove-Item $_.FullName -Force 2>$null
            }
        }
    }
}

$ErrorActionPreference = $oldEAP

Write-Host "`n🎉 Diamante Sandbox Reset Complete!" -ForegroundColor Green
Write-Host "You are ready to run a clean demo or onboarding pitch." -ForegroundColor Cyan
