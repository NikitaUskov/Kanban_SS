param([switch]$Quiet)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "common.ps1")

$repositoryRoot = Get-KanbanRepositoryRoot
$config = Get-KanbanEnvironment -RepositoryRoot $repositoryRoot
$runDir = $config["RUN_DIR"]
if (-not $runDir) {
    throw "RUN_DIR отсутствует в backend\.env."
}

Stop-KanbanPidProcess `
    -PidFile (Join-Path $runDir "cloudflared.pid") `
    -ExpectedCommandFragment "tunnel --url http://127.0.0.1:8000" `
    -Label "Cloudflare Quick Tunnel" `
    -Quiet:$Quiet

Stop-KanbanPidProcess `
    -PidFile (Join-Path $runDir "backend.pid") `
    -ExpectedCommandFragment "uvicorn app.main:app" `
    -Label "Kanban backend" `
    -Quiet:$Quiet

