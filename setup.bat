@echo off
title DIAD Onboarding Launcher
echo ==============================================================
echo        DIAD - AI Data Platform for Entrepreneurs             
echo        One-Click Onboarding Launcher                          
echo ==============================================================
echo.

if "%1"=="--reset" goto do_reset
if "%1"=="/reset" goto do_reset
goto check_version

:do_reset
echo [INFO] Performing clean reset of %USERPROFILE%\DIAD ...
rmdir /s /q "%USERPROFILE%\DIAD" 2>nul

:check_version
if not exist "%USERPROFILE%\DIAD\scripts\onboarding_dashboard.py" goto do_download

findstr /C:"Sync Cadence" "%USERPROFILE%\DIAD\scripts\onboarding_dashboard.py" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Detected older DIAD version. Upgrading to latest release...
    goto do_download
)
goto run_setup

:do_download
echo [INFO] Downloading latest DIAD release package from d4e.ai...
powershell -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://d4e.ai/DIAD_release_v1.0.zip' -OutFile ($env:TEMP + '\DIAD_release.zip'); Expand-Archive -Path ($env:TEMP + '\DIAD_release.zip') -DestinationPath ($env:USERPROFILE + '\DIAD') -Force; Remove-Item ($env:TEMP + '\DIAD_release.zip') -Force; Write-Host '[SUCCESS] DIAD updated to latest release.' -ForegroundColor Green"

:run_setup
cd /d "%USERPROFILE%\DIAD"

echo.
echo [INFO] Launching DIAD setup engine...
powershell -ExecutionPolicy Bypass -File .\setup.ps1
pause
