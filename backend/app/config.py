from __future__ import annotations

from pathlib import Path
import os
import shutil

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



def _find_blender() -> str:
    """Whatever Blender this machine actually has (2026-09-04).

    The two hardcoded candidates were "Blender 4.5" and "Blender", and this
    machine has "Blender 5.1" — so BLENDER_EXE resolved to a binary that does
    not exist and the bake lane failed at RUN time, one dead subprocess at a
    time, instead of saying so at import. An explicit BLENDER_EXE still wins;
    otherwise take the newest install present, then anything on PATH.
    """
    env = os.getenv("BLENDER_EXE")
    if env:
        return env
    cands = [Path(DEFAULT_BLENDER_EXE), Path(ALT_BLENDER_EXE)]
    for base in (Path(DEFAULT_BLENDER_EXE).parent.parent,
                 Path(DEFAULT_BLENDER_EXE).parent.parent.parent
                 / "Program Files (x86)" / "Blender Foundation"):
        try:
            if base.is_dir():
                cands += sorted(base.glob("Blender*/blender.exe"), reverse=True)
        except OSError:
            pass
    for c in cands:
        if c.exists():
            return str(c)
    return shutil.which("blender") or DEFAULT_BLENDER_EXE


BLENDER_EXE = _find_blender()

LOCAL_RENDER_MODE = os.getenv("LOCAL_RENDER_MODE", "1") == "1"
FPS = 24
DURATION_SECONDS = 6
RES_X = 720
RES_Y = 1280