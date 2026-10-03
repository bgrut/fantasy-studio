"""Rotation-transfer retargeting (2026-10-03).

WHY THIS REPLACES THE AIM RETARGET
----------------------------------
The aim retarget (mocap_retarget._RETARGET_CODE) pointed each of our bones
along the matching mocap bone's direction. A direction has no twist, so the
forearm and hand rolled wherever the minimal arc left them and elbows could
flip; and because the result looked wrong it grew corrections on top (a forced
trunk lean, an elbow bias, arm caps, a gaussian smooth), each of which made the
motion less like the actor's. Filmed beside a motion analyst's numbers, the
heroes moved like robots.

This is the method the industry uses (three-vrm, upf-gti/retargeting-threejs,
every engine's retargeter): transfer each joint's WORLD ROTATION relative to a
matched reference pose.

    Rs_b   the source bone's rest rotation (world, after the facing yaw)
    Rt_b   the target bone's rest rotation (world)
    C_b    the minimal rotation that turns the source bone's rest direction
           onto the target's (T-pose arms onto our A-pose arms, and so on)
    Wt(t) = Ws(t) . (C_b . Rs_b)^-1 . Rt_b

When the actor holds our rig's rest posture the target sits at rest; any
departure from it, twist included, is carried over exactly. World rotations
make the transfer indifferent to hierarchy differences (CMU's LowerBack, the
Xsens spine), so nothing is folded by hand. The pelvis carries its own
rotation and its bob; horizontal travel is removed (the game moves the body).

A cyclic clip is baked as exactly ONE gait cycle, its period found by
autocorrelating the thighs' left-minus-right swing, with the first frame
repeated at the end so the loop closes without a seam. Source frame rates are
read from each BVH (CMU 120 fps, 100STYLE 60 fps), so speeds stay true.
"""

RETARGET_ROT_CODE = r'''
BVHPATH=r"__BVH__"; FPS=__FPS__; TOTAL=__TOTAL__; CYCLIC=__CYCLIC__
LOF=__LOF__; HIF=__HIF__
LOOPBLEND=("__LOOPBLEND__"=="1")
FWDSIGN=float("__FWDSIGN__" if "__FWDSIGN__"[0] in "-0123456789." else "1")
import bpy, json, math
from mathutils import Vector, Matrix, Quaternion
rig=bpy.data.objects.get("HeroRig"); o=bpy.data.objects.get("__HERO__")
out={"ok":False}
if rig is None or o is None:
    out={"ok":False,"reason":"no rig/hero"}
else:
    # the source's own frame rate, from the file
    src_fps=120.0
    try:
        with open(BVHPATH,"r",errors="ignore") as fh:
            for ln in fh:
                if ln.strip().lower().startswith("frame time"):
                    src_fps=1.0/float(ln.split(":")[1]); break
    except Exception: pass
    pre=set(bpy.data.objects.keys())
    bpy.ops.import_anim.bvh(filepath=BVHPATH, global_scale=1.0, rotate_mode="NATIVE",
                            axis_forward="-Z", axis_up="Y", update_scene_fps=False, update_scene_duration=True)
    news=[bpy.data.objects[k] for k in bpy.data.objects.keys() if k not in pre]
    src=[x for x in news if x.type=="ARMATURE"][0]
    sc=bpy.context.scene
    # source joint names differ by dataset; the first that exists wins
    ALIASES={
      "hips":["Hips","hips","Pelvis","pelvis"],
      "spine":["Spine","spine","Spine1","Chest","LowerBack"],
      "chest":["Spine1","Spine2","Chest","chest","Spine3","UpperChest"],
      "neck":["Neck","neck","Neck1"],
      "head":["Head","head"],
      "clav_L":["LeftShoulder","LeftCollar","LShoulder"],
      "uparm_L":["LeftArm","LeftUpArm","LeftUpperArm"],
      "lowarm_L":["LeftForeArm","LeftLowArm","LeftLowerArm"],
      "lowarm_tw_L":["LeftForeArm","LeftLowArm","LeftLowerArm"],
      "hand_L":["LeftHand"],
      "clav_R":["RightShoulder","RightCollar","RShoulder"],
      "uparm_R":["RightArm","RightUpArm","RightUpperArm"],
      "lowarm_R":["RightForeArm","RightLowArm","RightLowerArm"],
      "lowarm_tw_R":["RightForeArm","RightLowArm","RightLowerArm"],
      "hand_R":["RightHand"],
      "upleg_L":["LeftUpLeg","LeftHip","LeftUpperLeg","LeftThigh"],
      "lowleg_L":["LeftLeg","LeftKnee","LeftLowerLeg","LeftShin"],
      "foot_L":["LeftFoot","LeftAnkle"],
      "upleg_R":["RightUpLeg","RightHip","RightUpperLeg","RightThigh"],
      "lowleg_R":["RightLeg","RightKnee","RightLowerLeg","RightShin"],
      "foot_R":["RightFoot","RightAnkle"],
    }
    sb=src.pose.bones
    # 100STYLE (Xsens) names its joints differently and one name collides:
    # its LeftShoulder is the upper arm, where CMU's is the collarbone. Its
    # four chest joints split as lower (spine) and upper (chest, where the
    # collars branch).
    if sb.get("LeftCollar") is not None and sb.get("LeftElbow") is not None:
        ALIASES.update({
          "spine":["Chest2","Chest"], "chest":["Chest4","Chest3"],
          "clav_L":["LeftCollar"], "uparm_L":["LeftShoulder"], "lowarm_L":["LeftElbow"],
          "lowarm_tw_L":["LeftElbow"], "hand_L":["LeftWrist"],
          "clav_R":["RightCollar"], "uparm_R":["RightShoulder"], "lowarm_R":["RightElbow"],
          "lowarm_tw_R":["RightElbow"], "hand_R":["RightWrist"],
          "upleg_L":["LeftHip"], "lowleg_L":["LeftKnee"], "foot_L":["LeftAnkle"],
          "upleg_R":["RightHip"], "lowleg_R":["RightKnee"], "foot_R":["RightAnkle"]})
    MAP={}
    for t,cands in ALIASES.items():
        if rig.pose.bones.get(t) is None: continue
        for c in cands:
            if sb.get(c) is not None: MAP[t]=c; break
    # order: parents before children, so each bone is set over a posed parent
    ORDER=[b.name for b in rig.data.bones if b.name in MAP]
    bvh_len=sc.frame_end
    try:
        _act=src.animation_data.action if src.animation_data else None
        if _act is not None: bvh_len=max(2,int(round(_act.frame_range[1])))
    except Exception: pass
    lo=max(1,int(LOF*bvh_len)); hi=max(lo+2,min(bvh_len-1,int(HIF*bvh_len)))
    step=src_fps/float(FPS)
    def setf(fr):
        i=int(math.floor(fr)); sc.frame_set(i, subframe=fr-i)
    def SW(n):   # source pose bone world matrix
        return src.matrix_world @ sb[n].matrix
    # ── facing: rotate the source about Z so its travel matches the hero's forward
    setf(lo); bpy.context.view_layer.update(); h0=SW(MAP.get("hips","Hips")).translation.copy()
    setf(hi); bpy.context.view_layer.update(); h1=SW(MAP.get("hips","Hips")).translation.copy()
    tr=(h1-h0); tr.z=0
    # units differ by dataset (100STYLE is in centimetres), so "travelled" is
    # measured in leg lengths; a clip that is not a cycle (idle, a swing)
    # always takes its forward from the pelvis, never from its drift
    setf(lo); bpy.context.view_layer.update()
    try: _sl=(SW(MAP["upleg_L"]).translation-SW(MAP["foot_L"]).translation).length
    except Exception: _sl=1.0
    if (not CYCLIC or tr.length < 0.25*_sl) and MAP.get("upleg_L") and MAP.get("upleg_R"):
        setf(lo); bpy.context.view_layer.update()
        lat=SW(MAP["upleg_L"]).translation-SW(MAP["upleg_R"]).translation; lat.z=0
        tr=lat.normalized().cross(Vector((0,0,1)))      # in-place clips: forward from the pelvis
    RB={b.name:b.matrix_local.to_3x3() for b in rig.data.bones}
    hero_fwd=(rig.matrix_world.to_3x3()@RB["foot_L"]@Vector((0,1,0))); hero_fwd.z=0
    # THE TOES SAY WHICH WAY IS FRONT (2026-10-03). The rig puts its forward
    # on +Y and the facing fix turns the mesh to match, but a mesh that still
    # faces the other way would walk its clips backwards (knees and elbows
    # bending the wrong way round), so the source is turned onto the mesh's
    # own front: the rigger's toe-against-heel reading about the shank's
    # centre when it is clear (a sword tip or a cape hem near the floor cannot
    # sway it), else the toe's reach about the ankle bone, which a foot
    # extends much further ahead of than behind. (The knight that first showed
    # this was a shrunken retopo body, see retopo.py; its facing was fine.)
    fwd_auto={"flipped":False}
    try:
        _rf=[float(v) for v in "__RIGFACE__".split(",")] if "__RIGFACE__"[0] in "0123456789." else None
        if _rf and min(_rf)>0 and max(_rf)/min(_rf)>1.5:
            fwd_auto.update(rig_toe=_rf[0], rig_heel=_rf[1], by="rig")
            if _rf[1]>_rf[0]:
                hero_fwd=-hero_fwd; fwd_auto["flipped"]=True
        else:
            _hf=hero_fwd.normalized()
            _ank={s:rig.matrix_world@rig.data.bones["foot_"+s].head_local for s in ("L","R")}
            _fr=[]
            for _o in bpy.data.objects:
                if _o.type!="MESH" or not any(m.type=="ARMATURE" and m.object==rig for m in _o.modifiers): continue
                _mw=_o.matrix_world
                for _v in _o.data.vertices:
                    _p=_mw@_v.co
                    for s,o in (("L","R"),("R","L")):
                        a=_ank[s]
                        if _p.z>a.z+0.02: continue
                        if (_p.xy-a.xy).length>(_p.xy-_ank[o].xy).length: continue
                        if (_p.xy-a.xy).length>0.4: continue
                        d=(_p-a); d.z=0
                        _fr.append(d.dot(_hf))
            if len(_fr)>40:
                _fr.sort(); n=len(_fr)
                front=_fr[int(0.98*(n-1))]; back=-_fr[int(0.02*(n-1))]
                fwd_auto.update(front=round(front,3), back=round(back,3), n=n, by="ankle")
                if back>front*1.2 and back>0.03:
                    hero_fwd=-hero_fwd; fwd_auto["flipped"]=True
    except Exception as _e:
        fwd_auto["error"]=str(_e)[:120]
    hero_fwd=hero_fwd*FWDSIGN
    yaw=0.0
    if hero_fwd.length>1e-4 and tr.length>1e-4:
        a=tr.normalized(); b=hero_fwd.normalized()
        yaw=math.atan2(a.cross(b).z, a.dot(b))
    Rz=Matrix.Rotation(yaw,3,'Z')
    # ── reference-pose alignment, per bone
    RW=rig.matrix_world.to_3x3()
    RWi=RW.inverted()
    srcW=src.matrix_world.to_3x3()
    Cal={}
    for t,s in MAP.items():
        Rs=Rz@srcW@src.data.bones[s].matrix_local.to_3x3()
        Rt=RW@RB[t]
        ds=(Rs@Vector((0,1,0))).normalized(); dt=(Rt@Vector((0,1,0))).normalized()
        C=ds.rotation_difference(dt).to_matrix()
        Cal[t]=( (C@Rs).inverted(), Rt )
    # ── the samples: one whole cycle for a cyclic clip
    win=hi-lo
    if CYCLIC and MAP.get("upleg_L") and MAP.get("upleg_R") and MAP.get("lowleg_L") and MAP.get("lowleg_R"):
        n_scan=int(min(win/step, 4.0*FPS))
        sig=[]
        for i in range(n_scan):
            setf(lo+i*step); bpy.context.view_layer.update()
            hw=(Rz@SW(MAP["hips"]).to_3x3()) if MAP.get("hips") else Matrix.Identity(3)
            hi_=hw.inverted()
            l=hi_@(Rz@(SW(MAP["lowleg_L"]).translation-SW(MAP["upleg_L"]).translation))
            r=hi_@(Rz@(SW(MAP["lowleg_R"]).translation-SW(MAP["upleg_R"]).translation))
            sig.append((l.x-r.x, l.y-r.y))
        ax=0 if sum(v[0]**2 for v in sig) > sum(v[1]**2 for v in sig) else 1
        x=[v[ax] for v in sig]; m=sum(x)/len(x); x=[v-m for v in x]
        best=None; bl=None
        for lag in range(int(0.45*FPS), min(len(x)-4, int(2.2*FPS))):
            c=sum(x[i]*x[i+lag] for i in range(len(x)-lag))/(len(x)-lag)
            if best is None or c>best: best=c; bl=lag
        N=bl if bl else TOTAL
    else:
        N=TOTAL
    N=max(4,int(N))
    for pb in rig.pose.bones: pb.rotation_mode="QUATERNION"
    sc.frame_start=1; sc.frame_end=N+1
    hips_rest_head=rig.pose.bones["hips"].bone.matrix_local.translation.copy() if rig.pose.bones.get("hips") else None
    # leg-length scale for the pelvis bob
    try:
        setf(lo); bpy.context.view_layer.update()
        sleg=(SW(MAP["upleg_L"]).translation-SW(MAP["foot_L"]).translation).length
        hleg=(rig.pose.bones["upleg_L"].bone.head_local-rig.pose.bones["foot_L"].bone.head_local).length
        scale=hleg/max(sleg,1e-6)
    except Exception:
        scale=1.0
    hz=[]; az=[]
    for i in range(N):
        setf(lo+i*step); bpy.context.view_layer.update()
        hz.append((Rz@SW(MAP["hips"]).translation).z if MAP.get("hips") else 0.0)
        if MAP.get("foot_L") and MAP.get("foot_R"):
            az.append(min(SW(MAP["foot_L"]).translation.z, SW(MAP["foot_R"]).translation.z))
    hzm=sum(hz)/max(len(hz),1)
    # THE PELVIS SITS AS HIGH AS THE SOURCE'S DOES (2026-10-03). The hips were
    # held at standing height with a +-8 cm bob, so a sneak's bent knees lifted
    # its feet 30 cm off the floor. Now the source hips' height above its own
    # planted ankles, measured against its standing (rest) height, sets ours
    # against our standing height: a crouch drops, a run keeps its flight.
    lift=None
    try:
        if az and MAP.get("hips") and rig.data.bones.get("foot_L") is not None:
            _az=sorted(az); g_src=_az[int(0.1*(len(_az)-1))]
            _sh=(src.matrix_world@src.data.bones[MAP["hips"]].head_local).z
            _sf=(src.matrix_world@src.data.bones[MAP["foot_L"]].head_local).z
            S_src=_sh-_sf
            foot_rest=rig.data.bones["foot_L"].head_local.z
            T_tgt=hips_rest_head.z-foot_rest
            if S_src>1e-6 and T_tgt>1e-6:
                lift=(g_src, S_src, foot_rest, T_tgt)
    except Exception:
        lift=None
    def sample(i):
        """the rig posed from source sample i, as local (rotation, location) per bone"""
        setf(lo+i*step); bpy.context.view_layer.update()
        zi=(Rz@SW(MAP["hips"]).translation).z if MAP.get("hips") else hzm
        got={}
        for t in ORDER:
            pb=rig.pose.bones[t]; s=MAP[t]
            inv,Rt=Cal[t]
            Wt=(Rz@SW(s).to_3x3())@inv@Rt
            M=RWi@Wt
            head=pb.matrix.translation.copy()
            if t=="hips" and hips_rest_head is not None:
                if lift:
                    g_src,S_src,foot_rest,T_tgt=lift
                    z=foot_rest+(zi-g_src)*T_tgt/S_src
                    z=max(foot_rest+0.35*T_tgt, min(hips_rest_head.z+0.35*T_tgt, z))
                    head=Vector((hips_rest_head.x,hips_rest_head.y,z))
                else:
                    head=hips_rest_head+Vector((0,0,max(-0.08,min(0.08,(zi-hzm)*scale))))
            pb.matrix=Matrix.Translation(head)@M.to_4x4()
            bpy.context.view_layer.update()
        # then exactly: our lowest ankle goes where the source's lowest ankle
        # is above its own ground (pelvis and leg proportions differ, which
        # left the walk 3-5 cm and the sneak 8 cm off the floor)
        if lift and MAP.get("foot_L") and MAP.get("foot_R") and rig.pose.bones.get("hips"):
            g_src,S_src,foot_rest,T_tgt=lift
            s_low=min(SW(MAP["foot_L"]).translation.z, SW(MAP["foot_R"]).translation.z)
            want=foot_rest+max(0.0,s_low-g_src)*T_tgt/S_src
            have=min(rig.pose.bones["foot_L"].head.z, rig.pose.bones["foot_R"].head.z)
            hp=rig.pose.bones["hips"]; m=hp.matrix.copy(); m.translation.z+=want-have
            hp.matrix=m; bpy.context.view_layer.update()
        for t in ORDER:
            pb=rig.pose.bones[t]
            got[t]=(pb.rotation_quaternion.copy(), pb.location.copy())
        return got
    def key(got, f):
        for t,(q,l) in got.items():
            pb=rig.pose.bones[t]
            pb.rotation_quaternion=q; pb.keyframe_insert("rotation_quaternion",frame=f)
            if t=="hips": pb.location=l; pb.keyframe_insert("location",frame=f)
    # A LOOP THAT IS NOT A CYCLE (2026-10-03): an idle has no period to find,
    # so its first K frames are crossfaded from the K frames that follow the
    # slice; the last frame then runs straight on into the first, no pop.
    K=min(int(0.25*N), int(0.6*FPS)) if (LOOPBLEND and not CYCLIC) else 0
    for i in range(N):
        g=sample(i)
        if i<K:
            w=(i+0.5)/K; w=w*w*(3-2*w)
            h=sample(N+i)
            g={t:(h[t][0].slerp(g[t][0],w) if h[t][0].dot(g[t][0])>=0 else (-h[t][0]).slerp(g[t][0],w),
                  h[t][1].lerp(g[t][1],w)) for t in g}
        key(g, 1+i)
    if CYCLIC:
        key(sample(0), N+1)         # the loop closes on its own first pose
    elif K:
        key(sample(N), N+1)         # = the blended first frame's source, so the wrap is seamless
    # quaternion sign continuity (q and -q are one rotation; interpolation is not)
    act=rig.animation_data.action if rig.animation_data else None
    if act:
        fcs=[]
        if hasattr(act,"fcurves") and len(getattr(act,"fcurves",[])):
            fcs=list(act.fcurves)
        else:
            for lay in getattr(act,"layers",[]):
                for st in lay.strips:
                    for cb in getattr(st,"channelbags",[]):
                        fcs+=list(cb.fcurves)
        from collections import defaultdict as _dd
        qg=_dd(dict)
        for fc in fcs:
            if fc.data_path.endswith("rotation_quaternion"): qg[fc.data_path][fc.array_index]=fc
        for dp,comp in qg.items():
            if len(comp)==4:
                f4=[comp[0],comp[1],comp[2],comp[3]]; n=len(f4[0].keyframe_points)
                for i in range(1,n):
                    d=sum(f4[k].keyframe_points[i].co[1]*f4[k].keyframe_points[i-1].co[1] for k in range(4))
                    if d<0:
                        for k in range(4): f4[k].keyframe_points[i].co[1]=-f4[k].keyframe_points[i].co[1]
                for fc in f4: fc.update()
    # tidy: the source armature and its action leave the scene
    for x in news:
        try:
            a=x.animation_data.action if x.animation_data else None
            bpy.data.objects.remove(x, do_unlink=True)
            if a is not None and a.users==0: bpy.data.actions.remove(a)
        except Exception: pass
    out={"ok":True,"frames":N+(1 if (CYCLIC or K) else 0),"loop_blend":K,"pelvis":("source" if lift else "bob"),"src_fps":round(src_fps,2),"mapped":len(MAP),
         "yaw_deg":round(math.degrees(yaw),1),"cyclic":bool(CYCLIC),"period_s":round(N/float(FPS),3),"fwd_auto":fwd_auto}
__result__=json.dumps(out)
'''
