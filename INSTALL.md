# Installing Fantasy Studio

This guide gets Fantasy Studio running on **Windows 10/11** end-to-end. macOS and Linux are untested for V1; community contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

> **Pre-launch note:** Fantasy Studio is a single monorepo with `backend/` (Python/FastAPI) and `frontend/` (React/Vite) subdirectories. One clone, one install path. (Pre-V0.1.1 the project was split across three sibling repos — that's now collapsed.)

---

## System requirements

### Minimum
- **OS**: Windows 10 (build 19041+) or Windows 11
- **CPU**: 6-core, 2.5 GHz+ (Intel i5-10400 / Ryzen 5 3600 class)
- **RAM**: 16 GB
- **GPU**: NVIDIA RTX 2060 / AMD RX 5700 / Apple M1 (8 GB VRAM)
- **Disk**: 30 GB free (Blender 3 GB + Ollama models 7 GB + assets cache up to 20 GB)
- **Network**: 10 Mbps for first-run model + asset downloads

### Recommended (smooth, fast iteration)
- **CPU**: 8-core+ (Intel i7-12700 / Ryzen 7 5800X class)
- **RAM**: 32 GB
- **GPU**: NVIDIA RTX 3060+ (12 GB VRAM) or RTX 4070 (sweet spot)
- **Disk**: 100 GB free, NVMe SSD
- **Network**: 50 Mbps+ for Objaverse fallback fetches

Cycles renders are GPU-bound; Eevee runs on integrated graphics but the Quick Preview tier becomes painful below RTX 2060.

---

## Prerequisites

Install all four before cloning. Verification commands run in PowerShell.

### 1. Blender 5.1 or later

- Download: <https://www.blender.org/download/>
- Verify:
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --version
  ```
  Should print `Blender 5.1.0` or higher.

Fantasy Studio shells out to `blender.exe -b` for every render, so any LTS install in `C:\Program Files\Blender Foundation\` is auto-detected.

### 2. Ollama (local LLM runtime)

- Download: <https://ollama.com/download/windows>
- After install, Ollama runs as a Windows service on `localhost:11434`.
- Verify:
  ```powershell
  ollama --version
  curl http://localhost:11434
  ```
  The curl call should return `Ollama is running`.

### 3. Sketchfab API key (optional but recommended)

Fantasy Studio uses Sketchfab as a fallback asset source when the curated library doesn't have what you need. Sketchfab requires a free API key.

1. Sign up at <https://sketchfab.com> (free account)
2. Go to **Settings → Password & API**
3. Copy your API token
4. Create a `.env` file in `backend/` with:
   ```env
   SKETCHFAB_API_TOKEN=your-token-here
   ```
   No quotes, no spaces around the `=`. Just the token.

If you skip this step, asset fetching will only use Objaverse and your local curated library. This works but limits the asset variety available for prompts not covered by your library — `[SKETCHFAB] skipped (no SKETCHFAB_API_TOKEN)` will appear in the log when a prompt would otherwise have hit Sketchfab.

> **Note**: pre-V1.0 the backend may require you to set `SKETCHFAB_API_TOKEN` as a Windows environment variable instead of via `.env`. If your `.env` token isn't picked up, set it manually:
> ```powershell
> [Environment]::SetEnvironmentVariable("SKETCHFAB_API_TOKEN", "your-token", "User")
> ```
> then restart your terminal. V1.0 ships with `.env` auto-loading.

### 4. Python 3.11+

- Download: <https://www.python.org/downloads/windows/>
- During install, **check "Add Python to PATH"**.
- Verify:
  ```powershell
  python --version
  ```
  Should print `Python 3.11.x` or higher.

### 5. Node.js 20+

- Download (LTS): <https://nodejs.org/en/download>
- Verify:
  ```powershell
  node --version
  npm --version
  ```
  Node should be `v20.x` or higher.

### 6. Git

- Download: <https://git-scm.com/download/win>
- Verify:
  ```powershell
  git --version
  ```

---

## Step-by-step Windows install

Open PowerShell. We'll work in `C:\Users\<you>\Desktop\FantasyAI\` — feel free to substitute another path.

### 0. Windows: Enable PowerShell scripts (one-time setup)

Required before running `setup.ps1`, `launch.ps1`, or any Python venv `Activate.ps1`.

Open PowerShell **as Administrator** and run:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Confirm with `Y`. This is a Windows default-restrictive setting; setting it once for `CurrentUser` is the standard fix and doesn't lower system-wide security.

### 1. Clone the monorepo

```powershell
mkdir C:\Users\$env:USERNAME\Desktop\FantasyAI
cd C:\Users\$env:USERNAME\Desktop\FantasyAI

git clone https://github.com/bgrut/fantasy-studio
cd fantasy-studio
```

The repo has two subdirectories: `backend/` (Python API + render pipeline) and `frontend/` (React/Vite UI).

### 2. One-command setup

```powershell
.\setup.ps1
```

This script:

- Verifies Python 3.11+ and Node 20+ are on PATH
- Checks Ollama reachability (warns and continues if not running)
- Creates `backend/venv` and installs `backend/requirements.txt`
- Runs `npm install` in `frontend/`
- Scaffolds `backend/.env` and `frontend/.env.local` from their respective `.env.example` files (idempotent — won't overwrite existing files)

Total time: 2–4 minutes depending on network. Re-run anytime; passing `-ForceVenvRecreate` rebuilds the Python venv from scratch.

### 3. Pull the LLM model

```powershell
ollama pull gemma3:12b
```

Downloads ~7 GB. First-time only.

### 4. (Optional) Add your tokens

If you have a Sketchfab API token (recommended — see [Sketchfab API key setup](#3-sketchfab-api-key-optional-but-recommended) above), edit `backend/.env`:

```
SKETCHFAB_API_TOKEN=your-token-here
```

Without it, fallback asset fetch only uses Objaverse + your local curated library.

### Manual setup (advanced)

Prefer to run each step yourself? `setup.ps1` is a thin orchestrator over these:

```powershell
# Backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
deactivate
cd ..

# Frontend
cd frontend
npm install
cd ..

# Env files (only if missing)
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

---

## First launch (single command)

After installation completes, launch Fantasy Studio with one command from the **`fantasy-studio`** repo root:

```powershell
cd C:\Users\$env:USERNAME\Desktop\FantasyAI\fantasy-studio
.\launch.ps1
```

The launcher opens two PowerShell windows — one for the backend (FastAPI on `:8789`) and one for the frontend (Vite on `:3000`) — and starts them in sequence with a small delay so the backend binds its port before the frontend tries to connect. The launcher verifies the venv exists, the frontend `package.json` is present, and prints clear errors if either is missing.

You should see in the launcher's parent window:

```
Fantasy Studio launching...
  Backend dir:  C:\Users\<you>\Desktop\FantasyAI\fantasy-studio\backend
  Frontend dir: C:\Users\<you>\Desktop\FantasyAI\fantasy-studio\frontend
  Backend port: 8789
Two PowerShell windows opened.
  Backend:  http://localhost:8789  (and /api/health for liveness)
  Frontend: http://localhost:3000  (Vite is configured with strictPort=true)
```

Open <http://localhost:3000> in your browser. To stop, close both PowerShell windows.

If you have repos in non-default locations, override:
```powershell
.\launch.ps1 -BackendDir "D:\code\fantasy-studio\backend" -FrontendDir "D:\code\fantasy-studio\frontend" -BackendPort 8800
```

### Manual launch (advanced / debugging)

If you want manual control over each process — to attach a debugger, capture logs, or pin specific flags — run them in two terminals yourself:

**Terminal 1 — Backend** (in `fantasy-studio/backend`):
```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --port 8789 --reload
```

You should see `[LLM] Ollama reachable at http://localhost:11434 (model=gemma3:12b)` and `Uvicorn running on http://127.0.0.1:8789`.

**Terminal 2 — Frontend** (in `fantasy-studio/frontend`):
```powershell
npm run dev
```

You should see `Local: http://localhost:3000/`. Open it in your browser.

> macOS / Linux: a `launch.sh` equivalent is on the V1.1 backlog. For now, run the manual two-terminal flow above; substitute `source venv/bin/activate` for the `Activate.ps1` line.

---

## First render walkthrough

> *Screenshot: cast panel + prompt entry — `.github/assets/install-step1.png`*

1. In the prompt box, type: **`a polar bear in the arctic at sunset`**
2. The cast panel auto-populates with the matched hero (polar bear) and environment (arctic). You can swap either via "Change cast".
3. Pick a render tier (start with **Quick Preview** — fastest feedback).
4. Click **Generate**.
5. The pipeline log streams in real time. Watch for `[PIPELINE] +XXX.XXXs RENDER_COMPLETE` (typically 30–90 s for Quick Preview).
6. The MP4 plays in the preview pane. Download buttons surface MP4, GIF, PNG sequence, and the source `.blend`.

If the render aborts with `[HERO_VERIFY] ABORT`, the API surfaces the cause as a user-facing error. See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## macOS / Linux note

V1 is **untested on macOS and Linux**. The pipeline is mostly cross-platform Python plus a Blender subprocess, so it should work — but Blender path detection, Windows-style path separators in some legacy code, and the Ollama service install differ. Community PRs to validate and fix these paths are very welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). If you get it running, please open an issue with your config so we can document it.

---

## Troubleshooting

Common errors and fixes are in **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)**. The top-three first-run issues:

1. **`Ollama not reachable`** → make sure the Ollama service is running (`ollama serve` or restart from system tray).
2. **`Blender executable not found`** → install in the default `C:\Program Files\Blender Foundation\` path or set `BLENDER_EXE` env var.
3. **`CUDA out of memory`** during render → drop to Quick Preview tier, or close other GPU-using apps.

---

## Verification

To confirm everything is wired up before your first render:

```powershell
# Backend reachable
curl http://127.0.0.1:8000/api/health
# Should return: {"ok":true, ...}

# Ollama reachable
curl http://localhost:11434
# Should return: Ollama is running

# Library populated
curl http://127.0.0.1:8000/api/library/browse?limit=1
# Should return: {"ok":true, "total":316, "hits":[...]}

# Blender callable (one-line dummy)
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b --python-expr "print('blender ok')"
# Should print: blender ok
```

A bundled `tools/healthcheck.py` script does not yet exist — it's on the post-launch list. For now run the four commands above.

---

## Next steps

- 📖 **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** — full how-to, prompt patterns, scene controls, refining a render
- 🎨 **[docs/GALLERY.md](docs/GALLERY.md)** — see what good output looks like
- 🧠 **[docs/PROMPTING.md](docs/PROMPTING.md)** — prompt engineering deep-dive
- 🏛️ **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — how the pipeline works under the hood
- 💬 **Discord** — coming soon for launch
