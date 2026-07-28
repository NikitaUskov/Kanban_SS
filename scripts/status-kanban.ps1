param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "common.ps1")

$repositoryRoot = Get-KanbanRepositoryRoot
$config = Get-KanbanEnvironment -RepositoryRoot $repositoryRoot
$runDir = $config["RUN_DIR"]
$pagesUrl = $config["GITHUB_PAGES_URL"]

function Show-PidStatus {
    param([string]$Name, [string]$PidPath)
    if (-not (Test-Path $PidPath)) {
        Write-Host "${Name}: PID-файл отсутствует"
        return
    }
    $raw = (Get-Content -LiteralPath $PidPath -Raw).Trim()
    $pidValue = 0
    if (-not [int]::TryParse($raw, [ref]$pidValue)) {
        Write-Host "${Name}: некорректный PID-файл"
        return
    }
    $process = Get-KanbanProcessInfo -ProcessId $pidValue
    if ($null -eq $process) {
        Write-Host "${Name}: процесс не найден, PID-файл устарел"
    }
    else {
        Write-Host "${Name}: работает, PID $pidValue"
    }
}

Show-PidStatus -Name "Backend" -PidPath (Join-Path $runDir "backend.pid")
Show-PidStatus -Name "Quick Tunnel" -PidPath (Join-Path $runDir "cloudflared.pid")

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 8
    Write-Host "Local health: $($health.status), app $($health.appVersion), DB $($health.database)"
}
catch {
    Write-Warning "Local health недоступен: $($_.Exception.Message)"
}

$runtimePath = Join-Path $repositoryRoot $config["RUNTIME_CONFIG_PATH"]
if (Test-Path $runtimePath) {
    $runtime = Get-Content -LiteralPath $runtimePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Host "Local runtime: configVersion=$($runtime.configVersion), $($runtime.apiBaseUrl)"
}

if ($pagesUrl) {
    try {
        $remote = Invoke-RestMethod `
            -Uri ($pagesUrl.TrimEnd("/") + "/runtime-config.json?ts=" + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) `
            -TimeoutSec 15 `
            -Headers @{ "Cache-Control" = "no-cache" }
        Write-Host "GitHub Pages runtime: configVersion=$($remote.configVersion), $($remote.apiBaseUrl)"
    }
    catch {
        Write-Warning "GitHub Pages runtime недоступен: $($_.Exception.Message)"
    }
}
