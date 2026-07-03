"""Bake a game-ready ANIMATION SET onto a Studio hero: auto-rig once, retarget
each CMU clip IN-PLACE onto its own NLA track (idle/walk/run...), export ONE
animated glTF whose named animations the web runtime switches between.

CPU-only — needs the headless Blender bridge (port 9876) but never the dGPU,
so this runs while the graphics card is down. Reuses the validated Tier A+B
rig (adaptive arm bones + voxel-proxy skin) from app.orchestrator.mocap_retarget.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.orchestrator import mocap_retarget as M

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# default game clip set: state name -> (CMU bvh, frames at 24fps)
DEFAULT_CLIPS = {
    "walk": ("02_01.bvh", 40),
    "run":  ("02_03.bvh", 28),
}
IDLE_FRAMES = 72


def _call(reg, label, code):
    res = reg.call("execute_python", {"code": code})
    raw = res.get("result") if isinstance(res, dict) else None
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return raw


# reset pose + push the freshly-baked action onto its own NLA track
_PUSH_NLA = r'''
import bpy, json
rig=bpy.data.objects.get("HeroRig")
ad=rig.animation_data
act=ad.action if ad else None
out={"ok":False}
if act:
    act.name="__NAME__"
    tr=ad.nla_tracks.new(); tr.name="__NAME__"
    tr.strips.new("__NAME__", 1, act)
    ad.action=None
    for pb in rig.pose.bones:            # clean slate for the next clip
        pb.rotation_quaternion=(1,0,0,0); pb.rotation_euler=(0,0,0); pb.location=(0,0,0)
    bpy.context.view_layer.update()
    out={"ok":True,"clip":"__NAME__","fcurves":-1}
__result__=json.dumps(out)
'''

# procedural idle: subtle breathing sway, exact-loop (whole sine cycles)
_IDLE_CODE = r'''
import bpy, json, math
from mathutils import Quaternion
rig=bpy.data.objects.get("HeroRig")
TOTAL=__TOTAL__
for pb in rig.pose.bones: pb.rotation_mode="QUATERNION"
sc=bpy.context.scene; sc.frame_start=1
sway={"spine":(0.020,'X'),"chest":(0.028,'X'),"head":(0.014,'X'),
      "uparm_L":(0.018,'Y'),"uparm_R":(0.018,'Y')}
AX={'X':(1,0,0),'Y':(0,1,0)}
for i in range(TOTAL):
    f=1+i; t=i/TOTAL
    for name,(amp,ax) in sway.items():
        pb=rig.pose.bones.get(name)
        if not pb: continue
        a=amp*math.sin(2*math.pi*t)        # one full cycle -> seamless loop
        pb.rotation_quaternion=Quaternion(AX[ax], a)
        pb.keyframe_insert("rotation_quaternion",frame=f)
__result__=json.dumps({"ok":True,"frames":TOTAL})
'''

_EXPORT_CODE = r'''
import bpy, json
rig=bpy.data.objects.get("HeroRig"); o=bpy.data.objects.get("__HERO__")
bpy.ops.object.select_all(action='DESELECT')
o.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active=rig
bpy.ops.export_scene.gltf(filepath=r"__OUT__", use_selection=True,
                          export_animation_mode='NLA_TRACKS',
                          export_animations=True, export_skins=True,
                          export_yup=True, export_apply=False)
tracks=[t.name for t in rig.animation_data.nla_tracks] if rig.animation_data else []
__result__=json.dumps({"ok":True,"out":r"__OUT__","tracks":tracks})
'''


_OPTIMIZE_CODE = r'''
import bpy, json
o=bpy.data.objects.get("Hero")
TARGET=__TARGET__
tris0=sum(len(p.vertices)-2 for p in o.data.polygons)
if tris0>TARGET:
    m=o.modifiers.new("dec","DECIMATE"); m.ratio=max(TARGET/float(tris0),0.02)
    bpy.context.view_layer.objects.active=o; o.select_set(True)
    bpy.ops.object.modifier_apply(modifier="dec")
tris1=sum(len(p.vertices)-2 for p in o.data.polygons)
bpy.ops.object.select_all(action='DESELECT'); o.select_set(True)
bpy.ops.export_scene.gltf(filepath=r"__OUT__", use_selection=True, export_yup=True)
__result__=json.dumps({"ok":True,"tris":[tris0,tris1]})
'''


def optimize_asset(src_glb: str | Path, out_glb: str | Path, target_tris: int = 45000,
                   height_m: float = 1.0, verbose: bool = True) -> dict:
    """Decimate a raw TRELLIS GLB into a game-budget asset (NPCs/props). Raw
    heroes run ~400k tris; two of those wedge an iGPU. CPU-only via bridge."""
    from app.mcp import registry, bridge
    out_glb = Path(out_glb); out_glb.parent.mkdir(parents=True, exist_ok=True)
    bridge.connect(timeout=8)
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {
        "filepath": str(src_glb), "name": "Hero", "normalize_size": height_m,
        "ground_to_z0": True, "join": True, "orientation_fix": None})
    r = _call(registry, "optimize",
              _OPTIMIZE_CODE.replace("__TARGET__", str(int(target_tris)))
                            .replace("__OUT__", str(out_glb).replace("\\", "/")))
    if not (r and r.get("ok")):
        raise RuntimeError(f"optimize failed: {r}")
    if verbose:
        mb = out_glb.stat().st_size / 1e6
        print(f"[bake] optimized {Path(src_glb).name}: {r['tris'][0]:,} -> {r['tris'][1]:,} tris, {mb:.1f} MB")
    return r


def bake_anim_set(hero_glb: str | Path, out_glb: str | Path,
                  clips: dict | None = None, height_m: float = 1.75,
                  fps: int = 24, verbose: bool = True) -> dict:
    """Returns {"ok": bool, "tracks": [...], "skin": "..."}; raises on bridge
    failure (a bake with no bridge is a hard setup error, not a fallback)."""
    from app.mcp import registry, bridge
    clips = clips or DEFAULT_CLIPS
    hero_glb = Path(hero_glb); out_glb = Path(out_glb)
    out_glb.parent.mkdir(parents=True, exist_ok=True)

    bridge.connect(timeout=8)
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {
        "filepath": str(hero_glb), "name": "Hero", "normalize_size": height_m,
        "ground_to_z0": True, "join": True, "orientation_fix": None})

    a = _call(registry, "autorig", M._AUTORIG_CODE.replace("__HERO__", "Hero"))
    if not (a and a.get("ok")):
        raise RuntimeError(f"autorig failed: {a}")
    if verbose:
        print(f"[bake] rig: {a.get('bones')} bones, skin={a.get('skin')}")

    # idle first (procedural), then each mocap clip — every one to its own track
    r = _call(registry, "idle", _IDLE_CODE.replace("__TOTAL__", str(IDLE_FRAMES)))
    if not (r and r.get("ok")):
        raise RuntimeError(f"idle bake failed: {r}")
    _call(registry, "push", _PUSH_NLA.replace("__NAME__", "idle"))

    for name, (bvh, frames) in clips.items():
        code = (M._RETARGET_CODE
                .replace("__HERO__", "Hero")
                .replace("__BVH__", str((M.MOCAP_DIR / bvh)).replace("\\", "/"))
                .replace("__TOTAL__", str(int(frames)))
                .replace("__FPS__", str(int(fps)))
                .replace("__TRACK__", "False")
                .replace("__WIDE__", "1.00")
                .replace("__INPLACE__", "True"))
        r = _call(registry, name, code)
        if not (r and r.get("ok")):
            raise RuntimeError(f"retarget '{name}' failed: {r}")
        p = _call(registry, "push", _PUSH_NLA.replace("__NAME__", name))
        if not (p and p.get("ok")):
            raise RuntimeError(f"NLA push '{name}' failed: {p}")
        if verbose:
            print(f"[bake] clip '{name}': {frames}f from {bvh}")

    e = _call(registry, "export",
              _EXPORT_CODE.replace("__HERO__", "Hero")
                          .replace("__OUT__", str(out_glb).replace("\\", "/")))
    if not (e and e.get("ok")):
        raise RuntimeError(f"export failed: {e}")
    if verbose:
        mb = out_glb.stat().st_size / 1e6 if out_glb.exists() else 0
        print(f"[bake] exported {out_glb.name} ({mb:.1f} MB, tracks={e.get('tracks')})")
    return {"ok": True, "tracks": e.get("tracks"), "skin": a.get("skin")}
