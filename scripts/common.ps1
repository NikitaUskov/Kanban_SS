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
        [int]$IntervalSeconds = 2,
        [switch]$FlushDnsOnFailure
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    $attempt = 0
    while ((Get-Date) -lt $deadline) {
        $attempt += 1
        try {
            return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 10 -Headers @{
                "Cache-Control" = "no-cache"
            }
        }
        catch {
            $lastError = $_.Exception.Message
            if ($FlushDnsOnFailure -and ($attempt % 3 -eq 0)) {
                try {
                    ipconfig /flushdns | Out-Null
                }
                catch {
                    # Очистка DNS-кэша является вспомогательной операцией.
                }
            }
            Start-Sleep -Seconds $IntervalSeconds
        }
    }
    throw "URL не ответил за $TimeoutSeconds секунд: $Url. Последняя ошибка: $lastError"
}

function Get-KanbanProcessInfo {
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
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
        return $false
    }

    $rawPid = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    $processId = 0
    if (-not [int]::TryParse($rawPid, [ref]$processId)) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-Warning "Некорректный PID-файл удалён: $PidFile"
        return $false
    }

    $processInfo = Get-KanbanProcessInfo -ProcessId $processId
    if ($null -eq $processInfo) {
        Remove-Item -LiteralPath $PidFile -Force
        if (-not $Quiet) {
            Write-Host "${Label}: процесс уже завершён, старый PID-файл удалён."
        }
        return $false
    }

    if (-not $processInfo.CommandLine -or -not $processInfo.CommandLine.Contains($ExpectedCommandFragment)) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-Warning "${Label}: PID $processId уже принадлежит другому процессу. Старый PID-файл удалён; чужой процесс не остановлен."
        return $false
    }

    Stop-Process -Id $processId -ErrorAction Stop
    try {
        Wait-Process -Id $processId -Timeout 8 -ErrorAction Stop
    }
    catch {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    if (-not $Quiet) {
        Write-Host "${Label}: остановлен."
    }
    return $true
}

function Stop-KanbanOrphanProcesses {
    param(
        [Parameter(Mandatory = $true)][string]$CommandFragment,
        [Parameter(Mandatory = $true)][string]$Label,
        [switch]$Quiet
    )
    $matches = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.CommandLine -and $_.CommandLine.Contains($CommandFragment)
            }
    )
    foreach ($processInfo in $matches) {
        Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction SilentlyContinue
        if (-not $Quiet) {
            Write-Host "${Label}: остановлен найденный процесс PID $($processInfo.ProcessId)."
        }
    }
    return $matches.Count
}
