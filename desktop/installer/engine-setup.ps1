# Fantasy Studio — first-run engine setup (2026-10-22).
#
# Run by the desktop app's setup window (never piped from the web). It installs
# everything the studio needs into the user's own profile, with nothing assumed
# on the machine beforehand:
#
#   1. uv (Astral's single-file Python manager), pinned and SHA-256 checked
#   2. the engine for this exact app version (backend + built UI), from the
#      GitHub release, SHA-256 checked against the release's own checksum file
#   3. a private Python 3.12 and the backend's packages (the GPU stack only in
#      "full" mode)
#   4. the 3D library and the sky HDRIs
#   5. Ollama (the local AI that reads your sentence) if it is missing, and its
#      model
#
# Progress is printed as   @@ <percent> <message>   lines for the window; the
# last line is   @@DONE   or   @@ERROR <message>.
param(
    [Parameter(Mandatory = $true)][string]$EngineDir,
    [Parameter(Mandatory = $true)][string]$Version,
    [ValidateSet('game', 'full')][string]$Mode = 'game',
    [string]$Repo = 'bgrut/fantasy-studio',
    [switch]$SkipOllama,
    [string]$Model = 'gemma3:12b',
    [string]$EngineZip = ''          # a local engine zip (offline / testing) instead of the release's
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Step([int]$pct, [string]$msg) { Write-Output "@@ $pct $msg" }
# Run a native tool and return its exit code. Windows PowerShell turns anything a
# program writes to stderr into an error record, and under 'Stop' the first progress
# line uv prints ("Downloading cpython...") ended the setup; success is the exit code
function Native([scriptblock]$b) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { & $b 2>&1 | Out-Null; return $LASTEXITCODE } finally { $ErrorActionPreference = $old }
}
function Fail([string]$msg) { Write-Output "@@ERROR $msg"; exit 1 }

$UV_VERSION = '0.6.14'
$UV_URL = "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-pc-windows-msvc.zip"

function Get-Checked([string]$url, [string]$out, [string]$shaUrl) {
    Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
    if ($shaUrl) {
        # (served as bytes by GitHub's release CDN: decode before reading the hash)
        $c = (Invoke-WebRequest -Uri $shaUrl -UseBasicParsing).Content
        if ($c -is [byte[]]) { $c = [System.Text.Encoding]::UTF8.GetString($c) }
        $want = ([string]$c).Trim().Split()[0].ToLower()
        $got = (Get-FileHash -Algorithm SHA256 $out).Hash.ToLower()
        if ($want -ne $got) { Remove-Item $out -Force; Fail "checksum mismatch for $(Split-Path $url -Leaf) (expected $want, got $got)" }
    }
}

try {
    New-Item -ItemType Directory -Force -Path $EngineDir | Out-Null
    $tmp = Join-Path $EngineDir '_download'
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null

    # 1. uv
    $uv = Join-Path $EngineDir 'tools\uv.exe'
    if (-not (Test-Path $uv)) {
        Step 3 'Downloading the Python manager (uv)'
        $z = Join-Path $tmp 'uv.zip'
        Get-Checked $UV_URL $z "$UV_URL.sha256"
        Expand-Archive -Force $z (Join-Path $EngineDir 'tools')
    }
    if (-not (Test-Path $uv)) { Fail 'uv did not unpack' }

    # 2. the engine for this version
    $app = Join-Path $EngineDir 'app'
    $stamp = Join-Path $app '.version'
    if (-not ((Test-Path $stamp) -and ((Get-Content $stamp -Raw).Trim() -eq $Version))) {
        Step 8 "Downloading Fantasy Studio $Version"
        $ez = Join-Path $tmp 'engine.zip'
        if ($EngineZip) { Copy-Item $EngineZip $ez -Force }
        else {
            $name = "fantasy-studio-engine-v$Version.zip"
            $base = "https://github.com/$Repo/releases/download/v$Version"
            Get-Checked "$base/$name" $ez "$base/$name.sha256"
        }
        Step 18 'Unpacking'
        if (Test-Path $app) {
            # keep the user's own work (games, renders, settings) across an update
            foreach ($keep in @('backend\renders', 'backend\data', 'backend\.env')) {
                $src = Join-Path $app $keep
                if (Test-Path $src) { $dst = Join-Path $EngineDir ('_keep\' + $keep); New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null; Move-Item -Force $src $dst }
            }
            Remove-Item -Recurse -Force $app
        }
        Expand-Archive -Force $ez $app
        foreach ($keep in @('backend\renders', 'backend\data', 'backend\.env')) {
            $src = Join-Path $EngineDir ('_keep\' + $keep)
            if (Test-Path $src) { $dst = Join-Path $app $keep; if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }; Move-Item -Force $src $dst }
        }
        Set-Content -Path $stamp -Value $Version -Encoding UTF8
    }
    $backend = Join-Path $app 'backend'
    if (-not (Test-Path (Join-Path $backend 'app\main.py'))) { Fail 'the engine is missing its backend' }

    # 3. Python and packages
    Step 22 'Installing a private Python 3.12'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $EngineDir 'python'
    if ((Native { & $uv python install 3.12 }) -ne 0) { Fail 'Python install failed' }
    $venv = Join-Path $backend 'venv'
    if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
        if ((Native { & $uv venv --python 3.12 $venv }) -ne 0) { Fail 'could not create the Python environment' }
    }
    $py = Join-Path $venv 'Scripts\python.exe'
    Step 30 'Installing the studio''s packages'
    if ((Native { & $uv pip install --python $py -r (Join-Path $backend 'requirements.txt') }) -ne 0) { Fail 'package install failed' }
    if ($Mode -eq 'full') {
        Step 40 'Installing the GPU stack (image and 3D generation; several GB)'
        if ((Native { & $uv pip install --python $py -r (Join-Path $backend 'requirements-diffusion.txt') }) -ne 0) { Write-Output '@@ 40 (the GPU stack did not install; game mode still works)' }
    }

    # 4. the 3D library and the skies
    Step 55 'Downloading the 3D model library (about 1.5 GB, first time only)'
    Push-Location $app
    try { $fa = Native { & $py (Join-Path $backend 'tools\fetch_assets.py') } } finally { Pop-Location }
    if ($fa -ne 0) { Write-Output '@@ 70 (the model library will finish downloading on the next start)' }
    Step 72 'Downloading sky lighting (about 25 MB)'
    $null = Native { & $py (Join-Path $backend 'scripts\fetch_hdris.py') }

    # 5. Ollama and its model
    if (-not $SkipOllama) {
        $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
        if (-not $ollama) { $o2 = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'; if (Test-Path $o2) { $ollama = $o2 } }
        if (-not $ollama) {
            Step 76 'Installing Ollama (the local AI that reads your sentence)'
            $os = Join-Path $tmp 'OllamaSetup.exe'
            Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile $os -UseBasicParsing
            $sig = Get-AuthenticodeSignature $os
            if ($sig.Status -ne 'Valid') { Fail "the Ollama installer is not validly signed ($($sig.Status))" }
            Start-Process -FilePath $os -ArgumentList '/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES' -Wait
            $ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
        }
        if (Test-Path $ollama) {
            Step 82 "Downloading the AI model $Model (about 8 GB, first time only)"
            # the service may still be starting after a fresh install
            for ($i = 0; $i -lt 30; $i++) { try { Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/version' -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 2 } }
            if ((Native { & $ollama pull $Model }) -ne 0) { Write-Output "@@ 95 (the model will download on first use: ollama pull $Model)" }
        } else { Write-Output '@@ 95 (Ollama could not be installed; the studio uses its built-in planner until it is)' }
    }

    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    Set-Content -Path (Join-Path $EngineDir 'installed.json') -Encoding UTF8 -Value (@{ version = $Version; mode = $Mode; when = (Get-Date).ToString('s') } | ConvertTo-Json)
    Step 100 'Ready'
    Write-Output '@@DONE'
} catch {
    Fail $_.Exception.Message
}
