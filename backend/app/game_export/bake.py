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
    K = min(3, dmat.shape[1])
    idxK = np.argsort(dmat, axis=1)[:, :K]
    dK = np.take_along_axis(dmat, idxK, 1)
    wK = 1.0 / np.maximum(dK, 1e-6) ** 3
    wK /= wK.sum(1, keepdims=True)
    wK[wK < 0.12] = 0.0
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
    __result__ = json.dumps({"ok": True, "legs": list(LEGMAP.keys()), "bones": len(arm.bones),
                             "H": round(float(H), 3)})
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


def optimize_asset(src_glb: str | Path, out_glb: str | Path, target_tris: int = 45000,
                   height_m: float = 1.0, verbose: bool = True,
                   ref_png: str | Path | None = None) -> dict:
    """Decimate a raw TRELLIS GLB into a game-budget asset (NPCs/props). Raw
    heroes run ~400k tris; two of those wedge an iGPU. CPU-only via bridge.

    ref_png (2026-07-05 quality round): when the mesh carries NO baked texture
    (TripoSR CPU generations arrive with washed-out vertex colors → ghosts),
    project the SDXL reference photo onto it — the video pipeline's Phase 19
    projection, REUSED — so the exported GLB ships real colors. TRELLIS gens
    already have textures and are left untouched."""
    from app.mcp import registry, bridge
    out_glb = Path(out_glb); out_glb.parent.mkdir(parents=True, exist_ok=True)
    bridge.connect(timeout=8)
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {
        "filepath": str(src_glb), "name": "Hero", "normalize_size": height_m,
        "ground_to_z0": True, "join": True, "orientation_fix": None})
    if ref_png and Path(ref_png).exists() and not _glb_has_images(src_glb):
        try:
            from app.orchestrator.composer import _apply_reference_texture
            _apply_reference_texture(_RegistryRunner(registry), "Hero",
                                     str(ref_png), verbose=verbose)
            if verbose:
                print(f"[bake] projected reference texture onto {Path(src_glb).name}")
        except Exception as _te:
            if verbose:
                print(f"[bake] ref projection skipped ({type(_te).__name__}: {_te})")
    r = _call(registry, "optimize",
              _OPTIMIZE_CODE.replace("__TARGET__", str(int(target_tris)))
                            .replace("__OUT__", str(out_glb).replace("\\", "/")))
    if not (r and r.get("ok")):
        raise RuntimeError(f"optimize failed: {r}")
    if verbose:
        mb = out_glb.stat().st_size / 1e6
        print(f"[bake] optimized {Path(src_glb).name}: {r['tris'][0]:,} -> {r['tris'][1]:,} tris, {mb:.1f} MB")
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
    a = _call(registry, "quad_rig", _QUAD_RIG_CODE)
    if not (a and a.get("ok")):
        raise RuntimeError(f"quad rig failed: {a}")
    if verbose:
        print(f"[bake] quad rig: {a.get('bones')} bones, legs={a.get('legs')}")
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
    for name, total, stride, amp in (("walk", 40, 20, 0.50), ("run", 36, 12, 0.72)):
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
    return {"ok": True, "tracks": e.get("tracks")}


def ensure_playable(kind: str, verbose: bool = True) -> str | None:
    """Return a PLAYER-grade (rigged+animated) GLB for `kind`, baking it on
    first use from the static library asset. Bipeds get the CMU mocap set,
    quadrupeds the trot gait; vehicles aren't playable yet (returns None)."""
    from . import library
    from .generate import guess_pattern
    anim = BACKEND_ROOT / "assets" / "library" / f"{kind.lower().replace(' ', '_')}_anim.glb"
    if anim.exists():
        return str(anim)
    static = library.resolve(kind)
    if not static:
        return None
    try:                       # already rigged+animated (e.g. the man player)?
        from .verify_game import _glb_json
        g = _glb_json(Path(static))
        if g.get("skins") and g.get("animations"):
            return static
    except Exception:
        pass
    pattern = guess_pattern(kind)
    h = library.default_height(kind)
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
