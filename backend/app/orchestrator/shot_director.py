"""Phase 31 — Shot Director: multi-shot sequencing for videos.

Turns one continuous clip into a DIRECTED scene: a beat plan (establish →
coverage → close) drives N cameras bound to Blender TIMELINE MARKERS —
Blender's native cut mechanism, so the render pass switches cameras
automatically at each beat. One scene, one motion bake, one render pass,
real cinema cuts, zero extra render cost.

Deterministic beat plans per action (an optional LLM planner can layer on
later — determinism first, per the no-errors rule). Camera moves reuse the
Phase 25 cinematography vocabulary. Never raises — on any failure the
existing single-camera setup stays in place.
"""
import json
import os

# ── beat plans: (start_frac, end_frac, move) ─────────────────────────────────
# moves: wide (static establishing), track_front (3/4-front follow),
# track_side (profile follow), push_in (approach), close (tight follow),
# circle (arc around subject)
SHOT_PLANS = {
    "walk": [
        (0.00, 0.25, "wide"),
        (0.25, 0.70, "track_front"),
        (0.70, 1.00, "close"),
    ],
    "run": [
        (0.00, 0.20, "wide"),
        (0.20, 0.60, "track_side"),
        (0.60, 1.00, "track_front"),
    ],
    "fight": [
        (0.00, 0.25, "wide"),
        (0.25, 0.65, "circle"),
        (0.65, 1.00, "close"),
    ],
    "showcase": [
        (0.00, 0.45, "circle"),
        (0.45, 1.00, "push_in"),
    ],
}


def plan_shots(action: str, total_frames: int) -> list[dict]:
    plan = SHOT_PLANS.get(action) or SHOT_PLANS["walk"]
    shots = []
    for i, (s, e, move) in enumerate(plan):
        f0 = max(1, int(round(1 + s * (total_frames - 1))))
        f1 = int(round(1 + e * (total_frames - 1)))
        if f1 - f0 < 4:            # beats under 4 frames read as glitches
            continue
        shots.append({"name": f"shot{i+1}_{move}", "move": move,
                      "start": f0, "end": f1})
    return shots


_SHOTS_CODE = r'''
import bpy, math, json
from mathutils import Vector
import numpy as np
o=bpy.data.objects.get("__HERO__"); sc=bpy.context.scene
SHOTS=__SHOTS__; TOTAL=__TOTAL__; LENS=__LENS__
if o is None:
    __result__=json.dumps({"ok":False,"reason":"no hero"})
else:
    # ── hero path: evaluated centroid + bbox per frame (as cinematography) ──
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

    # clear prior shot rig (idempotent re-runs)
    for mk in list(sc.timeline_markers): sc.timeline_markers.remove(mk)
    for ob in [x for x in bpy.data.objects if x.name.startswith("ShotCam_")]:
        bpy.data.objects.remove(ob, do_unlink=True)

    made=[]
    for sh in SHOTS:
        cd=bpy.data.cameras.new("ShotCam_"+sh["name"]); cd.lens=LENS
        cam=bpy.data.objects.new("ShotCam_"+sh["name"],cd)
        sc.collection.objects.link(cam)
        f0,f1=sh["start"],sh["end"]; n=max(f1-f0,1)
        # WIDE: static camera placed ahead-side of the WHOLE travel, sees the
        # journey enter the frame. Others: per-frame follow like cinematography.
        if sh["move"]=="wide":
            mid=(c0+c1)*0.5
            pos=mid + fwd*span*4.2 + side*span*3.0 + Vector((0,0,span*0.9))
            for f in (f0,f1):
                sc.frame_set(f)
                hp=Vector(path[f-1][0].tolist())
                cam.location=pos
                look=Vector((hp.x,hp.y,hp.z))-cam.location
                cam.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
                cam.keyframe_insert("location",frame=f); cam.keyframe_insert("rotation_euler",frame=f)
        else:
            for i in range(f0,f1+1):
                t=(i-f0)/n; e=smooth(t)
                c,mn,mx=path[i-1]
                hp=Vector((float(c[0]),float(c[1]),float(c[2])))
                midz=(float(mn[2])+float(mx[2]))/2.0
                if sh["move"]=="track_front":
                    d=span*2.2
                    cam.location=hp+fwd*d*0.85+side*d*0.55+Vector((0,0,midz+span*0.30))
                    tgt=Vector((hp.x,hp.y,midz+span*0.12))
                elif sh["move"]=="track_side":
                    d=span*2.4
                    cam.location=hp+side*d+Vector((0,0,midz+span*0.25))
                    tgt=Vector((hp.x,hp.y,midz))
                elif sh["move"]=="close":
                    d=span*(1.5-0.25*e)          # tight and tightening
                    cam.location=hp+fwd*d*0.9+side*d*0.35+Vector((0,0,midz+span*0.38))
                    tgt=Vector((hp.x,hp.y,midz+span*0.30))   # face height
                elif sh["move"]=="circle":
                    ang=math.radians(70)*e - math.radians(35)
                    rot=Vector((fwd.x*math.cos(ang)-fwd.y*math.sin(ang),
                                fwd.x*math.sin(ang)+fwd.y*math.cos(ang),0))
                    cam.location=hp+rot*span*2.3+Vector((0,0,midz+span*0.25))
                    tgt=Vector((hp.x,hp.y,midz))
                else:  # push_in
                    d=span*(3.0-1.4*e)
                    cam.location=hp+fwd*d*0.7+side*d*0.7+Vector((0,0,midz+span*0.3))
                    tgt=Vector((hp.x,hp.y,midz+span*0.1))
                look=tgt-cam.location
                cam.rotation_euler=look.to_track_quat('-Z','Y').to_euler()
                cam.keyframe_insert("location",frame=i); cam.keyframe_insert("rotation_euler",frame=i)
        # bezier-ease the camera curves
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
        # THE CUT: a timeline marker bound to this camera — Blender switches
        # scene.camera here automatically during playback and render.
        mk=sc.timeline_markers.new(sh["name"], frame=sh["start"])
        mk.camera=cam
        made.append({"name":sh["name"],"move":sh["move"],"start":sh["start"],"end":sh["end"]})
    if made:
        sc.camera=bpy.data.objects.get("ShotCam_"+made[0]["name"])
    __result__=json.dumps({"ok":True,"shots":made,"markers":len(sc.timeline_markers)})
'''


def build_shot_sequence(runner, hero_name, action, total_frames,
                        lens=40.0, verbose=False):
    """Multi-camera cut sequence via marker binds. Returns True on success;
    never raises (single-camera setup stays on failure)."""
    if os.environ.get("FS_SHOTS", "1") == "0":
        return False
    shots = plan_shots(action, int(total_frames))
    if len(shots) < 2:
        return False               # one beat = no cuts = not worth replacing
    try:
        code = (_SHOTS_CODE.replace("__HERO__", hero_name)
                .replace("__SHOTS__", json.dumps(shots))
                .replace("__TOTAL__", str(int(total_frames)))
                .replace("__LENS__", f"{float(lens):.1f}"))
        res = runner.run("shot_director", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        info = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else None)
        if info and info.get("ok") and info.get("shots"):
            if verbose:
                cuts = " → ".join(s["move"] for s in info["shots"])
                print(f"[composer] shot director: {len(info['shots'])} shots ({cuts})")
            return True
        if verbose:
            print(f"[composer] shot director: not applied ({info})")
        return False
    except Exception as e:
        if verbose:
            print(f"[composer] shot director: skipped ({type(e).__name__}: {e})")
        return False
