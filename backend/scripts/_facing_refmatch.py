"""Front/back candidate renders for the REF-MATCH facing gate (Phase 110).

The toe-direction sign heuristic lied on armored boots (soldier, knight) and
now the ranger. The reliable signal: every generated character has a
FRONT-FACING SDXL reference photo in the actor cache. This script renders the
mesh from +Y (the convention's front) and from -Y at matching framing on a
flat green background; the caller compares both against the reference photo —
whichever side matches is the true front.

Usage: blender --background --python _facing_refmatch.py -- in.glb out_dir
Writes out_dir/front.png (+Y camera) and out_dir/back.png (-Y camera).
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
glb, out_dir = argv[0], Path(argv[1])
out_dir.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
lo = Vector((1e9,) * 3)
hi = Vector((-1e9,) * 3)
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
ctr = (lo + hi) / 2
size = max(hi.z - lo.z, hi.x - lo.x, 0.1)

sc = bpy.context.scene
try:
    sc.render.engine = "BLENDER_EEVEE"
except Exception:
    sc.render.engine = "BLENDER_EEVEE_NEXT"
sc.render.resolution_x = sc.render.resolution_y = 384
sc.world = bpy.data.worlds.new("W")
sc.world.use_nodes = True
# flat GREEN background = trivial foreground mask for the caller
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.5, 0.55, 1)
sc.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

cam = bpy.data.cameras.new("C")
cam.type = "ORTHO"
cam.ortho_scale = size * 1.25
co = bpy.data.objects.new("C", cam)
sc.collection.objects.link(co)
sc.camera = co

for name, ydir in (("front", 1.0), ("back", -1.0)):
    co.location = (ctr.x, ctr.y + ydir * size * 3.0, ctr.z)
    d = ctr - co.location
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    # key light from the camera side so both renders are lit identically
    for l in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(l)
    ld = bpy.data.lights.new("L", "SUN")
    ld.energy = 6.0
    lo2 = bpy.data.objects.new("L", ld)
    sc.collection.objects.link(lo2)
    lo2.rotation_euler = co.rotation_euler
    sc.render.filepath = str(out_dir / (name + ".png"))
    bpy.ops.render.render(write_still=True)
    print("REFMATCH-RENDERED", name)
