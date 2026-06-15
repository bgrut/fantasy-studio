"""Phase 25 — cinematography.

A post-motion camera pass that replaces flat tracking shots with real camera
LANGUAGE: a 3/4-front tracking push-in for moving characters, a slow orbit for
showcases, a circling cover for fights. Reads the hero's BAKED path (evaluated
mesh centroid per frame) so it works regardless of how the motion was produced
(mocap, procedural gait, wheeled drive). Eased (smoothstep + Bezier f-curves)
so the moves read smooth and filmic.

Never raises — on any failure the existing motion-set camera is left in place.
"""
import json


# action/scene -> camera move
def pick_move(action, is_vehicle=False):
    if is_vehicle:
        return "orbit" if action == "showcase" else "chase"
    if action == "fight":
        return "circle"
    if action in ("walk", "run"):
        return "track_front"
    return "push_in"


_CINE_CODE = r'''
import bpy, math, json
from mathutils import Vector
import numpy as np
o=bpy.data.objects.get("__HERO__"); sc=bpy.context.scene
TOTAL=__TOTAL__; MODE="__MODE__"; LENS=__LENS__
if o is None:
    __result__=json.dumps({"ok":False,"reason":"no hero"})
else:
    cam=sc.camera
    if cam is None or cam.type!="CAMERA":
        cd=bpy.data.cameras.new("CineCam"); cam=bpy.data.objects.new("CineCam",cd)
        sc.collection.objects.link(cam); sc.camera=cam
    cam.data.lens=LENS
    # read the hero path: evaluated centroid + bbox per frame
    dg=bpy.context.evaluated_depsgraph_get()
    path=[]
    nv=len(o.data.vertices); step=max(1,nv//400)
    for f in range(1,TOTAL+1):
        sc.frame_set(f); oe=o.evaluated_get(dg)
        vs=np.array([list(oe.matrix_world@oe.data.vertices[i].co) for i in range(0,nv,step)])
        path.append((vs.mean(0), vs.min(0), vs.max(0)))
    c0=Vector(path[0][0].tolist()); c1=Vector(path[-1][0].tolist())
    fwd=Vector((c1.x-c0.x, c1.y-c0.y, 0.0))
    fwd=fwd.normalized() if fwd.length>1e-3 else Vector((0.0,1.0,0.0))
    side=Vector((-fwd.y, fwd.x, 0.0))
    H=float(path[0][2][2]-path[0][1][2]); span=max(H,1.0)
    def smooth(t): return t*t*(3-2*t)
    for i,(c,mn,mx) in enumerate(path):
        f=i+1; t=i/max(TOTAL-1,1); e=smooth(t)
        hp=Vector((float(c[0]),float(c[1]),float(c[2])))
        midz=(float(mn[2])+float(mx[2]))/2.0
        if MODE=="track_front":
            # 3/4 FRONT tracking with eased push-in — see the face/costume.
            d=span*(2.8-0.8*e)
            cam.location=hp + fwd*d*0.85 + side*d*0.55 + Vector((0,0,midz+span*0.30))
            tgt=Vector((hp.x,hp.y,midz+span*0.12))
        elif MODE=="circle":
            ang=math.radians(40)*math.sin(t*math.pi)   # gentle cover arc
            r=span*2.4
            rot=Vector((fwd.x*math.cos(ang)-fwd.y*math.sin(ang), fwd.x*math.sin(ang)+fwd.y*math.cos(ang),0))
            cam.location=hp + rot*r + Vector((0,0,midz+span*0.25))
            tgt=Vector((hp.x,hp.y,midz))
        elif MODE=="orbit":
            ang=2*math.pi*t; r=span*2.2
            cam.location=hp + Vector((r*math.cos(ang), r*math.sin(ang), midz+span*0.4))
            tgt=Vector((hp.x,hp.y,midz+span*0.1))
        else:  # push_in (static-ish subject)
            d=span*(3.0-1.0*e)
            cam.location=hp + fwd*d*0.7 + side*d*0.7 + Vector((0,0,midz+span*0.3))
            tgt=Vector((hp.x,hp.y,midz+span*0.1))
        look=tgt-cam.location
        cam.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
        cam.keyframe_insert("location",frame=f); cam.keyframe_insert("rotation_euler",frame=f)
    # Bezier easing on the camera curves for smooth, non-mechanical motion
    ad=cam.animation_data; act=ad.action if ad else None
    fcs=[]
    if act:
        if hasattr(act,"fcurves") and len(getattr(act,"fcurves",[])): fcs=list(act.fcurves)
        else:
            for lay in getattr(act,"layers",[]):
                for st in lay.strips:
                    for cb in getattr(st,"channelbags",[]): fcs+=list(cb.fcurves)
    for fc in fcs:
        for kp in fc.keyframe_points:
            kp.interpolation='BEZIER'; kp.handle_left_type='AUTO_CLAMPED'; kp.handle_right_type='AUTO_CLAMPED'
        fc.update()
    __result__=json.dumps({"ok":True,"mode":MODE,"frames":TOTAL})
'''


def build_cinematic_camera(runner, hero_name, action, total_frames,
                           is_vehicle=False, lens=40.0, verbose=False):
    """Replace the motion-set camera with a cinematic move. Returns True on
    success; never raises (leaves the existing camera on failure)."""
    import os
    if os.environ.get("FS_CINEMA", "1") == "0":
        return False
    mode = pick_move(action, is_vehicle)
    try:
        code = (_CINE_CODE.replace("__HERO__", hero_name)
                .replace("__TOTAL__", str(int(total_frames)))
                .replace("__MODE__", mode)
                .replace("__LENS__", f"{float(lens):.1f}"))
        res = runner.run("cinematography", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        info = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        if info and info.get("ok"):
            if verbose:
                print(f"[composer] cinematography: {mode} ({total_frames}f)")
            return True
        if verbose:
            print(f"[composer] cinematography: not applied ({info})")
        return False
    except Exception as e:
        if verbose:
            print(f"[composer] cinematography: skipped ({type(e).__name__}: {e})")
        return False
