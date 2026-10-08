# Render a coated character's rest pose straight-on from given sides, orthographic,
# with a known camera: writes <out>_<view>.png and <out>.json (ortho scale, centre, axes). (2026-10-08, tools/hd_views.py)
#
# HEAD VIEWS (2026-10-08, the user: faces "smeared and smushed or a little
# duplicitive"). The face was the reference photo laid over a head that is
# not quite the photo's, and wherever the two disagreed it showed two noses.
# A head view frames the head alone (its own centre and scale, written per
# view) from the front, the three-quarters and the sides, so a repaint of it
# keeps every feature where the geometry has it and projects back exactly.
# The views carry the body plan: a person faces +Y; an animal's head is found
# at its own end of the body.
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
scn.display.shading.light = "STUDIO"
scn.display.shading.color_type = "TEXTURE" if any(m.material_slots and any(s.material and s.material.use_nodes and any(n.type == "TEX_IMAGE" and n.image for n in s.material.node_tree.nodes) for s in m.material_slots) for m in meshes) and not any(m.data.color_attributes for m in meshes) else "VERTEX"
w = bpy.data.worlds.new("w"); w.color = (0.42, 0.42, 0.43); scn.world = w
scn.render.resolution_x = scn.render.resolution_y = RES
scn.view_settings.view_transform = "Standard"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scn.collection.objects.link(cam); scn.camera = cam
cam.data.type = "ORTHO"
size = max(mx.x - mn.x, mx.y - mn.y, mx.z - mn.z) * 1.08
# view name -> camera direction (from the body toward the camera), Blender axes; bipeds face +Y
s2 = math.sqrt(0.5)
DIRS = {"front": Vector((0, 1, 0)), "back": Vector((0, -1, 0)), "left": Vector((1, 0, 0)), "right": Vector((-1, 0, 0)),
        "head_front": Vector((0, 1, 0)), "head_left34": Vector((s2, s2, 0)), "head_right34": Vector((-s2, s2, 0)),
        "head_left": Vector((1, 0, 0)), "head_right": Vector((-1, 0, 0)), "head_back": Vector((0, -1, 0)),
        "head_top": Vector((0, 0.35, 1)).normalized()}

# the head: a person's is the top eighth of the body; an animal's (longer than
# tall) is the top of whichever end of the long axis stands higher
H = mx.z - mn.z
long_x = (mx.x - mn.x) > 1.15 * H or (mx.y - mn.y) > 1.15 * H
if not long_x:
    hp = [p for p in pts if p.z > mx.z - 0.13 * H]
    hsize = max(0.13 * H, max(p.x for p in hp) - min(p.x for p in hp), max(p.y for p in hp) - min(p.y for p in hp)) * 1.5
else:
    ax = 0 if (mx.x - mn.x) >= (mx.y - mn.y) else 1
    L = (mx.x - mn.x) if ax == 0 else (mx.y - mn.y)
    ends = []
    for sgn in (1, -1):
        e = [p for p in pts if sgn * ((p.x if ax == 0 else p.y) - (ctr.x if ax == 0 else ctr.y)) > 0.30 * L]
        ends.append((max(p.z for p in e) if e else -1e9, sgn, e))
    ends.sort(key=lambda t: -t[0])
    top, sgn, e = ends[0]
    hp = [p for p in e if p.z > top - 0.35 * H]
    hsize = max(0.30 * H, max(p.z for p in hp) - min(p.z for p in hp)) * 1.5
    # the animal's own "front" is along its head end; head views turn with it
    fwd = Vector((sgn, 0, 0)) if ax == 0 else Vector((0, sgn, 0))
    side = Vector((-fwd.y, fwd.x, 0))
    DIRS.update({"head_front": fwd, "head_left34": (fwd + side).normalized(), "head_right34": (fwd - side).normalized(),
                 "head_left": side, "head_right": -side, "head_back": -fwd, "head_top": (fwd * 0.35 + Vector((0, 0, 1))).normalized()})
hc = Vector((sum(p.x for p in hp) / len(hp), sum(p.y for p in hp) / len(hp), sum(p.z for p in hp) / len(hp))) if hp else ctr

meta = {"ortho": size, "centre": list(ctr), "res": RES, "views": {}, "animal": bool(long_x)}
for v in views:
    d = DIRS[v]
    c, o_ = (hc, hsize) if v.startswith("head") else (ctr, size)
    cam.data.ortho_scale = o_
    cam.location = c + d * 10
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    R = cam.matrix_world.to_3x3() @ Vector((1, 0, 0)); U = cam.matrix_world.to_3x3() @ Vector((0, 1, 0))
    meta["views"][v] = {"dir": list(d), "right": list(R), "up": list(U), "centre": list(c), "ortho": o_}
    scn.render.filepath = f"{out}_{v}.png"
    bpy.ops.render.render(write_still=True)
json.dump(meta, open(out + ".json", "w"))
print("VIEWS", json.dumps({k: v["dir"] for k, v in meta["views"].items()}), 'bbox', list(mn), list(mx), "animal", long_x)
