# start_headless_bridge.ps1
#
# Launches Blender in headless background mode with the fantasy_studio_bridge
# addon enabled. No Blender UI appears - it runs as a background service
# exposing the bridge socket on port 9876.
#
# Prerequisites:
#   1. Addon installed under Blender's addons folder
#   2. Blender installed (auto-detected from Program Files)
#
# Usage:
#   .\start_headless_bridge.ps1
#   .\start_headless_bridge.ps1 -BlenderExe "D:\Blender\blender.exe"
#   .\start_headless_bridge.ps1 -Port 9877
#
# Stop with Ctrl-C.

param(
    [string]$BlenderExe = "",
    [int]$Port = 9876
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$StartupScript = Join-Path $RepoRoot "scripts\headless_bridge_startup.py"

if (-not (Test-Path $StartupScript)) {
    Write-Host "ERROR: startup script not found at $StartupScript" -ForegroundColor Red
    exit 1
}

# Auto-detect Blender exe if not specified
if ([string]::IsNullOrEmpty($BlenderExe)) {
    $bfRoot = "${env:ProgramFiles}\Blender Foundation"
    if (Test-Path $bfRoot) {
        $found = Get-ChildItem $bfRoot -Filter "blender.exe" -Recurse -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($found) { $BlenderExe = $found.FullName }
    }
    if ([string]::IsNullOrEmpty($BlenderExe)) {
        Write-Host "ERROR: could not locate blender.exe. Pass -BlenderExe explicitly." -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path $BlenderExe)) {
    Write-Host "ERROR: BlenderExe not found at $BlenderExe" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Launching headless Blender bridge..." -ForegroundColor Cyan
Write-Host "  Blender: $BlenderExe" -ForegroundColor DarkGray
Write-Host "  Port:    127.0.0.1:$Port" -ForegroundColor DarkGray
Write-Host "  Stop:    Ctrl-C" -ForegroundColor DarkGray
Write-Host ""

$env:FANTASY_STUDIO_BRIDGE_PORT = "$Port"
$env:FANTASY_STUDIO_BRIDGE_AUTOSTART = "1"

& $BlenderExe --background --python $StartupScript
