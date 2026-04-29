from __future__ import annotations

from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]

# ── Load .env if present (secrets stay out of git) ─────────────────────
_env_path = ROOT / ".env"
if _env_path.exists():
    try:
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#"):
                continue
            if "=" in _line:
                _key, _, _val = _line.partition("=")
                _key = _key.strip()
                _val = _val.strip()
                if _key and _key not in os.environ:
                    os.environ[_key] = _val
    except Exception:
        pass
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "blender_lane.db"

HOST = os.getenv("BLENDER_LANE_HOST", "127.0.0.1")
PORT = int(os.getenv("BLENDER_LANE_PORT", "8789"))

DEFAULT_BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
ALT_BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender\blender.exe"

BLENDER_EXE = os.getenv("BLENDER_EXE", DEFAULT_BLENDER_EXE)
if not Path(BLENDER_EXE).exists() and Path(ALT_BLENDER_EXE).exists():
    BLENDER_EXE = ALT_BLENDER_EXE

LOCAL_RENDER_MODE = os.getenv("LOCAL_RENDER_MODE", "1") == "1"
FPS = 24
DURATION_SECONDS = 6
RES_X = 720
RES_Y = 1280