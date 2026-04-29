# Fantasy Studio launcher
# =======================
# Starts backend (FastAPI on :8789) and frontend (Vite on :3000) in
# two separate PowerShell windows. Each window stays open after the
# command exits so you can read errors. Close both to stop.
#
# Usage from the fantasy-studio repo root:
#     .\launch.ps1
#
# If your repos live somewhere other than the default (sibling to
# fantasy-studio/), edit $backendPath / $frontendPath below.

param(
    [int]$BackendPort = 8789,
    [string]$BackendDir,
    [string]$FrontendDir
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot

# Default to monorepo subdirectories: ./backend, ./frontend
if (-not $BackendDir) {
    $BackendDir = Join-Path $repoRoot "backend"
}
if (-not $FrontendDir) {
    $FrontendDir = Join-Path $repoRoot "frontend"
}

# Verify directories exist
if (-not (Test-Path $BackendDir)) {
    Write-Host "ERROR: Backend directory not found at $BackendDir" -ForegroundColor Red
    Write-Host "Pass -BackendDir <path> to override." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $FrontendDir)) {
    Write-Host "ERROR: Frontend directory not found at $FrontendDir" -ForegroundColor Red
    Write-Host "Pass -FrontendDir <path> to override." -ForegroundColor Yellow
    exit 1
}

$venvActivate = Join-Path $BackendDir "venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Host "ERROR: Backend venv not found at $venvActivate" -ForegroundColor Red
    Write-Host "Run installation first: see INSTALL.md" -ForegroundColor Yellow
    exit 1
}

$packageJson = Join-Path $FrontendDir "package.json"
if (-not (Test-Path $packageJson)) {
    Write-Host "ERROR: Frontend package.json not found at $packageJson" -ForegroundColor Red
    Write-Host "Run 'npm install' in $FrontendDir first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Fantasy Studio launching..." -ForegroundColor Cyan
Write-Host "  Backend dir:  $BackendDir"
Write-Host "  Frontend dir: $FrontendDir"
Write-Host "  Backend port: $BackendPort"
Write-Host ""

# Launch backend in a new PowerShell window
$backendCmd = "cd '$BackendDir'; & '$venvActivate'; Write-Host 'Starting backend on port $BackendPort...' -ForegroundColor Green; python -m uvicorn app.main:app --port $BackendPort --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# Brief delay so the backend can bind its port before the frontend
# tries to talk to it.
Start-Sleep -Seconds 3

# Launch frontend in a second PowerShell window
$frontendCmd = "cd '$FrontendDir'; Write-Host 'Starting frontend (Vite)...' -ForegroundColor Green; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host "Two PowerShell windows opened." -ForegroundColor Green
Write-Host ""
Write-Host "  Backend:  http://localhost:$BackendPort  (and /api/health for liveness)"
Write-Host "  Frontend: http://localhost:3000  (Vite is configured with strictPort=true)"
Write-Host ""
Write-Host "Open http://localhost:3000 in your browser to use the studio."
Write-Host "Close both PowerShell windows to stop the services."
