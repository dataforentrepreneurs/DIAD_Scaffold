@echo off
REM ==============================================================================
REM DIAD Cloud Run Deploy Launcher (Bypasses PowerShell Execution Policy)
REM ==============================================================================
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\phase9\9_2_deploy_cloud_run.ps1" %*
