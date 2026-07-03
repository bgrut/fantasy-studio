# Install InstantMesh's Python dependencies into the active venv.
#
# Prerequisites:
#   1. VS Build Tools installed (run install_vs_buildtools.ps1 first)
#   2. PyTorch + CUDA installed
#   3. venv activated
#
# Usage:
#   .\scripts\install_instantmesh_deps.ps1

$ErrorActionPreference = "Stop"

if (-not $env:VIRTUAL_ENV) {
    Write-Host "ERROR: no venv active. Run: .\venv\Scripts\Activate.ps1" -ForegroundColor Red
    exit 1
}
Write-Host "Active venv: $env:VIRTUAL_ENV" -ForegroundColor Cyan

$cl = Get-Command cl.exe -ErrorAction SilentlyContinue
if (-not $cl) {
    Write-Host "WARNING: cl.exe (MSVC compiler) not on PATH." -ForegroundColor Yellow
    Write-Host "  nvdiffrast compile will likely fail." -ForegroundColor Yellow
    Write-Host "  Run scripts\install_vs_buildtools.ps1 first, then RESTART PowerShell." -ForegroundColor Yellow
    $confirm = Read-Host "Continue anyway? (y/n)"
    if ($confirm -ne "y") { exit 1 }
}

Write-Host ""
Write-Host "1/4. Lightweight Python deps" -ForegroundColor Cyan
pip install --upgrade omegaconf einops xatlas trimesh
pip install --upgrade "diffusers>=0.27" "transformers>=4.40" accelerate safetensors

Write-Host ""
Write-Host "2/4. nvdiffrast (compiles from source)" -ForegroundColor Cyan
Write-Host "  This will take several minutes. If it fails, see notes at bottom."
pip install --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast.git"

Write-Host ""
Write-Host "3/4. InstantMesh's own requirements.txt" -ForegroundColor Cyan
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Split-Path -Parent $scriptDir
$reqFile = Join-Path $backendRoot "vendor\InstantMesh\requirements.txt"
if (Test-Path $reqFile) {
    $reqs = Get-Content $reqFile | Where-Object { $_ -notmatch "nvdiffrast" -and $_ -notmatch "^#" -and $_.Trim() -ne "" }
    foreach ($r in $reqs) {
        Write-Host "  installing: $r" -ForegroundColor DarkGray
        try { pip install $r } catch { Write-Host "    ! failed (continuing): $r" -ForegroundColor Yellow }
    }
}
else {
    Write-Host "  vendor InstantMesh requirements.txt not found -- run install_mesh_engines.ps1 first" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "4/4. Sanity check" -ForegroundColor Cyan
python -c "import nvdiffrast; print('  nvdiffrast OK')"
python -c "import xatlas; print('  xatlas OK')"
python -c "import diffusers, transformers, omegaconf, einops; print('  diffusers stack OK')"

Write-Host ""
Write-Host "Dependencies installed." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Verify everything:  python scripts\check_instantmesh.py"
Write-Host "  2. First test render:  python scripts\render_from_prompt.py 'a brown dog' --no-render"
Write-Host ""
Write-Host "If nvdiffrast failed to compile:" -ForegroundColor Yellow
Write-Host "  - Verify MSVC is on PATH: cl.exe"
Write-Host "  - Verify CUDA toolkit installed: nvcc --version"
Write-Host "  - You can fall back to TripoSR by deleting backend\vendor\InstantMesh"
Write-Host ""
