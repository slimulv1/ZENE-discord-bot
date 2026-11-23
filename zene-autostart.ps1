<#
Chạy bởi Task Scheduler mỗi lần đăng nhập Windows.
Token được đọc từ biến môi trường USER (do install-autostart.ps1 thiết lập).
Không ghi token vào file/log/repo.
#>
Set-Location -LiteralPath $PSScriptRoot
$ErrorActionPreference = 'Stop'

$logDir = Join-Path $PSScriptRoot 'logs'
$logFile = Join-Path $logDir 'autostart.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-AutostartLog([string]$Message) {
    Add-Content -LiteralPath $logFile -Value ("{0} {1}" -f (Get-Date -Format 's'), $Message)
}

if (-not $env:DISCORD_TOKEN) {
    Write-AutostartLog 'DISCORD_TOKEN missing — run install-autostart.ps1 once.'
    exit 1
}
if (-not $env:ZENE_OWNER_IDS) {
    Write-AutostartLog 'ZENE_OWNER_IDS missing — run install-autostart.ps1 once.'
    exit 1
}

$env:ZENE_MEDIA_LINKS_ENABLED = 'true'
$env:ZENE_MEDIA_ALLOWED_DOMAINS = 'x.com,instagram.com,facebook.com,tiktok.com,youtube.com'
$env:ZENE_MEDIA_USE_PROXIES = 'true'
$env:ZENE_MEDIA_AUTO_TRANSLATE = 'true'
$env:ZENE_MEDIA_MODE = 'impersonate'
$env:ZENE_REQUIRED_EXTENSIONS = 'zene_core.cogs.conversation,zene_core.cogs.ops,zene_core.cogs.avwiki,zene_core.cogs.amlich,zene_core.cogs.giaxang,zene_core.cogs.digest,zene_core.cogs.embedfix'

Write-AutostartLog 'bot supervisor started'
while ($true) {
    try {
        & '.\.venv\Scripts\python.exe' run.py
    }
    catch {
        Write-AutostartLog ("bot process error: " + $_.Exception.Message)
    }
    Write-AutostartLog 'bot exited; restarting in 10s'
    Start-Sleep -Seconds 10
}
