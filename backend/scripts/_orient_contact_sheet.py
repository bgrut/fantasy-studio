"""Render a GLB at all 24 axis-aligned orientations into one contact sheet.

Usage: blender --background --python _orient_contact_sheet.py -- <glb> <out.png>
Numbers printed map index -> (rx, ry, rz) degrees applied ON TOP of current.
"""
import sys
import math

import bpy
import numpy as np
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
glb, out_png = argv[0], argv[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
roots = [o for o in bpy.data.objects if o.parent is None]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]

seen = {}
cands = []
for rx in (0, 90, 180, 270):
    for ry in (0, 90, 180, 270):
        for rz in (0, 90, 180, 270):
            M = (Matrix.Rotation(math.radians(rz), 4, 'Z')
                 @ Matrix.Rotation(math.radians(ry), 4, 'Y')
                 @ Matrix.Rotation(math.radians(rx), 4, 'X')).to_3x3()
            key = tuple(int(round(M[i][j])) for i in range(3) for j in range(3))
            if key not in seen:
                seen[key] = (rx, ry, rz)
                cands.append((rx, ry, rz))
print("CANDS:", list(enumerate(cands)))

base = {o.name: o.matrix_world.copy() for o in roots}
cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
bpy.context.scene.collection.objects.link(cam)
sd = bpy.data.lights.new("S", "SUN"); sd.energy = 4
s = bpy.data.objects.new("S", sd); bpy.context.scene.collection.objects.link(s)
s.rotation_euler = (math.radians(55), 0, math.radians(40))
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
T = 220
sc.render.resolution_x = T; sc.render.resolution_y = T
sc.world = bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.45, 0.55, 0.65, 1)

tiles = []
for i, (rx, ry, rz) in enumerate(cands):
    R = (Matrix.Rotation(math.radians(rz), 4, 'Z')
         @ Matrix.Rotation(math.radians(ry), 4, 'Y')
         @ Matrix.Rotation(math.radians(rx), 4, 'X'))
    for o in roots:
        o.matrix_world = R @ base[o.name]
    bpy.context.view_layer.update()
    vs = []
    for o in meshes:
        # bpy prop collections reject step slices in Blender 5.1 — index instead
        verts = o.data.vertices
        vs += [(o.matrix_world @ verts[j].co)[:] for j in range(0, len(verts), 7)]
    V = np.array(vs); ctr = V.mean(0); span = float(max(V.max(0) - V.min(0)))
    cam.location = Vector((ctr[0] + span * 1.6, ctr[1] - span * 1.6, ctr[2] + span * 0.6))
    d = Vector(ctr.tolist()) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    tmp = out_png + f".tile{i}.png"
    sc.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(tmp)
    px = np.empty(T * T * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    tiles.append(px.reshape(T, T, 4))
    bpy.data.images.remove(img)

cols = 6
rows = (len(tiles) + cols - 1) // cols
sheet = np.zeros((rows * T, cols * T, 4), dtype=np.float32)
sheet[:, :, 3] = 1.0
for i, t in enumerate(tiles):
    r, c = divmod(i, cols)
    sheet[(rows - 1 - r) * T:(rows - r) * T, c * T:(c + 1) * T] = t
out = bpy.data.images.new("Sheet", cols * T, rows * T, alpha=False)
out.pixels.foreach_set(sheet.ravel())
out.filepath_raw = out_png
out.file_format = "PNG"
out.save()
import os
for i in range(len(tiles)):
    try:
        os.remove(out_png + f".tile{i}.png")
    except OSError:
        pass
print("SHEET", out_png)
