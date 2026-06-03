# All-in-one finisher: handles VS Build Tools env, CUDA 12.8 install if needed,
# nvdiffrast compile, InstantMesh weights, and final diagnostic.
#
# Usage:
#   .\venv\Scripts\Activate.ps1
#   .\scripts\finish_instantmesh_setup.ps1

if (-not $env:VIRTUAL_ENV) {
    Write-Host "ERROR: no venv active. Run .\venv\Scripts\Activate.ps1 first." -ForegroundColor Red
    exit 1
}

# --- 1. Load MSVC x64 env if cl.exe isn't already on PATH ---
$cl = Get-Command cl.exe -ErrorAction SilentlyContinue
if (-not $cl) {
    Write-Host "Loading MSVC x64 environment..." -ForegroundColor Cyan
    $vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
    if (-not (Test-Path $vcvars)) {
        Write-Host "ERROR: VS Build Tools not found at expected path." -ForegroundColor Red
        Write-Host "  Run scripts\install_vs_buildtools.ps1 first." -ForegroundColor Red
        exit 1
    }
    cmd.exe /c "`"$vcvars`" && set" | ForEach-Object {
        if ($_ -match "^(.*?)=(.*)$") { Set-Item -Path "env:$($matches[1])" -Value $matches[2] }
    }
}
Write-Host "  MSVC ready" -ForegroundColor Green

# --- 2. Locate CUDA 12.8 toolkit (must match PyTorch's CUDA version) ---
Write-Host ""
Write-Host "Looking for CUDA 12.8 toolkit (must match PyTorch's build)..." -ForegroundColor Cyan
$cudaRoot = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
$cuda128Path = Join-Path $cudaRoot "v12.8"
$cudaHome = $null
if (Test-Path $cuda128Path) {
    $cudaHome = $cuda128Path
    Write-Host "  Found: $cudaHome" -ForegroundColor Green
}
else {
    Write-Host "  CUDA 12.8 not installed. Installing now via winget (~5 min)..." -ForegroundColor Yellow
    # Try winget first
    winget install --id Nvidia.CUDA --version 12.8.0 --accept-package-agreements --accept-source-agreements
    if (-not (Test-Path $cuda128Path)) {
        Write-Host "  winget install didn't land 12.8 — downloading network installer directly..." -ForegroundColor Yellow
        $installerUrl = "https://developer.download.nvidia.com/compute/cuda/12.8.0/network_installers/cuda_12.8.0_windows_network.exe"
        $installerExe = "$env:TEMP\cuda_12.8_network.exe"
        if (-not (Test-Path $installerExe)) {
            Write-Host "  Downloading $installerUrl ..."
            Invoke-WebRequest -Uri $installerUrl -OutFile $installerExe -UseBasicParsing
        }
        Write-Host "  Running silent install (5-10 min)..."
        $installArgs = @("-s", "nvcc_12.8", "cudart_12.8", "thrust_12.8", "visual_studio_integration_12.8")
        $proc = Start-Process -FilePath $installerExe -ArgumentList $installArgs -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            Write-Host "ERROR: CUDA installer returned $($proc.ExitCode)" -ForegroundColor Red
            Write-Host "Manual install: open this URL and run the installer" -ForegroundColor Yellow
            Write-Host "  $installerUrl" -ForegroundColor Yellow
            exit 1
        }
    }
    if (Test-Path $cuda128Path) {
        $cudaHome = $cuda128Path
        Write-Host "  Installed: $cudaHome" -ForegroundColor Green
    }
    else {
        Write-Host "ERROR: CUDA 12.8 still not detected after install." -ForegroundColor Red
        Write-Host "Check: dir 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA'" -ForegroundColor Yellow
        exit 1
    }
}
$env:CUDA_HOME = $cudaHome
$env:CUDA_PATH = $cudaHome
$env:PATH = "$cudaHome\bin;$cudaHome\libnvvp;$env:PATH"

# --- 3. Install nvdiffrast (PyTorch wants DISTUTILS_USE_SDK when VC env is active) ---
$env:DISTUTILS_USE_SDK = "1"
$env:CXX = "cl.exe"
Write-Host ""
Write-Host "Installing nvdiffrast (this takes 5-10 min -- actual compile)..." -ForegroundColor Cyan
pip install --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast.git"
if ($LASTEXITCODE -ne 0) {
    Write-Host "nvdiffrast install FAILED. Common fixes:" -ForegroundColor Red
    Write-Host "  - close + reopen Developer PowerShell, re-run this script" -ForegroundColor Yellow
    Write-Host "  - verify v12.8 install: dir '$cudaHome\bin\nvcc.exe'" -ForegroundColor Yellow
    exit 1
}
python -c "import nvdiffrast; print('  nvdiffrast OK')"

# --- 4. Re-download InstantMesh weights (diagnostic showed missing) ---
Write-Host ""
Write-Host "Verifying InstantMesh weights..." -ForegroundColor Cyan
python scripts\download_diffusion_models.py --only instantmesh

# --- 5. Final diagnostic ---
Write-Host ""
Write-Host "Final diagnostic..." -ForegroundColor Cyan
python scripts\check_instantmesh.py

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "DONE. To test:" -ForegroundColor Green
Write-Host "  python scripts\render_from_prompt.py 'a brown dog' --no-render" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
