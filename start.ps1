<#
Khởi động ZENE bot trên Windows.

Token KHÔNG được lưu trong file này. Khi chạy, script sẽ hỏi token ẩn và ID Discord
(hoặc dùng các biến $env:DISCORD_TOKEN / $env:ZENE_OWNER_IDS nếu đã đặt sẵn).
Thêm -Force để bỏ qua giá trị cũ và hỏi lại.
#>
[CmdletBinding()]
param([switch]$Force)

Set-Location -LiteralPath $PSScriptRoot
$ErrorActionPreference = 'Stop'

if ($Force) {
    $env:DISCORD_TOKEN = $null
    $env:ZENE_OWNER_IDS = $null
}

if (-not $env:DISCORD_TOKEN) {
    $secure = Read-Host -AsSecureString 'DISCORD_TOKEN (sẽ không hiển thị khi gõ)'
    $env:DISCORD_TOKEN = [System.Net.NetworkCredential]::new('', $secure).Password
}

if (-not $env:ZENE_OWNER_IDS) {
    $ownerInput = Read-Host 'ZENE_OWNER_IDS - Discord user ID (numeric)'
    if ($ownerInput -notmatch '^[0-9]+$') {
        throw 'ZENE_OWNER_IDS must be a numeric Discord ID'
    }
    $env:ZENE_OWNER_IDS = $ownerInput
}

$env:ZENE_MEDIA_LINKS_ENABLED = 'true'
$env:ZENE_MEDIA_ALLOWED_DOMAINS = 'x.com,instagram.com,facebook.com,tiktok.com,youtube.com'
$env:ZENE_MEDIA_USE_PROXIES = 'true'
$env:ZENE_MEDIA_AUTO_TRANSLATE = 'true'
$env:ZENE_MEDIA_MODE = 'impersonate'
$env:ZENE_REQUIRED_EXTENSIONS = 'zene_core.cogs.conversation,zene_core.cogs.ops,zene_core.cogs.avwiki,zene_core.cogs.amlich,zene_core.cogs.giaxang,zene_core.cogs.digest,zene_core.cogs.embedfix'

& '.\.venv\Scripts\python.exe' run.py
