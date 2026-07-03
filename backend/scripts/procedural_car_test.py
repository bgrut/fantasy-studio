"""Phase 20 — PROCEDURAL hard-surface vehicle (crisp geometry + spinning wheels).

Image-to-3D blobs manufactured objects. For vehicles we build a parametric car
instead: a beveled body + greenhouse/glass cabin + 4 SEPARATE wheels. Separate
wheels mean we can actually spin them (the thing TripoSG's fused mesh couldn't
do), and the geometry is crisp (panels, wheels, windows) — recognizable as a car.

Convention matches the composer: length along Y (front +Y), up Z, grounded z=0.
Drive = body translates +Y, wheels spin about their axle (X) ∝ distance, plus a
suspension bob; a tracking camera follows over a striped road.

Usage: python scripts/procedural_car_test.py [out.mp4] [seconds] [r,g,b]
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.mcp import registry, bridge  # noqa: E402

BUILD_CODE = r'''
import bpy, math
from mathutils import Vector

R, G, B = __RGB__
TOTAL = __TOTAL__; FPS = __FPS__

# ── dimensions (a compact sports car, metres) ──
L, W = 4.1, 1.70
wheel_r, wheel_w = 0.44, 0.30
axle_z = wheel_r
body_h = 0.46
body_z = axle_z + 0.10 + body_h / 2.0   # raised so the wheels clearly show below
cab_l, cab_w, cab_h = L * 0.42, W * 0.78, 0.46
cab_z = body_z + body_h / 2.0 + cab_h / 2.0 - 0.02

def mat(name, rgb, metal=0.0, rough=0.5, emis=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emis is not None:
        try:
            b.inputs["Emission Color"].default_value = (emis[0], emis[1], emis[2], 1)
            b.inputs["Emission Strength"].default_value = 4.0
        except Exception: pass
    return m

paint = mat("Paint", (R, G, B), metal=0.7, rough=0.28)
glass = mat("Glass", (0.04, 0.05, 0.07), metal=0.0, rough=0.08)
rubber = mat("Tire", (0.03, 0.03, 0.035), metal=0.0, rough=0.85)
hub = mat("Hub", (0.6, 0.6, 0.62), metal=0.9, rough=0.25)
light = mat("Light", (1.0, 0.9, 0.6), emis=(1.0, 0.85, 0.5))

def box(name, sx, sy, sz, loc, material, bevel=0.06):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = bpy.context.active_object; o.name = name
    o.scale = (sx, sy, sz); bpy.ops.object.transform_apply(scale=True)
    bm = o.modifiers.new("Bevel", "BEVEL"); bm.width = bevel; bm.segments = 3
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o

# ── BODY (Hero) — single rounded hull, strongly beveled so it reads as a car ──
body = box("Hero", W, L, body_h, (0, 0, body_z), paint, bevel=0.16)

# ── CABIN greenhouse (glass): narrower, set slightly back, SEATED on the body and
#    tapered (top smaller than base) for a windshield rake ──
cab_w = W * 0.70; cab_l = L * 0.38
cab_seat_z = body_z + body_h / 2.0 + cab_h / 2.0 - 0.12
cabin = box("Cabin", cab_w, cab_l, cab_h, (0, -L * 0.04, cab_seat_z), glass, bevel=0.12)

# ── headlights / taillights flush on the nose/tail faces ──
for sy, col in ((+1, light), (-1, mat("Tail", (0.5, 0.02, 0.02), emis=(1.0, 0.05, 0.05)))):
    for sx in (-1, 1):
        box("Lamp", 0.18, 0.05, 0.09, (sx * W * 0.32, sy * (L / 2 - 0.04), body_z + 0.02), col, bevel=0.02)

# ── 4 SEPARATE wheels (cylinders, axis along X so they roll about X) ──
wheel_names = {}
for fb, wy in (("F", L * 0.32), ("B", -L * 0.32)):
    for lr, wx in (("L", -(W / 2 - 0.02)), ("R", (W / 2 - 0.02))):
        bpy.ops.mesh.primitive_cylinder_add(radius=wheel_r, depth=wheel_w, location=(wx, wy, axle_z))
        w = bpy.context.active_object; w.name = "Wheel_" + fb + lr
        w.rotation_euler = (0, math.radians(90), 0)   # axis -> X (rolls about X)
        bpy.ops.object.transform_apply(rotation=True)
        w.data.materials.append(rubber)
        bpy.ops.object.shade_smooth()
        # hub cap (small, set slightly outboard so it reads as a rim, not an eye)
        bpy.ops.mesh.primitive_cylinder_add(radius=wheel_r * 0.30, depth=wheel_w * 1.04, location=(wx, wy, axle_z))
        h = bpy.context.active_object; h.name = "Hub_" + fb + lr
        h.rotation_euler = (0, math.radians(90), 0); bpy.ops.object.transform_apply(rotation=True)
        h.data.materials.append(hub); bpy.ops.object.shade_smooth()
        h.parent = w
        w.parent = body
        wheel_names[fb + lr] = w.name

# parent cabin/spine/lamps to body so the whole car moves together
for ob in bpy.data.objects:
    if ob.name.startswith(("Cabin", "Spine", "Lamp")) and ob.parent is None:
        ob.parent = body

# ── DRIVE: body translates +Y across frame; wheels spin (dist/radius); bob ──
sc = bpy.context.scene; sc.frame_start = 1; sc.frame_end = TOTAL
travel = L * 6.0
start_y = -travel * 0.5
body.rotation_mode = "XYZ"
try: bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
except Exception: pass
for w in wheel_names.values():
    bpy.data.objects[w].rotation_mode = "XYZ"
for f in range(1, TOTAL + 1):
    frac = (f - 1) / max(TOTAL - 1, 1)
    dist = travel * frac
    body.location = (0.0, start_y + dist, 0.0 + 0.01 * math.sin(2 * math.pi * frac * 9))
    body.keyframe_insert("location", frame=f)
    spin = -dist / wheel_r
    for w in wheel_names.values():
        wo = bpy.data.objects[w]
        wo.rotation_euler = (spin, 0, 0)
        wo.keyframe_insert("rotation_euler", frame=f)

# ── striped road + sun + sky ──
bpy.ops.mesh.primitive_plane_add(size=travel * 1.6, location=(0, 0, 0))
gp = bpy.context.active_object; gm = mat("Road", (0.08, 0.08, 0.09), rough=0.9)
rt = gm.node_tree; rb = rt.nodes.get("Principled BSDF")
tc = rt.nodes.new("ShaderNodeTexCoord"); wv = rt.nodes.new("ShaderNodeTexWave")
wv.wave_type = "BANDS"; wv.inputs["Scale"].default_value = travel * 0.22
rmp = rt.nodes.new("ShaderNodeValToRGB")
rmp.color_ramp.elements[0].color = (0.07, 0.07, 0.08, 1); rmp.color_ramp.elements[1].color = (0.11, 0.11, 0.13, 1)
rt.links.new(tc.outputs["Generated"], wv.inputs["Vector"]); rt.links.new(wv.outputs["Fac"], rmp.inputs["Fac"])
rt.links.new(rmp.outputs["Color"], rb.inputs["Base Color"]); gp.data.materials.append(gm)
sun = bpy.data.lights.new("S", type="SUN"); sun.energy = 4.0; sun.color = (1.0, 0.95, 0.88)
so = bpy.data.objects.new("S", sun); bpy.context.scene.collection.objects.link(so)
so.rotation_euler = (math.radians(52), 0, math.radians(40))
w = bpy.context.scene.world or bpy.data.worlds.new("W"); bpy.context.scene.world = w; w.use_nodes = True
w.node_tree.nodes.get("Background").inputs["Color"].default_value = (0.55, 0.7, 0.95, 1)
w.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.6

# ── tracking camera (constant offset, follows the car) ──
cam = bpy.data.cameras.new("C"); cam.lens = 50
co = bpy.data.objects.new("C", cam); bpy.context.scene.collection.objects.link(co)
span = max(W, L, 2.0)
for f in range(1, TOTAL + 1):
    frac = (f - 1) / max(TOTAL - 1, 1); carY = start_y + travel * frac
    co.location = Vector((span * 2.0, carY - span * 2.4, span * 1.0))
    look = Vector((0, carY, body_z)) - co.location
    co.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    co.keyframe_insert("location", frame=f); co.keyframe_insert("rotation_euler", frame=f)
sc.camera = co; sc.render.engine = "BLENDER_EEVEE"; sc.render.resolution_x = 960; sc.render.resolution_y = 540
try: sc.view_settings.view_transform = "AgX"
except Exception: pass
try: sc.eevee.use_bloom = True
except Exception: pass
__result__ = {"wheels": list(wheel_names.keys()), "travel": round(travel, 2), "total": TOTAL}
'''


def main():
    mp4 = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (BACKEND / "renders" / "showcase" / "proc_car_drive.mp4")
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    rgb = sys.argv[3] if len(sys.argv) > 3 else "0.55,0.04,0.05"
    fps = 24
    total = int(round(seconds * fps))
    code = (BUILD_CODE.replace("__RGB__", "(" + rgb + ")")
            .replace("__TOTAL__", str(total)).replace("__FPS__", str(fps)))
    bridge.connect(timeout=5)
    registry.call("reset_scene", {})
    print(registry.call("execute_python", {"code": code}), flush=True)
    out_dir = (BACKEND / "renders" / "_proc_car")
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
