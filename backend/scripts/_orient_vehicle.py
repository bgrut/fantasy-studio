"""Wheels-down solver for generated vehicles (2026-07-22).

The fixed euler guess proved non-universal (the f-150's TRELLIS rest frame
differed from the cars'). This solves orientation from GEOMETRY: of the 24
axis-aligned rotations, a correctly-oriented vehicle is the one with the
SMALLEST height (Z extent) and the LONGEST footprint on X — length > width
> height holds for every car, truck, bus, and tank. Nose sign stays with the
runtime's alignLongAxis; a backwards nose is a per-asset yaw_offset fix.

Usage: blender --background --python _orient_vehicle.py -- in.glb out.glb
"""
import math
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
glb, out_glb = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)

roots = [o for o in bpy.data.objects if o.parent is None]
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
base = {o.name: o.matrix_world.copy() for o in roots}

seen = {}
cands = []
for rx in (0, 90, 180, 270):
    for ry in (0, 90, 180, 270):
        for rz in (0, 90, 180, 270):
            M = (Matrix.Rotation(math.radians(rz), 4, 'Z')
                 @ Matrix.Rotation(math.radians(ry), 4, 'Y')
                 @ Matrix.Rotation(math.radians(rx), 4, 'X'))
            key = tuple(int(round(M.to_3x3()[i][j])) for i in range(3) for j in range(3))
            if key not in seen:
                seen[key] = True
                cands.append((rx, ry, rz, M))

best = None
for rx, ry, rz, M in cands:
    for o in roots:
        o.matrix_world = M @ base[o.name]
    bpy.context.view_layer.update()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo.x = min(lo.x, w.x); lo.y = min(lo.y, w.y); lo.z = min(lo.z, w.z)
            hi.x = max(hi.x, w.x); hi.y = max(hi.y, w.y); hi.z = max(hi.z, w.z)
    ex, ey, ez = hi.x - lo.x, hi.y - lo.y, hi.z - lo.z
    # smallest height first; then longest along X (length on X, width on Y)
    score = (round(ez, 4), -round(ex, 4))
    if best is None or score < best[0]:
        best = (score, (rx, ry, rz), M)

(rx, ry, rz), M = best[1], best[2]
for o in roots:
    o.matrix_world = M @ base[o.name]
bpy.context.view_layer.update()
zmin = min((o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box)
for o in roots:
    o.matrix_world = Matrix.Translation((0, 0, -zmin)) @ o.matrix_world
bpy.ops.export_scene.gltf(filepath=out_glb, export_yup=True, export_apply=False)
print("VEHICLE-ORIENTED", rx, ry, rz)
