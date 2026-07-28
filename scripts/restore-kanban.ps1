param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [switch]$Force,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "common.ps1")

$resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path
if (-not $Force) {
    Write-Host "Будет остановлен Kanban и восстановлена база из:"
    Write-Host "  $resolvedBackup"
    $confirmation = Read-Host "Для продолжения введите ВОССТАНОВИТЬ"
    if ($confirmation -cne "ВОССТАНОВИТЬ") {
        Write-Host "Восстановление отменено."
        exit 0
    }
}

$repositoryRoot = Get-KanbanRepositoryRoot
$config = Get-KanbanEnvironment -RepositoryRoot $repositoryRoot
$backendDir = Join-Path $repositoryRoot "backend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"
$emergencyDir = Join-Path $config["BACKUP_DIR"] "emergency"

& (Join-Path $PSScriptRoot "stop-kanban.ps1")
Push-Location $backendDir
try {
    & $python -m scripts.restore_db `
        --backup $resolvedBackup `
        --database-url $config["DATABASE_URL"] `
        --emergency-dir $emergencyDir
    if ($LASTEXITCODE -ne 0) {
        throw "Восстановление не выполнено; рабочая база не должна была замениться."
    }
}
finally {
    Pop-Location
}

& (Join-Path $PSScriptRoot "start-kanban-server.ps1") -NoBrowser:$NoBrowser
$ready = Wait-KanbanJsonEndpoint -Url "http://127.0.0.1:8000/api/v1/ready" -TimeoutSeconds 90
Write-Host "Восстановление завершено. База готова, Alembic revision: $($ready.alembicRevision)."
