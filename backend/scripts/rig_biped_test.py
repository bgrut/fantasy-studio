"""Phase 20 — BIPED motion module (humans / characters / robots).

Same proven engine as the quadruped (auto-detect parts → fit skeleton →
nearest-bone manual skin → procedural pose cycle), but a 2-leg + spine + 2-arm
+ head topology and a biped walk gait (legs alternate, arms counter-swing).

Two things this module gets right that the quadruped prototype did not:
  1) TEXTURE-SAFE — it never clears the hero's materials. If the mesh already
     carries a (multiview-textured) material we keep it; we only add a neutral
     fallback when the mesh has zero materials. So texturing is never mangled.
  2) ARBITRARY LENGTH — stride PERIOD (frames per gait cycle) is decoupled from
     total frame count. Pass `seconds`; the character keeps walking the whole
     clip. Longer video => longer continuous motion (no single-stride freeze).

Usage: python scripts/rig_biped_test.py <biped.glb> [out.mp4] [seconds]
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.mcp import registry, bridge  # noqa: E402

# __TOTAL__  = total animation frames (duration*fps)
# __STRIDE__ = frames per full gait cycle (keeps a natural cadence at any length)
RIG_CODE = r'''
import bpy, math
import numpy as np
from mathutils import Vector

o = bpy.data.objects.get("Hero")
o.rotation_mode = "XYZ"; bpy.context.view_layer.update()
bpy.context.view_layer.objects.active=o; o.select_set(True)
def _bake():   # bake current rotation into the mesh so the next step composes in world space
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False); bpy.context.view_layer.update()

# ── Stand the biped up: the TALLEST dimension must be Z (height) ───────────
# Each orientation decision is BAKED before the next so incremental euler edits
# don't compose in the wrong order (XYZ euler applies X-first, which silently
# undoes a stand-up+flip done in one euler).
d = o.dimensions
if d.z < d.y and d.y >= d.x:        # lying along Y → tip up about X
    o.rotation_euler.x = math.radians(90); _bake()
elif d.z < d.x and d.x > d.y:       # lying along X → tip up about Y
    o.rotation_euler.y = math.radians(90); _bake()
# HEAD-UP disambiguation: head+torso+arms carry far more surface area (vertices)
# than two thin legs, so the vertex CENTROID is biased toward the head end. If the
# centroid sits in the LOWER half, the head is down => flip 180° about X.
_Zc=np.array([(o.matrix_world@v.co).z for v in o.data.vertices], dtype=np.float64)
if float(_Zc.mean()) < (_Zc.min()+_Zc.max())/2.0:
    o.rotation_euler.x = math.radians(180); _bake()
# Face the camera: make the SHALLOW horizontal axis the facing (Y).
xs0=[(o.matrix_world@Vector(c)).x for c in o.bound_box]; ys0=[(o.matrix_world@Vector(c)).y for c in o.bound_box]
if (max(xs0)-min(xs0)) < (max(ys0)-min(ys0)):
    o.rotation_euler.z = math.radians(90); _bake()
dz=o.dimensions.z or 1.0; s=1.7/dz; o.scale=(s,s,s); bpy.context.view_layer.update()  # ~1.7 m human
zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]; o.location=(0,0,-min(zs)); bpy.context.view_layer.update()
bpy.context.view_layer.objects.active=o; o.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.context.view_layer.update()

me=o.data
V=np.array([list(v.co) for v in me.vertices], dtype=np.float64)
X,Y,Z=V[:,0],V[:,1],V[:,2]
xmin,xmax=X.min(),X.max(); ymin,ymax=Y.min(),Y.max(); zmin,zmax=Z.min(),Z.max()
cx=(xmin+xmax)/2; cy=(ymin+ymax)/2; H=zmax-zmin; W=xmax-xmin; Lf=ymax-ymin

hip_z   = zmin + 0.50*H
chest_z = zmin + 0.72*H
knee_z  = zmin + 0.26*H
foot_z  = zmin + 0.02*H
neck_z  = zmin + 0.82*H
elbow_z = zmin + 0.62*H
hand_z  = zmin + 0.46*H

# ── Detect L/R FEET (bottom verts, split by X) and SHOULDERS (upper verts) ──
def lr_centroids(mask, fallback_dx):
    out={}
    for side, xsel in (("L", X <= cx), ("R", X > cx)):
        m = mask & xsel
        if int(m.sum()) > 4:
            out[side]=(float(X[m].mean()), float(Y[m].mean()))
        else:
            out[side]=(cx + (fallback_dx if side=="R" else -fallback_dx), cy)
    return out
feet      = lr_centroids(Z < (zmin + 0.18*H), W*0.18)
shoulders = lr_centroids((Z > (zmin + 0.72*H)) & (Z < (zmin + 0.90*H)), W*0.30)

# ── Build the biped armature ───────────────────────────────────────────────
arm=bpy.data.armatures.new("Rig"); rig=bpy.data.objects.new("Rig",arm)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active=rig; rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb=arm.edit_bones
segs=[]   # (name, head, tail) deform bones for manual weighting
def mk(name,h,t,parent=None,conn=False,deform=True):
    b=eb.new(name); b.head=Vector(h); b.tail=Vector(t)
    if parent: b.parent=parent; b.use_connect=conn
    if deform: segs.append((name, np.array(h,dtype=np.float64), np.array(t,dtype=np.float64)))
    return b
root =mk("root",(cx,cy,hip_z),(cx,cy+0.05,hip_z),deform=False)
spine=mk("spine",(cx,cy,hip_z),(cx,cy,chest_z),root)
neck =mk("neck",(cx,cy,chest_z),(cx,cy,neck_z),spine)
headb=mk("head",(cx,cy,neck_z),(cx,cy,zmax),neck)
legs={}; arms={}
for side,(fx,fy) in feet.items():
    th=mk(f"thigh_{side}",(fx,fy,hip_z),(fx,fy,knee_z),root)
    sh=mk(f"shin_{side}", (fx,fy,knee_z),(fx,fy,foot_z),th,True)
    legs[side]=(th.name,sh.name)
for side,(sx,sy) in shoulders.items():
    ua=mk(f"uarm_{side}",(sx,sy,neck_z),(sx,sy,elbow_z),spine)
    fa=mk(f"farm_{side}",(sx,sy,elbow_z),(sx,sy,hand_z),ua,True)
    arms[side]=(ua.name,fa.name)
bpy.ops.object.mode_set(mode="OBJECT")

# ── Manual NEAREST-BONE skinning (point→segment distance) ──────────────────
names=[s[0] for s in segs]
dmat=np.empty((len(V), len(segs)), dtype=np.float64)
for bi,(nm,h,t) in enumerate(segs):
    seg=t-h; L2=max(float(seg@seg),1e-9)
    u=np.clip(((V-h)@seg)/L2, 0.0, 1.0)
    proj=h[None,:]+u[:,None]*seg[None,:]
    dmat[:,bi]=np.linalg.norm(V-proj, axis=1)
nearest=dmat.argmin(axis=1)
o.parent=rig
amod=o.modifiers.new("Armature","ARMATURE"); amod.object=rig
for bi,nm in enumerate(names):
    vg=o.vertex_groups.get(nm) or o.vertex_groups.new(name=nm)
    idx=np.where(nearest==bi)[0].tolist()
    if idx: vg.add(idx, 1.0, "REPLACE")

# ── BIPED WALK gait (legs alternate, arms counter-swing); loops for the whole
#    clip because t uses STRIDE as the period, not the total frame count ─────
sc=bpy.context.scene; TOTAL=__TOTAL__; STRIDE=__STRIDE__
sc.frame_start=1; sc.frame_end=TOTAL
bpy.context.view_layer.objects.active=rig; bpy.ops.object.mode_set(mode="POSE")
try: bpy.context.preferences.edit.keyframe_new_interpolation_type="LINEAR"  # 5.1-safe even cadence
except Exception: pass
pb=rig.pose.bones
for b in pb: b.rotation_mode="XYZ"
legph={"L":0.0,"R":math.pi}
A_LEG=0.42; A_ARM=0.38
for f in range(1,TOTAL+1):
    t=2*math.pi*(f-1)/STRIDE
    for side,(thn,shn) in legs.items():
        ph=legph[side]
        pb[thn].rotation_euler=(A_LEG*math.sin(t+ph),0,0); pb[thn].keyframe_insert("rotation_euler",frame=f)
        bend=-0.55*A_LEG*(1+math.cos(t+ph))          # knee tucks on swing-through
        pb[shn].rotation_euler=(bend,0,0); pb[shn].keyframe_insert("rotation_euler",frame=f)
    for side,(uan,fan) in arms.items():
        ph=legph["R" if side=="L" else "L"]          # arm opposes same-side leg
        pb[uan].rotation_euler=(A_ARM*math.sin(t+ph),0,0); pb[uan].keyframe_insert("rotation_euler",frame=f)
        pb[fan].rotation_euler=(-0.3*A_ARM*(1+math.cos(t+ph)),0,0); pb[fan].keyframe_insert("rotation_euler",frame=f)
    pb["root"].location=(0,0,0.03*abs(math.sin(t)))   # pelvis bob (2x cadence)
    pb["root"].keyframe_insert("location",frame=f)
    pb["spine"].rotation_euler=(0,0.04*math.sin(t),0) # gentle torso counter-rotate
    pb["spine"].keyframe_insert("rotation_euler",frame=f)
bpy.ops.object.mode_set(mode="OBJECT")

# ── TEXTURE-SAFE material: keep existing; only add neutral fallback if none ─
had_mat = len(o.data.materials) > 0
if not had_mat:
    mat=bpy.data.materials.new("BipedFallback"); mat.use_nodes=True
    mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value=(0.6,0.5,0.42,1)
    o.data.materials.append(mat)

# ── Stage: ground + sun + 3/4 camera ───────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=24, location=(cx,cy,foot_z))
gp=bpy.context.active_object; gm=bpy.data.materials.new("G"); gm.use_nodes=True
gm.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value=(0.22,0.22,0.24,1); gp.data.materials.append(gm)
sun=bpy.data.lights.new("S",type="SUN"); sun.energy=3.6; so=bpy.data.objects.new("S",sun)
bpy.context.scene.collection.objects.link(so); so.rotation_euler=(math.radians(52),0,math.radians(35))
cam=bpy.data.cameras.new("C"); cam.lens=50; co=bpy.data.objects.new("C",cam); bpy.context.scene.collection.objects.link(co)
span=max(H,W,Lf); midz=(zmin+zmax)/2
co.location=Vector((span*1.6, -span*2.4, midz+span*0.35))
look=Vector((cx,cy,midz))-co.location; co.rotation_euler=look.to_track_quat("-Z","Y").to_euler()
sc.camera=co; sc.render.engine="BLENDER_EEVEE"; sc.render.resolution_x=540; sc.render.resolution_y=720
try: sc.view_settings.view_transform="AgX"
except Exception: pass
__result__={"feet":list(feet.keys()),"arms":list(arms.keys()),"bones":len(pb),
            "kept_material":had_mat,"total":TOTAL,"stride":STRIDE}
'''


def main():
    hero = Path(sys.argv[1]).resolve()
    mp4 = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else (BACKEND / "renders" / "showcase" / "biped_walk.mp4")
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
    fps = 24
    total = int(round(seconds * fps))
    stride = 28  # frames per full walk cycle (~1.17 s cadence)

    bridge.connect(timeout=5)
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {"filepath": str(hero), "name": "Hero", "orientation_fix": None})
    code = RIG_CODE.replace("__TOTAL__", str(total)).replace("__STRIDE__", str(stride))
    print(registry.call("execute_python", {"code": code}), flush=True)

    out_dir = (BACKEND / "renders" / "_biped_anim")
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4.parent.mkdir(parents=True, exist_ok=True)
    registry.call("render_animation", {"output_dir": str(out_dir.as_posix()),
                                       "frame_start": 1, "frame_end": total, "fps": fps})
    registry.call("encode_video", {"frame_dir": str(out_dir.as_posix()),
                                   "mp4_path": str(mp4.as_posix()), "fps": fps})
    print(f"video -> {mp4}  exists: {mp4.exists()}  ({seconds}s, {total} frames)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
