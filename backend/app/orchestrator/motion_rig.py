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

import os
from pathlib import Path
from typing import Any

# base_pattern → which builder handles it
SKELETAL_PATTERNS = {"quadruped", "biped"}


_QUADRUPED_GAIT = r'''
import bpy, math, json
import numpy as np
from mathutils import Vector

HERO = "__HERO__"; TOTAL = __TOTAL__; STRIDE = __STRIDE__; TRACK = __TRACK__; FPSV = __FPSV__
o = bpy.data.objects.get(HERO)
status = {"ok": False, "reason": ""}
if o is None or o.type != "MESH":
    __result__ = json.dumps({"ok": False, "reason": "no hero mesh"})
else:
    # WORLD-space vertices (hero keeps its live rotation+scale — do NOT bake).
    def _readV():
        mw = o.matrix_world
        return np.array([list(mw @ v.co) for v in o.data.vertices], dtype=np.float64)
    V = _readV()
    # HEAD-END check: the head/neck mass sits HIGH; if the high-vert centroid is
    # at -Y the mesh faces backward -> spin 180 about Z so it walks toward +Y
    # (and the face camera). World-Z spin; object-space texture unaffected.
    _Z = V[:, 2]; _Y = V[:, 1]
    _z0, _z1 = _Z.min(), _Z.max(); _hi = _Z > _z0 + 0.62 * (_z1 - _z0)
    if int(_hi.sum()) > 20 and float(_Y[_hi].mean()) < float((_Y.min() + _Y.max()) / 2.0):
        o.rotation_euler.z += math.pi
        bpy.context.view_layer.update()
        V = _readV()
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
    arm = bpy.data.armatures.new(HERO+"Rig"); rig = bpy.data.objects.new(HERO+"Rig", arm)
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
    # SOFT SKINNING (#119/#125): hard nearest-bone (weight 1.0) tears limbs off at
    # joints — neighboring verts snap to different bones. Blend each vert across
    # its 3 nearest bones with steep distance falloff (1/d^3), drop sub-12%
    # contributions, renormalize. Weights quantized to 64 levels so vg.add stays
    # batched (fast) instead of per-vert calls.
    K = min(3, dmat.shape[1])
    idxK = np.argsort(dmat, axis=1)[:, :K]
    dK = np.take_along_axis(dmat, idxK, 1)
    wK = 1.0 / np.maximum(dK, 1e-6) ** 3
    wK /= wK.sum(1, keepdims=True)
    wK[wK < 0.12] = 0.0
    wK /= np.maximum(wK.sum(1, keepdims=True), 1e-9)
    # Armature modifier ONLY (no parenting — the hero keeps its own transform;
    # Blender maps world↔armature space via the object matrices automatically).
    amod = o.modifiers.new("HeroArmature", "ARMATURE"); amod.object = rig
    for bi, nm in enumerate(names):
        wv = (wK * (idxK == bi)).sum(1)
        lv = np.where(wv > 1e-4)[0]
        if not len(lv): continue
        vg = o.vertex_groups.get(nm) or o.vertex_groups.new(name=nm)
        q = np.round(wv[lv] * 63).astype(np.int64)
        for level in np.unique(q):
            if level == 0: continue
            vg.add(lv[q == level].tolist(), float(level) / 63.0, "REPLACE")

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

    # ── FORWARD LOCOMOTION + FACE-SIDE TRACKING CAMERA ─────────────────────
    # The rig's head is at +Y by construction, so the creature walks toward +Y;
    # ~0.55 body-lengths per stride cycle reads as a natural ground-covering
    # walk. The scene camera is keyframed AHEAD at a 3/4 angle looking back, so
    # the FACE is visible and the subject stays framed while the world streams
    # past. WIDE widens the shot for city scenes so buildings read.
    WIDE = __WIDE__
    L_body = ymax - ymin
    travel = 1.25 * TOTAL / float(FPSV)   # unified 1.25 m/s walk: multi-actor stays together
    base = rig.location.copy()
    base_o = o.location.copy()
    cam = sc.camera
    span = max(L_body, H)
    for f in range(1, TOTAL + 1):
        frac = (f - 1) / max(TOTAL - 1, 1)
        # Move hero AND rig together: the rig-to-hero relative transform stays
        # constant, so the deform is identical to in-place (no smearing) while
        # the whole assembly covers ground.
        rig.location = (base.x, base.y + travel * frac, base.z)
        rig.keyframe_insert("location", frame=f)
        o.location = (base_o.x, base_o.y + travel * frac, base_o.z)
        o.keyframe_insert("location", frame=f)
        if TRACK and cam is not None:
            # FIXED camera position near the path's 3/4 point; rotation-only
            # tracking. The subject visibly approaches + grows in frame, which
            # reads as real motion even over featureless ground.
            hy = ymid + travel * frac
            cam.location = (cx + span * 1.6 * WIDE, ymid + travel * 0.75 + span * 2.0 * WIDE,
                            (zmin + zmax) / 2 + span * 0.6 * WIDE)
            look = Vector((cx, hy, (zmin + zmax) / 2)) - cam.location
            cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
            cam.keyframe_insert("location", frame=f)
            cam.keyframe_insert("rotation_euler", frame=f)
    __result__ = json.dumps({"ok": True, "legs": list(legs.keys()), "bones": len(pb),
                             "verts": int(len(V)), "total": TOTAL, "stride": STRIDE,
                             "travel": round(travel, 2), "wide": WIDE})
'''


_BIPED_GAIT = r'''
import bpy, math, json
import numpy as np
from mathutils import Vector

HERO = "__HERO__"; TOTAL = __TOTAL__; STRIDE = __STRIDE__; TRACK = __TRACK__; FPSV = __FPSV__
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
    arm = bpy.data.armatures.new(HERO+"Rig"); rig = bpy.data.objects.new(HERO+"Rig", arm)
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
    # SOFT SKINNING — blend across 3 nearest bones (1/d^3 falloff) so joints
    # bend instead of tearing limbs off (see quadruped template for rationale).
    K = min(2, dmat.shape[1])
    idxK = np.argsort(dmat, axis=1)[:, :K]
    dK = np.take_along_axis(dmat, idxK, 1)
    wK = 1.0 / np.maximum(dK, 1e-6) ** 3
    wK /= wK.sum(1, keepdims=True)
    wK[wK < 0.22] = 0.0
    wK /= np.maximum(wK.sum(1, keepdims=True), 1e-9)
    amod = o.modifiers.new("HeroArmature", "ARMATURE"); amod.object = rig
    for bi, nm in enumerate(names):
        wv = (wK * (idxK == bi)).sum(1)
        lv = np.where(wv > 1e-4)[0]
        if not len(lv): continue
        vg = o.vertex_groups.get(nm) or o.vertex_groups.new(name=nm)
        q = np.round(wv[lv] * 63).astype(np.int64)
        for level in np.unique(q):
            if level == 0: continue
            vg.add(lv[q == level].tolist(), float(level) / 63.0, "REPLACE")

    # ── Walk gait (legs alternate, arms counter-swing); swings along FORWARD.
    sc = bpy.context.scene; sc.frame_start = 1; sc.frame_end = TOTAL
    bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="POSE")
    try: bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    except Exception: pass
    pb = rig.pose.bones
    for b in pb: b.rotation_mode = "XYZ"
    legph = {"L": 0.0, "R": math.pi}
    A_LEG = 0.30; A_ARM = 0.18   # calm, natural walk — large swings shear thin limbs
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

    # ── FORWARD LOCOMOTION + FACE-SIDE TRACKING CAMERA (same engine as the
    # quadruped: rig translates, armature carries the hero; camera sits AHEAD
    # at a 3/4 angle looking back so the face is visible). Forward axis is the
    # NARROW horizontal (legs swing along it); forward SIGN from the toes —
    # feet extend toward the facing, so the low-band centroid is biased forward.
    WIDE = __WIDE__
    fwd_is_y = (SWING == 0)
    FA = Y if fwd_is_y else X
    fmid = cy if fwd_is_y else cx
    low = Z < (zmin + 0.10 * H)
    fsign = 1.0 if (int(low.sum()) > 10 and float(FA[low].mean()) > fmid) else -1.0
    travel = 1.25 * TOTAL / float(FPSV) * fsign   # unified 1.25 m/s walk
    base = rig.location.copy()
    cam = sc.camera
    span = max(H, xspan, yspan)
    midz = (zmin + zmax) / 2.0
    for f in range(1, TOTAL + 1):
        frac = (f - 1) / max(TOTAL - 1, 1)
        d = travel * frac
        rig.location = (base.x + (0 if fwd_is_y else d), base.y + (d if fwd_is_y else 0), base.z)
        rig.keyframe_insert("location", frame=f)
        if TRACK and cam is not None:
            hx = cx + (0 if fwd_is_y else d); hy = cy + (d if fwd_is_y else 0)
            ahead = travel / max(abs(travel), 1e-9)  # unit sign
            if fwd_is_y:
                cam.location = (hx + span * 1.4 * WIDE, hy + ahead * span * 2.2 * WIDE, midz + span * 0.5 * WIDE)
            else:
                cam.location = (hx + ahead * span * 2.2 * WIDE, hy + span * 1.4 * WIDE, midz + span * 0.5 * WIDE)
            look = Vector((hx, hy, midz)) - Vector(cam.location)
            cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
            cam.keyframe_insert("location", frame=f)
            cam.keyframe_insert("rotation_euler", frame=f)
    __result__ = json.dumps({"ok": True, "legs": list(legs.keys()), "arms": list(arms.keys()),
                             "bones": len(pb), "verts": int(len(V)), "total": TOTAL,
                             "stride": STRIDE, "swing_idx": SWING,
                             "travel": round(travel, 2), "wide": WIDE})
'''


_GAIT_CODE = {"quadruped": _QUADRUPED_GAIT, "biped": _BIPED_GAIT}
_GAIT_STRIDE = {"quadruped": 20, "biped": 28}


# Wheeled drive for the PROCEDURAL vehicle (body=Hero, wheels=Wheel_* parented).
# The body drives +Y, each wheel spins about its axle ∝ distance (no slip), a
# suspension bob, and the scene camera tracks the car so it stays framed while the
# ground streams past. Rigid — no skinning.
_WHEELED_DRIVE = r'''
import bpy, math, json
from mathutils import Vector

HERO="__HERO__"; TOTAL=__TOTAL__
MODE="__MODE__"; SPEED=__SPEED__
o=bpy.data.objects.get(HERO)
if o is None:
    __result__=json.dumps({"ok": False, "reason": "no hero"})
else:
    wheels=[w for w in bpy.data.objects if w.name.startswith("Wheel_") and w.type=="MESH"]
    # car length along Y to scale the drive + wheel radius for the spin rate
    ys=[(o.matrix_world@Vector(c)).y for c in o.bound_box]
    car_len=max(max(ys)-min(ys), 1.0)
    zs0=[(o.matrix_world@Vector(c)).z for c in o.bound_box]
    car_h=max(max(zs0)-min(zs0), 0.5)
    wheel_r=0.44
    if wheels:
        zs=[(wheels[0].matrix_world@Vector(c)).z for c in wheels[0].bound_box]
        wheel_r=max((max(zs)-min(zs))/2.0, 0.1)
    sc=bpy.context.scene; sc.frame_start=1; sc.frame_end=TOTAL
    try: bpy.context.preferences.edit.keyframe_new_interpolation_type="LINEAR"
    except Exception: pass
    # MODE: drive (default sweep) | race (fast + low chase cam) | showcase (static
    # car, 360-degree orbiting turntable camera — the social-media beauty shot).
    if MODE=="showcase": travel=0.0
    elif MODE=="race":   travel=car_len*4.5*SPEED
    else:                travel=car_len*1.5*SPEED
    base=o.location.copy()
    o.rotation_mode="XYZ"
    for w in wheels: w.rotation_mode="XYZ"
    wrest={w.name: w.location.copy() for w in wheels}   # wheels are independent objects
    for f in range(1,TOTAL+1):
        frac=(f-1)/max(TOTAL-1,1); dist=travel*(frac-0.5)   # -travel/2 .. +travel/2
        bob=(0.016 if MODE=="race" else 0.01)*math.sin(2*math.pi*frac*9)*(0.0 if MODE=="showcase" else 1.0)
        o.location=(base.x, base.y+dist, base.z+bob)
        o.keyframe_insert("location", frame=f)
        spin=-dist/wheel_r
        for w in wheels:
            r=wrest[w.name]
            w.location=(r.x, r.y+dist, r.z+bob); w.keyframe_insert("location", frame=f)
            w.rotation_euler=(spin,0,0); w.keyframe_insert("rotation_euler", frame=f)
    dc=bpy.data.cameras.new("DriveCam"); dc.lens=42
    dco=bpy.data.objects.new("DriveCam", dc); bpy.context.scene.collection.objects.link(dco)
    if MODE=="showcase":
        # Orbit 360 degrees around the static car at 3/4 height. lens 55 for a
        # tighter, more flattering beauty framing.
        dc.lens=55
        R=car_len*2.0
        for f in range(1,TOTAL+1):
            frac=(f-1)/max(TOTAL-1,1); ang=2*math.pi*frac
            dco.location=Vector((base.x+R*math.cos(ang), base.y+R*math.sin(ang), base.z+car_h*1.15))
            look=Vector((base.x, base.y, base.z+car_h*0.45))-dco.location
            dco.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
            dco.keyframe_insert("location", frame=f); dco.keyframe_insert("rotation_euler", frame=f)
    elif MODE=="race":
        # LOW chase camera tracking the car — speed reads from the ground rushing
        # past close to the lens.
        dc.lens=35
        offx=car_len*1.15; offy=-car_len*1.45; offz=car_h*0.45
        for f in range(1,TOTAL+1):
            frac=(f-1)/max(TOTAL-1,1); dist=travel*(frac-0.5)
            dco.location=Vector((base.x+offx, base.y+dist+offy, base.z+offz))
            look=Vector((base.x, base.y+dist+car_len*0.2, base.z+car_h*0.35))-dco.location
            dco.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
            dco.keyframe_insert("location", frame=f); dco.keyframe_insert("rotation_euler", frame=f)
    else:
        # Static side-3/4 wide enough to keep the whole sweep in frame.
        spanY=travel+car_len
        side=max(spanY*0.85, car_len*1.6)
        dco.location=Vector((base.x+side, base.y-side*0.35, base.z+side*0.45))
        look=Vector((base.x, base.y, base.z+0.2))-dco.location
        dco.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
    sc.camera=dco
    __result__=json.dumps({"ok": True, "wheels": len(wheels), "travel": round(travel,2),
                           "mode": MODE, "speed": SPEED, "cam": "DriveCam"})
'''


def build_wheeled_drive(runner, hero_name: str, total_frames: int, fps: int = 24,
                        mode: str = "drive", speed: float = 1.0,
                        verbose: bool = False) -> bool:
    """Drive the procedural vehicle: translate the body, spin the wheels, track
    with the camera. mode: drive | race (fast + low chase cam) | showcase
    (static turntable orbit). speed scales travel. Returns True if applied."""
    if mode not in ("drive", "race", "showcase"):
        mode = "drive"
    code = (_WHEELED_DRIVE.replace("__HERO__", hero_name)
            .replace("__TOTAL__", str(int(total_frames)))
            .replace("__MODE__", mode)
            .replace("__SPEED__", f"{float(speed):.2f}"))
    try:
        res = runner.run("wheeled_drive", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        import json as _json
        info = _json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        if info and info.get("ok"):
            if verbose:
                print(f"[composer] wheeled drive: {info.get('wheels')} wheels spinning, "
                      f"travel {info.get('travel')}m")
            return True
        if verbose:
            print(f"[composer] wheeled drive: not applied ({info.get('reason') if info else 'no result'})")
        return False
    except Exception as e:
        if verbose:
            print(f"[composer] wheeled drive: failed ({type(e).__name__}: {e})")
        return False


def build_skeletal_gait(runner, hero_name: str, base_pattern: str,
                        total_frames: int, fps: int = 24, track_camera: bool = True,
                        wide=None, verbose: bool = False) -> bool:
    """Rig the (already oriented + textured) hero and bake a procedural gait that
    loops for the whole clip. Returns True if a gait was applied (so the composer
    skips its crude object-translate locomotion). Never raises — on any failure it
    returns False and the composer falls back to the legacy motion path."""
    if base_pattern not in SKELETAL_PATTERNS:
        return False
    stride = _GAIT_STRIDE.get(base_pattern, 24)
    _env_wide = 1.9 if os.environ.get("FS_SCENE_SETTING", "") in ("street", "night_city") else 1.0
    wide = float(wide) if wide else _env_wide
    code = (_GAIT_CODE[base_pattern]
            .replace("__HERO__", hero_name)
            .replace("__TOTAL__", str(int(total_frames)))
            .replace("__STRIDE__", str(stride))
            .replace("__TRACK__", "True" if track_camera else "False")
            .replace("__FPSV__", str(int(fps)))
            .replace("__WIDE__", str(wide)))
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
