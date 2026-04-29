from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "render_scripts" / "normalize_asset_to_blend.py"


def normalize_to_blend(input_asset: str, output_blend: str) -> dict:
    blender_exe = os.getenv("BLENDER_EXE", "").strip()
    if not blender_exe:
        return {"ok": False, "error": "BLENDER_EXE is not set"}

    cmd = [
        blender_exe,
        "-b",
        "--python",
        str(SCRIPT_PATH),
        "--",
        str(input_asset),
        str(output_blend),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "error": None if proc.returncode == 0 else f"normalize failed: {proc.returncode}",
    }