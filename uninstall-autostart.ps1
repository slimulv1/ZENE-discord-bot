<# Gỡ tự khởi động: xóa Scheduled Task. Không xóa token trong registry. #>
$ErrorActionPreference = 'Stop'
Unregister-ScheduledTask -TaskName 'ZENE Bot' -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Removed scheduled task 'ZENE Bot' (if it existed). Token env var was NOT deleted."
