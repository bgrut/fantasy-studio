# Fantasy Studio desktop — single-terminal dev launcher (Aurora pattern).
# Starts the FastAPI backend (8789) + Vite frontend (3000) + the Tauri window.
# Ctrl-C closes the window; background jobs are cleaned up on exit.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Write-Host "[desktop] starting backend (8789)..." -ForegroundColor Cyan
$backend = Start-Process -PassThru -WindowStyle Hidden -FilePath "$root\backend\venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8789" `
    -WorkingDirectory "$root\backend"

Write-Host "[desktop] starting frontend (3000)..." -ForegroundColor Cyan
$frontend = Start-Process -PassThru -WindowStyle Hidden -FilePath "cmd" `
    -ArgumentList "/c", "npm run dev" -WorkingDirectory "$root\frontend"

try {
    Write-Host "[desktop] opening Fantasy Studio window..." -ForegroundColor Green
    Set-Location $PSScriptRoot
    npm run dev    # tauri dev — blocks until the window closes
} finally {
    Write-Host "[desktop] shutting down..." -ForegroundColor Yellow
    foreach ($p in @($backend, $frontend)) {
        if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
}
