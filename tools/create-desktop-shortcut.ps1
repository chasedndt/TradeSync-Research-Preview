[CmdletBinding()]
param([switch]$Update)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$logoPath = Join-Path $repoRoot 'docs\brand\assets\tradesync-mark.png'
$iconPath = Join-Path $repoRoot 'docs\brand\assets\tradesync-desktop.ico'
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopPath 'TradeSync.lnk'
$edgePath = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (!(Test-Path -LiteralPath $logoPath)) { throw 'Canonical logo is missing.' }
if (!(Test-Path -LiteralPath $edgePath)) { throw 'Microsoft Edge is unavailable.' }
if ((Test-Path -LiteralPath $shortcutPath) -and -not $Update) { throw 'TradeSync shortcut already exists; use -Update to replace it.' }

# Format conversion only: package the canonical PNG into a Windows icon.
Add-Type -AssemblyName System.Drawing
$source = [Drawing.Image]::FromFile($logoPath)
$bitmap = [Drawing.Bitmap]::new(256, 256)
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$png = [IO.MemoryStream]::new()
try {
    $graphics.Clear([Drawing.Color]::FromArgb(255, 7, 17, 31))
    $graphics.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.DrawImage($source, 0, 0, 256, 256)
    $bitmap.Save($png, [Drawing.Imaging.ImageFormat]::Png)
    $payload = $png.ToArray()
    $stream = [IO.File]::Open($iconPath, [IO.FileMode]::Create)
    $writer = [IO.BinaryWriter]::new($stream)
    try {
        $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]1)
        $writer.Write([byte]0); $writer.Write([byte]0); $writer.Write([byte]0); $writer.Write([byte]0)
        $writer.Write([uint16]1); $writer.Write([uint16]32)
        $writer.Write([uint32]$payload.Length); $writer.Write([uint32]22)
        $writer.Write($payload)
    } finally { $writer.Dispose(); $stream.Dispose() }
} finally { $png.Dispose(); $graphics.Dispose(); $bitmap.Dispose(); $source.Dispose() }

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $PSScriptRoot 'launch-tradesync.ps1')`""
$shortcut.WorkingDirectory = $repoRoot
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = 'Start or safely repair the TradeSync workstation stack, then open the local dashboard.'
$shortcut.Save()
$verified = $shell.CreateShortcut($shortcutPath)
[pscustomobject]@{ Shortcut=$shortcutPath; Target=$verified.TargetPath; Arguments=$verified.Arguments; Icon=$verified.IconLocation } | ConvertTo-Json
