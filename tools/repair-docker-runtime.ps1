[CmdletBinding()]
param(
    [switch]$RepairKnownSocketFailure,
    [ValidateRange(30, 300)]
    [int]$WaitSeconds = 150
)

$ErrorActionPreference = 'Stop'

function Test-DockerEngine {
    & docker info --format '{{.ServerVersion}}' *> $null
    return $LASTEXITCODE -eq 0
}

function Wait-DockerEngine {
    param([int]$Seconds)
    $deadline = [DateTimeOffset]::Now.AddSeconds($Seconds)
    while ([DateTimeOffset]::Now -lt $deadline) {
        if (Test-DockerEngine) { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}

if (Test-DockerEngine) {
    Write-Host 'Docker engine is already healthy.'
    exit 0
}

Write-Host 'Docker engine is unavailable. Starting Docker Desktop...'
& docker desktop start --timeout $WaitSeconds
if (Wait-DockerEngine -Seconds $WaitSeconds) {
    Write-Host 'Docker engine started normally.'
    exit 0
}

$desktopLogs = (& docker desktop logs --boot 0 --priority 2 --no-color 2>&1 | Out-String)
$knownSocketFailure =
    $desktopLogs -match '(?i)(sailor-ingest\.sock|dockerInference|docker-secrets-engine|AppData\\Local\\Docker\\run)' -and
    $desktopLogs -match '(?i)(file cannot be accessed by the system|cannot remove|access.*denied|failed.*sock)'

if (-not $knownSocketFailure) {
    throw 'Docker did not start, but the known disposable-runtime socket failure was not present. No files were changed. Run Docker Desktop diagnostics.'
}
if (-not $RepairKnownSocketFailure) {
    throw 'The known Docker runtime socket failure was detected. Re-run with -RepairKnownSocketFailure to quarantine only %LOCALAPPDATA%\Docker\run and retry.'
}

$dockerRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Docker'))
$runtimePath = [IO.Path]::GetFullPath((Join-Path $dockerRoot 'run'))
$expectedPath = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE 'AppData\Local\Docker\run'))
if (-not $runtimePath.Equals($expectedPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing repair: resolved runtime path is outside the exact Docker disposable-runtime directory: $runtimePath"
}

& docker desktop stop --force --timeout 30
Start-Sleep -Seconds 3

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$quarantinePath = Join-Path $dockerRoot "run.stale-$stamp"
if (Test-Path -LiteralPath $quarantinePath) {
    throw "Refusing repair because quarantine target already exists: $quarantinePath"
}

if (Test-Path -LiteralPath $runtimePath) {
    try {
        Move-Item -LiteralPath $runtimePath -Destination $quarantinePath -ErrorAction Stop
    }
    catch {
        # Broken AF_UNIX reparse points can be unreadable to Win32 while the
        # same exact directory remains movable through WSL's /mnt/c view.
        $linuxSource = '/mnt/c/' + $runtimePath.Substring(3).Replace('\', '/')
        $linuxTarget = '/mnt/c/' + $quarantinePath.Substring(3).Replace('\', '/')
        & wsl.exe -d Ubuntu -- mv -- $linuxSource $linuxTarget
        if ($LASTEXITCODE -ne 0) {
            throw "Could not quarantine Docker's disposable runtime directory. Original error: $($_.Exception.Message)"
        }
    }
}

New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
Write-Host "Quarantined only Docker's disposable runtime sockets at: $quarantinePath"
Write-Host 'Postgres volumes, Redis data, images, containers, Ubuntu, and Hermes were not reset or stopped.'

& docker desktop start --timeout $WaitSeconds
if (-not (Wait-DockerEngine -Seconds $WaitSeconds)) {
    throw 'Docker runtime sockets were quarantined, but the engine still did not become healthy. The preserved quarantine has not been deleted.'
}

Write-Host 'Docker engine recovered and is responding.'

