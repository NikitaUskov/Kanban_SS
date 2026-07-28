$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Get-KanbanRepositoryRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-KanbanEnvironment {
    param([string]$RepositoryRoot = (Get-KanbanRepositoryRoot))
    $envPath = Join-Path $RepositoryRoot "backend\.env"
    if (-not (Test-Path $envPath)) {
        throw "Не найден $envPath. Сначала выполните scripts\install-kanban.ps1."
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $values
}

function Assert-CommandAvailable {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$InstallHint = ""
    )
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        $message = "Не найдена команда '$Name'."
        if ($InstallHint) {
            $message += " $InstallHint"
        }
        throw $message
    }
}

function Wait-KanbanJsonEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 60,
        [int]$IntervalSeconds = 2
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ((Get-Date) -lt $deadline) {
        try {
            return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 10 -Headers @{
                "Cache-Control" = "no-cache"
            }
        }
        catch {
            $lastError = $_.Exception.Message
            Start-Sleep -Seconds $IntervalSeconds
        }
    }
    throw "URL не ответил за $TimeoutSeconds секунд: $Url. Последняя ошибка: $lastError"
}

function Stop-KanbanPidProcess {
    param(
        [Parameter(Mandatory = $true)][string]$PidFile,
        [Parameter(Mandatory = $true)][string]$ExpectedCommandFragment,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$Quiet
    )
    if (-not (Test-Path $PidFile)) {
        if (-not $Quiet) {
            Write-Host "${Label}: PID-файл отсутствует, пропуск."
        }
        return
    }
    $rawPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    $processId = 0
    if (-not [int]::TryParse($rawPid, [ref]$processId)) {
        throw "Некорректный PID-файл: $PidFile"
    }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    if ($null -eq $processInfo) {
        Remove-Item -LiteralPath $PidFile -Force
        if (-not $Quiet) {
            Write-Host "${Label}: процесс уже завершён."
        }
        return
    }
    if (-not $processInfo.CommandLine -or -not $processInfo.CommandLine.Contains($ExpectedCommandFragment)) {
        throw "PID $processId принадлежит другому процессу. PID-файл не использован: $PidFile"
    }
    Stop-Process -Id $processId -ErrorAction Stop
    try {
        Wait-Process -Id $processId -Timeout 8 -ErrorAction Stop
    }
    catch {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile -Force
    if (-not $Quiet) {
        Write-Host "$Label остановлен."
    }
}

