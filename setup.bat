@echo off
title DIAD Onboarding Launcher
echo ==============================================================
echo        DIAD - AI Data Platform for Entrepreneurs             
echo        One-Click Onboarding Launcher                          
echo ==============================================================
echo.

if "%1"=="--reset" (
    echo [INFO] Performing clean reset of %%USERPROFILE%%\DIAD ...
    rmdir /s /q "%USERPROFILE%\DIAD" 2>nul
)
if "%1"=="/reset" (
    echo [INFO] Performing clean reset of %%USERPROFILE%%\DIAD ...
    rmdir /s /q "%USERPROFILE%\DIAD" 2>nul
)

IF NOT EXIST "%USERPROFILE%\DIAD\scripts\onboarding_dashboard.py" (
    echo [INFO] Downloading DIAD release package from secure CDN...
    powershell -ExecutionPolicy Bypass -Command "iwr 'https://diad.d4e.ai/DIAD_release_v1.0.zip' -OutFile '$env:TEMP\DIAD.zip'; Expand-Archive '$env:TEMP\DIAD.zip' -DestinationPath '$home\DIAD' -Force; Remove-Item '$env:TEMP\DIAD.zip'"
)

cd /d "%USERPROFILE%\DIAD"

echo.
echo [INFO] Launching DIAD setup engine...
powershell -ExecutionPolicy Bypass -File .\setup.ps1
pause
