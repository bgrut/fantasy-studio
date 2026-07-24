"""Floater prune (Phase 112): remove FREE-FLOATING mesh shards.

!! NOT WIRED INTO THE PIPELINE — UNSAFE AS-IS (2026-07-24 test results):
!! fox dry-run pruned 9697 legit fur shells; knight lost his armor (TRELLIS
!! meshes are THOUSANDS of loose shells, and the gap test measures against
!! only the single largest shell, so everything reads as far/floating).
!! REDESIGN NEEDED before any use: build the trusted-body cloud from the
!! UNION of all components above the size threshold, then gap-test tiny
!! components against that union. Manual tool only until then.

The knight shipped with a flat triangle hovering near his head — a
disconnected TRELLIS component the silhouette/barnacle filters missed
(those target attached artifacts). Rule here is conservative on purpose:
a loose component dies only if it is BOTH tiny (< 1% of triangles) AND
physically separated from the main body (nearest vertex farther than 3%
of model height). Legit small shells (fur strips, eyes) touch the body
and survive the gap test.

Usage: blender --background --python _prune_floaters.py -- in.glb out.glb
Prints PRUNED <n> / KEPT <m>.
"""
import sys

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
glb, out_glb = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
pruned = kept = 0
for o in meshes:
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")

parts = [o for o in bpy.data.objects if o.type == "MESH"]
if len(parts) > 1:
    tri = {p.name: len(p.data.polygons) for p in parts}
    main = max(parts, key=lambda p: tri[p.name])
    total = sum(tri.values()) or 1
    # main-body vertex cloud (world space, subsampled) for the gap test
    mv = np.array([main.matrix_world @ v.co for v in main.data.vertices])
    if len(mv) > 4000:
        mv = mv[:: max(1, len(mv) // 4000)]
    height = float(mv[:, 2].max() - mv[:, 2].min()) or 1.0
    gap_limit = height * 0.08
    doomed = []
    for p in parts:
        if p is main:
            continue
        if tri[p.name] > total * 0.001:
            kept += 1
            continue
        pv = np.array([p.matrix_world @ v.co for v in p.data.vertices])
        if len(pv) > 400:
            pv = pv[:: max(1, len(pv) // 400)]
        d = np.sqrt(((pv[:, None, :] - mv[None, :, :]) ** 2).sum(-1)).min()
        if d > gap_limit:
            doomed.append(p)
        else:
            kept += 1
    for p in doomed:
        bpy.data.objects.remove(p, do_unlink=True)
        pruned += 1
    # re-join survivors into one mesh
    parts = [o for o in bpy.data.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = main
    if len(parts) > 1:
        bpy.ops.object.join()

bpy.ops.export_scene.gltf(filepath=out_glb, export_yup=True)
print(f"PRUNED {pruned} / KEPT {kept}")
