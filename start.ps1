<#
Khởi động ZENE bot trên Windows.

Token KHÔNG được lưu trong file này. Khi chạy, script sẽ hỏi token ẩn
(hoặc dùng $env:DISCORD_TOKEN nếu bạn đã đặt trong phiên PowerShell hiện tại).
#>
Set-Location -LiteralPath $PSScriptRoot
$ErrorActionPreference = 'Stop'

if (-not $env:DISCORD_TOKEN) {
    $secure = Read-Host -AsSecureString 'DISCORD_TOKEN (sẽ không hiển thị khi gõ)'
    $env:DISCORD_TOKEN = [System.Net.NetworkCredential]::new('', $secure).Password
}

$env:ZENE_OWNER_IDS = '374186828174983169'
$env:ZENE_MEDIA_LINKS_ENABLED = 'true'
$env:ZENE_MEDIA_ALLOWED_DOMAINS = 'x.com,instagram.com,facebook.com,tiktok.com,youtube.com'
$env:ZENE_MEDIA_USE_PROXIES = 'true'
$env:ZENE_MEDIA_AUTO_TRANSLATE = 'true'
$env:ZENE_MEDIA_MODE = 'impersonate'
$env:ZENE_REQUIRED_EXTENSIONS = 'zene_core.cogs.conversation,zene_core.cogs.ops,zene_core.cogs.avwiki,zene_core.cogs.amlich,zene_core.cogs.giaxang,zene_core.cogs.digest,zene_core.cogs.embedfix'

& '.\.venv\Scripts\python.exe' run.py
