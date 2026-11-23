<#
Setup MỘT LẦN cho Windows autostart:
1. Hỏi token ẩn và lưu vào biến môi trường USER (registry) — KHÔNG lưu trong repo.
2. Đăng kýScheduled Task chạy zene-autostart.ps1 mỗi lần đăng nhập.

Chạy: powershell -NoProfile -ExecutionPolicy Bypass -File .\install-autostart.ps1
#>
$ErrorActionPreference = 'Stop'

if (-not $env:DISCORD_TOKEN) {
    $secure = Read-Host -AsSecureString 'DISCORD_TOKEN bot (ẩn khi gõ)'
    $env:DISCORD_TOKEN = [System.Net.NetworkCredential]::new('', $secure).Password
}

# Persist for future logons, outside the repository.
[Environment]::SetEnvironmentVariable('DISCORD_TOKEN', $env:DISCORD_TOKEN, 'User')

$taskName = 'ZENE Bot'
$runner = Join-Path $PSScriptRoot 'zene-autostart.ps1'
$argument = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $runner

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "OK: task '$taskName' will start on logon. Token saved in USER environment variable (not in repo)."
Write-Host "Stop manually: Stop-ScheduledTask -TaskName '$taskName'"
