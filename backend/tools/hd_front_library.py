"""Give every library person a sharp front from their reference photo (2026-10-08).

For each rigged biped in assets/library (*_anim.glb) whose generation left a
reference photo in renders/_actor_cache, runs scripts/_hd_front.py: the
photo is projected onto the front of the coated body, aligned by agreement
with the coat, and shipped as its base colour. The coated original is kept in
renders/_coat_backup_hdfront/. A character whose photo does not agree with
its body (a side-on animal, a regenerated mesh) is left as it is.

    python tools/hd_front_library.py [name ...] [--force] [--dry]
"""
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

BK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BK))
LIB = BK / "assets" / "library"
CACHE = BK / "renders" / "_actor_cache"
BACKUP = BK / "renders" / "_coat_backup_hdfront"
SCRIPT = BK / "scripts" / "_hd_front.py"


def gltf_json(p: Path) -> dict:
    b = p.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    return json.loads(b[20:20 + n])


def is_biped(j: dict) -> bool:
    names = {(n.get("name") or "").lower() for n in j.get("nodes", [])}
    return {"upleg_l", "lowleg_l", "foot_l"} <= names


def is_coated(j: dict) -> bool:
    """A coated body carries colour on its vertices and has no base colour sheet."""
    return not any(m.get("pbrMetallicRoughness", {}).get("baseColorTexture") for m in j.get("materials", []))


def upgrade(anim: Path, force=False, dry=False, verbose=True) -> str:
    from app.game_export.generate import BLENDER_EXE
    kind = anim.stem[:-len("_anim")].replace("_", " ")
    ref = CACHE / (hashlib.md5(kind.lower().encode("utf-8")).hexdigest()[:12] + "_ref.png")
    if not ref.exists():
        return "no reference"
    j = gltf_json(anim)
    if not is_biped(j):
        return "not a biped"
    if not is_coated(j) and not force:
        return "already has a sheet"
    if dry:
        return "would upgrade"
    tmp = anim.with_name(anim.stem + "_hdtmp.glb")
    r = subprocess.run([str(BLENDER_EXE), "--background", "--python", str(SCRIPT), "--", str(anim), str(ref), str(tmp)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    line = next((l for l in (r.stdout or "").splitlines() if l.startswith(("HDF ", "HDFAIL"))), "HDFAIL no result")
    if not line.startswith("HDF ") or not tmp.exists():
        tmp.unlink(missing_ok=True)
        return line
    BACKUP.mkdir(parents=True, exist_ok=True)
    static = LIB / (anim.stem[:-len("_anim")] + ".glb")
    if (BACKUP / anim.name).exists() and static.exists() and static.stat().st_mtime > (BACKUP / anim.name).stat().st_mtime:
        (BACKUP / anim.name).unlink()             # a backup of a body made before this one
    if not (BACKUP / anim.name).exists():
        shutil.copy2(anim, BACKUP / anim.name)
    shutil.move(str(tmp), str(anim))
    # a stale JPEG hero bake would now be older than the rig and is passed over by the planner
    return line


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force, dry = "--force" in sys.argv, "--dry" in sys.argv
    files = [LIB / f"{a.replace(' ', '_')}_anim.glb" for a in args] if args else sorted(LIB.glob("*_anim.glb"))
    for f in files:
        if not f.exists():
            print(f"{f.name}: missing"); continue
        try:
            print(f"{f.name}: {upgrade(f, force=force, dry=dry)}", flush=True)
        except Exception as e:
            print(f"{f.name}: error {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    main()
