param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "common.ps1")

$repositoryRoot = Get-KanbanRepositoryRoot
$config = Get-KanbanEnvironment -RepositoryRoot $repositoryRoot
$backendDir = Join-Path $repositoryRoot "backend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"
$backupDir = $config["BACKUP_DIR"]
if (-not (Test-Path $python)) {
    throw "Не найдено виртуальное окружение backend."
}
if (-not $backupDir) {
    throw "BACKUP_DIR отсутствует в backend\.env."
}

Push-Location $backendDir
try {
    & $python -m scripts.backup_db --database-url $config["DATABASE_URL"] --backup-dir $backupDir
    if ($LASTEXITCODE -ne 0) {
        throw "Резервное копирование завершилось ошибкой."
    }
}
finally {
    Pop-Location
}
Write-Host "Резервная копия создана и прошла integrity_check."

