param(
    [string]$StartTaskName = "KanbanBoard-Autostart",
    [string]$BackupTaskName = "KanbanBoard-DailyBackup"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$startScript = (Resolve-Path (Join-Path $PSScriptRoot "start-kanban.ps1")).Path
$backupScript = (Resolve-Path (Join-Path $PSScriptRoot "backup-kanban.ps1")).Path
$powershell = (Get-Command powershell.exe).Source
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

$startAction = New-ScheduledTaskAction `
    -Execute $powershell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -NoBrowser"
$startTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$startPrincipal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
$startSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable
Register-ScheduledTask `
    -TaskName $StartTaskName `
    -Action $startAction `
    -Trigger $startTrigger `
    -Principal $startPrincipal `
    -Settings $startSettings `
    -Description "Запуск Kanban backend и Quick Tunnel при входе пользователя" `
    -Force | Out-Null

$backupAction = New-ScheduledTaskAction `
    -Execute $powershell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`""
$backupTrigger = New-ScheduledTaskTrigger -Daily -At "03:00"
$backupSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable
Register-ScheduledTask `
    -TaskName $BackupTaskName `
    -Action $backupAction `
    -Trigger $backupTrigger `
    -Principal $startPrincipal `
    -Settings $backupSettings `
    -Description "Ежедневная проверенная резервная копия Kanban SQLite" `
    -Force | Out-Null

Write-Host "Созданы задачи:"
Write-Host "  $StartTaskName - при входе $currentUser"
Write-Host "  $BackupTaskName - ежедневно в 03:00"
Write-Host "Проверка: откройте Task Scheduler Library и найдите обе задачи."

