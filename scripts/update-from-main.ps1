param(
    [switch]$RunTests,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "common.ps1")

$repositoryRoot = Get-KanbanRepositoryRoot
$config = Get-KanbanEnvironment -RepositoryRoot $repositoryRoot
$backendDir = Join-Path $repositoryRoot "backend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"

Push-Location $repositoryRoot
try {
    $changes = @(& git status --porcelain --untracked-files=all)
    if ($changes.Count -gt 0) {
        throw "Перед обновлением Git-дерево должно быть чистым:`n$($changes -join [Environment]::NewLine)"
    }
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        throw "Переключитесь на main. Сейчас: $branch"
    }
}
finally {
    Pop-Location
}

Write-Host "Создание резервной копии..."
& (Join-Path $PSScriptRoot "backup-kanban.ps1")
& (Join-Path $PSScriptRoot "stop-kanban.ps1")

Push-Location $repositoryRoot
try {
    & git fetch origin main --prune
    if ($LASTEXITCODE -ne 0) {
        throw "git fetch завершился ошибкой."
    }
    & git pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) {
        throw "git pull --ff-only завершился ошибкой."
    }
}
finally {
    Pop-Location
}

& $python -m pip install -r (Join-Path $backendDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось обновить Python-зависимости."
}

Push-Location $backendDir
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Миграции завершились ошибкой."
    }
    & $python -m alembic check
    if ($LASTEXITCODE -ne 0) {
        throw "Модель SQLAlchemy и Alembic migration расходятся."
    }
    if ($RunTests) {
        & $python -m pip install -r requirements-dev.txt
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось установить dev-зависимости."
        }
        & $python -m ruff check app scripts tests
        if ($LASTEXITCODE -ne 0) {
            throw "Ruff check завершился ошибкой."
        }
        & $python -m ruff format --check app scripts tests
        if ($LASTEXITCODE -ne 0) {
            throw "Ruff format --check завершился ошибкой."
        }
        & $python -m pytest
        if ($LASTEXITCODE -ne 0) {
            throw "Pytest завершился ошибкой."
        }
    }
}
finally {
    Pop-Location
}

& (Join-Path $PSScriptRoot "start-kanban-server.ps1") -NoBrowser:$NoBrowser
Write-Host "Обновление из origin/main завершено."
