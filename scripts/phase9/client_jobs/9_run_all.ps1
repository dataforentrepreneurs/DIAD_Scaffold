param(
  [string]$EnvFile = "$PSScriptRoot\env.ps1"
)
$ErrorActionPreference = "Stop"

Write-Host "=== Phase9 Client Jobs: RUN ALL ==="
& "$PSScriptRoot\1_bootstrap_project.ps1" -EnvFile $EnvFile
& "$PSScriptRoot\2_upsert_secrets.ps1" -EnvFile $EnvFile
& "$PSScriptRoot\3_build_image.ps1" -EnvFile $EnvFile
& "$PSScriptRoot\4_deploy_job.ps1" -EnvFile $EnvFile
& "$PSScriptRoot\5_schedule_job.ps1" -EnvFile $EnvFile

Write-Host "`n✅ All done."
