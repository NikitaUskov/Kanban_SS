param(
    [int]$BackendTimeoutSeconds = 90,
    [int]$TunnelTimeoutSeconds = 180,
    [int]$PagesTimeoutSeconds = 420,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Remove-KanbanHostsMarker {
    param(
        [Parameter(Mandatory = $true)][string]$HostsPath,
        [Parameter(Mandatory = $true)][string]$Marker
    )
    if (-not (Test-Path $HostsPath)) {
        return
    }
    $lines = @(Get-Content -LiteralPath $HostsPath -ErrorAction Stop)
    if (-not ($lines | Where-Object { $_.Contains($Marker) })) {
        return
    }
    $clean = @($lines | Where-Object { -not $_.Contains($Marker) })
    [IO.File]::WriteAllLines($HostsPath, $clean, [Text.Encoding]::ASCII)
}

if (-not (Test-IsAdministrator)) {
    throw "Запустите PowerShell от имени администратора. Это требуется только для временной IPv4-записи в hosts."
}

$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$cloudflareHost = "api.trycloudflare.com"
$marker = "# kanban-quick-tunnel-ipv4"
$startScript = Join-Path $PSScriptRoot "start-kanban.ps1"
if (-not (Test-Path $startScript)) {
    throw "Не найден $startScript"
}

# Удаляем запись, которая могла остаться после аварийного выключения Windows.
Remove-KanbanHostsMarker -HostsPath $hostsPath -Marker $marker
$originalHosts = [IO.File]::ReadAllBytes($hostsPath)

$ipv4 = Resolve-DnsName -Name $cloudflareHost -Type A -DnsOnly -ErrorAction Stop |
    Where-Object { $_.IPAddress -match '^\d{1,3}(\.\d{1,3}){3}$' } |
    Select-Object -ExpandProperty IPAddress -First 1
if (-not $ipv4) {
    throw "Не удалось получить IPv4-адрес $cloudflareHost."
}

$previousEdgeIpVersion = $env:TUNNEL_EDGE_IP_VERSION
try {
    Add-Content -LiteralPath $hostsPath -Value "`r`n$ipv4 $cloudflareHost $marker" -Encoding ASCII
    ipconfig /flushdns | Out-Null
    $env:TUNNEL_EDGE_IP_VERSION = "4"

    Write-Host "Для регистрации Quick Tunnel временно используется IPv4: $cloudflareHost -> $ipv4"
    & $startScript `
        -BackendTimeoutSeconds $BackendTimeoutSeconds `
        -TunnelTimeoutSeconds $TunnelTimeoutSeconds `
        -PagesTimeoutSeconds $PagesTimeoutSeconds `
        -NoBrowser:$NoBrowser
}
finally {
    # Возвращаем hosts побайтово, чтобы не менять его кодировку, комментарии и переносы строк.
    [IO.File]::WriteAllBytes($hostsPath, $originalHosts)
    ipconfig /flushdns | Out-Null
    if ($null -eq $previousEdgeIpVersion) {
        Remove-Item Env:TUNNEL_EDGE_IP_VERSION -ErrorAction SilentlyContinue
    }
    else {
        $env:TUNNEL_EDGE_IP_VERSION = $previousEdgeIpVersion
    }
    Write-Host "Временная IPv4-запись удалена; исходная работа IPv6 не менялась."
}
