param([switch]$Quiet)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "common.ps1")

$repositoryRoot = Get-KanbanRepositoryRoot
$config = Get-KanbanEnvironment -RepositoryRoot $repositoryRoot
$runDir = $config["RUN_DIR"]
$backendPython = Join-Path $repositoryRoot "backend\.venv\Scripts\python.exe"
if (-not $runDir) {
    throw "RUN_DIR отсутствует в backend\.env."
}

$stoppedTunnel = Stop-KanbanPidProcess `
    -PidFile (Join-Path $runDir "cloudflared.pid") `
    -ExpectedCommandFragment "--url http://127.0.0.1:8000" `
    -Label "Cloudflare Quick Tunnel" `
    -Quiet:$Quiet

$stoppedBackend = Stop-KanbanPidProcess `
    -PidFile (Join-Path $runDir "backend.pid") `
    -ExpectedCommandFragment "uvicorn app.main:app" `
    -Label "Kanban backend" `
    -Quiet:$Quiet

# PID-файл может устареть, если Windows повторно использовала PID. В таком случае
# останавливаем только процессы с однозначной командной строкой Kanban.
if (-not $stoppedTunnel) {
    Stop-KanbanOrphanProcesses `
        -CommandFragment "--url http://127.0.0.1:8000" `
        -Label "Cloudflare Quick Tunnel" `
        -Quiet:$Quiet | Out-Null
}

if (-not $stoppedBackend) {
    $backendProcesses = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine.Contains("uvicorn app.main:app") -and
                $_.ExecutablePath -and
                $_.ExecutablePath.Equals($backendPython, [StringComparison]::OrdinalIgnoreCase)
            }
    )
    foreach ($processInfo in $backendProcesses) {
        Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction SilentlyContinue
        if (-not $Quiet) {
            Write-Host "Kanban backend: остановлен найденный процесс PID $($processInfo.ProcessId)."
        }
    }
}

Remove-Item -LiteralPath (Join-Path $runDir "cloudflared.pid") -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $runDir "backend.pid") -Force -ErrorAction SilentlyContinue
