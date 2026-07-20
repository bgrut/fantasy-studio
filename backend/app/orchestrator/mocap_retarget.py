"""Phase 24 — mocap retargeting.

Retarget a commercial-safe CMU BVH clip onto an auto-rigged TRELLIS biped, so
"walk"/"run"/"fight" actions use real motion-capture instead of procedural
gaits. Validated recipe (see docs/motion_library_plan.md):
  1. canonical 19-bone skeleton (landmark-placed) + manual nearest-bone skin
     (NO mesh parenting — armature modifier only);
  2. import BVH (axis -Z/Y), frame-align the source to the hero (yaw about Z);
  3. per frame, parents-before-children, aim each canonical bone along its
     mapped source bone's world direction (pb.matrix), keyframe; hips stays
     upright, forward translation = scaled source-hip displacement;
  4. loop the clip to fill the requested duration; side-tracking camera.

Never raises — any failure returns False and the composer falls back to the
procedural gait.
"""
import json
import os
from pathlib import Path

MOCAP_DIR = Path(__file__).resolve().parents[2] / "assets" / "mocap" / "cmu"

# action -> candidate clips (random/seeded pick — the "Fortnite emote" idea)
CATALOG = {
    "walk": ["02_01.bvh", "02_02.bvh", "07_01.bvh", "08_01.bvh", "35_01.bvh"],
    "run":  ["02_03.bvh", "09_01.bvh", "16_01.bvh"],
    "fight": ["02_05.bvh", "02_07.bvh"],
}
MOCAP_ACTIONS = set(CATALOG.keys())


def pick_clip(action, seed=0):
    clips = CATALOG.get(action) or CATALOG["walk"]
    return clips[int(seed) % len(clips)]


# ── BLOCK 1: canonical skeleton + manual skin (validated). __HERO__ substituted.
_AUTORIG_CODE = r'''
import bpy, json
import numpy as np
from mathutils import Vector
o=bpy.data.objects.get("__HERO__"); me=o.data; mw=o.matrix_world
V=np.array([list(mw@v.co) for v in me.vertices], dtype=np.float64)
X,Y,Z=V[:,0],V[:,1],V[:,2]
zmin,zmax=Z.min(),Z.max(); H=zmax-zmin; cx=(X.min()+X.max())/2; cy=(Y.min()+Y.max())/2
ab=(Z>zmin+0.68*H)&(Z<zmin+0.95*H)
ax=float(X[ab].max()-X[ab].min()) if ab.sum()>20 else (X.max()-X.min())
ay=float(Y[ab].max()-Y[ab].min()) if ab.sum()>20 else (Y.max()-Y.min())
sx = not (ay>=ax); SA=(X if sx else Y); smid=(cx if sx else cy)
def pt(so,zf,fwd=0.0):
    z=zmin+zf*H
    return (smid+so,cy+fwd,z) if sx else (cx+fwd,smid+so,z)
amax=float(SA.max()); amin=float(SA.min())
for old in ("HeroRig",):
    ob=bpy.data.objects.get(old)
    if ob: bpy.data.objects.remove(ob, do_unlink=True)
arm=bpy.data.armatures.new("HeroRig"); rig=bpy.data.objects.new("HeroRig",arm)
bpy.context.scene.collection.objects.link(rig); bpy.context.view_layer.objects.active=rig; rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT"); eb=arm.edit_bones; segs=[]
def mk(n,h,t,p=None):
    b=eb.new(n); b.head=Vector(h); b.tail=Vector(t)
    if p: b.parent=p; b.use_connect=False
    segs.append((n,np.array(h,dtype=np.float64),np.array(t,dtype=np.float64))); return b
hips=mk("hips",pt(0,0.50),pt(0,0.55)); spine=mk("spine",pt(0,0.55),pt(0,0.62),hips)
chest=mk("chest",pt(0,0.62),pt(0,0.72),spine); neck=mk("neck",pt(0,0.78),pt(0,0.86),chest)
mk("head",pt(0,0.86),pt(0,1.0),neck)
# ADAPTIVE ARM PLACEMENT — lay the arm bones along the REAL arm line
# (shoulder->hand), DETECTED from the mesh, instead of a flat horizontal T.
# TRELLIS bipeds come in an arms-out/down A-pose (hands sit ~0.18H BELOW the
# shoulders); a flat-T skeleton bound to drooping arms is exactly what sheared
# the geometry into "string arms". zf=height frac, latS=signed lateral offset.
_zf=(Z-zmin)/H; _latS=(SA-smid)
_sb=(_zf>=0.76)&(_zf<0.82)
_shoff=float(np.percentile(np.abs(_latS[_sb]),85)) if int(_sb.sum())>5 else 0.12*H
_shoff=max(_shoff,0.06*H)
for s in ("L","R"):
    sgn=-1.0 if s=="L" else 1.0; lg=sgn*0.10*H
    sh_lat=sgn*_shoff
    # detect the hand: lowest vertex that is clearly OUTBOARD on this side
    _side=(np.sign(_latS)==sgn)&(np.abs(_latS)>0.55*_shoff)&(_zf<0.80)&(_zf>0.28)
    if int(_side.sum())>8:
        _zz=Z[_side]; _jl=int(np.argmin(_zz))
        hand_lat=float(_latS[_side][_jl]); hand_zf=float((_zz[_jl]-zmin)/H)
        if abs(hand_lat)<0.5*_shoff or hand_zf>0.78 or hand_zf<0.30:
            hand_lat=sgn*0.40*H; hand_zf=0.52     # detection unreliable -> A-pose default
    else:
        hand_lat=sgn*0.40*H; hand_zf=0.52
    _al=lambda t: sh_lat+(hand_lat-sh_lat)*t      # lateral along shoulder->hand
    _az=lambda t: 0.80+(hand_zf-0.80)*t           # height  along shoulder->hand
    cl=mk("clav_"+s,pt(0,0.80),pt(sh_lat,0.80),chest)
    ua=mk("uparm_"+s,pt(_al(0.0),_az(0.0)),pt(_al(0.45),_az(0.45)),cl)
    fa=mk("lowarm_"+s,pt(_al(0.45),_az(0.45)),pt(_al(0.85),_az(0.85)),ua)
    mk("hand_"+s,pt(_al(0.85),_az(0.85)),pt(_al(1.0),_az(1.0)),fa)
    th=mk("upleg_"+s,pt(lg,0.50),pt(lg,0.28),hips); sh=mk("lowleg_"+s,pt(lg,0.28),pt(lg,0.05),th)
    mk("foot_"+s,pt(lg,0.05),pt(lg,0.0,0.12),sh)
bpy.ops.object.mode_set(mode="OBJECT")
amod=o.modifiers.get("HeroArmature") or o.modifiers.new("HeroArmature","ARMATURE"); amod.object=rig
# ── SMOOTH SKIN via a watertight VOXEL PROXY + bone-heat, weights transferred to
# the detail mesh. Bone-heat fails on raw TRELLIS shells (non-watertight -> empty
# weights), but a voxel remesh is closed/manifold so it succeeds, giving smooth
# deltoid/shoulder/elbow falloff instead of crude nearest-bone steps. Weights come
# back via data_transfer (nearest-interpolated). Falls back to manual nearest-bone
# on ANY problem, so this can never bind worse than before.
skin_mode="manual"
# RETRY LADDER (Phase 82): bone-heat goes SPARSE when the voxel proxy still
# has disconnected shells (armor plates, gear). Coarser voxels FUSE the
# shells into one watertight body, so step up until the heat solve covers.
for _vox in (max(0.012,H/110.0), max(0.02,H/70.0), max(0.03,H/45.0)):
    try:
        bpy.ops.object.select_all(action='DESELECT')
        proxy=o.copy(); proxy.data=o.data.copy(); proxy.name="HeroProxy"
        for _m in list(proxy.modifiers): proxy.modifiers.remove(_m)
        bpy.context.scene.collection.objects.link(proxy)
        _rm=proxy.modifiers.new("rm","REMESH"); _rm.mode='VOXEL'; _rm.voxel_size=_vox
        bpy.context.view_layer.objects.active=proxy; proxy.select_set(True)
        bpy.ops.object.modifier_apply(modifier="rm")
        bpy.ops.object.select_all(action='DESELECT')
        proxy.select_set(True); rig.select_set(True); bpy.context.view_layer.objects.active=rig
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')   # bone-heat onto the watertight proxy
        proxy.parent=None
        _cov=sum(1 for v in proxy.data.vertices if len(v.groups))
        if not len(proxy.vertex_groups) or _cov < 0.6*len(proxy.data.vertices):
            raise RuntimeError("boneheat_sparse")
        for vg in proxy.vertex_groups:
            if vg.name not in o.vertex_groups: o.vertex_groups.new(name=vg.name)
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True); proxy.select_set(True); bpy.context.view_layer.objects.active=proxy
        bpy.ops.object.data_transfer(data_type='VGROUP_WEIGHTS', vert_mapping='POLYINTERP_NEAREST',
                                     layers_select_src='ALL', layers_select_dst='NAME')
        skin_mode="voxel_proxy(v%.3f)"%_vox
    except Exception as _e:
        skin_mode="manual("+type(_e).__name__+")"
        for _g in list(o.vertex_groups):      # half-written groups poison retry
            o.vertex_groups.remove(_g)
    finally:
        _p=bpy.data.objects.get("HeroProxy")
        if _p: bpy.data.objects.remove(_p, do_unlink=True)
        bpy.ops.object.select_all(action='DESELECT')
    if skin_mode.startswith("voxel"): break
if not skin_mode.startswith("voxel"):
    # ── MANUAL nearest-bone fallback (proven). SAME-SIDE limb constraint: a vertex
    # clearly on one side of the centreline must NOT bind to the opposite side's
    # leg/arm bones (else thin close-set legs merge into a blob under stride).
    names=[s[0] for s in segs]; dmat=np.empty((len(V),len(segs)))
    for bi,(nm,h,t) in enumerate(segs):
        seg=t-h; L2=max(float(seg@seg),1e-9); u=np.clip(((V-h)@seg)/L2,0,1)
        proj=h[None,:]+u[:,None]*seg[None,:]; dmat[:,bi]=np.linalg.norm(V-proj,axis=1)
    _mar=0.05*H
    for bi,nm in enumerate(names):
        if nm.endswith("_L"):       dmat[SA>smid+_mar, bi]=1e9
        elif nm.endswith("_R"):     dmat[SA<smid-_mar, bi]=1e9
    K=min(4,dmat.shape[1]); idxK=np.argsort(dmat,axis=1)[:,:K]; dK=np.take_along_axis(dmat,idxK,1)
    wK=1.0/np.maximum(dK,1e-6)**2; wK/=wK.sum(1,keepdims=True); wK[wK<0.03]=0; wK/=np.maximum(wK.sum(1,keepdims=True),1e-9)
    # densify: W (nv x nbones)
    W=np.zeros((len(V), len(segs)), dtype=np.float64)
    np.put_along_axis(W, idxK, wK, axis=1)
    # LAPLACIAN WEIGHT SMOOTHING: hard nearest-bone steps tear thin strands in
    # motion (the 'strings'). Diffuse weights over mesh adjacency so joints get
    # bone-heat-like smooth falloff; re-assert the same-side mask each pass so
    # L/R never bleed across the centreline.
    ecount=len(me.edges)
    ev=np.empty(ecount*2, dtype=np.int64); me.edges.foreach_get("vertices", ev)
    ev=ev.reshape(-1,2)
    nb_acc=np.zeros_like(W); nb_cnt=np.zeros(len(V))
    np.add.at(nb_cnt, ev[:,0], 1); np.add.at(nb_cnt, ev[:,1], 1)
    nb_cnt=np.maximum(nb_cnt,1)[:,None]
    side_mask=np.ones_like(W)
    for bi,nm in enumerate(names):
        if nm.endswith("_L"):   side_mask[SA>smid+_mar, bi]=0.0
        elif nm.endswith("_R"): side_mask[SA<smid-_mar, bi]=0.0
    for _it in range(8):
        nb_acc[:]=0.0
        np.add.at(nb_acc, ev[:,0], W[ev[:,1]])
        np.add.at(nb_acc, ev[:,1], W[ev[:,0]])
        W=0.55*W+0.45*(nb_acc/nb_cnt)
        W*=side_mask
        W/=np.maximum(W.sum(1,keepdims=True),1e-9)
    W[W<0.05]=0.0
    W/=np.maximum(W.sum(1,keepdims=True),1e-9)
    for bi,nm in enumerate(names):
        wv=W[:,bi]; lv=np.where(wv>1e-4)[0]
        if not len(lv): continue
        vg=o.vertex_groups.get(nm) or o.vertex_groups.new(name=nm)
        q=np.round(wv[lv]*63).astype(np.int64)
        for L in np.unique(q):
            if L: vg.add(lv[q==L].tolist(),float(L)/63.0,"REPLACE")
__result__=json.dumps({"ok":True,"H":round(float(H),3),"side":"X" if sx else "Y","bones":len(arm.bones),"skin":skin_mode})
'''


# ── BLOCK 2: import BVH, frame-align, retarget (loop to TOTAL), camera, bake.
_RETARGET_CODE = r'''
BVHPATH=r"__BVH__"; TOTAL=__TOTAL__; FPS=__FPS__; TRACK=__TRACK__; WIDE=__WIDE__
# INPLACE: game-export mode — no root/object translation keyframes (the game's
# physics controller moves the character) and no rest ease-in (clips must loop
# cleanly). False for the video pipeline = behavior unchanged.
INPLACE=__INPLACE__
import bpy, json, math
import numpy as np
from mathutils import Vector, Matrix
rig=bpy.data.objects.get("HeroRig"); o=bpy.data.objects.get("__HERO__")
if rig is None or o is None:
    __result__=json.dumps({"ok":False,"reason":"no rig/hero"})
else:
    pre=set(bpy.data.objects.keys())
    bpy.ops.import_anim.bvh(filepath=BVHPATH, global_scale=1.0, rotate_mode="NATIVE",
                            axis_forward="-Z", axis_up="Y", update_scene_fps=False, update_scene_duration=True)
    src=[bpy.data.objects[k] for k in bpy.data.objects.keys() if k not in pre and bpy.data.objects[k].type=="ARMATURE"][0]
    MAP={"spine":"Spine","chest":"Spine1","neck":"Neck","head":"Head",
     "clav_L":"LeftShoulder","uparm_L":"LeftArm","lowarm_L":"LeftForeArm","hand_L":"LeftHand",
     "clav_R":"RightShoulder","uparm_R":"RightArm","lowarm_R":"RightForeArm","hand_R":"RightHand",
     "upleg_L":"LeftUpLeg","lowleg_L":"LeftLeg","foot_L":"LeftFoot",
     "upleg_R":"RightUpLeg","lowleg_R":"RightLeg","foot_R":"RightFoot"}
    ORDER=["spine","chest","neck","head","clav_L","uparm_L","lowarm_L","hand_L",
     "clav_R","uparm_R","lowarm_R","hand_R","upleg_L","lowleg_L","foot_L","upleg_R","lowleg_R","foot_R"]
    sc=bpy.context.scene
    bvh_len=sc.frame_end; step=max(1,int(round(120.0/FPS)))
    RB={b.name:b.matrix_local.to_3x3() for b in rig.data.bones}
    def swm(n):
        pb=src.pose.bones.get(n); return (src.matrix_world@pb.matrix) if pb else None
    # CLEAN WALK WINDOW: CMU clips open with a calibration/settle pose (feet
    # together, arms out — a near-T-pose) before the walk establishes. Looping
    # the whole clip to fill TOTAL frames re-samples that startup pose and the
    # character goes airborne/legs-together mid-shot. Trim leading calibration +
    # trailing settle and forward-loop ONLY within the clean window.
    lo=max(1,int(0.06*bvh_len)); hi=max(lo+2, bvh_len-int(0.02*bvh_len)); win=max(1,hi-lo)
    # net forward travel over the clean window (robust frame-align, immune to the loop)
    sc.frame_set(lo); bpy.context.view_layer.update(); hip_lo=swm("Hips").translation.copy()
    sc.frame_set(hi); bpy.context.view_layer.update(); hip_hi=swm("Hips").translation.copy()
    samp=[]
    for i in range(TOTAL):
        sc.frame_set(lo+(i*step)%win); bpy.context.view_layer.update()
        dirs={c:((swm(b).to_3x3()@Vector((0,1,0))).normalized() if swm(b) else None) for c,b in MAP.items()}
        samp.append((dirs, swm("Hips").translation.copy()))
    hip0=samp[0][1]
    slu=swm("LeftUpLeg"); slf=swm("LeftFoot")
    sleg=(Vector(slu.translation)-Vector(slf.translation)).length or 1.0
    hleg=(Vector(rig.pose.bones["upleg_L"].head)-Vector(rig.pose.bones["foot_L"].head)).length or 1.0
    scale=hleg/sleg
    # FRAME-ALIGN by FORWARD — keep the body at the REFERENCE orientation (like
    # the procedural gait / animals / cars) and rotate the MOCAP so the clip's
    # travel maps to the hero's reference forward (the foot-bone direction). The
    # character then walks in the direction it already FACES; we do NOT re-orient
    # the torso (re-orienting it was what flipped the torso vs the legs/feet).
    Rz=Matrix.Identity(3)
    hero_fwd=(RB["foot_L"]@Vector((0,1,0))); hero_fwd.z=0
    src_tr=(hip_hi-hip_lo).copy(); src_tr.z=0
    if hero_fwd.length>1e-3 and src_tr.length>1e-3:
        hero_fwd.normalize(); src_tr.normalize()
        yaw=math.atan2(src_tr.cross(hero_fwd).z, src_tr.dot(hero_fwd)); Rz=Matrix.Rotation(yaw,3,'Z')
        samp=[({c:(Rz@v if v else None) for c,v in dd.items()}, hip0+Rz@(hp-hip0)) for dd,hp in samp]
    net=Rz@(hip_hi-hip_lo)   # per-cycle forward travel (in aligned space) — keeps
                             # world translation CONTINUOUS across the loop wrap.
    for pb in rig.pose.bones: pb.rotation_mode="QUATERNION"
    sc.frame_start=1; sc.frame_end=TOTAL
    try: bpy.context.preferences.edit.keyframe_new_interpolation_type="LINEAR"
    except Exception: pass
    base=rig.location.copy(); baseo=o.location.copy()
    def aim(c, dirv):
        pb=rig.pose.bones[c]; head=pb.matrix.translation.copy(); rest=pb.bone.matrix_local
        d0=(rest.to_3x3()@Vector((0,1,0))).normalized()
        basis=(d0.rotation_difference(dirv).to_matrix()@rest.to_3x3())
        pb.matrix=Matrix.Translation(head)@basis.to_4x4(); bpy.context.view_layer.update()
    def aim_full(name, R3, frame):
        pb=rig.pose.bones[name]; head=pb.matrix.translation.copy()
        pb.matrix=Matrix.Translation(head)@R3.to_4x4(); bpy.context.view_layer.update()
        pb.keyframe_insert("rotation_quaternion",frame=frame)
    path=[]
    for i in range(TOTAL):
        f=1+i; dirs,hp=samp[i]
        cyc=(i*step)//win   # completed loop cycles -> add net travel so we keep walking forward
        dx=(hp.x-hip0.x+cyc*net.x)*scale; dy=(hp.y-hip0.y+cyc*net.y)*scale; dz=(hp.z-hip0.z)*scale*0.5
        if not INPLACE:
            rig.location=(base.x+dx,base.y+dy,base.z+dz); rig.keyframe_insert("location",frame=f)
            o.location=(baseo.x+dx,baseo.y+dy,baseo.z+dz); o.keyframe_insert("location",frame=f)
        bpy.context.view_layer.update()
        # hips stays at REST orientation (= reference facing); we do NOT retarget
        # the root rotation, so the torso never flips away from the reference.
        for c in ORDER:
            d=dirs.get(c)
            # ARM STRAIGHTEN: the T-pose->arms-down retarget over-bends the elbow
            # into a stubby 'T-rex' pose. Bias the forearm/hand toward the UPPER
            # arm direction so the arm swings as a natural near-straight line.
            if c in ("lowarm_L","hand_L") and dirs.get("uparm_L") is not None and d is not None:
                d=(dirs["uparm_L"]*0.7+d*0.3).normalized()
            elif c in ("lowarm_R","hand_R") and dirs.get("uparm_R") is not None and d is not None:
                d=(dirs["uparm_R"]*0.7+d*0.3).normalized()
            if d is None: continue
            aim(c,d); rig.pose.bones[c].keyframe_insert("rotation_quaternion",frame=f)
        path.append((base.x+dx, base.y+dy, baseo.z))
    # DE-CHOPPER: gaussian-smooth the baked bone curves to kill the small
    # frame-to-frame twist jitter the per-bone aim introduces, so the motion
    # reads smooth/continuous instead of choppy. (Keyframes are continuous
    # quaternions from pb.matrix, so component-wise smoothing is safe.)
    act=rig.animation_data.action if rig.animation_data else None
    if act:
        fcs=[]
        if hasattr(act,"fcurves") and len(getattr(act,"fcurves",[])):
            fcs=list(act.fcurves)
        else:   # Blender 4.4+ slotted actions
            for lay in getattr(act,"layers",[]):
                for st in lay.strips:
                    for cb in getattr(st,"channelbags",[]):
                        fcs+=list(cb.fcurves)
        # group quaternion components per bone so we can fix SIGN CONTINUITY (q and
        # -q are the same rotation; smoothing components across a sign flip would
        # corrupt the pose — this is what threw the arms up). Flip negatives first.
        from collections import defaultdict as _dd
        qgrp=_dd(dict); flat=[]
        for fc in fcs:
            if fc.data_path.endswith("rotation_quaternion"):
                qgrp[fc.data_path][fc.array_index]=fc
            else:
                flat.append(fc)
        for dp,comp in qgrp.items():
            if len(comp)==4:
                f=[comp[0],comp[1],comp[2],comp[3]]; n=len(f[0].keyframe_points)
                for i in range(1,n):
                    dot=sum(f[k].keyframe_points[i].co[1]*f[k].keyframe_points[i-1].co[1] for k in range(4))
                    if dot<0:
                        for k in range(4): f[k].keyframe_points[i].co[1]=-f[k].keyframe_points[i].co[1]
            flat.extend(comp.values())
        ker=(0.06,0.24,0.40,0.24,0.06)
        for fc in flat:
            kp=fc.keyframe_points; n=len(kp)
            if n<5: continue
            v=[p.co[1] for p in kp]
            for i in range(2,n-2):
                kp[i].co[1]=ker[0]*v[i-2]+ker[1]*v[i-1]+ker[2]*v[i]+ker[3]*v[i+1]+ker[4]*v[i+2]
            fc.update()
        # REST EASE-IN: frame 1 starts at the mesh's natural REST pose (identity
        # rotation = the clean A-pose the rig was built in) and eases into the
        # mocap over EASE frames via smoothstep. Kills the frame-1 "pop" into a
        # mid-stride/broken-arm pose. Quaternions only (root translation already
        # starts at base, so the body just accelerates forward as the pose eases).
        from mathutils import Quaternion as _Q
        EASE=0 if INPLACE else min(8, max(2, TOTAL//6))   # looping game clips: no ease
        def _ss(x): return x*x*(3-2*x)
        _qg={}
        for fc in flat:
            if fc.data_path.endswith("rotation_quaternion"):
                _qg.setdefault(fc.data_path,{})[fc.array_index]=fc
        for dp,comp in _qg.items():
            if len(comp)!=4: continue
            f0,f1,f2,f3=comp[0],comp[1],comp[2],comp[3]; n=len(f0.keyframe_points)
            for i in range(min(EASE,n)):
                w=_ss(i/max(EASE-1,1))
                q=_Q((f0.keyframe_points[i].co[1],f1.keyframe_points[i].co[1],
                      f2.keyframe_points[i].co[1],f3.keyframe_points[i].co[1]))
                q.normalize()
                qb=_Q().slerp(q,w)
                f0.keyframe_points[i].co[1]=qb.w; f1.keyframe_points[i].co[1]=qb.x
                f2.keyframe_points[i].co[1]=qb.y; f3.keyframe_points[i].co[1]=qb.z
            for fc in comp.values(): fc.update()
    # FOOT GROUND-PLANT (#119, 2026-07-07): evaluate the baked clip and key the
    # ROOT Z so feet neither sink below the ground nor hover. Penetration is
    # always fully corrected; float is pulled down gently (capped at 3.5% of
    # height) so run flight-phases survive. Root-only correction — bone curves
    # stay untouched, so this can NEVER bend a pose (no new limb bugs by
    # construction; the three historical retarget bugs live in bone space).
    try:
        zmins=[]
        for i in range(TOTAL):
            bpy.context.scene.frame_set(1+i)
            m=None
            for fb in ("foot_L","foot_R"):
                pbf=rig.pose.bones.get(fb)
                if pbf is None: continue
                wz=(rig.matrix_world@pbf.tail).z
                m=wz if m is None else min(m,wz)
            zmins.append(0.0 if m is None else m)
        tolf=0.02*H; capf=0.035*H; fixed=0
        for i in range(TOTAL):
            m=zmins[i]; dzf=0.0
            if m<0.0: dzf=-m
            elif m>tolf: dzf=-min(m-tolf,capf)
            if abs(dzf)>1e-5:
                bpy.context.scene.frame_set(1+i)
                rig.location.z=rig.matrix_world.translation.z+dzf
                rig.keyframe_insert("location",index=2,frame=1+i)
                o.location.z=o.matrix_world.translation.z+dzf
                o.keyframe_insert("location",index=2,frame=1+i)
                fixed+=1
        bpy.context.scene.frame_set(1)
    except Exception:
        pass   # grounding is polish — a failure must never kill the bake
    bpy.data.objects.remove(src, do_unlink=True)
    # ── side-tracking camera following the walk
    cam=sc.camera
    if TRACK and cam is not None and len(path)>1:
        zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]
        midz=base.z+0.5*(max(zs)-min(zs)); span=max(1.2,(max(zs)-min(zs)))
        p0=Vector(path[0]); p1=Vector(path[-1]); fwd=(p1-p0)
        fwd=fwd.normalized() if fwd.length>1e-3 else Vector((0,1,0))
        side=Vector((-fwd.y,fwd.x,0))
        for i in range(TOTAL):
            f=1+i; hp=Vector(path[i])
            cam.location=hp+side*span*2.4*WIDE+Vector((0,0,midz+span*0.35))
            look=Vector((hp.x,hp.y,midz))-cam.location
            cam.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
            cam.keyframe_insert("location",frame=f); cam.keyframe_insert("rotation_euler",frame=f)
    __result__=json.dumps({"ok":True,"total":TOTAL,"scale":round(float(scale),3),"clip_frames":bvh_len})
'''


def _run(runner, label, code, verbose):
    res = runner.run(label, "execute_python", {"code": code}, critical=False)
    raw = res.get("result") if isinstance(res, dict) else None
    try:
        info = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
    except Exception:
        info = None
    return info


def build_mocap_motion(runner, hero_name, action, total_frames, fps=24,
                       track_camera=True, wide=1.0, seed=0, verbose=False):
    """Auto-rig the biped hero + retarget a CMU clip for `action`. Returns True
    on success. Falls back (returns False) on any problem so the composer can
    use the procedural gait."""
    if os.environ.get("FS_MOCAP", "1") == "0":
        return False
    action = action if action in MOCAP_ACTIONS else "walk"
    clip = pick_clip(action, seed)
    bvh = MOCAP_DIR / clip
    if not bvh.exists():
        if verbose:
            print(f"[composer] mocap: clip missing ({bvh.name}) — falling back")
        return False
    try:
        a = _run(runner, "mocap_autorig", _AUTORIG_CODE.replace("__HERO__", hero_name), verbose)
        if not (a and a.get("ok")):
            if verbose:
                print(f"[composer] mocap: autorig failed ({a}) — falling back")
            return False
        code = (_RETARGET_CODE
                .replace("__HERO__", hero_name)
                .replace("__BVH__", str(bvh).replace("\\", "/"))
                .replace("__TOTAL__", str(int(total_frames)))
                .replace("__FPS__", str(int(fps)))
                .replace("__TRACK__", "True" if track_camera else "False")
                .replace("__WIDE__", f"{float(wide):.2f}")
                .replace("__INPLACE__", "False"))   # video path: always False
        r = _run(runner, "mocap_retarget", code, verbose)
        if r and r.get("ok"):
            if verbose:
                print(f"[composer] mocap: '{action}' via {clip} "
                      f"({a.get('bones')} bones, {total_frames}f, scale {r.get('scale')})")
            return True
        if verbose:
            print(f"[composer] mocap: retarget failed ({r}) — falling back")
        return False
    except Exception as e:
        if verbose:
            print(f"[composer] mocap: error ({type(e).__name__}: {e}) — falling back")
        return False
