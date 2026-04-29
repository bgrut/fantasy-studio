# Fantasy Studio — One-command setup
# ===================================
# Verifies prerequisites and installs all dependencies for the
# backend (Python venv + pip) and the frontend (npm).
#
# Usage from the fantasy-studio repo root:
#     .\setup.ps1
#
# After this completes, run:
#     .\launch.ps1

param(
    [switch]$SkipOllamaCheck,
    [switch]$ForceVenvRecreate
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot

Write-Host ""
Write-Host "Fantasy Studio Setup" -ForegroundColor Cyan
Write-Host "====================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Verify Python 3.11+ ───────────────────────────────────────
try {
    $pythonVersion = (& python --version) 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "python --version returned $LASTEXITCODE" }
    Write-Host "  [OK]   Python: $($pythonVersion.Trim())" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Python not found." -ForegroundColor Red
    Write-Host "         Install Python 3.11+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "         Be sure to check 'Add Python to PATH' during install." -ForegroundColor Yellow
    exit 1
}

# ── 2. Verify Node.js 20+ ────────────────────────────────────────
try {
    $nodeVersion = (& node --version) 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "node --version returned $LASTEXITCODE" }
    Write-Host "  [OK]   Node.js: $($nodeVersion.Trim())" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Node.js not found." -ForegroundColor Red
    Write-Host "         Install Node 20+ LTS from https://nodejs.org/" -ForegroundColor Yellow
    exit 1
}

# ── 3. Verify Ollama (warn-only) ─────────────────────────────────
if (-not $SkipOllamaCheck) {
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:11434/api/version" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Write-Host "  [OK]   Ollama: reachable on http://localhost:11434" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] Ollama not reachable on http://localhost:11434" -ForegroundColor Yellow
        Write-Host "         Install from https://ollama.com and start the service." -ForegroundColor Yellow
        Write-Host "         Then run:  ollama pull gemma3:12b" -ForegroundColor Yellow
        Write-Host "         Continuing setup — render quality will use the deterministic fallback director until Ollama is available." -ForegroundColor Yellow
    }
}

# ── 4. Backend setup ─────────────────────────────────────────────
Write-Host ""
Write-Host "Setting up backend..." -ForegroundColor Cyan
$backendPath = Join-Path $repoRoot "backend"

if (-not (Test-Path $backendPath)) {
    Write-Host "  [FAIL] Backend directory not found at $backendPath" -ForegroundColor Red
    exit 1
}

Push-Location $backendPath
try {
    $venvPath = Join-Path $backendPath "venv"
    if ($ForceVenvRecreate -and (Test-Path $venvPath)) {
        Write-Host "  [..]   Removing existing venv (force recreate)..." -ForegroundColor DarkGray
        Remove-Item -Recurse -Force $venvPath
    }
    if (-not (Test-Path $venvPath)) {
        Write-Host "  [..]   Creating Python venv..." -ForegroundColor DarkGray
        & python -m venv venv
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
    } else {
        Write-Host "  [OK]   venv exists (use -ForceVenvRecreate to rebuild)" -ForegroundColor Green
    }

    Write-Host "  [..]   Installing dependencies from requirements.txt..." -ForegroundColor DarkGray
    & .\venv\Scripts\pip.exe install --upgrade pip --quiet
    & .\venv\Scripts\pip.exe install -r requirements.txt --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt failed" }
    Write-Host "  [OK]   Backend dependencies installed" -ForegroundColor Green
} finally {
    Pop-Location
}

# ── 5. Frontend setup ────────────────────────────────────────────
Write-Host ""
Write-Host "Setting up frontend..." -ForegroundColor Cyan
$frontendPath = Join-Path $repoRoot "frontend"

if (-not (Test-Path $frontendPath)) {
    Write-Host "  [FAIL] Frontend directory not found at $frontendPath" -ForegroundColor Red
    exit 1
}

Push-Location $frontendPath
try {
    Write-Host "  [..]   Running npm install (1-3 minutes)..." -ForegroundColor DarkGray
    & npm install --silent
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    Write-Host "  [OK]   Frontend dependencies installed" -ForegroundColor Green
} finally {
    Pop-Location
}

# ── 6. .env file scaffolding ─────────────────────────────────────
Write-Host ""
Write-Host "Configuring environment files..." -ForegroundColor Cyan
$backendEnv = Join-Path $backendPath ".env"
$backendEnvExample = Join-Path $backendPath ".env.example"
if ((-not (Test-Path $backendEnv)) -and (Test-Path $backendEnvExample)) {
    Copy-Item $backendEnvExample $backendEnv
    Write-Host "  [OK]   Created backend/.env from .env.example" -ForegroundColor Green
    Write-Host "         Edit it to add your Sketchfab token (optional but recommended)." -ForegroundColor Yellow
} else {
    Write-Host "  [OK]   backend/.env already exists (leaving alone)" -ForegroundColor Green
}

$frontendEnv = Join-Path $frontendPath ".env.local"
$frontendEnvExample = Join-Path $frontendPath ".env.example"
if ((-not (Test-Path $frontendEnv)) -and (Test-Path $frontendEnvExample)) {
    Copy-Item $frontendEnvExample $frontendEnv
    Write-Host "  [OK]   Created frontend/.env.local from .env.example" -ForegroundColor Green
    Write-Host "         Edit it to add Blink credentials (optional)." -ForegroundColor Yellow
} else {
    Write-Host "  [OK]   frontend/.env.local already exists (leaving alone)" -ForegroundColor Green
}

# ── Done ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  1. (Optional) Edit backend/.env and frontend/.env.local with your tokens"
Write-Host "  2. Run .\launch.ps1 to start Fantasy Studio"
Write-Host ""
