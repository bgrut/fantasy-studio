"""Phase 20 — skeletal motion inside the composer.

Unlike the standalone scripts/rig_*_test.py prototypes (which import a RAW mesh
and re-orient/re-stage it), this module animates the hero that the composer has
ALREADY oriented (length→Y, flanks→±X, up→Z), textured (multiview), and grounded.
So it does the minimum and touches nothing else:

  • works in WORLD coordinates (the composer leaves a live rotation+scale on the
    hero — we must NOT transform_apply, or the object-space texture projection
    shifts), so we read `matrix_world @ v.co` and place bones at world positions;
  • NEVER changes materials (texture-safe), camera, lights, or ground;
  • builds an armature + nearest-bone skin + a procedural gait that loops for the
    WHOLE clip (stride period decoupled from total frame count).

The hero arrives in the composer's canonical frame, so the quadruped builder uses
the same convention the standalone cheetah test validated: body length along Y
(front = +Y), legs swing fore/aft about world X.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# base_pattern → which builder handles it
SKELETAL_PATTERNS = {"quadruped", "biped"}


_QUADRUPED_GAIT = r'''
import bpy, math, json
import numpy as np
from mathutils import Vector

HERO = "__HERO__"; TOTAL = __TOTAL__; STRIDE = __STRIDE__
o = bpy.data.objects.get(HERO)
status = {"ok": False, "reason": ""}
if o is None or o.type != "MESH":
    __result__ = json.dumps({"ok": False, "reason": "no hero mesh"})
else:
    # WORLD-space vertices (hero keeps its live rotation+scale — do NOT bake).
    mw = o.matrix_world
    V = np.array([list(mw @ v.co) for v in o.data.vertices], dtype=np.float64)
    X, Y, Z = V[:, 0], V[:, 1], V[:, 2]
    xmin, xmax = X.min(), X.max(); ymin, ymax = Y.min(), Y.max(); zmin, zmax = Z.min(), Z.max()
    cx = (xmin + xmax) / 2.0; ymid = (ymin + ymax) / 2.0
    L = ymax - ymin; W = xmax - xmin; H = zmax - zmin
    body_z = zmin + H * 0.60; knee_z = zmin + H * 0.30; foot_z = zmin + 0.01 * H
    head_y = ymax; back_y = ymin + L * 0.28; front_y = ymin + L * 0.70

    # ── Detect the 4 leg positions (centroid of bottom verts per F/B × L/R quadrant)
    bottom = Z < (zmin + 0.40 * H)
    feet = {}
    for fb, ysel in (("F", Y > ymid), ("B", Y <= ymid)):
        for side, xsel in (("L", X <= cx), ("R", X > cx)):
            msk = bottom & ysel & xsel
            if int(msk.sum()) > 4:
                feet[fb + side] = (float(X[msk].mean()), float(Y[msk].mean()))
            else:
                feet[fb + side] = (cx + (W * 0.28 if side == "R" else -W * 0.28),
                                   front_y if fb == "F" else back_y)

    # ── Armature at world origin (identity) so edit-bone coords == world coords.
    arm = bpy.data.armatures.new("HeroRig"); rig = bpy.data.objects.new("HeroRig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig; rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    segs = []   # (name, head, tail) deform bones for manual weighting
    def mk(name, h, t, parent=None, deform=True):
        b = eb.new(name); b.head = Vector(h); b.tail = Vector(t)
        if parent: b.parent = parent
        if deform: segs.append((name, np.array(h, dtype=np.float64), np.array(t, dtype=np.float64)))
        return b
    root = mk("root", (cx, ymid, body_z), (cx, ymid + 0.05 * max(L, 1e-3), body_z), deform=False)
    spine = mk("spine", (cx, back_y, body_z), (cx, front_y, body_z), root)
    mk("neck", (cx, front_y, body_z), (cx, head_y, zmax * 0.80 + zmin * 0.20), spine)
    mk("tail", (cx, back_y, body_z), (cx, ymin, body_z * 0.7 + zmin * 0.3), spine)
    legs = {}
    for key, (fx, fy) in feet.items():
        th = mk("thigh_" + key, (fx, fy, body_z), (fx, fy, knee_z), spine)
        sh = mk("shin_" + key, (fx, fy, knee_z), (fx, fy, foot_z), th, True)
        legs[key] = (th.name, sh.name)
    bpy.ops.object.mode_set(mode="OBJECT")

    # ── Manual NEAREST-BONE skin (bone-heat returns 0 verts on generated meshes).
    names = [s[0] for s in segs]
    dmat = np.empty((len(V), len(segs)), dtype=np.float64)
    for bi, (nm, h, t) in enumerate(segs):
        seg = t - h; L2 = max(float(seg @ seg), 1e-9)
        u = np.clip(((V - h) @ seg) / L2, 0.0, 1.0)
        proj = h[None, :] + u[:, None] * seg[None, :]
        dmat[:, bi] = np.linalg.norm(V - proj, axis=1)
    nearest = dmat.argmin(axis=1)
    # Armature modifier ONLY (no parenting — the hero keeps its own transform;
    # Blender maps world↔armature space via the object matrices automatically).
    amod = o.modifiers.new("HeroArmature", "ARMATURE"); amod.object = rig
    for bi, nm in enumerate(names):
        vg = o.vertex_groups.get(nm) or o.vertex_groups.new(name=nm)
        idx = np.where(nearest == bi)[0].tolist()
        if idx: vg.add(idx, 1.0, "REPLACE")

    # ── Trot gait (diagonal pairs); loops for the whole clip via STRIDE period.
    sc = bpy.context.scene; sc.frame_start = 1; sc.frame_end = TOTAL
    bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="POSE")
    try: bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    except Exception: pass
    pb = rig.pose.bones
    for b in pb: b.rotation_mode = "XYZ"
    phase = {"FL": 0.0, "BR": 0.0, "FR": math.pi, "BL": math.pi}
    A = 0.50
    for f in range(1, TOTAL + 1):
        t = 2 * math.pi * (f - 1) / STRIDE
        for leg, (thn, shn) in legs.items():
            ph = phase.get(leg, 0.0)
            pb[thn].rotation_euler = (A * math.sin(t + ph), 0, 0)
            pb[thn].keyframe_insert("rotation_euler", frame=f)
            pb[shn].rotation_euler = (-0.5 * A * (1 + math.cos(t + ph)), 0, 0)
            pb[shn].keyframe_insert("rotation_euler", frame=f)
        pb["root"].location = (0, 0, 0.03 * H * abs(math.sin(t)))
        pb["root"].keyframe_insert("location", frame=f)
        pb["spine"].rotation_euler = (0, 0, 0.05 * math.sin(t))
        pb["spine"].keyframe_insert("rotation_euler", frame=f)
    bpy.ops.object.mode_set(mode="OBJECT")
    __result__ = json.dumps({"ok": True, "legs": list(legs.keys()), "bones": len(pb),
                             "verts": int(len(V)), "total": TOTAL, "stride": STRIDE})
'''


_BIPED_GAIT = r'''
import bpy, math, json
import numpy as np
from mathutils import Vector

HERO = "__HERO__"; TOTAL = __TOTAL__; STRIDE = __STRIDE__
o = bpy.data.objects.get(HERO)
if o is None or o.type != "MESH":
    __result__ = json.dumps({"ok": False, "reason": "no hero mesh"})
else:
    # WORLD-space verts (hero arrives oriented up=Z by the silhouette gate; do NOT bake).
    mw = o.matrix_world
    V = np.array([list(mw @ v.co) for v in o.data.vertices], dtype=np.float64)
    X, Y, Z = V[:, 0], V[:, 1], V[:, 2]
    xmin, xmax = X.min(), X.max(); ymin, ymax = Y.min(), Y.max(); zmin, zmax = Z.min(), Z.max()
    cx = (xmin + xmax) / 2.0; cy = (ymin + ymax) / 2.0; H = zmax - zmin
    xspan = xmax - xmin; yspan = ymax - ymin

    # The composer azimuth-normalizes the LONG horizontal axis to Y. For a biped the
    # wider horizontal is the shoulder/hip (L-R) axis; the narrower is the facing.
    # SIDE = L-R axis (split legs/arms here); legs swing along FORWARD. A down-pointing
    # bone swings along world Y on euler index 0 and world X on euler index 2 (matches
    # the validated quadruped). So forward=Y→idx0, forward=X→idx2.
    if yspan >= xspan:
        SA = Y; side_mid = cy; SWING = 2          # side=Y, forward=X
    else:
        SA = X; side_mid = cx; SWING = 0          # side=X, forward=Y

    hip_z = zmin + 0.50 * H; chest_z = zmin + 0.72 * H; knee_z = zmin + 0.26 * H
    foot_z = zmin + 0.02 * H; neck_z = zmin + 0.82 * H; elbow_z = zmin + 0.62 * H; hand_z = zmin + 0.46 * H

    def lr(mask, fallback_off):
        out = {}
        for s, sel in (("L", SA <= side_mid), ("R", SA > side_mid)):
            m = mask & sel
            if int(m.sum()) > 4:
                out[s] = (float(X[m].mean()), float(Y[m].mean()))
            else:
                off = fallback_off if s == "R" else -fallback_off
                out[s] = (cx + (off if SA is X else 0.0), cy + (off if SA is Y else 0.0))
        return out
    feet = lr(Z < (zmin + 0.18 * H), 0.18 * max(xspan, yspan))
    shoulders = lr((Z > (zmin + 0.72 * H)) & (Z < (zmin + 0.90 * H)), 0.30 * max(xspan, yspan))

    # ── Armature at world origin (identity) so edit-bone coords == world coords.
    arm = bpy.data.armatures.new("HeroRig"); rig = bpy.data.objects.new("HeroRig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig; rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones; segs = []
    def mk(name, h, t, parent=None, deform=True):
        b = eb.new(name); b.head = Vector(h); b.tail = Vector(t)
        if parent: b.parent = parent
        if deform: segs.append((name, np.array(h, dtype=np.float64), np.array(t, dtype=np.float64)))
        return b
    root = mk("root", (cx, cy, hip_z), (cx, cy + 0.04 * max(H, 1e-3), hip_z), deform=False)
    spine = mk("spine", (cx, cy, hip_z), (cx, cy, chest_z), root)
    neck = mk("neck", (cx, cy, chest_z), (cx, cy, neck_z), spine)
    mk("head", (cx, cy, neck_z), (cx, cy, zmax), neck)
    legs = {}; arms = {}
    for s, (fx, fy) in feet.items():
        th = mk("thigh_" + s, (fx, fy, hip_z), (fx, fy, knee_z), root)
        sh = mk("shin_" + s, (fx, fy, knee_z), (fx, fy, foot_z), th, True)
        legs[s] = (th.name, sh.name)
    for s, (sx, sy) in shoulders.items():
        ua = mk("uarm_" + s, (sx, sy, neck_z), (sx, sy, elbow_z), spine)
        fa = mk("farm_" + s, (sx, sy, elbow_z), (sx, sy, hand_z), ua, True)
        arms[s] = (ua.name, fa.name)
    bpy.ops.object.mode_set(mode="OBJECT")

    # ── Manual NEAREST-BONE skin.
    names = [s[0] for s in segs]
    dmat = np.empty((len(V), len(segs)), dtype=np.float64)
    for bi, (nm, h, t) in enumerate(segs):
        seg = t - h; L2 = max(float(seg @ seg), 1e-9)
        u = np.clip(((V - h) @ seg) / L2, 0.0, 1.0)
        proj = h[None, :] + u[:, None] * seg[None, :]
        dmat[:, bi] = np.linalg.norm(V - proj, axis=1)
    nearest = dmat.argmin(axis=1)
    amod = o.modifiers.new("HeroArmature", "ARMATURE"); amod.object = rig
    for bi, nm in enumerate(names):
        vg = o.vertex_groups.get(nm) or o.vertex_groups.new(name=nm)
        idx = np.where(nearest == bi)[0].tolist()
        if idx: vg.add(idx, 1.0, "REPLACE")

    # ── Walk gait (legs alternate, arms counter-swing); swings along FORWARD.
    sc = bpy.context.scene; sc.frame_start = 1; sc.frame_end = TOTAL
    bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="POSE")
    try: bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    except Exception: pass
    pb = rig.pose.bones
    for b in pb: b.rotation_mode = "XYZ"
    legph = {"L": 0.0, "R": math.pi}
    A_LEG = 0.42; A_ARM = 0.36
    def rot(v):
        e = [0.0, 0.0, 0.0]; e[SWING] = v; return tuple(e)
    for f in range(1, TOTAL + 1):
        t = 2 * math.pi * (f - 1) / STRIDE
        for s, (thn, shn) in legs.items():
            ph = legph[s]
            pb[thn].rotation_euler = rot(A_LEG * math.sin(t + ph)); pb[thn].keyframe_insert("rotation_euler", frame=f)
            pb[shn].rotation_euler = rot(-0.55 * A_LEG * (1 + math.cos(t + ph))); pb[shn].keyframe_insert("rotation_euler", frame=f)
        for s, (uan, fan) in arms.items():
            ph = legph["R" if s == "L" else "L"]   # arm opposes same-side leg
            pb[uan].rotation_euler = rot(A_ARM * math.sin(t + ph)); pb[uan].keyframe_insert("rotation_euler", frame=f)
            pb[fan].rotation_euler = rot(-0.3 * A_ARM * (1 + math.cos(t + ph))); pb[fan].keyframe_insert("rotation_euler", frame=f)
        pb["root"].location = (0, 0, 0.03 * H * abs(math.sin(t))); pb["root"].keyframe_insert("location", frame=f)
    bpy.ops.object.mode_set(mode="OBJECT")
    __result__ = json.dumps({"ok": True, "legs": list(legs.keys()), "arms": list(arms.keys()),
                             "bones": len(pb), "verts": int(len(V)), "total": TOTAL,
                             "stride": STRIDE, "swing_idx": SWING})
'''


_GAIT_CODE = {"quadruped": _QUADRUPED_GAIT, "biped": _BIPED_GAIT}
_GAIT_STRIDE = {"quadruped": 20, "biped": 28}


def build_skeletal_gait(runner, hero_name: str, base_pattern: str,
                        total_frames: int, fps: int = 24, verbose: bool = False) -> bool:
    """Rig the (already oriented + textured) hero and bake a procedural gait that
    loops for the whole clip. Returns True if a gait was applied (so the composer
    skips its crude object-translate locomotion). Never raises — on any failure it
    returns False and the composer falls back to the legacy motion path."""
    if base_pattern not in SKELETAL_PATTERNS:
        return False
    stride = _GAIT_STRIDE.get(base_pattern, 24)
    code = (_GAIT_CODE[base_pattern]
            .replace("__HERO__", hero_name)
            .replace("__TOTAL__", str(int(total_frames)))
            .replace("__STRIDE__", str(stride)))
    try:
        res = runner.run("skeletal_gait", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        import json as _json
        info = _json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        if info and info.get("ok"):
            if verbose:
                print(f"[composer] skeletal gait: {base_pattern} rigged "
                      f"({info.get('bones')} bones, {info.get('verts')} verts, "
                      f"{total_frames}f / stride {info.get('stride')})")
            return True
        if verbose:
            print(f"[composer] skeletal gait: not applied ({info.get('reason') if info else 'no result'})")
        return False
    except Exception as e:  # never destabilize the composer
        if verbose:
            print(f"[composer] skeletal gait: failed ({type(e).__name__}: {e}) — using legacy motion")
        return False
