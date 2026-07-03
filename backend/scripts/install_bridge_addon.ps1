# ╔══════════════════════════════════════════════════════════════════════╗
# ║ install_bridge_addon.ps1                                             ║
# ║                                                                      ║
# ║ Copies the fantasy_studio_bridge addon into Blender's user scripts/  ║
# ║ addons folder so Blender can find and enable it.                     ║
# ║                                                                      ║
# ║ Usage:                                                               ║
# ║   .\install_bridge_addon.ps1                  # autodetect Blender   ║
# ║   .\install_bridge_addon.ps1 -BlenderVersion 4.2                     ║
# ║                                                                      ║
# ║ After install: open Blender → Edit > Preferences > Add-ons →         ║
# ║ enable "Fantasy Studio Bridge". It auto-starts on enable.            ║
# ╚══════════════════════════════════════════════════════════════════════╝

param(
    [string]$BlenderVersion = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$AddonSrc = Join-Path $RepoRoot "blender_addons\fantasy_studio_bridge"

if (-not (Test-Path $AddonSrc)) {
    Write-Host "ERROR: addon source not found at $AddonSrc" -ForegroundColor Red
    exit 1
}

# Locate Blender's user-scripts folder
$AppData = $env:APPDATA
$BlenderRoot = Join-Path $AppData "Blender Foundation\Blender"

if (-not (Test-Path $BlenderRoot)) {
    Write-Host "ERROR: Blender user folder not found at $BlenderRoot" -ForegroundColor Red
    Write-Host "Is Blender installed and has it been launched at least once?" -ForegroundColor Yellow
    exit 1
}

# Auto-detect version if not specified — pick newest
if ([string]::IsNullOrEmpty($BlenderVersion)) {
    $versions = Get-ChildItem -Path $BlenderRoot -Directory | Where-Object { $_.Name -match '^\d+\.\d+$' } | Sort-Object Name -Descending
    if ($versions.Count -eq 0) {
        Write-Host "ERROR: no Blender version folders found under $BlenderRoot" -ForegroundColor Red
        exit 1
    }
    $BlenderVersion = $versions[0].Name
    Write-Host "Auto-detected Blender version: $BlenderVersion" -ForegroundColor Cyan
}

$AddonsDir = Join-Path $BlenderRoot "$BlenderVersion\scripts\addons"
if (-not (Test-Path $AddonsDir)) {
    New-Item -ItemType Directory -Path $AddonsDir -Force | Out-Null
    Write-Host "Created addons dir: $AddonsDir" -ForegroundColor Yellow
}

$AddonDst = Join-Path $AddonsDir "fantasy_studio_bridge"

if (Test-Path $AddonDst) {
    Write-Host "Removing existing install at $AddonDst" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $AddonDst
}

Copy-Item -Recurse $AddonSrc $AddonDst
Write-Host ""
Write-Host "✓ Installed fantasy_studio_bridge to:" -ForegroundColor Green
Write-Host "  $AddonDst" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps (interactive mode):" -ForegroundColor Cyan
Write-Host "  1. Open Blender"
Write-Host "  2. Edit menu, then Preferences, then Add-ons"
Write-Host "  3. Search 'Fantasy Studio Bridge', enable the checkbox"
Write-Host "  4. Bridge auto-starts on port 9876. Status in N-panel, Studio tab."
Write-Host ""
Write-Host "Or for headless mode (no Blender UI):" -ForegroundColor Cyan
Write-Host "  .\scripts\start_headless_bridge.ps1"
Write-Host ""
Write-Host "Test the connection:" -ForegroundColor Cyan
Write-Host "  python scripts\smoke_test_bridge.py"

