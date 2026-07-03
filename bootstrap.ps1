# Fantasy Studio — one-command installer.
#
#   irm https://raw.githubusercontent.com/bgrut/fantasy-studio/main/bootstrap.ps1 | iex
#
# Checks prerequisites, clones the repo (or updates an existing clone in the
# current directory), runs setup.ps1 (venv + npm + env files), pulls the local
# LLM model, and tells you exactly how to launch. Safe to re-run.

$ErrorActionPreference = "Stop"
$repo = "https://github.com/bgrut/fantasy-studio"

Write-Host ""
Write-Host "  Fantasy Studio installer" -ForegroundColor Magenta
Write-Host "  ------------------------" -ForegroundColor DarkGray

# ── prerequisites ────────────────────────────────────────────────────────────
$missing = @()
function Need($cmd, $label, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        $script:missing += "$label  ->  $hint"
        Write-Host "  [MISSING] $label" -ForegroundColor Red
    } else {
        Write-Host "  [ok] $label" -ForegroundColor Green
    }
}
Need git    "Git"          "winget install Git.Git"
Need python "Python 3.11+" "winget install Python.Python.3.12"
Need node   "Node.js 20+"  "winget install OpenJS.NodeJS.LTS"
Need ollama "Ollama"       "winget install Ollama.Ollama   (then reopen terminal)"

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "  Install the missing prerequisites, reopen PowerShell, and re-run this command." -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "    $_" }
    return
}

# ── clone or update ──────────────────────────────────────────────────────────
if (Test-Path "fantasy-studio\setup.ps1") {
    Write-Host "  [ok] existing clone found — updating" -ForegroundColor Green
    Push-Location fantasy-studio; git pull --ff-only; Pop-Location
} elseif (Test-Path ".\setup.ps1") {
    Write-Host "  [ok] running inside the repo" -ForegroundColor Green
} else {
    Write-Host "  cloning $repo ..." -ForegroundColor Cyan
    git clone $repo
}
if (Test-Path "fantasy-studio") { Set-Location fantasy-studio }

# ── setup + model ────────────────────────────────────────────────────────────
Write-Host "  running setup.ps1 (venv + npm + env files, 2-4 min) ..." -ForegroundColor Cyan
.\setup.ps1

Write-Host "  pulling local LLM (gemma3:12b, ~7 GB, first time only) ..." -ForegroundColor Cyan
try { ollama pull gemma3:12b } catch { Write-Host "  (Ollama pull failed — start Ollama and run: ollama pull gemma3:12b)" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  Done! Launch Fantasy Studio:" -ForegroundColor Magenta
Write-Host ""
Write-Host "      .\desktop\launch.ps1     # native desktop app (recommended)" -ForegroundColor White
Write-Host "      .\launch.ps1             # browser mode (backend + localhost:3000)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Game mode needs NO GPU. Video renders + new-asset generation want an NVIDIA GPU."
Write-Host "  Full guide: INSTALL.md"
