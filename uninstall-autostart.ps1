<#
Gỡ tự khởi động: xóa Scheduled Task.
By default the token/ID in user env are kept.
Use -ClearSecrets to delete both USER variables too.
#>
[CmdletBinding()]
param([switch]$ClearSecrets)

$ErrorActionPreference = 'Stop'
Unregister-ScheduledTask -TaskName 'ZENE Bot' -Confirm:$false -ErrorAction SilentlyContinue

if ($ClearSecrets) {
    [Environment]::SetEnvironmentVariable('DISCORD_TOKEN', $null, 'User')
    [Environment]::SetEnvironmentVariable('ZENE_OWNER_IDS', $null, 'User')
    Write-Host "Removed task and USER variables DISCORD_TOKEN / ZENE_OWNER_IDS."
}
else {
    Write-Host "Removed scheduled task 'ZENE Bot'. Token env var was NOT deleted."
}
