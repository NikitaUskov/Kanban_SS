param(
    [int]$BackendTimeoutSeconds = 90,
    [int]$TunnelTimeoutSeconds = 180,
    [int]$PagesTimeoutSeconds = 420,
    [int]$PushRetryCount = 3,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "common.ps1")

function Assert-GitState {
    param(
        [string]$RepositoryRoot,
        [string]$AllowedRuntimePath = ""
    )
    Push-Location $RepositoryRoot
    try {
        $inside = (& git rev-parse --is-inside-work-tree 2>$null).Trim()
        if ($inside -ne "true") {
            throw "Каталог не является Git-репозиторием: $RepositoryRoot"
        }
        $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
        if ($branch -ne "main") {
            throw "Для автоматического runtime commit переключитесь на ветку main. Сейчас: $branch"
        }
        $statusLines = @(& git status --porcelain --untracked-files=all)
        $foreign = @()
        foreach ($line in $statusLines) {
            if (-not $line) {
                continue
            }
            $path = $line.Substring(3).Trim()
            if ($path.Contains(" -> ")) {
                $path = $path.Split(" -> ", 2)[1]
            }
            $normalized = $path.Replace("\", "/").Trim('"')
            if (-not $AllowedRuntimePath -or $normalized -ne $AllowedRuntimePath) {
                $foreign += $line
            }
        }
        if ($foreign.Count -gt 0) {
            throw "Есть посторонние незакоммиченные изменения. Сохраните их до запуска:`n$($foreign -join [Environment]::NewLine)"
        }
    }
    finally {
        Pop-Location
    }
}

function Ensure-HttpsGitRemote {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$PagesUrl
    )
    Push-Location $RepositoryRoot
    try {
        $remote = (& git remote get-url origin 2>$null).Trim()
        if (-not $remote) {
            throw "В Git-репозитории отсутствует remote origin."
        }
        if ($remote.StartsWith("https://", [StringComparison]::OrdinalIgnoreCase)) {
            return
        }

        $parsedPages = [Uri]$PagesUrl
        $owner = $parsedPages.Host.Split(".")[0]
        $repositoryName = $parsedPages.AbsolutePath.Trim("/").Split("/")[0]
        if (-not $owner -or -not $repositoryName) {
            throw "Не удалось определить owner/repository из GITHUB_PAGES_URL: $PagesUrl"
        }
        $httpsRemote = "https://github.com/$owner/$repositoryName.git"
        & git remote set-url origin $httpsRemote
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось переключить origin на HTTPS."
        }
        Write-Host "Git remote origin переключён на HTTPS: $httpsRemote"
    }
    finally {
        Pop-Location
    }
}

function Push-RuntimeCommit {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$RuntimeRelative,
        [int]$RetryCount = 3
    )
    Push-Location $RepositoryRoot
    try {
        & git add -- $RuntimeRelative
        if ($LASTEXITCODE -ne 0) {
            throw "git add завершился ошибкой."
        }
        $staged = @(& git diff --cached --name-only)
        if ($staged.Count -ne 1 -or $staged[0].Replace("\", "/") -ne $RuntimeRelative) {
            & git reset -- $RuntimeRelative | Out-Null
            throw "В Git index присутствуют файлы кроме $RuntimeRelative. Commit отменён."
        }
        & git commit -m "chore(runtime): update quick tunnel URL"
        if ($LASTEXITCODE -ne 0) {
            throw "git commit завершился ошибкой."
        }

        for ($attempt = 1; $attempt -le $RetryCount; $attempt += 1) {
            & git push origin main
            if ($LASTEXITCODE -eq 0) {
                return $true
            }
            if ($attempt -lt $RetryCount) {
                $delay = 5 * $attempt
                Write-Warning "git push не выполнен. Повтор $($attempt + 1) через $delay секунд."
                Start-Sleep -Seconds $delay
            }
        }
        return $false
    }
    finally {
        Pop-Location
    }
}

Assert-CommandAvailable -Name "git" -InstallHint "Установите Git for Windows."
Assert-CommandAvailable -Name "cloudflared" -InstallHint "Установите cloudflared."

$repositoryRoot = Get-KanbanRepositoryRoot
$config = Get-KanbanEnvironment -RepositoryRoot $repositoryRoot
$frontendRepositoryRoot = if ($config["FRONTEND_REPOSITORY_PATH"]) {
    $config["FRONTEND_REPOSITORY_PATH"]
}
else {
    $repositoryRoot
}
$frontendRepositoryRoot = (Resolve-Path -LiteralPath $frontendRepositoryRoot).Path
$runtimeRelative = $config["RUNTIME_CONFIG_PATH"].Replace("\", "/").TrimStart("/")
$backendDir = Join-Path $repositoryRoot "backend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Не найдено виртуальное окружение. Выполните scripts\install-kanban.ps1."
}
$logDir = $config["LOG_DIR"]
$runDir = $config["RUN_DIR"]
$pagesUrl = $config["GITHUB_PAGES_URL"]
if (-not $logDir -or -not $runDir -or -not $pagesUrl) {
    throw "В backend\.env должны быть LOG_DIR, RUN_DIR и GITHUB_PAGES_URL."
}
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
New-Item -ItemType Directory -Path $runDir -Force | Out-Null

$cloudflareConfigCandidates = @(
    (Join-Path $env:USERPROFILE ".cloudflared\config.yaml"),
    (Join-Path $env:USERPROFILE ".cloudflared\config.yml")
)
foreach ($candidate in $cloudflareConfigCandidates) {
    if (Test-Path $candidate) {
        throw "Quick Tunnel не запускается при наличии $candidate. Временно переименуйте этот файл и повторите запуск."
    }
}

if ($frontendRepositoryRoot -eq $repositoryRoot) {
    Assert-GitState -RepositoryRoot $repositoryRoot -AllowedRuntimePath $runtimeRelative
}
else {
    Assert-GitState -RepositoryRoot $repositoryRoot
    Assert-GitState -RepositoryRoot $frontendRepositoryRoot -AllowedRuntimePath $runtimeRelative
}
Ensure-HttpsGitRemote -RepositoryRoot $frontendRepositoryRoot -PagesUrl $pagesUrl
& (Join-Path $PSScriptRoot "stop-kanban.ps1") -Quiet

$startupComplete = $false
try {
    Push-Location $backendDir
    try {
        & $python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось применить миграции."
        }
    }
    finally {
        Pop-Location
    }

    $backendOut = Join-Path $logDir "backend-stdout.log"
    $backendErr = Join-Path $logDir "backend-stderr.log"
    $backendProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "1") `
        -WorkingDirectory $backendDir `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Utf8NoBom -Path (Join-Path $runDir "backend.pid") -Content ([string]$backendProcess.Id)

    $health = Wait-KanbanJsonEndpoint `
        -Url "http://127.0.0.1:8000/api/v1/health" `
        -TimeoutSeconds $BackendTimeoutSeconds
    Write-Host "Backend запущен: PID $($backendProcess.Id), версия $($health.appVersion)."

    $tunnelOut = Join-Path $logDir "cloudflared-stdout.log"
    $tunnelErr = Join-Path $logDir "cloudflared-stderr.log"
    Remove-Item -LiteralPath $tunnelOut, $tunnelErr -Force -ErrorAction SilentlyContinue
    $cloudflaredPath = (Get-Command cloudflared).Source
    $tunnelProcess = Start-Process `
        -FilePath $cloudflaredPath `
        -ArgumentList @(
            "tunnel",
            "--edge-ip-version", "4",
            "--protocol", "http2",
            "--url", "http://127.0.0.1:8000",
            "--no-autoupdate",
            "--loglevel", "info"
        ) `
        -WorkingDirectory $repositoryRoot `
        -RedirectStandardOutput $tunnelOut `
        -RedirectStandardError $tunnelErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Utf8NoBom -Path (Join-Path $runDir "cloudflared.pid") -Content ([string]$tunnelProcess.Id)

    $deadline = (Get-Date).AddSeconds($TunnelTimeoutSeconds)
    $tunnelUrl = $null
    while ((Get-Date) -lt $deadline -and -not $tunnelUrl) {
        $combined = ""
        foreach ($path in @($tunnelOut, $tunnelErr)) {
            if (Test-Path $path) {
                $combined += Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue
            }
        }
        $match = [Regex]::Match(
            $combined,
            "https://(?!api\.)[-a-z0-9]+\.trycloudflare\.com",
            [Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
        if ($match.Success) {
            $tunnelUrl = $match.Value.ToLowerInvariant()
            break
        }
        if ($tunnelProcess.HasExited) {
            throw "cloudflared завершился до выдачи URL. Проверьте $tunnelErr"
        }
        Start-Sleep -Seconds 2
    }
    if (-not $tunnelUrl) {
        throw "Не удалось получить URL Quick Tunnel за $TunnelTimeoutSeconds секунд. Проверьте $tunnelErr"
    }

    Write-Host "Ожидание публикации DNS Quick Tunnel..."
    Start-Sleep -Seconds 10
    $publicHealth = Wait-KanbanJsonEndpoint `
        -Url "$tunnelUrl/api/v1/health" `
        -TimeoutSeconds $TunnelTimeoutSeconds `
        -IntervalSeconds 3 `
        -FlushDnsOnFailure
    Write-Host "Quick Tunnel отвечает: $tunnelUrl, API $($publicHealth.apiVersion)."
    $startupComplete = $true

    $runtimePath = if ([IO.Path]::IsPathRooted($runtimeRelative)) {
        $runtimeRelative
    }
    else {
        Join-Path $frontendRepositoryRoot $runtimeRelative
    }
    $oldVersion = 0
    if (Test-Path $runtimePath) {
        try {
            $oldVersion = [int](
                (Get-Content -LiteralPath $runtimePath -Raw -Encoding UTF8 | ConvertFrom-Json).configVersion
            )
        }
        catch {
            $oldVersion = 0
        }
    }
    $runtimeObject = [ordered]@{
        apiBaseUrl = "$tunnelUrl/api/v1"
        generatedAt = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
        configVersion = $oldVersion + 1
        appVersion = $health.appVersion
        apiVersion = $health.apiVersion
    }
    $runtimeJson = $runtimeObject | ConvertTo-Json -Depth 4
    $runtimeTemp = "$runtimePath.tmp"
    Write-Utf8NoBom -Path $runtimeTemp -Content ($runtimeJson + [Environment]::NewLine)
    Move-Item -LiteralPath $runtimeTemp -Destination $runtimePath -Force
    Write-Host "runtime-config.json обновлён: configVersion=$($runtimeObject.configVersion)."

    $published = $false
    try {
        $published = Push-RuntimeCommit `
            -RepositoryRoot $frontendRepositoryRoot `
            -RuntimeRelative $runtimeRelative `
            -RetryCount $PushRetryCount
    }
    catch {
        Write-Warning "Backend и туннель работают, но runtime commit не создан: $($_.Exception.Message)"
    }

    if (-not $published) {
        Write-Warning @"
Backend и туннель работают, но новый URL не опубликован в GitHub Pages.
Выполните вручную из репозитория: git push origin main
До успешного push постоянная страница может использовать старый URL.
"@
    }
    else {
        $configUrl = $pagesUrl.TrimEnd("/") + "/runtime-config.json"
        $pagesDeadline = (Get-Date).AddSeconds($PagesTimeoutSeconds)
        $pagesReady = $false
        while ((Get-Date) -lt $pagesDeadline) {
            try {
                $remoteConfig = Invoke-RestMethod `
                    -Uri ($configUrl + "?ts=" + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) `
                    -Method Get `
                    -TimeoutSec 15 `
                    -Headers @{ "Cache-Control" = "no-cache" }
                if ([int]$remoteConfig.configVersion -eq [int]$runtimeObject.configVersion) {
                    $pagesReady = $true
                    break
                }
            }
            catch {
                # GitHub Pages может быть временно недоступен во время deployment.
            }
            Start-Sleep -Seconds 10
        }
        if ($pagesReady) {
            Write-Host "GitHub Pages получил configVersion=$($runtimeObject.configVersion): $pagesUrl"
            if (-not $NoBrowser) {
                Start-Process $pagesUrl
            }
        }
        else {
            Write-Warning "Git push выполнен, но GitHub Pages не опубликовал новую версию за $PagesTimeoutSeconds секунд. Проверьте Actions."
        }
    }

    Write-Host "Система продолжает работать в фоне. Для остановки: .\scripts\stop-kanban.ps1"
    $global:LASTEXITCODE = 0
}
catch {
    if (-not $startupComplete) {
        try {
            & (Join-Path $PSScriptRoot "stop-kanban.ps1") -Quiet
        }
        catch {
            # Не скрываем исходную ошибку запуска.
        }
    }
    throw
}
