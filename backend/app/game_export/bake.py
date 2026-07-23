"""Bake a game-ready ANIMATION SET onto a Studio hero: auto-rig once, retarget
each CMU clip IN-PLACE onto its own NLA track (idle/walk/run...), export ONE
animated glTF whose named animations the web runtime switches between.

CPU-only — needs the headless Blender bridge (port 9876) but never the dGPU,
so this runs while the graphics card is down. Reuses the validated Tier A+B
rig (adaptive arm bones + voxel-proxy skin) from app.orchestrator.mocap_retarget.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from app.orchestrator import mocap_retarget as M

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def ensure_bridge(verbose: bool = True) -> bool:
    """Blender bridge self-heal: the headless Blender behind the bridge dies
    sometimes (flaky iGPU driver, crashes, restarts) and every bake after
    that fails silently as 'generation failed'. Try to connect; if down,
    relaunch the headless instance and wait for it. The wolf of 2026-07-06
    took 40 CPU-minutes to generate and then vanished because of this."""
    from app.mcp import bridge
    try:
        bridge.connect(timeout=8)
        return True
    except Exception:
        pass
    if verbose:
        print("[bake] blender bridge down — relaunching headless instance")
    import subprocess
    import time
    exe = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
    try:
        from app.main import get_setting   # lazy: avoids circular import at load time
        exe = get_setting("blender_executable_path") or exe
    except Exception:
        pass
    try:
        subprocess.Popen(
            [exe, "--background", "--python",
             str(BACKEND_ROOT / "scripts" / "headless_bridge_startup.py")],
            cwd=str(BACKEND_ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(12):                      # up to ~60 s for addon boot
            time.sleep(5)
            try:
                bridge.connect(timeout=8)
                if verbose:
                    print("[bake] bridge back up")
                return True
            except Exception:
                continue
    except Exception:
        pass
    if verbose:
        print("[bake] bridge relaunch FAILED — bake cannot proceed")
    return False

# default game clip set: state name -> (CMU bvh, frames at 24fps)
DEFAULT_CLIPS = {
    "walk": ("02_01.bvh", 40),
    "run":  ("02_03.bvh", 28),
    "attack": ("02_05.bvh", 16),   # fight-clip strike slice — the swing
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
from mathutils import Quaternion, Vector, Matrix
rig=bpy.data.objects.get("HeroRig")
TOTAL=__TOTAL__
for pb in rig.pose.bones: pb.rotation_mode="QUATERNION"
sc=bpy.context.scene; sc.frame_start=1
# ARMS DOWN (Phase 63): generated bipeds REST in a T-pose, so an idle that
# only sways around rest SHOWS the T-pose whenever the player stands still
# (the Mountain Dog Duty screenshot). Aim each upper arm mostly down, kept in
# its own outward plane so hands clear the thighs; the forearm/hand chain
# inherits. The CMU walk/run/attack clips already pose arms correctly.
armQ={}
for s in ("L","R"):
    p=rig.pose.bones.get("uparm_"+s)
    if not p: continue
    rest=p.bone.matrix_local
    d0=(rest.to_3x3() @ Vector((0,1,0))).normalized()
    dv=Vector((d0.x*0.22, d0.y*0.10, -1.0)).normalized()
    q=d0.rotation_difference(dv)
    p.matrix=Matrix.Translation(p.bone.head_local) @ ((q.to_matrix() @ rest.to_3x3()).to_4x4())
    armQ["uparm_"+s]=p.rotation_quaternion.copy()
sway={"spine":(0.020,'X'),"chest":(0.028,'X'),"head":(0.014,'X'),
      "uparm_L":(0.018,'Y'),"uparm_R":(0.018,'Y')}
AX={'X':(1,0,0),'Y':(0,1,0)}
for i in range(TOTAL):
    f=1+i; t=i/TOTAL
    for name,(amp,ax) in sway.items():
        pb=rig.pose.bones.get(name)
        if not pb: continue
        a=amp*math.sin(2*math.pi*t)        # one full cycle -> seamless loop
        qs=Quaternion(AX[ax], a)
        pb.rotation_quaternion=(armQ[name] @ qs) if name in armQ else qs
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


# ── QUADRUPED rig+skin: the video pipeline's validated recipe (motion_rig
# _QUADRUPED_GAIT rig section) — head-end check, per-quadrant foot detection,
# 11-bone skeleton, soft 1/d^3 nearest-bone skin. Gait is baked separately so
# each clip (walk/run) lands on its own NLA track.
_QUAD_RIG_CODE = r'''
import bpy, math, json
import numpy as np
from mathutils import Vector
o = bpy.data.objects.get("Hero")
if o is None or o.type != "MESH":
    __result__ = json.dumps({"ok": False, "reason": "no hero mesh"})
else:
    def _readV():
        mw = o.matrix_world
        return np.array([list(mw @ v.co) for v in o.data.vertices], dtype=np.float64)
    V = _readV()
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
    # NOTE (Phase 56, tested + rejected): anchoring leg columns at the true
    # foot clusters (bottom-15% centroid) was measured WORSE on the morph
    # harness (bear 0.702->0.738, cat 0.613->0.640) — it drags the thigh top
    # away from the upper-leg mass and increases bleed. The broad bottom-40%
    # centroid places the whole COLUMN better for binding. Keep as-is.
    arm = bpy.data.armatures.new("HeroRig"); rig = bpy.data.objects.new("HeroRig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig; rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    segs = []
    def mk(name, h, t, parent=None, deform=True):
        b = eb.new(name); b.head = Vector(h); b.tail = Vector(t)
        if parent: b.parent = parent
        if deform: segs.append((name, np.array(h, dtype=np.float64), np.array(t, dtype=np.float64)))
        return b
    root = mk("root", (cx, ymid, body_z), (cx, ymid + 0.05 * max(L, 1e-3), body_z), deform=False)
    spine = mk("spine", (cx, back_y, body_z), (cx, front_y, body_z), root)
    mk("neck", (cx, front_y, body_z), (cx, head_y, zmax * 0.80 + zmin * 0.20), spine)
    mk("tail", (cx, back_y, body_z), (cx, ymin, body_z * 0.7 + zmin * 0.3), spine)
    LEGMAP = {}
    for key, (fx, fy) in feet.items():
        th = mk("thigh_" + key, (fx, fy, body_z), (fx, fy, knee_z), spine)
        sh = mk("shin_" + key, (fx, fy, knee_z), (fx, fy, foot_z), th, True)
        LEGMAP[key] = (th.name, sh.name)
    bpy.ops.object.mode_set(mode="OBJECT")
    names = [s[0] for s in segs]
    dmat = np.empty((len(V), len(segs)), dtype=np.float64)
    for bi, (nm, h, t) in enumerate(segs):
        seg = t - h; L2 = max(float(seg @ seg), 1e-9)
        u = np.clip(((V - h) @ seg) / L2, 0.0, 1.0)
        proj = h[None, :] + u[:, None] * seg[None, :]
        dmat[:, bi] = np.linalg.norm(V - proj, axis=1)
    # SKIN V2 (Phase 54): same-side/end constraints + geodesic leg distance.
    # Any failure falls back to the untouched Euclidean dmat above.
    _s2status = "off"
    if __SKINV2__:
        try:
            dmat = _s2_refine_dmat(dmat, V, segs, names, o)
            _s2status = "refined"
        except Exception as _s2e:
            _s2status = "refine_failed: %s: %s" % (type(_s2e).__name__, _s2e)
    K = min(3, dmat.shape[1])
    idxK = np.argsort(dmat, axis=1)[:, :K]
    dK = np.take_along_axis(dmat, idxK, 1)
    wK = 1.0 / np.maximum(dK, 1e-6) ** 3
    wK /= wK.sum(1, keepdims=True)
    wK[wK < 0.12] = 0.0
    wK /= np.maximum(wK.sum(1, keepdims=True), 1e-9)
    # SKIN V2 (Phase 54): Laplacian weight smoothing + max-4-influence clamp.
    if __SKINV2__:
        try:
            wK, idxK = _s2_smooth(wK, idxK, len(segs), V, o)
            _s2status += "+smoothed"
        except Exception as _s2e:
            _s2status += "; smooth_failed: %s: %s" % (type(_s2e).__name__, _s2e)
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
    # SKIN HEAT (Phase 71 experiment, FS_SKIN_HEAT): Blender's bone-heat auto
    # weights FAIL on raw TRELLIS topology (0 verts) but succeed on a
    # watertight VOXEL-REMESHED proxy of the same shape. Compute heat weights
    # on the proxy, then DataTransfer them onto the detailed hero (nearest
    # face-interpolated) — clean-topology weights, original mesh untouched.
    # Any failure keeps the manual weights already assigned above.
    _heat_status = "off"
    if __SKINHEAT__:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.select_all(action='DESELECT')
            o.select_set(True); bpy.context.view_layer.objects.active = o
            bpy.ops.object.duplicate()
            proxy = bpy.context.view_layer.objects.active
            proxy.name = "HeroProxy"
            proxy.modifiers.clear()
            # INSTANT-MESHES PROXY (Phase 105, the KEYSTONE unblocked): a
            # clean QUAD retopo beats the voxel blob for heat weights —
            # edge loops follow the limbs, so shoulder/armpit weights stop
            # bleeding. BSD-3 binary at tools/instant-meshes. Any failure
            # falls back to the proven voxel proxy below.
            _im_ok = False
            try:
                import subprocess as _sp, os as _os, tempfile as _tf
                _im = r"__IMEXE__"
                if _im and _os.path.exists(_im):
                    _t1 = _os.path.join(_tf.gettempdir(), "fs_im_src.obj")
                    _t2 = _os.path.join(_tf.gettempdir(), "fs_im_out.obj")
                    bpy.ops.object.select_all(action='DESELECT')
                    proxy.select_set(True)
                    bpy.context.view_layer.objects.active = proxy
                    bpy.ops.wm.obj_export(filepath=_t1,
                        export_selected_objects=True, export_materials=False)
                    _r = _sp.run([_im, _t1, "-o", _t2, "--faces", "9000",
                                  "--deterministic"], capture_output=True,
                                 timeout=180)
                    if _r.returncode == 0 and _os.path.exists(_t2):
                        _before = set(bpy.data.objects)
                        bpy.ops.wm.obj_import(filepath=_t2)
                        _news = [x for x in bpy.data.objects
                                 if x not in _before and x.type == 'MESH']
                        if _news:
                            bpy.data.objects.remove(proxy, do_unlink=True)
                            proxy = _news[0]
                            proxy.name = "HeroProxy"
                            # WATERTIGHT-IFY: bone heat solves a diffusion
                            # problem — open boundaries break it (0 weights
                            # on the raw IM mesh). Weld + fill closes it.
                            bpy.ops.object.select_all(action='DESELECT')
                            proxy.select_set(True)
                            bpy.context.view_layer.objects.active = proxy
                            bpy.ops.object.mode_set(mode='EDIT')
                            bpy.ops.mesh.select_all(action='SELECT')
                            bpy.ops.mesh.remove_doubles(threshold=0.0008)
                            bpy.ops.mesh.fill_holes(sides=0)
                            bpy.ops.mesh.normals_make_consistent(inside=False)
                            bpy.ops.object.mode_set(mode='OBJECT')
                            _im_ok = True
            except Exception:
                _im_ok = False
            if not _im_ok:
                rm = proxy.modifiers.new("VoxRM", "REMESH")
                rm.mode = 'VOXEL'; rm.voxel_size = max(float(H) / 64.0, 0.008)
                bpy.ops.object.modifier_apply(modifier=rm.name)
            for vg in list(proxy.vertex_groups):
                proxy.vertex_groups.remove(vg)
            bpy.ops.object.select_all(action='DESELECT')
            proxy.select_set(True); rig.select_set(True)
            bpy.context.view_layer.objects.active = rig
            bpy.ops.object.parent_set(type='ARMATURE_AUTO')
            _nw = sum(1 for v in proxy.data.vertices if v.groups)
            if _nw < len(proxy.data.vertices) * 0.5:
                raise RuntimeError("heat sparse: %d/%d verts weighted"
                                   % (_nw, len(proxy.data.vertices)))
            # replace the manual weights on the hero with the proxy's
            for vg in list(o.vertex_groups):
                o.vertex_groups.remove(vg)
            bpy.ops.object.select_all(action='DESELECT')
            o.select_set(True); bpy.context.view_layer.objects.active = o
            dt = o.modifiers.new("WDT", "DATA_TRANSFER")
            dt.object = proxy; dt.use_vert_data = True
            dt.data_types_verts = {'VGROUP_WEIGHTS'}
            dt.vert_mapping = 'POLYINTERP_NEAREST'
            dt.layers_vgroup_select_src = 'ALL'; dt.layers_vgroup_select_dst = 'NAME'
            bpy.ops.object.datalayout_transfer(modifier=dt.name)
            bpy.ops.object.modifier_apply(modifier=dt.name)
            bpy.data.objects.remove(proxy, do_unlink=True)
            _heat_status = ("heat_ok_im" if _im_ok else "heat_ok") + "(%d verts)" % _nw
        except Exception as _he:
            _heat_status = "heat_failed: %s: %s" % (type(_he).__name__, _he)
            try:
                _pr = bpy.data.objects.get("HeroProxy")
                if _pr: bpy.data.objects.remove(_pr, do_unlink=True)
            except Exception:
                pass
    __result__ = json.dumps({"ok": True, "legs": list(LEGMAP.keys()), "bones": len(arm.bones),
                             "H": round(float(H), 3), "skin_v2": _s2status,
                             "skin_heat": _heat_status})
'''

# one IN-PLACE trot clip: whole sine cycles -> seamless loop. AMP/STRIDE vary
# per clip (walk vs run); root bob + spine sway match the video-side gait.
_QUAD_CLIP_CODE = r'''
import bpy, math, json
TOTAL=__TOTAL__; STRIDE=__STRIDE__; AMP=__AMP__
rig=bpy.data.objects.get("HeroRig"); o=bpy.data.objects.get("Hero")
import numpy as np
mw=o.matrix_world
_vs=o.data.vertices; _st=max(1,len(_vs)//200)
zs=[(mw @ _vs[i].co).z for i in range(0,len(_vs),_st)]
H=max(zs)-min(zs) if zs else 1.0
bpy.context.view_layer.objects.active=rig
bpy.ops.object.mode_set(mode="POSE")
try: bpy.context.preferences.edit.keyframe_new_interpolation_type="LINEAR"
except Exception: pass
pb=rig.pose.bones
for b in pb: b.rotation_mode="XYZ"
phase={"FL":0.0,"BR":0.0,"FR":math.pi,"BL":math.pi}
legs={k.split("_")[1]:None for k in pb.keys() if k.startswith("thigh_")}
for f in range(1, TOTAL+1):
    t=2*math.pi*(f-1)/STRIDE
    for leg in legs:
        ph=phase.get(leg,0.0)
        thn, shn = "thigh_"+leg, "shin_"+leg
        pb[thn].rotation_euler=(AMP*math.sin(t+ph),0,0)
        pb[thn].keyframe_insert("rotation_euler",frame=f)
        pb[shn].rotation_euler=(-0.5*AMP*(1+math.cos(t+ph)),0,0)
        pb[shn].keyframe_insert("rotation_euler",frame=f)
    pb["root"].location=(0,0,0.03*H*abs(math.sin(t)))
    pb["root"].keyframe_insert("location",frame=f)
    pb["spine"].rotation_euler=(0,0,0.05*math.sin(t))
    pb["spine"].keyframe_insert("rotation_euler",frame=f)
    if "tail" in pb:
        pb["tail"].rotation_euler=(0,0,0.18*math.sin(t*0.5))
        pb["tail"].keyframe_insert("rotation_euler",frame=f)
bpy.ops.object.mode_set(mode="OBJECT")
__result__=json.dumps({"ok":True,"frames":TOTAL,"legs":sorted(legs)})
'''

# quadruped idle: breathing bob + slow tail wag + gentle head dip, exact loop
_QUAD_IDLE_CODE = r'''
import bpy, math, json
rig=bpy.data.objects.get("HeroRig"); TOTAL=__TOTAL__
bpy.context.view_layer.objects.active=rig
bpy.ops.object.mode_set(mode="POSE")
pb=rig.pose.bones
for b in pb: b.rotation_mode="XYZ"
for i in range(TOTAL):
    f=1+i; t=i/TOTAL
    s1=math.sin(2*math.pi*t); s2=math.sin(4*math.pi*t)
    pb["root"].location=(0,0,0.004*s1)
    pb["root"].keyframe_insert("location",frame=f)
    if "neck" in pb:
        pb["neck"].rotation_euler=(0.03*s1,0,0)
        pb["neck"].keyframe_insert("rotation_euler",frame=f)
    if "tail" in pb:
        pb["tail"].rotation_euler=(0,0,0.22*s2)
        pb["tail"].keyframe_insert("rotation_euler",frame=f)
bpy.ops.object.mode_set(mode="OBJECT")
__result__=json.dumps({"ok":True,"frames":TOTAL})
'''


_OPTIMIZE_CODE = r'''
import bpy, json
import numpy as np
o=bpy.data.objects.get("Hero")
TARGET=__TARGET__
me=o.data
# SHARD CLEANUP (video-side trellis2_clean port): TRELLIS meshes carry small
# disconnected islands ("strings"/floaters). Rigging them binds junk to bones
# and they smear in motion. Union-find on edges; keep only components >= 1.5%
# of verts (the body + large parts), drop the debris.
nv=len(me.vertices)
if nv>1000:
    par=np.arange(nv, dtype=np.int64)
    def _f(a):
        r=a
        while par[r]!=r: r=par[r]
        while par[a]!=r: par[a],a=r,par[a]
        return r
    ecount=len(me.edges)
    ev=np.empty(ecount*2, dtype=np.int64)
    me.edges.foreach_get("vertices", ev)
    ev=ev.reshape(-1,2)
    for a,b in ev:
        ra,rb=_f(a),_f(b)
        if ra!=rb: par[rb]=ra
    roots=np.array([_f(i) for i in range(nv)])
    uniq,counts=np.unique(roots, return_counts=True)
    keep=set(uniq[counts>=max(int(nv*0.015),50)].tolist())
    kill=np.where(~np.isin(roots, list(keep)))[0]
    if 0 < len(kill) < nv*0.4:
        import bmesh
        bm=bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.verts[i] for i in kill.tolist()], context='VERTS')
        bm.to_mesh(me); bm.free(); me.update()
dropped=nv-len(me.vertices)
# FUSED-SPIKE (needle) filter — the #125 'strings', ported from the video
# pipeline but WITHOUT the organic skip: game characters can't wear needles.
# A needle is a CHAIN of sparse occupancy cells, long in one axis and tiny in
# the others; ears/tails/fur are dense cells and survive. (Validated on the
# samurai: vertical hair-thin strands through the body.)
nv2=len(me.vertices)
if nv2>1000:
    co=np.empty(nv2*3); me.vertices.foreach_get("co", co); co=co.reshape(-1,3)
    span=float(max(co.max(0)-co.min(0)))
    cellS=span*0.02
    gc=np.floor(co/cellS).astype(np.int64)
    cells,vcell=np.unique(gc, axis=0, return_inverse=True)
    vcell=np.asarray(vcell).reshape(-1)
    cl=cells.tolist()
    cmap={(c[0],c[1],c[2]):k for k,c in enumerate(cl)}
    offs=[(dx,dy,dz) for dx in(-1,0,1) for dy in(-1,0,1) for dz in(-1,0,1) if (dx,dy,dz)!=(0,0,0)]
    ncc=np.zeros(len(cl), dtype=np.int32)
    for _k,_c in enumerate(cl):
        _cnt=0
        for dx,dy,dz in offs:
            if (_c[0]+dx,_c[1]+dy,_c[2]+dz) in cmap: _cnt+=1
        ncc[_k]=_cnt
    tend=np.where(ncc<=6)[0]
    n_spike=0
    if 0 < len(tend) < int(len(cl)*0.6):
        tset=set(tend.tolist())
        cpar=np.arange(len(cl), dtype=np.int64)
        def _cf(a):
            r=a
            while cpar[r]!=r: r=cpar[r]
            while cpar[a]!=r: cpar[a],a=r,cpar[a]
            return r
        for _k in tend.tolist():
            _c=cl[_k]
            for dx,dy,dz in offs:
                _nb=cmap.get((_c[0]+dx,_c[1]+dy,_c[2]+dz))
                if _nb is not None and _nb in tset:
                    _ra,_rb=_cf(_k),_cf(_nb)
                    if _ra!=_rb: cpar[_rb]=_ra
        sroots=np.array([_cf(_k) for _k in tend])
        scell=[]
        for _r in np.unique(sroots):
            _grp=tend[sroots==_r]
            _pts=cells[_grp].astype(np.float64)*cellS
            _e=np.sort(_pts.max(0)-_pts.min(0))
            # needle: long (>=8% span) in ONE axis, hair-thin (<2.5 cells) in
            # the other two — ears/tails are thicker and keep their cells
            if _e[2]>=0.08*span and _e[1]<=cellS*2.5:
                scell.extend(_grp.tolist())
        if scell:
            spk=np.where(np.isin(vcell, scell))[0]
            if 0 < len(spk) <= int(nv2*0.12):
                n_spike=int(len(spk))
                import bmesh
                bm=bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
                bmesh.ops.delete(bm, geom=[bm.verts[i] for i in spk.tolist()], context='VERTS')
                bm.to_mesh(me); bm.free(); me.update()
    dropped+=n_spike
tris0=sum(len(p.vertices)-2 for p in o.data.polygons)
# SAFETY (2026-07-06): a mangled import once exported an 80-tri husk OVER a
# healthy library asset (man.glb, restored from git). If the import looks
# broken, FAIL before the export can overwrite anything.
if tris0 < 500:
    raise RuntimeError(f"import produced only {tris0} tris — refusing to overwrite output")
if tris0>TARGET:
    m=o.modifiers.new("dec","DECIMATE"); m.ratio=max(TARGET/float(tris0),0.02)
    bpy.context.view_layer.objects.active=o; o.select_set(True)
    bpy.ops.object.modifier_apply(modifier="dec")
tris1=sum(len(p.vertices)-2 for p in o.data.polygons)
# ALPHA REWIRE: TRELLIS hair/fringe strips rely on texture transparency; the
# import/export round-trip can drop the image->Alpha link, rendering the
# transparent strips as solid black "strands". If the base-color image carries
# an alpha channel, wire it to Principled Alpha and keep an alpha-aware blend.
alpha_wired=0
for _mt in me.materials:
    if not (_mt and _mt.use_nodes): continue
    _b=_mt.node_tree.nodes.get("Principled BSDF")
    if not _b: continue
    _ain=_b.inputs.get("Alpha")
    if _ain is None or _ain.is_linked: continue
    _base=_b.inputs.get("Base Color")
    _img=None
    if _base and _base.is_linked:
        _src=_base.links[0].from_node
        if _src.type=="TEX_IMAGE" and _src.image and _src.image.depth==32:
            _img=_src
    if _img is not None:
        _mt.node_tree.links.new(_img.outputs["Alpha"], _ain)
        # CLIP -> glTF alphaMode MASK: hard fragment discard, deterministic in
        # EVERY engine (three.js alphaTest, Godot, Unreal). BLEND left fringe
        # strips visible in three.js despite correct alpha.
        _mt.blend_method='CLIP'
        try: _mt.alpha_threshold=0.5
        except Exception: pass
        alpha_wired+=1
for _mt in me.materials:
    if _mt: _mt.use_backface_culling=True
# NORMALS HYGIENE (realism plan R1.2): generated meshes carry pockets of
# inverted faces that render BLACK under filmic tonemapping (the car-hood
# "black spots"). Recalculate consistent outside-facing normals.
try:
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True)
    bpy.context.view_layer.objects.active=o
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
except Exception:
    try: bpy.ops.object.mode_set(mode='OBJECT')
    except Exception: pass
bpy.ops.object.select_all(action='DESELECT'); o.select_set(True)
bpy.ops.export_scene.gltf(filepath=r"__OUT__", use_selection=True, export_yup=True)
__result__=json.dumps({"ok":True,"tris":[tris0,tris1],"shard_verts_dropped":int(dropped),
                       "alpha_wired":alpha_wired})
'''


class _RegistryRunner:
    """Adapter: composer texture helpers expect runner.run(name, op, params)."""
    def __init__(self, registry):
        self._r = registry

    def run(self, name, op, params, critical=False):
        return self._r.call(op, params)


def _glb_has_images(glb: str | Path) -> bool:
    import struct as _st
    try:
        with open(glb, "rb") as f:
            f.read(12)
            clen, _ = _st.unpack("<II", f.read(8))
            return bool(json.loads(f.read(clen)).get("images"))
    except Exception:
        return True                      # unsure → don't touch the materials


_DERIVE_NORMALS_CODE = r'''
import bpy, json
import numpy as np
o=bpy.data.objects.get('Hero')
made=0
seen=set()
for mt in (o.data.materials if o else []):
    if not (mt and mt.use_nodes): continue
    nt=mt.node_tree
    b=nt.nodes.get('Principled BSDF')
    if not b or b.inputs['Normal'].is_linked: continue
    base=b.inputs.get('Base Color')
    if not (base and base.is_linked): continue
    src=base.links[0].from_node
    if src.type!='TEX_IMAGE' or not src.image or src.image.name in seen: continue
    img=src.image; seen.add(img.name)
    w,h=img.size
    if w*h==0 or w<64: continue
    px=np.empty(w*h*4, dtype=np.float32)
    img.pixels.foreach_get(px)
    lum=px.reshape(h,w,4)[:,:,:3].mean(2)
    # light blur (3x3 box) so micro-noise doesn't become normal grain
    p=np.pad(lum,1,mode='edge')
    lum=(p[:-2,:-2]+p[:-2,1:-1]+p[:-2,2:]+p[1:-1,:-2]+p[1:-1,1:-1]+p[1:-1,2:]
         +p[2:,:-2]+p[2:,1:-1]+p[2:,2:])/9.0
    # sobel gradients -> tangent-space normal (albedo-as-height approximation)
    p=np.pad(lum,1,mode='edge')
    dx=(p[:-2,2:]+2*p[1:-1,2:]+p[2:,2:]) - (p[:-2,:-2]+2*p[1:-1,:-2]+p[2:,:-2])
    dy=(p[2:,:-2]+2*p[2:,1:-1]+p[2:,2:]) - (p[:-2,:-2]+2*p[:-2,1:-1]+p[:-2,2:])
    S=1.6   # strength: visible relief without embossing
    nx=-dx*S; ny=-dy*S; nz=np.ones_like(dx)
    ln=np.sqrt(nx*nx+ny*ny+nz*nz)
    out=np.empty((h,w,4), dtype=np.float32)
    out[:,:,0]=nx/ln*0.5+0.5; out[:,:,1]=ny/ln*0.5+0.5
    out[:,:,2]=nz/ln*0.5+0.5; out[:,:,3]=1.0
    nimg=bpy.data.images.new(img.name+'_nrm', width=w, height=h, alpha=False)
    nimg.colorspace_settings.name='Non-Color'
    nimg.pixels.foreach_set(out.ravel())
    if max(w,h) > 1024:                     # relief doesn't need albedo res —
        s=1024.0/max(w,h)                   # keeps library GLBs shippable
        nimg.scale(int(w*s), int(h*s))
    nimg.pack()
    tex=nt.nodes.new('ShaderNodeTexImage'); tex.image=nimg
    nm=nt.nodes.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value=0.5
    nt.links.new(tex.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    made+=1
__result__=json.dumps({"ok":True,"normal_maps":made})
'''

_DESPECKLE_CODE = r'''
import bpy, json
import numpy as np
o=bpy.data.objects.get('Hero')
healed=0; imgs=0
seen=set()
for mt in (o.data.materials if o else []):
    if not (mt and mt.use_nodes): continue
    for nd in mt.node_tree.nodes:
        if nd.type!='TEX_IMAGE' or not nd.image or nd.image.name in seen: continue
        img=nd.image; seen.add(img.name)
        w,h=img.size
        if w*h==0 or w<64 or h<64: continue
        px=np.empty(w*h*4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px=px.reshape(h,w,4)
        changed=False
        # two healing scales: 8px kills specks; 24px kills the LARGE dark
        # patches (hood blotches) whose 8px neighborhoods are themselves dark
        for B in (8, 24):
            lum=px[:,:,:3].mean(2)
            HB,WB=(h//B)*B,(w//B)*B
            if HB==0 or WB==0: continue
            blk=lum[:HB,:WB].reshape(HB//B,B,WB//B,B).mean((1,3))
            nb=np.repeat(np.repeat(blk,B,0),B,1)
            m=(lum[:HB,:WB] < 0.45*nb) & (nb > 0.18)
            n=int(m.sum())
            if n==0 or n > 0.15*HB*WB: continue
            blkc=px[:HB,:WB,:3].reshape(HB//B,B,WB//B,B,3).mean((1,3))
            nbc=np.repeat(np.repeat(blkc,B,axis=0),B,axis=1)
            sub=px[:HB,:WB,:3]
            sub[m]=nbc[m]
            px[:HB,:WB,:3]=sub
            healed+=n; changed=True
        if changed:
            img.pixels.foreach_set(px.ravel())
            img.update()
            imgs+=1
__result__=json.dumps({"ok":True,"healed_px":healed,"images":imgs})
'''


# ── ORIENTATION GUARANTEE (Phase 57) ────────────────────────────────────────
# The 24-view silhouette gate is best-effort (a belly-up bear once passed at
# IoU 0.34). This closes the loop: geometric feet-down/head-up check on the
# FINAL exported GLB — fresh import, actual verts, no renders — with
# auto-correct + re-export + re-check when clearly inverted. An unverified
# orientation never ships silently.
_ORIENT_VERIFY_CODE = r'''
import bpy, math, json
import numpy as np
from mathutils import Matrix
PAT="__PATTERN__"; FIX=__FIX__; OUT=r"__OUT__"
bpy.ops.import_scene.gltf(filepath=OUT)
meshes=[o for o in bpy.data.objects if o.type=="MESH"]
if not meshes:
    __result__=json.dumps({"ok":False,"reason":"no mesh in GLB"})
else:
    # Force rest pose: raw v.co on a SKINNED glTF mesh is Y-up BIND space —
    # measuring it flipped a correct bear once (2026-07-11). The EVALUATED
    # depsgraph mesh in REST position is true world-space Z-up geometry
    # (same method the quality harness uses).
    for _a in bpy.data.objects:
        if _a.type == "ARMATURE":
            _a.data.pose_position = "REST"
    bpy.context.view_layer.update()
    def _verts():
        dg = bpy.context.evaluated_depsgraph_get(); dg.update()
        vs=[]
        for o in meshes:
            ev = o.evaluated_get(dg); me = ev.to_mesh()
            mw = ev.matrix_world
            vs += [list(mw @ v.co) for v in me.vertices]
            ev.to_mesh_clear()
        return np.array(vs, dtype=np.float64)
    def _gap(V, zlo, zhi):
        # leg-gap detector (same prior the composer gate uses): the FEET end
        # has a left/right (and front/back) split between limbs; the back/head
        # end is a solid blob. Gap at the TOP => the character is inverted.
        Z=V[:,2]; z0,z1=Z.min(),Z.max(); H=max(z1-z0,1e-6)
        sel=(Z>=z0+zlo*H)&(Z<z0+zhi*H)
        if int(sel.sum())<30: return 0.0
        best=0.0
        for ax in (0,1):
            a=V[sel,ax]; c=float(np.median(a)); hw=max((a.max()-a.min())/2,1e-6)
            fill=float((np.abs(a-c)<0.25*hw).mean())
            best=max(best,1.0-fill)
        return best
    V=_verts()
    bot=_gap(V,0.0,0.40 if PAT=="biped" else 0.35)
    top=_gap(V,0.60 if PAT=="biped" else 0.65,1.0)
    upright = not (top > bot + 0.05)      # only CLEAR inversions fail
    flipped=0
    if not upright and FIX:
        # quadruped: roll 180 about Y (body long axis) keeps the heading;
        # biped: flip about X (the composer prior's proven convention).
        ax = "X" if PAT=="biped" else "Y"
        R=Matrix.Rotation(math.pi,4,ax)
        for o in bpy.data.objects:
            if o.parent is None:
                o.matrix_world = R @ o.matrix_world
        bpy.context.view_layer.update()
        zmin=float(_verts()[:,2].min())
        for o in bpy.data.objects:
            if o.parent is None:
                o.matrix_world = Matrix.Translation((0,0,-zmin)) @ o.matrix_world
        bpy.context.view_layer.update()
        V=_verts()
        bot=_gap(V,0.0,0.40 if PAT=="biped" else 0.35)
        top=_gap(V,0.60 if PAT=="biped" else 0.65,1.0)
        upright = not (top > bot + 0.05)
        flipped=1
        for _a in bpy.data.objects:              # back to POSE before export
            if _a.type == "ARMATURE":
                _a.data.pose_position = "POSE"
        bpy.context.view_layer.update()
        bpy.ops.export_scene.gltf(filepath=OUT, export_animation_mode="NLA_TRACKS",
                                  export_animations=True, export_skins=True,
                                  export_yup=True, export_apply=False)
    __result__=json.dumps({"ok":True,"upright":bool(upright),"flipped":flipped,
                           "bottom_gap":round(bot,3),"top_gap":round(top,3)})
'''


def verify_glb_orientation(glb: str | Path, pattern: str | None, fix: bool = False,
                           verbose: bool = True) -> dict:
    """Orientation TELEMETRY on a final GLB (legged patterns only) — detection
    only, gated off by default (FS_ORIENT_VERIFY=1 to enable).

    AUTO-FIX IS REJECTED BY EVIDENCE (2026-07-11): two independent geometric
    leg-gap detectors (raw-bind-space AND evaluated-rest-space) both produced
    FALSE POSITIVES on known-good rigs — the first flipped a correct polar
    bear twice; the trimesh cross-check false-flagged a correct fox. Vertex
    statistics cannot tell a chunky animal's back from its belly reliably
    (same lesson as the Phase 52 silhouette CoM tiebreak). Orientation is
    guaranteed where it is provable: the 24-view silhouette gate vs the
    REFERENCE IMAGE at bake time (composer) + the feet-down/head-up priors +
    ensure_playable's mtime invalidation. A future render-based verifier
    (final GLB silhouette vs reference) may flag for RE-BAKE — but must never
    flip files in place on a statistical signal."""
    if os.environ.get("FS_ORIENT_VERIFY", "0") != "1":
        return {"ok": True, "skipped": "FS_ORIENT_VERIFY off"}
    if pattern not in ("quadruped", "biped"):
        return {"ok": True, "skipped": pattern or "unknown"}
    from app.mcp import registry, bridge
    try:
        bridge.connect(timeout=8)
        registry.call("reset_scene", {})
        code = (_ORIENT_VERIFY_CODE
                .replace("__PATTERN__", pattern)
                .replace("__FIX__", "1" if fix else "0")
                .replace("__OUT__", str(Path(glb).resolve()).replace("\\", "/")))
        r = _call(registry, "orient_verify", code)
    except Exception as e:  # verify must never kill a bake — but never be silent
        r = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    if verbose:
        if r and r.get("ok"):
            print(f"[bake] orientation verify: upright={r.get('upright')} "
                  f"flipped={r.get('flipped')} (gaps bottom={r.get('bottom_gap')} "
                  f"top={r.get('top_gap')})")
        else:
            print(f"[bake] orientation verify FAILED to run: {r}")
    return r or {"ok": False}


def optimize_asset(src_glb: str | Path, out_glb: str | Path, target_tris: int = 45000,
                   height_m: float = 1.0, verbose: bool = True,
                   ref_png: str | Path | None = None,
                   despeckle: bool = False,
                   derive_normals: bool = True,
                   pattern: str | None = None) -> dict:
    """Decimate a raw TRELLIS GLB into a game-budget asset (NPCs/props). Raw
    heroes run ~400k tris; two of those wedge an iGPU. CPU-only via bridge.

    ref_png (2026-07-05 quality round): when the mesh carries NO baked texture
    (TripoSR CPU generations arrive with washed-out vertex colors → ghosts),
    project the SDXL reference photo onto it — the video pipeline's Phase 19
    projection, REUSED — so the exported GLB ships real colors. TRELLIS gens
    already have textures and are left untouched."""
    from app.mcp import registry
    out_glb = Path(out_glb); out_glb.parent.mkdir(parents=True, exist_ok=True)
    if not ensure_bridge(verbose):
        raise RuntimeError("blender bridge unavailable and relaunch failed — "
                           "asset bake cannot run")
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {
        "filepath": str(src_glb), "name": "Hero", "normalize_size": height_m,
        "ground_to_z0": True, "join": True, "orientation_fix": None})
    if ref_png and Path(ref_png).exists():
        # ORIENTATION GATE (2026-07-06, the no-more-guessing fix): render the
        # mesh at all 24 axis-aligned orientations and BAKE the one whose
        # silhouette best matches the reference image. The runtime stops
        # guessing — assets arrive correct. Same verified machinery the video
        # side has used since Phase 20.
        try:
            from app.orchestrator.composer import _orient_hero_by_reference
            _scratch = out_glb.parent / "_orient_scratch"
            _scratch.mkdir(parents=True, exist_ok=True)
            _og = _orient_hero_by_reference(
                _RegistryRunner(registry), "Hero", str(ref_png), _scratch,
                upright_biped=(pattern == "biped"),
                wheels_down=(pattern == "vehicle"),
                quad_feet_down=(pattern == "quadruped"),
                verbose=verbose)
            if verbose:
                print(f"[bake] orientation gate: ok={_og.get('ok')} "
                      f"iou={_og.get('iou', 0):.2f}")
        except Exception as _oe:
            if verbose:
                print(f"[bake] orientation gate skipped ({type(_oe).__name__}: {_oe})")
        finally:
            shutil.rmtree(out_glb.parent / "_orient_scratch", ignore_errors=True)
        if not _glb_has_images(src_glb):
            try:
                from app.orchestrator.composer import _apply_reference_texture
                _apply_reference_texture(_RegistryRunner(registry), "Hero",
                                         str(ref_png), verbose=verbose)
                if verbose:
                    print(f"[bake] projected reference texture onto {Path(src_glb).name}")
                # TEXTURE V2 (Phase 60, FS_TEX_V2): the flat projection above
                # smears every surface not facing the reference camera (the
                # "half-stretched face"). Re-bake into a smart-UV atlas —
                # photo where trustworthy, pyramid-inpainted fur where not.
                # Failure keeps the v1 texture.
                from . import texture_v2
                if texture_v2.enabled():
                    _t2 = texture_v2.run(
                        "Hero", str(ref_png),
                        str(out_glb.with_suffix("")) + "_atlas.png")
                    if verbose:
                        print(f"[bake] texture v2: {_t2}")
            except Exception as _te:
                if verbose:
                    print(f"[bake] ref projection skipped ({type(_te).__name__}: {_te})")
    if despeckle:
        # heal dark speck clusters baked INTO the albedo (hood "black spots").
        # Vehicles only — organic textures have legitimate small dark features
        # (eyes, nostrils) this rule would eat.
        d = _call(registry, "despeckle", _DESPECKLE_CODE)
        if verbose and d:
            print(f"[bake] despeckle: healed {d.get('healed_px', 0)} px "
                  f"across {d.get('images', 0)} image(s)")
    if derive_normals:
        # PHOTOREAL LADDER step 4 (2026-07-06): derive a tangent-space normal
        # map from the albedo (blur -> sobel -> normal). Approximate but
        # transformative — flat CPU-era textures gain surface relief that
        # responds to every light in both engines. Skipped automatically when
        # a real normal map already exists (GPU-era assets keep theirs).
        nr = _call(registry, "derive_normals", _DERIVE_NORMALS_CODE)
        if verbose and nr:
            print(f"[bake] derived {nr.get('normal_maps', 0)} normal map(s) from albedo")
    r = _call(registry, "optimize",
              _OPTIMIZE_CODE.replace("__TARGET__", str(int(target_tris)))
                            .replace("__OUT__", str(out_glb).replace("\\", "/")))
    if not (r and r.get("ok")):
        raise RuntimeError(f"optimize failed: {r}")
    if verbose:
        mb = out_glb.stat().st_size / 1e6
        print(f"[bake] optimized {Path(src_glb).name}: {r['tris'][0]:,} -> {r['tris'][1]:,} tris, {mb:.1f} MB")
    # ORIENTATION GUARANTEE (Phase 57): never ship an unverified orientation.
    r["orientation"] = verify_glb_orientation(out_glb, pattern, verbose=verbose)
    return r


def bake_quadruped_anim_set(hero_glb: str | Path, out_glb: str | Path,
                            height_m: float = 0.6, verbose: bool = True) -> dict:
    """Species-correct playable QUADRUPED: video-side rig + trot gait baked
    in-place as idle/walk/run NLA clips, exported as one animated glTF."""
    from app.mcp import registry, bridge
    hero_glb = Path(hero_glb); out_glb = Path(out_glb)
    out_glb.parent.mkdir(parents=True, exist_ok=True)
    bridge.connect(timeout=8)
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {
        "filepath": str(hero_glb), "name": "Hero", "normalize_size": height_m,
        "ground_to_z0": True, "join": True, "orientation_fix": None})
    from . import skin_v2, retopo
    # KEYSTONE (Phase 58, FS_RETOPO=1): rebuild the hero as even manifold
    # quads BEFORE rigging — clean joint loops for the skinning. Any failure
    # leaves the original mesh untouched.
    if retopo.enabled():
        rr = retopo.run("Hero")            # long-timeout bridge call
        if verbose:
            print(f"[bake] retopo: {rr}")
    a = _call(registry, "quad_rig", skin_v2.wrap(_QUAD_RIG_CODE))
    if not (a and a.get("ok")):
        raise RuntimeError(f"quad rig failed: {a}")
    if verbose:
        print(f"[bake] quad rig: {a.get('bones')} bones, legs={a.get('legs')}, "
              f"skin_v2={a.get('skin_v2', '?')}, skin_heat={a.get('skin_heat', '?')}")
    r = _call(registry, "idle", _QUAD_IDLE_CODE.replace("__TOTAL__", "72"))
    if not (r and r.get("ok")):
        raise RuntimeError(f"quad idle failed: {r}")
    _call(registry, "push", _PUSH_NLA.replace("__NAME__", "idle"))
    # attack: one-shot POUNCE (pitch down + rebound) — quadruped strike
    r = _call(registry, "pounce", r'''
import bpy, math, json
rig=bpy.data.objects.get("HeroRig")
bpy.context.view_layer.objects.active=rig
bpy.ops.object.mode_set(mode="POSE")
pb=rig.pose.bones
for b in pb: b.rotation_mode="XYZ"
T=14
for f in range(1, T+1):
    t=(f-1)/(T-1)
    a=math.sin(t*math.pi)          # 0 -> peak -> 0
    pb["spine"].rotation_euler=(0.55*a,0,0)
    pb["spine"].keyframe_insert("rotation_euler",frame=f)
    if "neck" in pb:
        pb["neck"].rotation_euler=(-0.35*a,0,0)
        pb["neck"].keyframe_insert("rotation_euler",frame=f)
    pb["root"].location=(0,0.10*a,-0.02*a)
    pb["root"].keyframe_insert("location",frame=f)
bpy.ops.object.mode_set(mode="OBJECT")
__result__=json.dumps({"ok":True,"frames":T})
''')
    if r and r.get("ok"):
        _call(registry, "push", _PUSH_NLA.replace("__NAME__", "attack"))
    # walk: 2 cycles @ stride 20; run: 3 cycles @ stride 12, bigger swing
    # GAIT-SCALE (2026-07-15): big animals lope, small ones scurry — a 1.4 m
    # bear at cat cadence "moved kinda funny". Cycle length grows ~size^0.35.
    _gk = min(max((height_m / 0.6) ** 0.35, 0.8), 1.6)
    for name, total, stride, amp in (
            ("walk", int(40 * _gk), max(int(20 * _gk), 8), 0.50),
            ("run", int(36 * _gk), max(int(12 * _gk), 6), 0.72)):
        r = _call(registry, name, (_QUAD_CLIP_CODE
                                   .replace("__TOTAL__", str(total))
                                   .replace("__STRIDE__", str(stride))
                                   .replace("__AMP__", f"{amp:.2f}")))
        if not (r and r.get("ok")):
            raise RuntimeError(f"quad clip '{name}' failed: {r}")
        p = _call(registry, "push", _PUSH_NLA.replace("__NAME__", name))
        if not (p and p.get("ok")):
            raise RuntimeError(f"NLA push '{name}' failed: {p}")
        if verbose:
            print(f"[bake] quad clip '{name}': {total}f stride {stride}")
    e = _call(registry, "export",
              _EXPORT_CODE.replace("__HERO__", "Hero")
                          .replace("__OUT__", str(out_glb).replace("\\", "/")))
    if not (e and e.get("ok")):
        raise RuntimeError(f"export failed: {e}")
    if verbose:
        mb = out_glb.stat().st_size / 1e6 if out_glb.exists() else 0
        print(f"[bake] exported {out_glb.name} ({mb:.1f} MB, tracks={e.get('tracks')})")
    # ORIENTATION GUARANTEE (Phase 57): verify the final animated artifact.
    ov = verify_glb_orientation(out_glb, "quadruped", verbose=verbose)
    return {"ok": True, "tracks": e.get("tracks"), "orientation": ov}


def ensure_playable(kind: str, verbose: bool = True) -> str | None:
    """Return a PLAYER-grade (rigged+animated) GLB for `kind`, baking it on
    first use from the static library asset. Bipeds get the CMU mocap set,
    quadrupeds the trot gait; vehicles aren't playable yet (returns None)."""
    from . import library
    from .generate import guess_pattern
    anim = BACKEND_ROOT / "assets" / "library" / f"{kind.lower().replace(' ', '_')}_anim.glb"
    static = library.resolve(kind)
    # Serve the cached rig ONLY if it is at least as new as the static mesh it was
    # rigged from. A re-baked static (an orientation or texture fix) MUST
    # invalidate the derived _anim.glb — otherwise the stale rig ships silently.
    # This is exactly how a corrected polar bear kept playing UPSIDE-DOWN: the
    # static was fixed but the older _anim.glb (rigged from the belly-up mesh)
    # still existed, so the game used it (2026-07-08).
    if anim.exists():
        try:
            fresh = bool(static) and anim.stat().st_mtime >= Path(static).stat().st_mtime
        except OSError:
            fresh = True
        if fresh:
            return str(anim)
    if not static:
        return str(anim) if anim.exists() else None
    try:                       # already rigged+animated (e.g. the man player)?
        from .verify_game import _glb_json
        g = _glb_json(Path(static))
        if g.get("skins") and g.get("animations"):
            return static
    except Exception:
        pass
    pattern = guess_pattern(kind)
    h = library.default_height(kind)
    if pattern in ("quadruped", "biped") and not ensure_bridge(verbose):
        return static                       # honest fallback: static mesh > no mesh
    try:
        if pattern == "quadruped":
            bake_quadruped_anim_set(static, anim, height_m=h, verbose=verbose)
        elif pattern == "biped":
            bake_anim_set(static, anim, height_m=h, verbose=verbose)
        else:
            return None                      # vehicles: wheeled players are future work
        return str(anim)
    except Exception as e:
        if verbose:
            print(f"[bake] ensure_playable('{kind}') failed ({type(e).__name__}: {e})")
        return None


_FACING_GATE_CODE = r"""
import bpy, math, json
import numpy as np
o = bpy.data.objects['Hero']
dg = bpy.context.evaluated_depsgraph_get()
me = o.evaluated_get(dg).to_mesh()
n = len(me.vertices)
co = np.empty(n*3, dtype=np.float64); me.vertices.foreach_get('co', co)
V = co.reshape(-1,3)
M = np.array(o.matrix_world)
Vw = V @ M[:3,:3].T + M[:3,3]
z = Vw[:,2]; zmin, zmax = z.min(), z.max(); H = zmax - zmin
torso = Vw[(z > zmin + 0.35*H) & (z < zmin + 0.75*H)]
ext_x = float(torso[:,0].max()-torso[:,0].min())
ext_y = float(torso[:,1].max()-torso[:,1].min())
ratio = max(ext_x, ext_y) / max(min(ext_x, ext_y), 1e-6)
if ratio < 1.3:
    __result__ = json.dumps({"ok": True, "skipped": "ambiguous", "ratio": round(ratio,2)})
else:
    fb = 0 if ext_x < ext_y else 1
    feet = Vw[z < zmin + 0.08*H]
    sign = 1.0 if float(feet[:,fb].mean()) > float(np.median(torso[:,fb])) else -1.0
    v = (sign, 0.0) if fb == 0 else (0.0, sign)
    fwd = math.degrees(math.atan2(v[1], v[0]))
    rot = math.radians(90.0 - fwd)          # hunter convention: +Y forward
    if abs(rot) > 1e-3:
        o.rotation_euler[2] += rot
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.transform_apply(rotation=True)
    __result__ = json.dumps({"ok": True, "was_deg": fwd, "rotated_deg": round(math.degrees(rot),1)})
"""


_FACING_DETECT_FILE = r"""
import bpy, math, json
import numpy as np
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.import_scene.gltf(filepath=r"__GLB__")
ms = [o for o in bpy.data.objects if o.type == 'MESH']
o = ms[0]
dg = bpy.context.evaluated_depsgraph_get()
me = o.evaluated_get(dg).to_mesh()
co = np.empty(len(me.vertices)*3); me.vertices.foreach_get('co', co)
V = co.reshape(-1,3)
M = np.array(o.matrix_world)
Vw = V @ M[:3,:3].T + M[:3,3]
z = Vw[:,2]; zmin, zmax = z.min(), z.max(); H = zmax - zmin
torso = Vw[(z > zmin + 0.35*H) & (z < zmin + 0.75*H)]
ext_x = float(torso[:,0].max()-torso[:,0].min())
ext_y = float(torso[:,1].max()-torso[:,1].min())
ratio = max(ext_x, ext_y) / max(min(ext_x, ext_y), 1e-6)
if ratio < 1.3:
    __result__ = json.dumps({"ok": True, "skipped": "ambiguous"})
else:
    fb = 0 if ext_x < ext_y else 1
    feet = Vw[z < zmin + 0.08*H]
    sign = 1.0 if float(feet[:,fb].mean()) > float(np.median(torso[:,fb])) else -1.0
    v = (sign, 0.0) if fb == 0 else (0.0, sign)
    __result__ = json.dumps({"ok": True,
                             "forward_deg": math.degrees(math.atan2(v[1], v[0]))})
"""


def fix_facing_on_disk(hero_glb: Path, verbose: bool = True) -> None:
    """FACING GUARANTEE v2 (Phase 84): rotate the STATIC glb ON DISK to the
    hunter convention (+Y forward) before rigging. The in-session gate
    rotation does NOT survive the armature bake/export (verified: soldier
    and knight shipped un-rotated despite the gate reporting success), so
    the file itself must be fixed — exactly the manual path that made the
    hunter correct. Detection: shoulders = wide axis, toes point forward.
    Ambiguous silhouettes (T-pose arms) are left untouched."""
    import math
    import subprocess
    from app.mcp import registry
    code = _FACING_DETECT_FILE.replace("__GLB__", str(hero_glb).replace("\\", "/"))
    r = _call(registry, "facing-detect", code)
    if not (isinstance(r, dict) and r.get("ok")) or r.get("skipped"):
        if verbose:
            print(f"[bake] disk facing: skip ({r})")
        return
    rot = 90.0 - float(r["forward_deg"])
    while rot > 180: rot -= 360
    while rot < -180: rot += 360
    if abs(rot) < 1.0:
        return
    # AXIS-ONLY (2026-07-20): the toe-direction SIGN lied on armored boots
    # (soldier/knight read 'forward' while facing backward), so the automatic
    # pass only fixes SIDEWAYS cases (+/-90). A true 180 is corrected once by
    # hand (_apply_euler ... 0 0 180) and must never be auto-undone.
    if abs(abs(rot) - 180.0) < 45.0:
        if verbose:
            print(f"[bake] disk facing: {rot:.0f} deg is a SIGN call — skipping (axis-only policy)")
        return
    exe = r"C:\Program Files\Blender Foundation\Blender 5.1lender.exe"
    try:
        from app.main import get_setting
        exe = get_setting("blender_executable_path") or exe
    except Exception:
        pass
    subprocess.run([exe, "--background", "--python",
                    str(BACKEND_ROOT / "scripts" / "_apply_euler.py"), "--",
                    str(hero_glb), str(hero_glb), "0", "0", str(rot)],
                   capture_output=True, timeout=300)
    if verbose:
        print(f"[bake] disk facing: rotated {hero_glb.name} by {rot:.0f} deg")


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
    fix_facing_on_disk(hero_glb, verbose=verbose)   # Phase 84: fix the FILE
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {
        "filepath": str(hero_glb), "name": "Hero", "normalize_size": height_m,
        "ground_to_z0": True, "join": True, "orientation_fix": None})

    # BIPED FACING GATE (Phase 80): every biped rig must share ONE facing
    # convention or in-game heading is per-character roulette (soldier walked
    # sideways, knight backward, hunter fine). Detect facing from the BODY:
    # shoulders span the wide axis, the front-back axis is the narrow one,
    # and toes point forward. Rotate to the hunter-calibrated convention
    # (+Y forward). Skips when the silhouette is ambiguous (T-pose arms make
    # the extents near-equal, e.g. the legacy 'man' mesh).
    fg = _call(registry, "facing-gate", _FACING_GATE_CODE)
    if verbose and fg:
        print(f"[bake] facing gate: {fg.get('result') or fg}")

    # KEYSTONE (Phase 58, FS_RETOPO=1): clean quad topology before rigging.
    from . import retopo
    if retopo.enabled():
        rr = retopo.run("Hero")            # long-timeout bridge call
        if verbose:
            print(f"[bake] retopo: {rr}")
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
    # ORIENTATION GUARANTEE (Phase 57): verify the final animated artifact.
    ov = verify_glb_orientation(out_glb, "biped", verbose=verbose)
    return {"ok": True, "tracks": e.get("tracks"), "skin": a.get("skin"),
            "orientation": ov}
