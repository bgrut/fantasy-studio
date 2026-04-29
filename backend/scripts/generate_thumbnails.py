#!/usr/bin/env python3
"""
generate_thumbnails.py
======================
One-shot thumbnail generator for every library.json entry.

For each entry missing a ``thumbnail_path``, launches a headless Blender
subprocess to:
    1. Import the asset (.glb / .gltf / .blend / .fbx)
    2. Set up a neutral 3-point light + camera auto-framed on bbox
    3. Render 256×256 PNG to ``assets/thumbnails/<id>.png``
    4. Write ``thumbnail_path`` back into library.json

Runs once.  Re-run when new assets are ingested — existing thumbnails
are skipped.  Thumbnails are served by the /api/assets/thumbnail/<id>
FastAPI route with aggressive cache headers.

Usage:
    python scripts/generate_thumbnails.py
    python scripts/generate_thumbnails.py --force      # re-render all
    python scripts/generate_thumbnails.py --limit 5    # test on first 5
    python scripts/generate_thumbnails.py --blender "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"

Requires a working Blender install.  Tries to auto-detect the Blender
executable from common Windows paths; override with --blender if needed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "app" / "data" / "library.json"
THUMB_DIR = ROOT / "assets" / "thumbnails"
BLENDER_SCRIPT_PATH = ROOT / "render_scripts" / "_thumb_render_subprocess.py"


_BLENDER_CANDIDATES = [
    "blender",
    r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
    "/Applications/Blender.app/Contents/MacOS/Blender",
    "/usr/bin/blender",
]


def _find_blender(explicit: str | None) -> str | None:
    if explicit:
        return explicit if Path(explicit).exists() or shutil.which(explicit) else None
    for cand in _BLENDER_CANDIDATES:
        if shutil.which(cand) or Path(cand).exists():
            return cand
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Blender subprocess script (written out once and invoked repeatedly)
# ═══════════════════════════════════════════════════════════════════════════

_SUBPROCESS_SOURCE = r'''"""
_thumb_render_subprocess.py
===========================
Runs inside Blender.  Arguments after ``--``:
    --asset-path <file>      path to GLB/GLTF/BLEND/FBX
    --out <file>             output PNG path
    --size <int>             square size (default 256)

Doesn't import the full fantasy-studio pipeline — keeps startup fast
(~2s) and avoids dragging in bpy-dependent modules that only matter
for full renders.
"""
import argparse
import os
import sys
import bpy
from mathutils import Vector

# ─── argparse after ``--`` ──────────────────────────────────────────
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument("--asset-path", required=True)
p.add_argument("--out", required=True)
p.add_argument("--size", type=int, default=256)
args = p.parse_args(argv)

# ─── Clean scene ────────────────────────────────────────────────────
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for coll in list(bpy.data.collections):
    try:
        bpy.data.collections.remove(coll)
    except Exception:
        pass

# ─── Import the asset ──────────────────────────────────────────────
ext = os.path.splitext(args.asset_path)[1].lower()
try:
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=args.asset_path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=args.asset_path)
    elif ext == ".obj":
        try:
            bpy.ops.wm.obj_import(filepath=args.asset_path)
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=args.asset_path)
    elif ext == ".blend":
        with bpy.data.libraries.load(args.asset_path, link=False) as (src, dst):
            dst.objects = list(src.objects)
        for o in dst.objects:
            if o is not None:
                bpy.context.collection.objects.link(o)
    else:
        print(f"[THUMB] unsupported ext: {ext}", flush=True)
        sys.exit(2)
except Exception as e:
    print(f"[THUMB] import failed: {e}", flush=True)
    sys.exit(3)

# ─── Compute combined bbox (world space) ───────────────────────────
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
coords = []
for m in meshes:
    try:
        for c in m.bound_box:
            coords.append(m.matrix_world @ Vector(c))
    except Exception:
        pass
if not coords:
    print("[THUMB] no mesh bbox — bailing", flush=True)
    sys.exit(4)

mn = Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
mx = Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
center = (mn + mx) * 0.5
diag = (mx - mn).length
if diag < 0.001:
    diag = 1.0

# ─── Camera auto-framed 3/4 angle ──────────────────────────────────
import math
cam_dist = max(diag * 1.4, 2.0)
ang = math.radians(25)
cam_loc = Vector((
    center.x + cam_dist * math.sin(ang),
    center.y - cam_dist * math.cos(ang),
    center.z + diag * 0.35,
))
bpy.ops.object.camera_add(location=cam_loc)
cam = bpy.context.active_object
# Aim at subject
direction = center - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = cam
cam.data.lens = 50.0

# ─── 3-point light ─────────────────────────────────────────────────
def _add_light(kind, loc, energy, color=(1.0, 1.0, 1.0)):
    bpy.ops.object.light_add(type=kind, location=loc)
    lt = bpy.context.active_object
    lt.data.energy = energy
    lt.data.color = color
    if hasattr(lt.data, "size"):
        lt.data.size = 4.0
    return lt

_add_light("AREA", (cam_loc.x + 2, cam_loc.y - 1, cam_loc.z + 2),    800)   # key
_add_light("AREA", (cam_loc.x - 3, cam_loc.y + 0, cam_loc.z + 1),    300, color=(0.92, 0.95, 1.0))  # fill
_add_light("AREA", (center.x + 0, center.y + 3, center.z + 3),        500, color=(1.0, 0.95, 0.88))   # back

# ─── World: neutral grey ambient ───────────────────────────────────
world = bpy.context.scene.world
if world is None:
    world = bpy.data.worlds.new(name="ThumbWorld")
    bpy.context.scene.world = world
world.use_nodes = True
try:
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.14, 0.14, 0.15, 1.0)
    bg.inputs["Strength"].default_value = 1.0
except Exception:
    pass

# ─── Render settings (fast Eevee) ──────────────────────────────────
scene = bpy.context.scene
try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except Exception:
    try:
        scene.render.engine = "BLENDER_EEVEE"
    except Exception:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 16
scene.render.resolution_x = args.size
scene.render.resolution_y = args.size
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = args.out
try:
    scene.eevee.taa_render_samples = 16
except Exception:
    pass

# ─── Render ────────────────────────────────────────────────────────
bpy.ops.render.render(write_still=True)
print(f"[THUMB] wrote {args.out}", flush=True)
'''


def _ensure_subprocess_script() -> Path:
    BLENDER_SCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not BLENDER_SCRIPT_PATH.exists() or \
            BLENDER_SCRIPT_PATH.read_text(encoding="utf-8") != _SUBPROCESS_SOURCE:
        BLENDER_SCRIPT_PATH.write_text(_SUBPROCESS_SOURCE, encoding="utf-8")
    return BLENDER_SCRIPT_PATH


def _load_library() -> dict:
    if not LIBRARY_PATH.exists():
        return {"assets": []}
    return json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))


def _save_library(lib: dict) -> None:
    LIBRARY_PATH.write_text(json.dumps(lib, indent=2), encoding="utf-8")


def _resolve_asset_path(entry: dict) -> Path | None:
    p = entry.get("path")
    if not p:
        return None
    abs_p = Path(p)
    if not abs_p.is_absolute():
        abs_p = ROOT / p
    if abs_p.exists():
        return abs_p
    return None


def _thumb_path(asset_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in asset_id)
    return THUMB_DIR / f"{safe}.png"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="re-render thumbnails that already exist")
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after N thumbnails (for testing)")
    parser.add_argument("--blender", default=None,
                        help="path to Blender executable")
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--timeout", type=int, default=90,
                        help="per-asset subprocess timeout in seconds")
    args = parser.parse_args()

    blender = _find_blender(args.blender)
    if not blender:
        print(f"[THUMB] Blender executable not found. "
              f"Pass --blender <path> or install Blender.", file=sys.stderr)
        sys.exit(1)
    print(f"[THUMB] using Blender: {blender}")

    _ensure_subprocess_script()
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    library = _load_library()
    assets = library.get("assets", [])

    to_render: list = []
    for entry in assets:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        if not eid:
            continue
        tp = _thumb_path(eid)
        if tp.exists() and not args.force:
            entry["thumbnail_path"] = str(tp.relative_to(ROOT)).replace("\\", "/")
            continue
        if entry.get("category") == "hdri":
            continue  # skip HDRI thumbnail generation (different approach)
        asset_path = _resolve_asset_path(entry)
        if not asset_path:
            continue
        to_render.append((entry, asset_path, tp))

    if args.limit:
        to_render = to_render[:args.limit]

    print(f"[THUMB] {len(to_render)} thumbnail(s) to generate "
          f"(total library: {len(assets)})")

    ok = 0
    failed = 0
    start = time.time()
    for i, (entry, asset_path, thumb_path) in enumerate(to_render, 1):
        eid = entry.get("id")
        print(f"[THUMB] [{i}/{len(to_render)}] {eid} ...", flush=True)
        try:
            cmd = [
                blender, "--background", "--factory-startup",
                "--python", str(BLENDER_SCRIPT_PATH),
                "--",
                "--asset-path", str(asset_path),
                "--out", str(thumb_path),
                "--size", str(args.size),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout,
            )
            if proc.returncode == 0 and thumb_path.exists():
                entry["thumbnail_path"] = str(thumb_path.relative_to(ROOT)).replace("\\", "/")
                ok += 1
            else:
                failed += 1
                # Tail of stderr for diagnosis
                stderr_tail = (proc.stderr or "").splitlines()[-3:]
                print(f"[THUMB]   FAIL rc={proc.returncode} "
                      f"tail={stderr_tail}", flush=True)
        except subprocess.TimeoutExpired:
            failed += 1
            print(f"[THUMB]   TIMEOUT after {args.timeout}s", flush=True)
        except Exception as e:
            failed += 1
            print(f"[THUMB]   EXCEPTION {e}", flush=True)

        # Incremental save every 10 thumbnails
        if i % 10 == 0:
            _save_library(library)

    _save_library(library)
    elapsed = time.time() - start
    print(f"[THUMB] done: ok={ok} failed={failed} "
          f"elapsed={elapsed:.1f}s avg={elapsed/max(1, ok + failed):.1f}s/asset")


if __name__ == "__main__":
    main()
