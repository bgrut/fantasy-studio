# Install Microsoft Visual Studio Build Tools 2022 with the C++ workload.
# Required to compile nvdiffrast (and other CUDA-extending packages) from source.
# One-time install; ~3 GB on disk.
#
# Usage:
#   .\scripts\install_vs_buildtools.ps1
#
# After install, RESTART your PowerShell window so the new MSVC environment
# variables get picked up.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "Installing Visual Studio 2022 Build Tools with C++ workload" -ForegroundColor Cyan
Write-Host "This is a one-time install of about 3 GB."
Write-Host ""

$useWinget = $null -ne (Get-Command winget -ErrorAction SilentlyContinue)

if ($useWinget) {
    Write-Host "Using winget..." -ForegroundColor Cyan
    $overrideArgs = "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    winget install --id Microsoft.VisualStudio.2022.BuildTools --override $overrideArgs --accept-package-agreements --accept-source-agreements
}
else {
    Write-Host "winget not available -- downloading installer directly..." -ForegroundColor Yellow
    $url = "https://aka.ms/vs/17/release/vs_BuildTools.exe"
    $exe = "$env:TEMP\vs_BuildTools.exe"
    Invoke-WebRequest -Uri $url -OutFile $exe
    $args = @("--quiet", "--wait", "--add", "Microsoft.VisualStudio.Workload.VCTools", "--includeRecommended")
    Start-Process -FilePath $exe -ArgumentList $args -Wait
}

Write-Host ""
Write-Host "VS Build Tools install attempted." -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: close this PowerShell window and open a NEW one" -ForegroundColor Yellow
Write-Host "           so the MSVC environment variables get loaded." -ForegroundColor Yellow
Write-Host ""
Write-Host "Then verify with:" -ForegroundColor Cyan
Write-Host "  cl.exe   # should print 'Microsoft (R) C/C++ Optimizing Compiler...'"
Write-Host ""
