"""Phase 20 prototype: auto-rig a generated QUADRUPED mesh + a procedural
walk/trot cycle. Validates the hardest parts (armature fit + auto-skin + bone
animation deforming the mesh). Renders a few frames across the gait so we can
see the legs actually move.

Usage: python scripts/rig_walk_test.py <quadruped.glb> [out_prefix]
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.mcp import registry, bridge  # noqa: E402

# Build rig + skin + bake a trot cycle, then render `nframes` across the cycle.
RIG_CODE = r'''
import bpy, math
import numpy as np
from mathutils import Vector

o = bpy.data.objects.get("Hero")
o.rotation_mode = "XYZ"
bpy.context.view_layer.objects.active=o; o.select_set(True); bpy.context.view_layer.update()
def _bake():
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False); bpy.context.view_layer.update()
# ── ROBUST quadruped orientation (raw TripoSG meshes import in arbitrary poses;
#    the naive "assume upright" version exploded the dog / nose-dived the cat /
#    laid the fox flat). A standing quadruped has: length(longest)=Y, height=Z,
#    width(smallest)=X. Bake each 90° step so eulers compose in world space. ──
d=o.dimensions
# 1) longest extent → Y (body length, nose-to-tail)
longest=max(range(3), key=lambda i:(d.x,d.y,d.z)[i])
if longest==0: o.rotation_euler.z=math.radians(90); _bake()      # X→Y
elif longest==2: o.rotation_euler.x=math.radians(90); _bake()    # Z→Y
# 2) of the two remaining axes, the TALLER (height) → Z, smaller (width) → X
if o.dimensions.x > o.dimensions.z: o.rotation_euler.y=math.radians(90); _bake()  # X→Z
# 3) FEET-DOWN: body+head carry far more surface area than four thin legs, so the
#    vertex centroid sits in the UPPER half when upright. If it's in the lower
#    half the animal is belly-up → flip 180° about Y (keeps the length axis).
_Zc=np.array([(o.matrix_world@v.co).z for v in o.data.vertices], dtype=np.float64)
if float(_Zc.mean()) < (_Zc.min()+_Zc.max())/2.0:
    o.rotation_euler.y=math.radians(180); _bake()
dz=o.dimensions.z or 1.0; s=1.0/dz; o.scale=(s,s,s); bpy.context.view_layer.update()
zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]; o.location=(0,0,-min(zs)); bpy.context.view_layer.update()
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.context.view_layer.update()

me=o.data
V=np.array([list(v.co) for v in me.vertices], dtype=np.float64)
X,Y,Z=V[:,0],V[:,1],V[:,2]
xmin,xmax=X.min(),X.max(); ymin,ymax=Y.min(),Y.max(); zmin,zmax=Z.min(),Z.max()
cx=(xmin+xmax)/2; xmid=cx; ymid=(ymin+ymax)/2; L=ymax-ymin; W=xmax-xmin; H=zmax-zmin
body_z=zmin+H*0.60; knee_z=zmin+H*0.30; foot_z=zmin+0.01
head_y=ymax; back_y=ymin+L*0.28; front_y=ymin+L*0.70

# ── DETECT the 4 leg positions from the mesh (centroid of bottom verts per quadrant) ──
bottom = Z < (zmin + 0.40*H)
feet={}
for fb, ysel in (("F", Y > ymid), ("B", Y <= ymid)):
    for side, xsel in (("L", X <= xmid), ("R", X > xmid)):
        msk = bottom & ysel & xsel
        if int(msk.sum()) > 4:
            feet[fb+side] = (float(X[msk].mean()), float(Y[msk].mean()))
        else:
            feet[fb+side] = (cx + (W*0.28 if side=="R" else -W*0.28), front_y if fb=="F" else back_y)

# ── Build armature with detected leg positions ───────────────────────────
arm=bpy.data.armatures.new("Rig"); rig=bpy.data.objects.new("Rig",arm)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active=rig; rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb=arm.edit_bones
segs=[]  # (name, head, tail) for manual weighting (deform bones only)
def mk(name,h,t,parent=None,conn=False,deform=True):
    b=eb.new(name); b.head=Vector(h); b.tail=Vector(t)
    if parent: b.parent=parent; b.use_connect=conn
    if deform: segs.append((name, np.array(h,dtype=np.float64), np.array(t,dtype=np.float64)))
    return b
root=mk("root",(cx,ymid,body_z),(cx,ymid+0.05,body_z),deform=False)
spine=mk("spine",(cx,back_y,body_z),(cx,front_y,body_z),root)
neck=mk("neck",(cx,front_y,body_z),(cx,head_y,zmax*0.80),spine)
headb=mk("head",(cx,head_y,zmax*0.80),(cx,head_y+0.08,zmax*0.86),neck)
tailb=mk("tail",(cx,back_y,body_z),(cx,ymin,body_z*0.7),spine)
legs={}
for key,(fx,fy) in feet.items():
    fb, side = key[0], key[1]
    th=mk(f"thigh_{key}",(fx,fy,body_z),(fx,fy,knee_z),spine)
    sh=mk(f"shin_{key}",(fx,fy,knee_z),(fx,fy,foot_z),th,True)
    legs[key]=(th.name,sh.name)
bpy.ops.object.mode_set(mode="OBJECT")

# ── Manual NEAREST-BONE weighting (point→segment distance, numpy) ─────────
# Guarantees every vertex is assigned (bone-heat returns 0 on generated meshes).
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
skinned="manual"
for bi,nm in enumerate(names):
    vg=o.vertex_groups.get(nm) or o.vertex_groups.new(name=nm)
    idx=np.where(nearest==bi)[0].tolist()
    if idx: vg.add(idx, 1.0, "REPLACE")

# ── Animate a TROT cycle (diagonal pairs) ────────────────────────────────
sc=bpy.context.scene; TOTAL=__TOTAL__; STRIDE=__STRIDE__; sc.frame_start=1; sc.frame_end=TOTAL
bpy.context.view_layer.objects.active=rig; bpy.ops.object.mode_set(mode="POSE")
try: bpy.context.preferences.edit.keyframe_new_interpolation_type="LINEAR"
except Exception: pass
pb=rig.pose.bones
for b in pb: b.rotation_mode="XYZ"
phase={"FL":0.0,"BR":0.0,"FR":math.pi,"BL":math.pi}   # trot: FL+BR vs FR+BL
A=0.55  # thigh swing amplitude (rad)
for f in range(1,TOTAL+1):
    t=2*math.pi*(f-1)/STRIDE   # STRIDE-frame period => keeps trotting for the whole clip
    for leg,(thn,shn) in legs.items():
        ph=phase[leg]
        swing=A*math.sin(t+ph)
        bend=-0.5*A*(1+math.cos(t+ph))   # shin tucks on the back-swing
        pb[thn].rotation_euler=(swing,0,0); pb[thn].keyframe_insert("rotation_euler",frame=f)
        pb[shn].rotation_euler=(bend,0,0); pb[shn].keyframe_insert("rotation_euler",frame=f)
    # body bob (2x) + slight spine sway
    pb["root"].location=(0,0,0.03*abs(math.sin(t))); pb["root"].keyframe_insert("location",frame=f)
    pb["spine"].rotation_euler=(0,0,0.05*math.sin(t)); pb["spine"].keyframe_insert("rotation_euler",frame=f)
bpy.ops.object.mode_set(mode="OBJECT")

# TEXTURE-SAFE: keep the hero's existing material; brown fallback only if none
if len(o.data.materials)==0:
    mat=bpy.data.materials.new("H"); mat.use_nodes=True
    mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value=(0.4,0.28,0.16,1)
    o.data.materials.append(mat)
# ground + sun + side camera
bpy.ops.mesh.primitive_plane_add(size=20, location=(cx,(ymin+ymax)/2,foot_z))
sun=bpy.data.lights.new("S",type="SUN"); sun.energy=3.5; so=bpy.data.objects.new("S",sun)
bpy.context.scene.collection.objects.link(so); so.rotation_euler=(math.radians(55),0,math.radians(40))
cam=bpy.data.cameras.new("C"); cam.lens=50; co=bpy.data.objects.new("C",cam); bpy.context.scene.collection.objects.link(co)
span=max(L,H,W); midz=(zmin+zmax)/2
co.location=Vector((span*3.2,(ymin+ymax)/2-span*0.4,midz+span*0.2)); look=Vector((cx,(ymin+ymax)/2,midz))-co.location
co.rotation_euler=look.to_track_quat("-Z","Y").to_euler()
sc.camera=co; sc.render.engine="BLENDER_EEVEE"; sc.render.resolution_x=480; sc.render.resolution_y=480
__result__={"skinned":skinned,"legs":list(legs.keys()),"bones":len(pb)}
'''


def main():
    hero = Path(sys.argv[1]).resolve()
    mp4 = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else (BACKEND / "renders" / "showcase" / "walk.mp4")
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
    fps = 24
    total = int(round(seconds * fps))
    stride = 20  # frames per trot cycle (~0.83 s) -> brisk, keeps trotting all clip
    bridge.connect(timeout=5)
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {"filepath": str(hero), "name": "Hero", "orientation_fix": None})
    code = RIG_CODE.replace("__TOTAL__", str(total)).replace("__STRIDE__", str(stride))
    print(registry.call("execute_python", {"code": code}), flush=True)
    # Render the full gait loop to a frame dir, then encode an MP4.
    out_dir = (BACKEND / "renders" / "_rig_anim")
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
