param(
    [string]$StartTaskName = "KanbanBoard-Autostart",
    [string]$BackupTaskName = "KanbanBoard-DailyBackup",
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Откройте PowerShell от имени администратора."
}

$startScript = (Resolve-Path (Join-Path $PSScriptRoot "start-kanban-server.ps1")).Path
$backupScript = (Resolve-Path (Join-Path $PSScriptRoot "backup-kanban.ps1")).Path
$powershell = (Get-Command powershell.exe).Source
$currentUser = $identity.Name

$startAction = New-ScheduledTaskAction `
    -Execute $powershell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -NoBrowser"
$startTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$taskPrincipal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Highest
$startSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask `
    -TaskName $StartTaskName `
    -Action $startAction `
    -Trigger $startTrigger `
    -Principal $taskPrincipal `
    -Settings $startSettings `
    -Description "Запуск Kanban backend и Quick Tunnel при входе владельца сервера" `
    -Force | Out-Null

$backupAction = New-ScheduledTaskAction `
    -Execute $powershell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`""
$backupTrigger = New-ScheduledTaskTrigger -Daily -At "03:00"
$backupSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask `
    -TaskName $BackupTaskName `
    -Action $backupAction `
    -Trigger $backupTrigger `
    -Principal $taskPrincipal `
    -Settings $backupSettings `
    -Description "Ежедневная проверенная резервная копия Kanban SQLite" `
    -Force | Out-Null

Write-Host "Созданы задачи:"
Write-Host "  $StartTaskName - при входе $currentUser, с повышенными правами"
Write-Host "  $BackupTaskName - ежедневно в 03:00"
Write-Host "Проверка: Task Scheduler Library -> указанные задачи -> Last Run Result = 0x0."

if ($StartNow) {
    Start-ScheduledTask -TaskName $StartTaskName
    Write-Host "Задача запуска Kanban отправлена на выполнение."
}
