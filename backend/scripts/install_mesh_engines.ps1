# Install TripoSR + InstantMesh by cloning into backend/vendor.
#
# Neither repo ships a setup.py / pyproject.toml, so pip-install-from-git fails.
# Standard practice in the research ML community is to clone + add to PYTHONPATH.
# That's what asset_gen/mesh.py expects — it looks for backend/vendor/TripoSR
# and backend/vendor/InstantMesh and adds them to sys.path automatically.
#
# Usage:
#     .\scripts\install_mesh_engines.ps1
#     .\scripts\install_mesh_engines.ps1 -SkipInstantMesh
#     .\scripts\install_mesh_engines.ps1 -Update    # git pull existing clones

param(
    [switch]$SkipTripoSR,
    [switch]$SkipInstantMesh,
    [switch]$Update
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VendorDir = Join-Path $RepoRoot "vendor"

if (-not (Test-Path $VendorDir)) {
    New-Item -ItemType Directory -Path $VendorDir | Out-Null
    Write-Host "Created vendor dir: $VendorDir"
}

function Install-Repo {
    param([string]$Name, [string]$Url, [string[]]$Reqs)

    $dst = Join-Path $VendorDir $Name
    if (Test-Path $dst) {
        if ($Update) {
            Write-Host "[$Name] git pull..." -ForegroundColor Cyan
            Push-Location $dst
            git pull --ff-only
            Pop-Location
        } else {
            Write-Host "[$Name] already cloned at $dst (use -Update to refresh)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[$Name] cloning $Url..." -ForegroundColor Cyan
        git clone --depth 1 $Url $dst
    }

    # Install the repo's runtime deps if requirements.txt exists
    $reqFile = Join-Path $dst "requirements.txt"
    if (Test-Path $reqFile) {
        Write-Host "[$Name] installing runtime deps from requirements.txt..." -ForegroundColor Cyan
        pip install -r $reqFile
    }

    # Extra deps not in requirements (or known-tricky ones)
    foreach ($r in $Reqs) {
        Write-Host "[$Name] pip install $r" -ForegroundColor Cyan
        pip install $r
    }

    Write-Host "[$Name] done." -ForegroundColor Green
}

if (-not $SkipTripoSR) {
    # TripoSR extra deps: torchmcubes (CUDA marching cubes) — Windows wheels
    # are unstable, but the official repo also supports pure-python mcubes.
    Install-Repo -Name "TripoSR" -Url "https://github.com/VAST-AI-Research/TripoSR" -Reqs @()
}

if (-not $SkipInstantMesh) {
    # InstantMesh has heavier deps including pytorch3d. We let its requirements.txt
    # try to install them; failures are documented in README. Most users on
    # Windows will rely on TripoSR alone — InstantMesh is the cinematic-tier upgrade.
    Install-Repo -Name "InstantMesh" -Url "https://github.com/TencentARC/InstantMesh" -Reqs @()
}

Write-Host ""
Write-Host "Vendor install complete." -ForegroundColor Green
Write-Host "  Vendor root: $VendorDir"
Write-Host ""
Write-Host "Test it:" -ForegroundColor Cyan
Write-Host "  python -c `"import sys; sys.path.insert(0, r'$VendorDir/TripoSR'); from tsr.system import TSR; print('TripoSR import OK')`""
Write-Host ""
