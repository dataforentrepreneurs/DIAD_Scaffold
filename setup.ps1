# ============================================================================
# DIAD - One-Click Client Onboarding Setup Script
# ============================================================================
# Usage (paste this single line into PowerShell):
#   irm https://raw.githubusercontent.com/dataforentrepreneurs/DIAD_Scaffold/main/setup.ps1 | iex
#
# Or if you already cloned the repo, run from inside the DIAD folder:
#   .\setup.ps1
# ============================================================================

param(
    [switch]$SkipBrowser,
    [string]$InstallDir = "DIAD",
    [string]$ZipUrl = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # speeds up Invoke-WebRequest

# -- Pretty output helpers ----------------------------------------------------
function Write-Banner {
    Write-Host ""
    Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host "  |                                                              |" -ForegroundColor Cyan
    Write-Host "  |        DIAD - AI Data Platform for Entrepreneurs             |" -ForegroundColor Cyan
    Write-Host "  |        One-Click Onboarding Setup                            |" -ForegroundColor Cyan
    Write-Host "  |                                                              |" -ForegroundColor Cyan
    Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  This script will set up your local DIAD onboarding environment." -ForegroundColor Gray
    Write-Host "  Everything runs on YOUR machine - your data never leaves your ecosystem." -ForegroundColor Gray
    Write-Host ""
}

function Write-Step  { param($n, $msg) Write-Host "  [$n] " -NoNewline -ForegroundColor Yellow; Write-Host $msg }
function Write-Ok    { param($msg) Write-Host "      [OK] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "      [WARN] $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "      [ERROR] $msg" -ForegroundColor Red }
function Write-Info  { param($msg) Write-Host "      [INFO] $msg" -ForegroundColor Gray }

# -- Prerequisite check helpers -----------------------------------------------
function Test-Command { param($cmd) return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Get-PythonCmd {
    # Try common python commands; return first one that works with Python 3.9+
    foreach ($cmd in @("python", "python3", "py")) {
        if (Test-Command $cmd) {
            try {
                $ver = & $cmd --version 2>&1
                if ($ver -match "Python (\d+)\.(\d+)") {
                    $major = [int]$Matches[1]; $minor = [int]$Matches[2]
                    if ($major -ge 3 -and $minor -ge 9) { return $cmd }
                }
            } catch {}
        }
    }
    return $null
}

function Test-Winget {
    return (Test-Command "winget")
}

function Install-WithWinget {
    param($PackageId, $FriendlyName)
    Write-Info "Installing $FriendlyName via winget..."
    $proc = Start-Process -FilePath "winget" -ArgumentList "install", $PackageId, "--accept-package-agreements", "--accept-source-agreements", "--silent" -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -eq 0) {
        Write-Ok "$FriendlyName installed successfully."
        # Refresh PATH for the current session
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        return $true
    } else {
        Write-Err "$FriendlyName installation failed (exit code $($proc.ExitCode))."
        return $false
    }
}

function Request-Install {
    param($ToolName, $WingetId, $ManualUrl)
    
    if (Test-Winget) {
        Write-Warn "$ToolName is not installed."
        $choice = Read-Host "      Install $ToolName automatically? (Y/n)"
        if ($choice -eq "" -or $choice -match "^[Yy]") {
            return Install-WithWinget -PackageId $WingetId -FriendlyName $ToolName
        }
    }
    
    # Fallback: manual install
    Write-Err "$ToolName is required but not installed."
    Write-Info "Please install it manually from: $ManualUrl"
    Write-Info "After installing, restart PowerShell and re-run this script."
    return $false
}

# ============================================================================
# MAIN SCRIPT
# ============================================================================

Write-Banner

# -- Determine if we are already inside the repo ------------------------------
$insideRepo = (Test-Path "scripts/onboarding_dashboard.py") -and (Test-Path "requirements.txt")
if ($insideRepo) {
    $repoDir = Get-Location
    Write-Info "Detected: Running from inside the DIAD project directory."
} else {
    $repoDir = Join-Path (Get-Location) $InstallDir
}

# -- STEP 1: Check & Install Python ------------------------------------------
Write-Step "1/6" "Checking Python 3.9+ ..."

$pythonCmd = Get-PythonCmd
if ($pythonCmd) {
    $pyVer = & $pythonCmd --version 2>&1
    Write-Ok "Found: $pyVer"
} else {
    $installed = Request-Install -ToolName "Python 3.11" -WingetId "Python.Python.3.11" -ManualUrl "https://www.python.org/downloads/"
    if (-not $installed) { 
        Write-Host ""
        Write-Err "Cannot continue without Python. Exiting."
        exit 1 
    }
    $pythonCmd = Get-PythonCmd
    if (-not $pythonCmd) {
        Write-Err "Python was installed but is not yet on PATH."
        Write-Info "Please close and reopen PowerShell, then re-run this script."
        exit 1
    }
    $pyVer = & $pythonCmd --version 2>&1
    Write-Ok "Installed: $pyVer"
}

# -- STEP 2: Check & Install Git ---------------------------------------------
Write-Step "2/6" "Checking Git ..."

if (Test-Command "git") {
    $gitVer = (git --version) 2>&1
    Write-Ok "Found: $gitVer"
} else {
    if (-not $insideRepo) {
        # Git is only needed if we need to clone
        $installed = Request-Install -ToolName "Git" -WingetId "Git.Git" -ManualUrl "https://git-scm.com/downloads"
        if (-not $installed) {
            Write-Warn "Git not installed. Will attempt ZIP download instead."
        }
    } else {
        Write-Info "Git not found, but repo already cloned - skipping."
    }
}

# -- STEP 3: Check & Install Google Cloud SDK --------------------------------
Write-Step "3/6" "Checking Google Cloud SDK (gcloud) ..."

$gcloudAvailable = (Test-Command "gcloud") -or (Test-Command "gcloud.cmd")
if ($gcloudAvailable) {
    try {
        $gcloudVer = (gcloud --version 2>&1) | Select-Object -First 1
        Write-Ok "Found: $gcloudVer"
    } catch {
        Write-Ok "Found: Google Cloud SDK (version check skipped)"
    }
} else {
    $installed = Request-Install -ToolName "Google Cloud SDK" -WingetId "Google.CloudSDK" -ManualUrl "https://cloud.google.com/sdk/docs/install"
    if ($installed) {
        Write-Ok "Google Cloud SDK installed."
    } else {
        Write-Warn "gcloud not installed. You can install it later - the dashboard will still work."
        Write-Info "gcloud is needed for pipeline steps (deploying chatbots, syncing secrets)."
    }
}

# -- STEP 4: Clone Repository ------------------------------------------------
Write-Step "4/6" "Setting up DIAD project ..."

if ($insideRepo) {
    Write-Ok "Project already present at: $repoDir"
} else {
    if (Test-Path $repoDir) {
        Write-Ok "Directory $InstallDir already exists. Using it."
    } else {
        $downloaded = $false
        if ([string]::IsNullOrWhiteSpace($ZipUrl) -and (Test-Command "git")) {
            Write-Info "Attempting repository clone from GitHub..."
            $oldEAP = $ErrorActionPreference
            $ErrorActionPreference = "SilentlyContinue"
            git clone https://github.com/dataforentrepreneurs/DIAD_Scaffold.git $InstallDir 2>&1 | ForEach-Object { Write-Info $_ }
            $ErrorActionPreference = $oldEAP
            if ($LASTEXITCODE -eq 0 -and (Test-Path $repoDir)) {
                $downloaded = $true
                Write-Ok "Repository cloned to: $repoDir"
            }
        }

        if (-not $downloaded) {
            $targetUrl = if (-not [string]::IsNullOrWhiteSpace($ZipUrl)) { $ZipUrl } else { "https://github.com/dataforentrepreneurs/DIAD_Scaffold/archive/refs/heads/main.zip" }
            Write-Info "Downloading DIAD Scaffold archive from: $targetUrl ..."
            $zipPath = Join-Path (Get-Location) "DIAD_temp.zip"
            $oldEAP = $ErrorActionPreference
            $ErrorActionPreference = "SilentlyContinue"
            try {
                Invoke-WebRequest -Uri $targetUrl -OutFile $zipPath -UseBasicParsing
                $ErrorActionPreference = $oldEAP
                Write-Info "Extracting archive..."
                $extractTemp = Join-Path (Get-Location) "DIAD_extract_temp"
                if (Test-Path $extractTemp) { Remove-Item $extractTemp -Recurse -Force }
                Expand-Archive -Path $zipPath -DestinationPath $extractTemp -Force
                Remove-Item $zipPath -Force

                # GitHub ZIPs create a root folder like DIAD_Scaffold-main
                $nested = Get-ChildItem -Path $extractTemp -Directory | Select-Object -First 1
                if ($nested -and (Test-Path (Join-Path $nested.FullName "scripts"))) {
                    Move-Item -Path $nested.FullName -Destination $repoDir -Force
                } else {
                    Move-Item -Path $extractTemp -Destination $repoDir -Force
                }
                if (Test-Path $extractTemp) { Remove-Item $extractTemp -Recurse -Force -ErrorAction SilentlyContinue }
                $downloaded = $true
                Write-Ok "Project archive downloaded and extracted to: $repoDir"
            } catch {
                $ErrorActionPreference = $oldEAP
                Write-Err "Download/extraction failed: $_"
                exit 1
            }
        }
    }
    # Move into the project directory for remaining steps
    Set-Location $repoDir
}

# -- STEP 5: Create Virtual Environment & Install Dependencies ---------------
Write-Step "5/6" "Setting up Python environment ..."

$venvPath = "venv_dbt"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip    = Join-Path $venvPath "Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Info "Creating virtual environment..."
    & $pythonCmd -m venv $venvPath 2>&1 | ForEach-Object { Write-Info $_ }
    Write-Ok "Virtual environment created: $venvPath"
} else {
    Write-Ok "Virtual environment already exists."
}

# Install lightweight onboarding deps (fast - no torch/ML libraries)
$reqFile = "requirements_onboarding.txt"
if (-not (Test-Path $reqFile)) {
    # Fallback: use full requirements if onboarding-specific file doesn't exist
    $reqFile = "requirements.txt"
    Write-Warn "Lightweight requirements not found - using full requirements.txt (may take longer)."
}

Write-Info "Installing dependencies from $reqFile ..."
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& $venvPip install -r $reqFile --quiet 2>&1 | ForEach-Object { Write-Info $_ }
$ErrorActionPreference = $oldEAP

if ($LASTEXITCODE -ne 0) {
    Write-Err "Dependency installation failed. Trying with --no-cache-dir..."
    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & $venvPip install -r $reqFile --quiet --no-cache-dir 2>&1 | ForEach-Object { Write-Info $_ }
    $ErrorActionPreference = $oldEAP
}
Write-Ok "Dependencies installed."

# -- STEP 6: Launch Dashboard ------------------------------------------------
Write-Step "6/6" "Launching DIAD Onboarding Dashboard ..."

# Force-kill any existing dashboard server process to guarantee fresh code reload
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*onboarding_dashboard.py*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Green
Write-Host "  |                                                              |" -ForegroundColor Green
Write-Host "  |   Dashboard starting at: http://localhost:8000               |" -ForegroundColor Green
Write-Host "  |                                                              |" -ForegroundColor Green
Write-Host "  |   Your browser will open automatically.                      |" -ForegroundColor Green
Write-Host "  |   Press Ctrl+C in this window to stop the server.            |" -ForegroundColor Green
Write-Host "  |                                                              |" -ForegroundColor Green
Write-Host "  +--------------------------------------------------------------+" -ForegroundColor Green
Write-Host ""

# Auto-open browser after a short delay (give server time to start)
if (-not $SkipBrowser) {
    Start-Job -ScriptBlock { Start-Sleep -Seconds 3; Start-Process "http://localhost:8000" } | Out-Null
}

# Launch the dashboard server (blocking - keeps terminal alive)
& $venvPython scripts/onboarding_dashboard.py
