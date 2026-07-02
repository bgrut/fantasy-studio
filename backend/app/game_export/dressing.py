"""Shared world-dressing (Phase 26, shared-enhancement rule).

ONE prop library (assets/props/*.glb — ours, commercial-safe) and ONE
per-setting recipe, consumed by BOTH backends:
  - game:  `game_scatter()` -> ScatterSpec dicts for the web exporter
  - video: `build_video_dressing()` -> scatters the same GLBs into the Blender
    scene as background dressing, so video parks/gardens stop being bare planes.

Video placement is a RING (8..18 m) around the hero: adds depth without
walking a tree between the tracking camera and the subject. Gated FS_DRESS;
never raises — a failed dressing pass costs nothing.
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path

PROPS_DIR = Path(__file__).resolve().parents[2] / "assets" / "props"

# setting keyword -> [(prop, game_count, video_count), ...]
_RECIPES = {
    "park":        [("tree", 16, 7), ("rock", 6, 3), ("lamp", 6, 2)],
    "garden":      [("tree", 10, 5), ("rock", 8, 4)],
    "forest":      [("tree", 40, 12), ("rock", 10, 4)],
    "meadow":      [("tree", 6, 3), ("rock", 8, 4)],
    "countryside": [("tree", 10, 5), ("rock", 8, 3)],
    "field":       [("tree", 5, 3), ("rock", 6, 3)],
    "grass":       [("tree", 8, 4), ("rock", 5, 3)],
    "backyard":    [("tree", 4, 2), ("rock", 4, 2), ("lamp", 2, 1)],
}


def recipe_for(setting: str | None):
    s = (setting or "").lower()
    for key, rec in _RECIPES.items():
        if key in s:
            return rec
    return None


def game_scatter(setting: str | None) -> list[dict]:
    """ScatterSpec dicts for GameSpec.world.scatter (empty if no recipe/props)."""
    rec = recipe_for(setting)
    if not rec:
        return []
    out = []
    for prop, game_n, _ in rec:
        glb = PROPS_DIR / f"{prop}.glb"
        if glb.exists():
            out.append({"asset": str(glb), "count": game_n,
                        "min_dist_m": 5.0, "scale_jitter": 0.3,
                        "collide": prop != "rock"})
    return out


_VIDEO_DRESS_CODE = r'''
import bpy, json, math, random
RECIPE=__RECIPE__; SEED=__SEED__
random.seed(SEED)
placed=0; kinds=[]
for glb, count in RECIPE:
    pre=set(bpy.data.objects.keys())
    try:
        bpy.ops.import_scene.gltf(filepath=glb)
    except Exception:
        continue
    new=[bpy.data.objects[k] for k in bpy.data.objects.keys() if k not in pre]
    meshes=[o for o in new if o.type=="MESH"]
    if not meshes: continue
    # group the prop under one empty so we can duplicate it as a unit
    root=bpy.data.objects.new("PropRoot", None)
    bpy.context.scene.collection.objects.link(root)
    for o in meshes:
        o.parent=root
    def place(obj, ang, dist, s):
        obj.location=(math.cos(ang)*dist, math.sin(ang)*dist, 0.0)
        obj.rotation_euler=(0,0,random.uniform(0,6.283))
        obj.scale=(s,s,s)
    for i in range(count):
        ang=random.uniform(0,2*math.pi)
        dist=random.uniform(8.0,18.0)          # background ring: never between
        s=random.uniform(0.8,1.35)             # camera (~5-8m) and the hero
        if i==0:
            place(root, ang, dist, s)
        else:
            dup=root.copy()
            bpy.context.scene.collection.objects.link(dup)
            for ch in root.children:
                c=ch.copy(); c.parent=dup      # linked mesh data — cheap instances
                bpy.context.scene.collection.objects.link(c)
            place(dup, ang, dist, s)
        placed+=1
    kinds.append(glb.split("/")[-1])
bpy.context.view_layer.update()
__result__=json.dumps({"ok":True,"placed":placed,"kinds":kinds})
'''


def build_video_dressing(runner, setting: str | None, seed_key: str = "0",
                         verbose: bool = False) -> bool:
    """Scatter the shared props into the CURRENT Blender scene (video side).
    Returns True if anything was placed; never raises."""
    import os
    if os.environ.get("FS_DRESS", "1") == "0":
        return False
    rec = recipe_for(setting)
    if not rec:
        return False
    pairs = []
    for prop, _, video_n in rec:
        glb = PROPS_DIR / f"{prop}.glb"
        if glb.exists() and video_n > 0:
            pairs.append([str(glb).replace("\\", "/"), video_n])
    if not pairs:
        return False
    seed = zlib.crc32(str(seed_key).encode()) % 100000
    try:
        code = (_VIDEO_DRESS_CODE
                .replace("__RECIPE__", json.dumps(pairs))
                .replace("__SEED__", str(seed)))
        res = runner.run("dressing", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        info = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        ok = bool(info and info.get("ok") and info.get("placed"))
        if verbose and ok:
            print(f"[composer] dressing: {info.get('placed')} props "
                  f"({', '.join(info.get('kinds', []))}) for '{setting}'")
        return ok
    except Exception as e:
        if verbose:
            print(f"[composer] dressing skipped ({type(e).__name__}: {e})")
        return False
