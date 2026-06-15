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
for s in ("L","R"):
    a=(amax-smid) if s=="R" else (amin-smid); lg=(0.10*H) if s=="R" else (-0.10*H)
    cl=mk("clav_"+s,pt(0,0.80),pt(a*0.30,0.80),chest)
    ua=mk("uparm_"+s,pt(a*0.30,0.80),pt(a*0.62,0.80),cl)
    fa=mk("lowarm_"+s,pt(a*0.62,0.80),pt(a*0.92,0.80),ua); mk("hand_"+s,pt(a*0.92,0.80),pt(a*1.0,0.80),fa)
    th=mk("upleg_"+s,pt(lg,0.50),pt(lg,0.28),hips); sh=mk("lowleg_"+s,pt(lg,0.28),pt(lg,0.05),th)
    mk("foot_"+s,pt(lg,0.05),pt(lg,0.0,0.12),sh)
bpy.ops.object.mode_set(mode="OBJECT")
names=[s[0] for s in segs]; dmat=np.empty((len(V),len(segs)))
for bi,(nm,h,t) in enumerate(segs):
    seg=t-h; L2=max(float(seg@seg),1e-9); u=np.clip(((V-h)@seg)/L2,0,1)
    proj=h[None,:]+u[:,None]*seg[None,:]; dmat[:,bi]=np.linalg.norm(V-proj,axis=1)
K=min(4,dmat.shape[1]); idxK=np.argsort(dmat,axis=1)[:,:K]; dK=np.take_along_axis(dmat,idxK,1)
wK=1.0/np.maximum(dK,1e-6)**2; wK/=wK.sum(1,keepdims=True); wK[wK<0.03]=0; wK/=np.maximum(wK.sum(1,keepdims=True),1e-9)
amod=o.modifiers.new("HeroArmature","ARMATURE"); amod.object=rig
for bi,nm in enumerate(names):
    wv=(wK*(idxK==bi)).sum(1); lv=np.where(wv>1e-4)[0]
    if not len(lv): continue
    vg=o.vertex_groups.get(nm) or o.vertex_groups.new(name=nm)
    q=np.round(wv[lv]*63).astype(np.int64)
    for L in np.unique(q):
        if L: vg.add(lv[q==L].tolist(),float(L)/63.0,"REPLACE")
__result__=json.dumps({"ok":True,"H":round(float(H),3),"side":"X" if sx else "Y","bones":len(arm.bones)})
'''


# ── BLOCK 2: import BVH, frame-align, retarget (loop to TOTAL), camera, bake.
_RETARGET_CODE = r'''
BVHPATH=r"__BVH__"; TOTAL=__TOTAL__; FPS=__FPS__; TRACK=__TRACK__; WIDE=__WIDE__
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
    # sample source (loop clip to fill TOTAL output frames)
    samp=[]
    for i in range(TOTAL):
        sc.frame_set(1+(i*step)%max(1,bvh_len-1)); bpy.context.view_layer.update()
        hwm=swm("Hips")
        dirs={c:((swm(b).to_3x3()@Vector((0,1,0))).normalized() if swm(b) else None) for c,b in MAP.items()}
        samp.append((dirs, hwm.translation.copy(), hwm.to_3x3()))
    hip0=samp[0][1]
    slu=swm("LeftUpLeg"); slf=swm("LeftFoot")
    sleg=(Vector(slu.translation)-Vector(slf.translation)).length or 1.0
    hleg=(Vector(rig.pose.bones["upleg_L"].head)-Vector(rig.pose.bones["foot_L"].head)).length or 1.0
    scale=hleg/sleg
    # frame-align: yaw about Z so source left-right axis matches the hero's
    sl=(samp[0][0]["uparm_L"]-samp[0][0]["uparm_R"]).copy(); sl.z=0
    hl=((RB["uparm_L"]@Vector((0,1,0)))-(RB["uparm_R"]@Vector((0,1,0)))); hl.z=0
    if sl.length>1e-4 and hl.length>1e-4:
        sl.normalize(); hl.normalize()
        yaw=math.atan2(sl.cross(hl).z, sl.dot(hl)); Rz=Matrix.Rotation(yaw,3,'Z')
        samp=[({c:(Rz@v if v else None) for c,v in dd.items()}, hip0+Rz@(hp-hip0), Rz@hr) for dd,hp,hr in samp]
    # ROOT FACING: retarget the hips orientation so the WHOLE body (torso/head/
    # arms) faces the walk direction — without this the legs walk one way while
    # the upper body keeps the rest facing (the 'torso facing backward' bug).
    offh=RB["hips"]@samp[0][2].inverted()
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
        f=1+i; dirs,hp,hr=samp[i]
        dx=(hp.x-hip0.x)*scale; dy=(hp.y-hip0.y)*scale; dz=(hp.z-hip0.z)*scale*0.5
        rig.location=(base.x+dx,base.y+dy,base.z+dz); rig.keyframe_insert("location",frame=f)
        o.location=(baseo.x+dx,baseo.y+dy,baseo.z+dz); o.keyframe_insert("location",frame=f)
        bpy.context.view_layer.update()
        aim_full("hips", offh@hr, f)   # root faces the walk direction
        for c in ORDER:
            d=dirs.get(c)
            if d is None: continue
            aim(c,d); rig.pose.bones[c].keyframe_insert("rotation_quaternion",frame=f)
        path.append((base.x+dx, base.y+dy, baseo.z))
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
                .replace("__WIDE__", f"{float(wide):.2f}"))
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
