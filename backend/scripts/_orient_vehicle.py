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

cands_out = []
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
    # normalized center of mass height: a car's mass (chassis, engine) sits
    # LOW — wheels-down has the smaller value; upside-down the larger
    zsum = 0.0
    zn = 0
    for o in meshes:
        mw = o.matrix_world
        vs = o.data.vertices
        step = max(1, len(vs) // 800)
        for vi in range(0, len(vs), step):
            zsum += (mw @ vs[vi].co).z
            zn += 1
    cz_norm = ((zsum / max(zn, 1)) - lo.z) / max(ez, 1e-6)
    cands_out.append((ez, ex, ey, cz_norm, (rx, ry, rz), M))

cands_out2 = cands_out
min_ez = min(c[0] for c in cands_out2)
# NEAR-SQUARE FIX (2026-07-27 London taxi): a tall cab's height ~= width, so
# min-height alone picked 'on its side'. Among candidates within 12% of the
# flattest, prefer the LARGEST footprint (a car upright covers more ground
# than a car on its side), then longest along X.
pool = [c for c in cands_out2 if c[0] <= min_ez * 1.12]
# footprint separates side-vs-upright; center-of-mass separates up-vs-down
# up-vs-down is NOT reliably decidable from geometry on hollow TRELLIS
# meshes (tested: centroid heuristics flip on interior shells) — footprint
# fixes the side-lying class; a rare upside-down lands as a one-command
# data fix (_apply_euler 180 roll). Honest > clever.
pool.sort(key=lambda c: (-round(c[1] * c[2], 1), -c[1]))
best = (None, pool[0][4], pool[0][5])

(rx, ry, rz), M = best[1], best[2]
for o in roots:
    o.matrix_world = M @ base[o.name]
bpy.context.view_layer.update()
zmin = min((o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box)
for o in roots:
    o.matrix_world = Matrix.Translation((0, 0, -zmin)) @ o.matrix_world
bpy.ops.export_scene.gltf(filepath=out_glb, export_yup=True, export_apply=False)
print("VEHICLE-ORIENTED", rx, ry, rz)
