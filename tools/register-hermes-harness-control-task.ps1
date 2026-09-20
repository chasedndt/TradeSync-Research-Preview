<#
Registers TradeSync-Hermes-Harness-Control, the Windows task that runs the agent harness kill switch's
host control process (tools\hermes_harness_control.py) with pythonw: hidden, from logon, restarted a
minute after a failure, and started again within five minutes if it has exited (never a second copy).
Registering starts nothing, and nothing here stops or starts Hermes.

    powershell -NoProfile -ExecutionPolicy Bypass -File tools\register-hermes-harness-control-task.ps1
    Start-ScheduledTask -TaskName TradeSync-Hermes-Harness-Control

Refuses to replace an existing task unless -Replace is given.
#>
param(
    [string]$Repo = 'E:\Projects\TradeSync\dashboard-overhaul-2026-09-01',
    [switch]$Replace
)
$ErrorActionPreference = 'Stop'
$taskName = 'TradeSync-Hermes-Harness-Control'
$pythonw = Join-Path $Repo '.venv\Scripts\pythonw.exe'
$script = Join-Path $Repo 'tools\hermes_harness_control.py'
if (!(Test-Path -LiteralPath $pythonw)) { throw "pythonw.exe not found at $pythonw" }
if (!(Test-Path -LiteralPath $script)) { throw "The host control process is not at $script; merge the kill switch branch into that checkout first." }
if ((Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) -and !$Replace) {
    throw "$taskName already exists; pass -Replace to register it again."
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`"" -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
# Repeats every five minutes after logon with no end: an exited process starts again, a running one is kept (IgnoreNew).
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)).Repetition
$settings = New-ScheduledTaskSettingsSet -Hidden -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$description = 'TradeSync agent harness kill switch: applies stop and start requests from the Cockpit to the Hermes gateway in WSL. Does not control the ChaseOS coordination daemon.'
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description $description -Force:$Replace | Out-Null

$task = Get-ScheduledTask -TaskName $taskName
[pscustomobject]@{
    Task = $task.TaskName
    State = [string]$task.State
    Execute = $task.Actions[0].Execute
    Arguments = $task.Actions[0].Arguments
    Trigger = 'At logon, repeating every 5 minutes'
    RestartCount = $task.Settings.RestartCount
    RestartInterval = $task.Settings.RestartInterval
} | ConvertTo-Json
