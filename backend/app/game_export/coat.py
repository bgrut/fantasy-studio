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
import re
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


def source_for(path) -> str | None:
    """The static model a rigged character was baked from (fox_anim -> fox),
    whose coat survives when the rig bake's sheet came out black."""
    name = Path(path).name
    for suf in ("_anim.glb", "_hero.glb"):
        if name.endswith(suf):
            kind = name[: -len(suf)].replace("_", " ")
            try:
                from . import library
                p = library.resolve(kind, any_quality=True)
            except Exception:
                p = None
            if p and Path(p).exists() and Path(p).resolve() != Path(path).resolve():
                return str(p)
    return None


PLATED = ("robot", "knight", "astronaut", "android", "cyborg", "armor", "armour", "mech", "droid", "golem")


def is_plated(stem: str) -> bool:
    """Kinds whose surface really is metal; everyone else is matte (2026-10-08)."""
    s = stem.lower().replace("_anim", "").replace("_", " ")
    return any(w in s for w in PLATED)


def coat(path, backup_dir: Path | None = None, source: str | None = None, force: bool = False) -> tuple[bool, str]:
    """Coat one GLB in place. Returns (kept_a_sound_file, what_happened).
    source: the static model it was rigged from; its colour is used when the
    rig's own sheet is far darker (a bake that lost the coat)."""
    path = Path(path)
    before = facts(path)
    if before["color"] and not before["textured"] and not force:
        return True, "already coated"
    if source is None:
        source = source_for(path)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / path.name
        extra = [f"--from={source}"] if source else []
        if not is_plated(path.stem):
            extra.append("--matte")
        r = subprocess.run([_blender(), "--background", "--python", str(SCRIPT), "--", str(path), str(out)] + extra,
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
        how = " (colour from the source model)" if "FROM SOURCE" in (r.stdout or "") else ""
        clear = re.search(r"CLEAR cut (\d+)", r.stdout or "")
        if clear:
            how += f" ({clear.group(1)} see-through faces removed)"
        return True, f"{line}  {mb0:.1f} -> {path.stat().st_size / 1e6:.1f} MB, clips {len(after['anims'])}{how}"
