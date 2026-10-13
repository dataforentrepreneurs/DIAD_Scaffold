@echo off
title DIAD Onboarding Launcher
echo ==============================================================
echo        DIAD - AI Data Platform for Entrepreneurs             
echo        One-Click Onboarding Launcher                          
echo ==============================================================
echo.

if "%1"=="--reset" (
    echo [INFO] Performing clean reset of %USERPROFILE%\DIAD ...
    rmdir /s /q "%USERPROFILE%\DIAD" 2>nul
)
if "%1"=="/reset" (
    echo [INFO] Performing clean reset of %USERPROFILE%\DIAD ...
    rmdir /s /q "%USERPROFILE%\DIAD" 2>nul
)

:: Check if latest release needs to be downloaded or upgraded
set "NEED_DOWNLOAD=0"
if not exist "%USERPROFILE%\DIAD\scripts\onboarding_dashboard.py" set "NEED_DOWNLOAD=1"

if exist "%USERPROFILE%\DIAD\scripts\onboarding_dashboard.py" (
    findstr /C:"Sync Cadence" "%USERPROFILE%\DIAD\scripts\onboarding_dashboard.py" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Detected older DIAD version. Upgrading to latest release...
        set "NEED_DOWNLOAD=1"
    )
)

if "%NEED_DOWNLOAD%"=="1" (
    echo [INFO] Downloading latest DIAD release package from d4e.ai...
    powershell -ExecutionPolicy Bypass -Command "$zipUrl = 'https://d4e.ai/DIAD_release_v1.0.zip'; $tempZip = \"$env:TEMP\DIAD_release.zip\"; try { iwr $zipUrl -OutFile $tempZip -UseBasicParsing; Expand-Archive $tempZip -DestinationPath \"$home\DIAD\" -Force; Remove-Item $tempZip -Force; Write-Host '[SUCCESS] DIAD updated to latest release.' -ForegroundColor Green } catch { Write-Host \"[WARN] Error downloading zip: $($_.Exception.Message)\" -ForegroundColor Yellow }"
)

cd /d "%USERPROFILE%\DIAD"

echo.
echo [INFO] Launching DIAD setup engine...
powershell -ExecutionPolicy Bypass -File .\setup.ps1
pause
