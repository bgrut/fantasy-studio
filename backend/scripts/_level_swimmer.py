"""Lay a generated swimmer level (2026-09-29).

A dolphin's reference showed it leaping on a diagonal, TRELLIS kept the pose,
and the player swam a dolphin standing on its tail. A swimmer's body is long
and its long axis belongs in the horizontal plane. This finds that axis from
the geometry (the principal component of the vertices), and when it points
more than 15 degrees out of level it is rotated down into the horizontal plane
about the axis that keeps its heading, so the head still points where it did.
The body is then set on the ground (min Z = 0) and exported.

Usage: blender --background --python _level_swimmer.py -- in.glb out.glb
Prints LEVEL <degrees corrected> on success.
"""
import math
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
glb, out_glb = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
pts = []
for o in meshes:
    mw = o.matrix_world
    co = np.empty(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    if len(co) > 20000:                       # a sample is plenty for one axis
        co = co[:: max(1, len(co) // 20000)]
    M = np.array(mw)
    pts.append(co @ M[:3, :3].T + M[:3, 3])
P = np.concatenate(pts) if pts else np.zeros((0, 3))
corrected = 0.0
if len(P) > 10:
    C = P - P.mean(axis=0)
    w, V = np.linalg.eigh(np.cov(C.T))
    v = V[:, int(np.argmax(w))]
    horiz = math.hypot(v[0], v[1])
    pitch = math.degrees(math.atan2(abs(v[2]), horiz))
    if pitch > 15.0 and horiz > 1e-6:
        vv = Vector((float(v[0]), float(v[1]), float(v[2]))).normalized()
        h = Vector((float(v[0]), float(v[1]), 0.0)).normalized()
        axis = vv.cross(h)
        if axis.length > 1e-6:
            ang = vv.angle(h)
            R = Matrix.Rotation(ang, 4, axis.normalized())
            roots = [o for o in bpy.data.objects if o.parent is None]
            for o in roots:
                o.matrix_world = R @ o.matrix_world
            corrected = pitch
    elif pitch > 15.0:
        # the long axis is straight up: lay it along Y
        roots = [o for o in bpy.data.objects if o.parent is None]
        for o in roots:
            o.matrix_world = Matrix.Rotation(math.radians(90), 4, 'X') @ o.matrix_world
        corrected = pitch
bpy.context.view_layer.update()
# rest it on the ground
zmin = min((o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box) if meshes else 0.0
for o in [o for o in bpy.data.objects if o.parent is None]:
    o.matrix_world = Matrix.Translation((0, 0, -zmin)) @ o.matrix_world
bpy.ops.export_scene.gltf(filepath=out_glb, export_format="GLB")
print("LEVEL %.1f" % corrected)
