"""Phase 20 — WHEELED motion module (cars / trucks / bikes).

Wheeled vehicles are RIGID — realism is not skeletal deformation but: the body
translating along its heading, the wheels spinning at the right rate for the
distance travelled, and a little suspension bob. We model that with the SAME
armature engine as the legged module:
  • 1 body bone  → all chassis/cabin verts (rigid)
  • 4 wheel bones (axle along X) → only the verts inside each wheel disc
The whole rig translates forward (object-level) so the car drives across frame;
each wheel pose-bone spins about its axle by (distance / wheel_radius).

TEXTURE-SAFE: never clears the hero's materials (keeps multiview texture).
ARBITRARY LENGTH: travel & wheel-spin are functions of time, so the car keeps
driving for the whole clip — longer video => longer drive, wheels always synced.

Usage: python scripts/rig_wheeled_test.py <car.glb> [out.mp4] [seconds]
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.mcp import registry, bridge  # noqa: E402

# __TOTAL__ total frames; __FPS__ fps; values baked numerically for the gait.
RIG_CODE = r'''
import bpy, math
import numpy as np
from mathutils import Vector

o=bpy.data.objects.get("Hero"); o.rotation_mode="XYZ"
bpy.context.view_layer.objects.active=o; o.select_set(True); bpy.context.view_layer.update()
def _bake():
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False); bpy.context.view_layer.update()
# A car's three extents are length(longest) > width > height(shortest). Orient so
# height→Z (up), length→Y (heading), width→X — baking each 90° step so eulers
# compose in world space. (TripoSG often imports the car standing on its bumper.)
# 1) shortest extent → Z (up)
d=o.dimensions; shortest=min(range(3), key=lambda i:(d.x,d.y,d.z)[i])
if shortest==0: o.rotation_euler.y=math.radians(90); _bake()      # X→Z
elif shortest==1: o.rotation_euler.x=math.radians(90); _bake()    # Y→Z
# 2) longest remaining horizontal → Y (heading)
if o.dimensions.x > o.dimensions.y: o.rotation_euler.z=math.radians(90); _bake()
# 3) WHEELS-DOWN: the roof/cabin is NARROWER (in X) than the wheeled underside.
#    If the narrow end is at the bottom, the car is upside-down → flip about Y.
_Wc=np.array([list(o.matrix_world@v.co) for v in o.data.vertices], dtype=np.float64)
_Zc=_Wc[:,2]; _Xc=_Wc[:,0]; _z0,_z1=_Zc.min(),_Zc.max(); _Hh=max(_z1-_z0,1e-6)
def _xw(sel):
    return (_Xc[sel].max()-_Xc[sel].min()) if int(sel.sum())>6 else 0.0
if _xw(_Zc>_z1-0.15*_Hh) > _xw(_Zc<_z0+0.15*_Hh):   # wide top, narrow bottom => inverted
    o.rotation_euler.y=math.radians(180); _bake()
dz=o.dimensions.z or 1.0; s=1.45/dz; o.scale=(s,s,s); bpy.context.view_layer.update()  # ~1.45 m tall car
zs=[(o.matrix_world@Vector(c)).z for c in o.bound_box]; o.location=(0,0,-min(zs)); bpy.context.view_layer.update()
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.context.view_layer.update()

me=o.data
V=np.array([list(v.co) for v in me.vertices], dtype=np.float64)
X,Y,Z=V[:,0],V[:,1],V[:,2]
xmin,xmax=X.min(),X.max(); ymin,ymax=Y.min(),Y.max(); zmin,zmax=Z.min(),Z.max()
cx=(xmin+xmax)/2; cy=(ymin+ymax)/2; H=zmax-zmin; W=xmax-xmin; Lf=ymax-ymin

# ── Heading: drive toward +Y if the nose is at +Y, else -Y. A car nose end is
#    typically LOWER/narrower than the tall cabin; pick the +Y vs -Y direction
#    whose far end sits lower (hood) as "forward". Not critical — symmetric look.
front_sign = 1.0
hi = Z > zmin + 0.55*H
if int(hi.sum()) > 10:
    if Y[hi].mean() > cy: front_sign = -1.0   # cabin biased +Y => nose is -Y

# ── TEXTURE-SAFE: keep existing materials; neutral red fallback only if none ─
had_mat=len(o.data.materials)>0
if not had_mat:
    mat=bpy.data.materials.new("CarFallback"); mat.use_nodes=True
    b=mat.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=(0.55,0.05,0.06,1); b.inputs["Metallic"].default_value=0.7; b.inputs["Roughness"].default_value=0.3
    o.data.materials.append(mat)

# ── RIGID DRIVE (no skeletal deform — vehicles are rigid; TripoSG fuses wheels
#    into the body so spinning them tears the chassis). The car is one rigid
#    object: translate along heading + a subtle suspension bob. A future part-
#    segmented car (separate wheel meshes) can add real wheel-spin on top. ────
sc=bpy.context.scene; TOTAL=__TOTAL__; FPS=__FPS__
sc.frame_start=1; sc.frame_end=TOTAL
travel = max(Lf, 1.0) * 9.0                  # metres driven across the clip
o.rotation_mode="XYZ"
o.keyframe_insert("rotation_euler", frame=1)  # lock orientation
base_z = o.location.z
for f in range(1,TOTAL+1):
    frac=(f-1)/max(TOTAL-1,1)
    dist=travel*frac*front_sign
    bob=0.004*Lf*math.sin(2*math.pi*frac*9)   # gentle suspension bob
    o.location=(o.location.x, cy + dist, base_z + bob)
    o.keyframe_insert("location", frame=f)
try: bpy.context.preferences.edit.keyframe_new_interpolation_type="LINEAR"
except Exception: pass

# ── Striped ROAD (so the motion reads) + sun ────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=travel*1.6, location=(cx,cy,zmin+0.001))
gp=bpy.context.active_object; gm=bpy.data.materials.new("Road"); gm.use_nodes=True; rt=gm.node_tree
rb=rt.nodes.get("Principled BSDF"); rb.inputs["Roughness"].default_value=0.85
tc=rt.nodes.new("ShaderNodeTexCoord"); wv=rt.nodes.new("ShaderNodeTexWave")
wv.wave_type="BANDS"; wv.inputs["Scale"].default_value=travel*0.25   # lane stripes along the drive
ramp=rt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color=(0.07,0.07,0.08,1); ramp.color_ramp.elements[1].color=(0.10,0.10,0.12,1)
rt.links.new(tc.outputs["Generated"], wv.inputs["Vector"]); rt.links.new(wv.outputs["Fac"], ramp.inputs["Fac"])
rt.links.new(ramp.outputs["Color"], rb.inputs["Base Color"]); gp.data.materials.append(gm)
sun=bpy.data.lights.new("S",type="SUN"); sun.energy=3.8; sun.color=(1.0,0.85,0.7); so=bpy.data.objects.new("S",sun)
bpy.context.scene.collection.objects.link(so); so.rotation_euler=(math.radians(50),0,math.radians(30))

# ── TRACKING camera: constant 3/4 offset from the car, keyframed to follow it,
#    so the car stays framed the whole drive while the road streams past. ─────
cam=bpy.data.cameras.new("C"); cam.lens=50; co=bpy.data.objects.new("C",cam); bpy.context.scene.collection.objects.link(co)
span=max(W,Lf,H)
off=Vector((span*2.2, -span*2.6*front_sign, zmin+span*1.3))   # behind-and-to-the-side
look_off=Vector((0,0,zmin+H*0.45))
for f in range(1,TOTAL+1):
    frac=(f-1)/max(TOTAL-1,1); carY=cy+travel*frac*front_sign
    co.location=Vector((cx+off.x, carY+off.y, off.z))
    look=(Vector((cx,carY,0))+look_off)-co.location
    co.rotation_euler=look.to_track_quat("-Z","Y").to_euler()
    co.keyframe_insert("location", frame=f); co.keyframe_insert("rotation_euler", frame=f)
sc.camera=co; sc.render.engine="BLENDER_EEVEE"; sc.render.resolution_x=960; sc.render.resolution_y=540
try: sc.view_settings.view_transform="AgX"
except Exception: pass
__result__={"kept_material":had_mat,"total":TOTAL,"travel_m":round(travel,2),"front_sign":front_sign}
'''


def main():
    hero = Path(sys.argv[1]).resolve()
    mp4 = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else (BACKEND / "renders" / "showcase" / "car_drive.mp4")
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
    fps = 24
    total = int(round(seconds * fps))

    bridge.connect(timeout=5)
    registry.call("reset_scene", {})
    registry.call("import_mesh_file", {"filepath": str(hero), "name": "Hero", "orientation_fix": None})
    code = RIG_CODE.replace("__TOTAL__", str(total)).replace("__FPS__", str(fps))
    print(registry.call("execute_python", {"code": code}), flush=True)

    out_dir = (BACKEND / "renders" / "_wheeled_anim")
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
