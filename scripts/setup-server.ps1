param(
    [string]$InstallRoot = "C:\Kanban",
    [Parameter(Mandatory = $true)][string]$GitHubOwner,
    [Parameter(Mandatory = $true)][string]$RepositoryName,
    [string]$FirstUsername = "",
    [string]$FirstDisplayName = "",
    [string]$FirstEmail = "",
    [switch]$RegisterAutostart
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Откройте PowerShell от имени администратора."
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$expectedRepository = Join-Path $InstallRoot "repository"
if (-not $repositoryRoot.Equals($expectedRepository, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Рекомендуемый путь репозитория: $expectedRepository. Текущий путь: $repositoryRoot"
}

& (Join-Path $PSScriptRoot "install-kanban.ps1") `
    -InstallRoot $InstallRoot `
    -GitHubOwner $GitHubOwner `
    -RepositoryName $RepositoryName `
    -ConfigureHttpsRemote $true

if ($FirstUsername) {
    if (-not $FirstDisplayName) {
        $FirstDisplayName = $FirstUsername
    }
    $python = Join-Path $repositoryRoot "backend\.venv\Scripts\python.exe"
    Push-Location (Join-Path $repositoryRoot "backend")
    try {
        $createArguments = @("-m", "scripts.manage_users", "create", $FirstUsername, "--display-name", $FirstDisplayName)
        if ($FirstEmail) {
            $createArguments += @("--email", $FirstEmail)
        }
        & $python @createArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось создать первого пользователя."
        }
    }
    finally {
        Pop-Location
    }
}

if ($RegisterAutostart) {
    & (Join-Path $PSScriptRoot "register-autostart.ps1")
}

Push-Location $repositoryRoot
try {
    Write-Host "Проверка GitHub HTTPS-аутентификации (push --dry-run)..."
    & git push --dry-run origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "GitHub-аутентификация не завершена. Выполните вручную: git push --dry-run origin main"
    }
}
finally {
    Pop-Location
}

Write-Host "Настройка сервера завершена. Первый запуск: .\scripts\start-kanban-server.ps1"
