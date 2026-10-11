# powershell -ExecutionPolicy Bypass -File scripts/phase9/9_1_run_local.ps1
param(
  [string]$ConfigPath = "config/client_rawdata.json",
  [int]$InternalPort = 8001,
  [int]$ExternalPort = 8002
)

$ErrorActionPreference = "Stop"

Write-Host "=== Phase 9.1 Run Local (Internal + External) ==="
Write-Host "ConfigPath: $ConfigPath"

# Make sure FastAPI reads the correct config
$env:DIAD_CONFIG = $ConfigPath

# Load .env if present (simple KEY=VALUE)
$envFile = Join-Path (Get-Location) ".\.env.local"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    $parts = $_.Split("=",2)
    if ($parts.Count -eq 2) {
      $k = $parts[0].Trim()
      $v = $parts[1].Trim().Trim('"')
      [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
    }
  }
}


Write-Host "Starting INTERNAL API on port $InternalPort ..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv_dbt\Scripts\python.exe -m uvicorn chatbot.internal_api:app --reload --port $InternalPort"

Write-Host "Starting EXTERNAL API on port $ExternalPort ..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv_dbt\Scripts\python.exe -m uvicorn chatbot.external_api:app --reload --port $ExternalPort"

Write-Host ""
Write-Host "Started. Test:"
Write-Host " - http://127.0.0.1:$InternalPort/docs"
Write-Host " - http://127.0.0.1:$ExternalPort/docs"
