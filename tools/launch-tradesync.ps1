$ErrorActionPreference = 'Stop'
$chromePaths = @(
    'C:\Program Files\Google\Chrome\Application\chrome.exe',
    'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
)
$edgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$chromeUserData = Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'
$phantomExtensionId = 'bfnaelmomeimhlpmgjnjophhpkkoljpa'
$logPath = 'E:\Projects\TradeSync\dashboard-runtime\launcher.log'
$cockpitUrl = 'http://127.0.0.1:3000/'

try {
    # Compose writes ordinary progress lines to stderr. Preserve those in the
    # log, but judge startup by the child script's exit code rather than by the
    # stream PowerShell chose for the line.
    $ErrorActionPreference = 'Continue'
    & (Join-Path $PSScriptRoot 'start-tradesync.ps1') *>> $logPath
    $startExitCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($startExitCode -ne 0) { throw "TradeSync startup exited with code $startExitCode." }

    $deadline = [DateTimeOffset]::Now.AddSeconds(120)
    $ready = $false
    while ([DateTimeOffset]::Now -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $cockpitUrl -TimeoutSec 3
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        }
        catch { Start-Sleep -Seconds 2 }
    }
    if (-not $ready) { throw 'Docker started, but the TradeSync Cockpit did not become ready within 120 seconds.' }

    Add-Content -LiteralPath $logPath -Value "[$([DateTimeOffset]::Now.ToString('o'))] READY $cockpitUrl"
    $chromePath = $chromePaths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if ($chromePath) {
        # Use the ordinary Chrome profile store so an operator-installed Phantom
        # extension can inject its provider. Prefer whichever profile already has
        # Phantom, otherwise use Default and let the in-app official install link
        # complete the one-time operator setup. Never share the automated
        # StrikeZone profile merely to gain wallet access.
        $profileDirectory = 'Default'
        $localStatePath = Join-Path $chromeUserData 'Local State'
        if (Test-Path -LiteralPath $localStatePath -PathType Leaf) {
            try {
                $localState = Get-Content -LiteralPath $localStatePath -Raw | ConvertFrom-Json
                $phantomProfile = $localState.profile.info_cache.PSObject.Properties |
                    Where-Object {
                        $extensionPath = Join-Path (Join-Path (Join-Path $chromeUserData $_.Name) 'Extensions') $phantomExtensionId
                        Test-Path -LiteralPath $extensionPath -PathType Container
                    } |
                    Select-Object -First 1
                if ($phantomProfile) { $profileDirectory = $phantomProfile.Name }
            }
            catch {
                Add-Content -LiteralPath $logPath -Value "[$([DateTimeOffset]::Now.ToString('o'))] Browser profile discovery failed: $($_.Exception.Message)"
            }
        }
        $phantomDetected = Test-Path -LiteralPath (Join-Path (Join-Path (Join-Path $chromeUserData $profileDirectory) 'Extensions') $phantomExtensionId) -PathType Container
        Add-Content -LiteralPath $logPath -Value "[$([DateTimeOffset]::Now.ToString('o'))] BROWSER chrome profile='$profileDirectory' phantom_installed=$phantomDetected"
        Start-Process -FilePath $chromePath -ArgumentList @("--profile-directory=$profileDirectory", "--app=$cockpitUrl")
    }
    elseif (Test-Path -LiteralPath $edgePath -PathType Leaf) {
        Add-Content -LiteralPath $logPath -Value "[$([DateTimeOffset]::Now.ToString('o'))] BROWSER edge fallback"
        Start-Process -FilePath $edgePath -ArgumentList "--app=$cockpitUrl"
    }
    else {
        Start-Process $cockpitUrl
    }
}
catch {
    Add-Content -LiteralPath $logPath -Value "[$([DateTimeOffset]::Now.ToString('o'))] $($_.Exception.Message)"
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "TradeSync could not start. Details were saved to:`n$logPath",
        'TradeSync startup',
        [System.Windows.MessageBoxButton]::OK,
        [System.Windows.MessageBoxImage]::Error
    ) | Out-Null
    exit 1
}
