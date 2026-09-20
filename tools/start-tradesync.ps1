[CmdletBinding()]
param(
    [string]$RuntimeEnv = 'E:\Projects\TradeSync\dashboard-runtime\runtime.env',
    [switch]$SkipDockerRepair
)

$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$composeBase = Join-Path $repo 'ops\compose.full.yml'
$composeOverlay = Join-Path $repo 'ops\compose.market-command.yml'
$previousIgnoreOrphans = $env:COMPOSE_IGNORE_ORPHANS

if (-not (Test-Path -LiteralPath $RuntimeEnv -PathType Leaf)) {
    throw "TradeSync runtime environment was not found: $RuntimeEnv"
}

try {
    # cloudflared and signer can be running from their deliberately separate
    # overlays. They are not disposable orphans and must neither block startup
    # nor be removed by the desktop launcher.
    $env:COMPOSE_IGNORE_ORPHANS = 'true'

    if (-not $SkipDockerRepair) {
        & (Join-Path $PSScriptRoot 'repair-docker-runtime.ps1') -RepairKnownSocketFailure
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    # Operator, evidence and notification services are the safe workstation set.
    # paper-exec and analytics remain opt-in; this launcher never enables live
    # execution, signing, withdrawals, bridges or wallet approvals.
    $composeErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & docker compose `
        --project-name tradesync-full `
        --env-file $RuntimeEnv `
        -f $composeBase `
        -f $composeOverlay `
        --profile operator `
        --profile evidence `
        --profile notifications `
        up -d
    $upExitCode = $LASTEXITCODE
    $ErrorActionPreference = $composeErrorPreference
    if ($upExitCode -ne 0) { exit $upExitCode }

    $ErrorActionPreference = 'Continue'
    & docker compose `
        --project-name tradesync-full `
        --env-file $RuntimeEnv `
        -f $composeBase `
        -f $composeOverlay `
        --profile operator `
        --profile evidence `
        --profile notifications `
        ps
    $psExitCode = $LASTEXITCODE
    $ErrorActionPreference = $composeErrorPreference
    if ($psExitCode -ne 0) { exit $psExitCode }
    Write-Host 'TradeSync workstation services are started. Cockpit: http://127.0.0.1:3000/'
}
finally {
    $env:COMPOSE_IGNORE_ORPHANS = $previousIgnoreOrphans
}
