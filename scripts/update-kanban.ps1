param(
    [Parameter(Mandatory = $true)][string]$VersionTag,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "common.ps1")

$repositoryRoot = Get-KanbanRepositoryRoot
$config = Get-KanbanEnvironment -RepositoryRoot $repositoryRoot
$backendDir = Join-Path $repositoryRoot "backend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"
$previousCommit = ""
$targetCommit = ""

Push-Location $repositoryRoot
try {
    $changes = @(& git status --porcelain --untracked-files=all)
    if ($changes.Count -gt 0) {
        throw "Перед обновлением рабочее дерево должно быть чистым. Сохраните или отмените изменения вручную."
    }
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        throw "Обновление выполняется только из ветки main. Сейчас: $branch"
    }
    $previousCommit = (& git rev-parse HEAD).Trim()
    & git fetch origin --tags --prune
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось получить теги из origin."
    }
    $targetCommit = (& git rev-parse "refs/tags/$VersionTag^{commit}" 2>$null).Trim()
    if (-not $targetCommit) {
        throw "Тег не найден: $VersionTag"
    }
    & git merge-base --is-ancestor $previousCommit $targetCommit
    if ($LASTEXITCODE -ne 0) {
        throw "Тег $VersionTag не является fast-forward обновлением текущей версии."
    }
}
finally {
    Pop-Location
}

Write-Host "Создание резервной копии перед обновлением..."
& (Join-Path $PSScriptRoot "backup-kanban.ps1")
& (Join-Path $PSScriptRoot "stop-kanban.ps1")

try {
    Push-Location $repositoryRoot
    try {
        & git merge --ff-only $VersionTag
        if ($LASTEXITCODE -ne 0) {
            throw "git merge --ff-only завершился ошибкой."
        }
    }
    finally {
        Pop-Location
    }

    & $python -m pip install -r (Join-Path $backendDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось обновить зависимости."
    }
    Push-Location $backendDir
    try {
        & $python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "Миграции завершились ошибкой."
        }
    }
    finally {
        Pop-Location
    }
    & (Join-Path $PSScriptRoot "start-kanban.ps1") -NoBrowser:$NoBrowser
    $ready = Wait-KanbanJsonEndpoint -Url "http://127.0.0.1:8000/api/v1/ready" -TimeoutSeconds 90
    Write-Host "Обновление до $VersionTag завершено. Alembic revision: $($ready.alembicRevision)."
}
catch {
    Write-Error @"
Обновление прервано: $($_.Exception.Message)

Автоматический откат не выполнялся, чтобы не перезаписать ваши файлы.
Предыдущий Git commit: $previousCommit
Целевой commit: $targetCommit

Порядок ручного отката:
1. Убедитесь, что процессы остановлены: .\scripts\stop-kanban.ps1
2. Посмотрите последние backup: Get-ChildItem "$($config["BACKUP_DIR"])" -Filter *.db | Sort-Object LastWriteTime -Descending
3. Верните код только после проверки Git-состояния:
   git reset --keep $previousCommit
4. Переустановите зависимости:
   .\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
5. Если миграция успела изменить базу, восстановите выбранный backup:
   .\scripts\restore-kanban.ps1 -BackupPath "<полный путь к backup>"
"@
    exit 1
}
