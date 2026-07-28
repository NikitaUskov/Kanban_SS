param(
    [string]$InstallRoot = "C:\Kanban",
    [string]$GitHubOwner = "",
    [string]$RepositoryName = "",
    [switch]$InstallPrerequisites,
    [bool]$ConfigureHttpsRemote = $true
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "common.ps1")

function Install-MissingPrograms {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget не найден. Установите Python 3.11+, Git for Windows и cloudflared вручную."
    }
    if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
        winget install --exact --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        winget install --exact --id Git.Git --accept-package-agreements --accept-source-agreements
    }
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
        winget install --exact --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
    }
    Write-Host "Установка программ завершена. Закройте PowerShell, откройте заново и повторите команду без -InstallPrerequisites."
}

function Set-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$Value
    )
    $pattern = "(?m)^" + [Regex]::Escape($Key) + "=.*$"
    if ([Regex]::IsMatch($Text, $pattern)) {
        return [Regex]::Replace($Text, $pattern, "$Key=$Value")
    }
    return $Text.TrimEnd() + [Environment]::NewLine + "$Key=$Value" + [Environment]::NewLine
}

function Get-EnvValueFromText {
    param(
        [Parameter(Mandatory = $true)][string]$Text,
        [Parameter(Mandatory = $true)][string]$Key
    )
    $pattern = "(?m)^" + [Regex]::Escape($Key) + "=(.*)$"
    $match = [Regex]::Match($Text, $pattern)
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }
    return ""
}

if ($InstallPrerequisites) {
    Install-MissingPrograms
    exit 0
}

Assert-CommandAvailable -Name "git" -InstallHint "Установите: winget install --exact --id Git.Git"
Assert-CommandAvailable -Name "cloudflared" -InstallHint "Установите: winget install --exact --id Cloudflare.cloudflared"
if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python не найден. Установите: winget install --exact --id Python.Python.3.11"
}

$repositoryRoot = Get-KanbanRepositoryRoot
$backendDir = Join-Path $repositoryRoot "backend"
if (-not (Test-Path (Join-Path $backendDir "requirements.txt"))) {
    throw "Скрипт должен находиться внутри полного репозитория Kanban Board."
}

if (-not $GitHubOwner) {
    $GitHubOwner = (Read-Host "Введите GitHub username или имя организации").Trim()
}
if (-not $RepositoryName) {
    $RepositoryName = (Read-Host "Введите точное имя репозитория").Trim()
}
if ($GitHubOwner -notmatch "^[A-Za-z0-9-]+$" -or $RepositoryName -notmatch "^[A-Za-z0-9._-]+$") {
    throw "GitHubOwner или RepositoryName имеют недопустимый формат."
}

$ownerLower = $GitHubOwner.ToLowerInvariant()
$pagesOrigin = "https://$ownerLower.github.io"
$pagesUrl = "$pagesOrigin/$RepositoryName/"
$httpsRemote = "https://github.com/$GitHubOwner/$RepositoryName.git"

$dataDir = Join-Path $InstallRoot "data"
$logDir = Join-Path $InstallRoot "logs"
$backupDir = Join-Path $InstallRoot "backups"
$runDir = Join-Path $InstallRoot "run"
foreach ($directory in @($InstallRoot, $dataDir, $logDir, $backupDir, $runDir)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$venvDir = Join-Path $backendDir ".venv"
if (-not (Test-Path (Join-Path $venvDir "Scripts\python.exe"))) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 -c "import sys; assert sys.version_info >= (3, 11)"
        if ($LASTEXITCODE -ne 0) {
            throw "Python 3.11+ не найден через py launcher."
        }
        & py -3.11 -m venv $venvDir
    }
    else {
        & python -c "import sys; assert sys.version_info >= (3, 11)"
        if ($LASTEXITCODE -ne 0) {
            throw "Требуется Python 3.11 или новее."
        }
        & python -m venv $venvDir
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось создать виртуальное окружение."
    }
}

$python = Join-Path $venvDir "Scripts\python.exe"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось обновить pip."
}
& $python -m pip install -r (Join-Path $backendDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось установить Python-зависимости."
}

$envExample = Join-Path $backendDir ".env.example"
$envPath = Join-Path $backendDir ".env"
$envCreated = -not (Test-Path $envPath)
if ($envCreated) {
    $envText = Get-Content -LiteralPath $envExample -Raw -Encoding UTF8
    $secretBytes = New-Object byte[] 64
    $randomGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
    $randomGenerator.GetBytes($secretBytes)
    $randomGenerator.Dispose()
    $jwtSecret = [Convert]::ToBase64String($secretBytes)
    $envText = Set-EnvValue -Text $envText -Key "JWT_SECRET" -Value $jwtSecret
}
else {
    $envText = Get-Content -LiteralPath $envPath -Raw -Encoding UTF8
}

$normalizedInstall = $InstallRoot.Replace("\", "/").TrimEnd("/")
$normalizedRepository = $repositoryRoot.Replace("\", "/")
$currentOrigins = Get-EnvValueFromText -Text $envText -Key "ALLOWED_ORIGINS"
$origins = New-Object 'System.Collections.Generic.List[string]'
foreach ($origin in ($currentOrigins -split ",")) {
    $normalized = $origin.Trim().TrimEnd("/")
    if ($normalized -and -not $origins.Contains($normalized)) {
        $origins.Add($normalized)
    }
}
foreach ($requiredOrigin in @($pagesOrigin, "http://127.0.0.1:5500", "http://localhost:5500")) {
    if (-not $origins.Contains($requiredOrigin)) {
        $origins.Add($requiredOrigin)
    }
}

$envText = Set-EnvValue -Text $envText -Key "APP_VERSION" -Value "1.1.0"
$envText = Set-EnvValue -Text $envText -Key "DATABASE_URL" -Value "sqlite:///$normalizedInstall/data/kanban.db"
$envText = Set-EnvValue -Text $envText -Key "LOG_DIR" -Value "$normalizedInstall/logs"
$envText = Set-EnvValue -Text $envText -Key "RUN_DIR" -Value "$normalizedInstall/run"
$envText = Set-EnvValue -Text $envText -Key "BACKUP_DIR" -Value "$normalizedInstall/backups"
$envText = Set-EnvValue -Text $envText -Key "ALLOWED_ORIGINS" -Value ($origins -join ",")
$envText = Set-EnvValue -Text $envText -Key "GITHUB_PAGES_URL" -Value $pagesUrl
$envText = Set-EnvValue -Text $envText -Key "REPOSITORY_PATH" -Value $normalizedRepository
$envText = Set-EnvValue -Text $envText -Key "FRONTEND_REPOSITORY_PATH" -Value $normalizedRepository
$envText = Set-EnvValue -Text $envText -Key "RUNTIME_CONFIG_PATH" -Value "frontend/runtime-config.json"
Write-Utf8NoBom -Path $envPath -Content $envText
if ($envCreated) {
    Write-Host "Создан backend\.env; JWT_SECRET сгенерирован локально и не выводился."
}
else {
    Write-Host "backend\.env сохранён; публичные URL и пути приведены к текущей установке."
}

if ($ConfigureHttpsRemote) {
    Push-Location $repositoryRoot
    try {
        $inside = (& git rev-parse --is-inside-work-tree 2>$null).Trim()
        if ($inside -eq "true") {
            $originExists = @(& git remote) -contains "origin"
            if ($originExists) {
                & git remote set-url origin $httpsRemote
            }
            else {
                & git remote add origin $httpsRemote
            }
            if ($LASTEXITCODE -ne 0) {
                throw "Не удалось настроить Git remote origin."
            }
            Write-Host "Git remote origin использует HTTPS: $httpsRemote"
        }
        else {
            Write-Warning "Каталог не является Git-репозиторием. Автопубликация runtime-config потребует клонирования репозитория через Git."
        }
    }
    finally {
        Pop-Location
    }
}

Push-Location $backendDir
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Alembic migration завершилась ошибкой."
    }
    & $python -c "from app.health.service import ready; print(ready().model_dump_json())"
    if ($LASTEXITCODE -ne 0) {
        throw "Проверка структуры базы завершилась ошибкой."
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Установка завершена."
Write-Host "Следующий шаг - создать пользователя:"
Write-Host "  cd `"$backendDir`""
Write-Host "  .\.venv\Scripts\python.exe -m scripts.manage_users create <username> --display-name `"<Имя>`""
Write-Host "После создания пользователей запустите от администратора: .\scripts\start-kanban-server.ps1"
