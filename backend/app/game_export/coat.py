"""One clean coat for every animated character (2026-09-29).

scripts/_clean_coat.py does the work in Blender (its docstring has the why):
the colour is rebuilt on the surface from the generated atlas, the flecks
and the atlas's confetti are voted out, and the model ships that colour as
vertex colour with no sheet, no UVs and no embossed normal map. This module
runs it and keeps the result only when it is sound: the same animation
clips, still skinned, and carrying COLOR_0. Anything else keeps its original.

FS_COAT=0 turns it off.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "_clean_coat.py"


def enabled() -> bool:
    return os.environ.get("FS_COAT", "1") == "1"


def _blender() -> str:
    from .generate import BLENDER_EXE
    return str(BLENDER_EXE)


def facts(p: Path) -> dict:
    d = Path(p).read_bytes()
    n = struct.unpack_from("<I", d, 12)[0]
    j = json.loads(d[20:20 + n])
    prims = [pr for m in j.get("meshes", []) for pr in m.get("primitives", [])]
    mats = j.get("materials", [])
    return {"anims": sorted(a.get("name", "") for a in j.get("animations", [])),
            "skins": len(j.get("skins", [])),
            "color": bool(prims) and all("COLOR_0" in pr.get("attributes", {}) for pr in prims),
            "textured": any(pr.get("material") is not None and pr["material"] < len(mats)
                            and "baseColorTexture" in mats[pr["material"]].get("pbrMetallicRoughness", {})
                            for pr in prims)}


def coat(path, backup_dir: Path | None = None) -> tuple[bool, str]:
    """Coat one GLB in place. Returns (kept_a_sound_file, what_happened)."""
    path = Path(path)
    before = facts(path)
    if before["color"] and not before["textured"]:
        return True, "already coated"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / path.name
        r = subprocess.run([_blender(), "--background", "--python", str(SCRIPT), "--", str(path), str(out)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        line = next((l for l in (r.stdout or "").splitlines() if l.startswith("COAT")), None)
        if not out.exists() or not line:
            tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-3:]
            return False, "coat failed: " + " | ".join(tail)[:200]
        after = facts(out)
        if after["anims"] != before["anims"] or after["skins"] != before["skins"] or not after["color"]:
            return False, f"not sound, kept the original: {before} -> {after}"
        if backup_dir is not None:
            backup_dir.mkdir(parents=True, exist_ok=True)
            if not (backup_dir / path.name).exists():
                shutil.copy2(path, backup_dir / path.name)
        mb0 = path.stat().st_size / 1e6
        shutil.copy2(out, path)
        return True, f"{line}  {mb0:.1f} -> {path.stat().st_size / 1e6:.1f} MB, clips {len(after['anims'])}"
