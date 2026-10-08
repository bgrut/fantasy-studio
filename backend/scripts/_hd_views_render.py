# Render a coated character's rest pose straight-on from given sides, orthographic,
# with a known camera: writes <out>_<view>.png and <out>.json (ortho scale, centre, axes). (2026-10-08, tools/hd_views.py)
import bpy, sys, json, math
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
src, out = argv[0], argv[1]
views = argv[2].split(",") if len(argv) > 2 else ["back"]
RES = 1024
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in bpy.data.objects:
    if o.type == "ARMATURE": o.data.pose_position = "REST"
bpy.context.view_layer.update()
meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups) > 0] or [o for o in bpy.data.objects if o.type == "MESH"]
for o in bpy.data.objects:
    if o.type == "MESH" and o not in meshes: o.hide_render = True
pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
ctr = (mn + mx) / 2
scn = bpy.context.scene
scn.render.engine = "BLENDER_WORKBENCH"
scn.display.shading.light = "STUDIO"; scn.display.shading.color_type = "VERTEX"
w = bpy.data.worlds.new("w"); w.color = (0.42, 0.42, 0.43); scn.world = w
scn.render.resolution_x = scn.render.resolution_y = RES
scn.view_settings.view_transform = "Standard"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scn.collection.objects.link(cam); scn.camera = cam
cam.data.type = "ORTHO"
size = max(mx.x - mn.x, mx.y - mn.y, mx.z - mn.z) * 1.08
cam.data.ortho_scale = size
# view name -> camera direction (from the body toward the camera), Blender axes; bipeds face +Y
DIRS = {"front": Vector((0, 1, 0)), "back": Vector((0, -1, 0)), "left": Vector((1, 0, 0)), "right": Vector((-1, 0, 0))}
meta = {"ortho": size, "centre": list(ctr), "res": RES, "views": {}}
for v in views:
    d = DIRS[v]
    cam.location = ctr + d * 10
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    R = cam.matrix_world.to_3x3() @ Vector((1, 0, 0)); U = cam.matrix_world.to_3x3() @ Vector((0, 1, 0))
    meta["views"][v] = {"dir": list(d), "right": list(R), "up": list(U)}
    scn.render.filepath = f"{out}_{v}.png"
    bpy.ops.render.render(write_still=True)
json.dump(meta, open(out + ".json", "w"))
print("VIEWS", json.dumps(meta["views"]), 'bbox', list(mn), list(mx))
