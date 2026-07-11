"""Render one frame of an animated GLB for visual QA (quality harness tool).

Usage: blender --background --python _render_pose_check.py -- <glb> <out.png> [frame] [clip]
"""
import sys
import math

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
glb, out_png = argv[0], argv[1]
frame = int(argv[2]) if len(argv) > 2 else 9
clip = argv[3] if len(argv) > 3 else "run"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
if rigs:
    rig = rigs[0]
    if rig.animation_data is None:
        rig.animation_data_create()
    for tr in rig.animation_data.nla_tracks:
        tr.mute = True
    act = next((a for a in bpy.data.actions if a.name == clip), None)
    if act is not None:
        rig.animation_data.action = act
        try:
            if act.slots:
                rig.animation_data.action_slot = act.slots[0]
        except Exception:
            pass
        bpy.context.scene.frame_set(frame)

dg = bpy.context.evaluated_depsgraph_get(); dg.update()
vs = []
for o in bpy.data.objects:
    if o.type == "MESH":
        ev = o.evaluated_get(dg); me = ev.to_mesh()
        vs += [(ev.matrix_world @ v.co)[:] for v in me.vertices]
        ev.to_mesh_clear()
V = np.array(vs); ctr = V.mean(0); span = float(max(V.max(0) - V.min(0)))

cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
bpy.context.scene.collection.objects.link(cam)
cam.location = Vector((ctr[0] + span * 1.7, ctr[1] - span * 1.7, ctr[2] + span * 0.7))
d = Vector(ctr.tolist()) - cam.location
cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = cam
sd = bpy.data.lights.new("S", "SUN"); sd.energy = 4
s = bpy.data.objects.new("S", sd); bpy.context.scene.collection.objects.link(s)
s.rotation_euler = (math.radians(55), 0, math.radians(40))
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"; sc.render.resolution_x = 560; sc.render.resolution_y = 480
sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.45, 0.55, 0.65, 1)
sc.render.filepath = out_png
bpy.ops.render.render(write_still=True)
print("RENDERED", out_png)
