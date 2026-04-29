"""
_thumb_render_subprocess.py
===========================
Runs inside Blender.  Arguments after ``--``:
    --asset-path <file>      path to GLB/GLTF/BLEND/FBX
    --out <file>             output PNG path
    --size <int>             square size (default 256)

Doesn't import the full fantasy-studio pipeline — keeps startup fast
(~2s) and avoids dragging in bpy-dependent modules that only matter
for full renders.
"""
import argparse
import os
import sys
import bpy
from mathutils import Vector

# ─── argparse after ``--`` ──────────────────────────────────────────
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument("--asset-path", required=True)
p.add_argument("--out", required=True)
p.add_argument("--size", type=int, default=256)
args = p.parse_args(argv)

# ─── Clean scene ────────────────────────────────────────────────────
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for coll in list(bpy.data.collections):
    try:
        bpy.data.collections.remove(coll)
    except Exception:
        pass

# ─── Import the asset ──────────────────────────────────────────────
ext = os.path.splitext(args.asset_path)[1].lower()
try:
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=args.asset_path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=args.asset_path)
    elif ext == ".obj":
        try:
            bpy.ops.wm.obj_import(filepath=args.asset_path)
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=args.asset_path)
    elif ext == ".blend":
        with bpy.data.libraries.load(args.asset_path, link=False) as (src, dst):
            dst.objects = list(src.objects)
        for o in dst.objects:
            if o is not None:
                bpy.context.collection.objects.link(o)
    else:
        print(f"[THUMB] unsupported ext: {ext}", flush=True)
        sys.exit(2)
except Exception as e:
    print(f"[THUMB] import failed: {e}", flush=True)
    sys.exit(3)

# ─── Compute combined bbox (world space) ───────────────────────────
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
coords = []
for m in meshes:
    try:
        for c in m.bound_box:
            coords.append(m.matrix_world @ Vector(c))
    except Exception:
        pass
if not coords:
    print("[THUMB] no mesh bbox — bailing", flush=True)
    sys.exit(4)

mn = Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
mx = Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
center = (mn + mx) * 0.5
diag = (mx - mn).length
if diag < 0.001:
    diag = 1.0

# ─── Camera auto-framed 3/4 angle ──────────────────────────────────
import math
cam_dist = max(diag * 1.4, 2.0)
ang = math.radians(25)
cam_loc = Vector((
    center.x + cam_dist * math.sin(ang),
    center.y - cam_dist * math.cos(ang),
    center.z + diag * 0.35,
))
bpy.ops.object.camera_add(location=cam_loc)
cam = bpy.context.active_object
# Aim at subject
direction = center - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = cam
cam.data.lens = 50.0

# ─── 3-point light ─────────────────────────────────────────────────
def _add_light(kind, loc, energy, color=(1.0, 1.0, 1.0)):
    bpy.ops.object.light_add(type=kind, location=loc)
    lt = bpy.context.active_object
    lt.data.energy = energy
    lt.data.color = color
    if hasattr(lt.data, "size"):
        lt.data.size = 4.0
    return lt

_add_light("AREA", (cam_loc.x + 2, cam_loc.y - 1, cam_loc.z + 2),    800)   # key
_add_light("AREA", (cam_loc.x - 3, cam_loc.y + 0, cam_loc.z + 1),    300, color=(0.92, 0.95, 1.0))  # fill
_add_light("AREA", (center.x + 0, center.y + 3, center.z + 3),        500, color=(1.0, 0.95, 0.88))   # back

# ─── World: neutral grey ambient ───────────────────────────────────
world = bpy.context.scene.world
if world is None:
    world = bpy.data.worlds.new(name="ThumbWorld")
    bpy.context.scene.world = world
world.use_nodes = True
try:
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.14, 0.14, 0.15, 1.0)
    bg.inputs["Strength"].default_value = 1.0
except Exception:
    pass

# ─── Render settings (fast Eevee) ──────────────────────────────────
scene = bpy.context.scene
try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except Exception:
    try:
        scene.render.engine = "BLENDER_EEVEE"
    except Exception:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 16
scene.render.resolution_x = args.size
scene.render.resolution_y = args.size
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = args.out
try:
    scene.eevee.taa_render_samples = 16
except Exception:
    pass

# ─── Render ────────────────────────────────────────────────────────
bpy.ops.render.render(write_still=True)
print(f"[THUMB] wrote {args.out}", flush=True)
