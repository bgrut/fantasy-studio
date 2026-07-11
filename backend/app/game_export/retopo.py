"""KEYSTONE — auto-retopology before rigging (Phase 58, plan Section 3.5).

Every character-quality failure (morphing, patchy textures, popping LODs)
shares one root cause: generated meshes are chaotic triangle soup — open
shells, disconnected shards, wildly uneven density. This pass rebuilds the
hero BEFORE rigging:

    voxel remesh   -> manifold, WATERTIGHT, shard-fused, even density
    island filter  -> drop interior shells / leftover fragments
    QuadriFlow     -> curvature-aligned quads (best-effort; see below)
    UV + material transfer from the original (textures survive)

HONEST STATUS (2026-07-11): Blender 5.1's quadriflow_remesh rejects the
voxel-remeshed TRELLIS heroes with "mesh needs to be manifold / consistent
normals" even when edit-mode reports 0 non-manifold verts, 1 island,
consistent outward normals, no degenerates (probed exhaustively: symmetry
off, triangulated, mesh-doctor combo — all CANCELLED; a subdivided cube
passes in the same session, so it is mesh-shape-specific wrapper behavior).
QuadriFlow therefore runs BEST-EFFORT: when it cancels we keep the VOXEL
mesh, which already delivers the keystone's core value (watertight manifold
+ even density + fused shards). Curvature-aligned loops upgrade path:
standalone instant-meshes binary (BSD-3) or a newer Blender — GPU-day item.

Gated by FS_RETOPO (default OFF until the harness proves it per-pattern);
any failure before the voxel stage completes restores the ORIGINAL mesh.
"""
from __future__ import annotations

import os

# Operates on the already-imported hero object (name substituted at __HERO__).
RETOPO_CODE = r'''
import bpy, json, time
import numpy as np
HERO = "__HERO__"; TARGET_FACES = __FACES__
o = bpy.data.objects.get(HERO)
out = {"ok": False, "reason": ""}
try:
    if o is None or o.type != "MESH":
        raise RuntimeError("no hero mesh")
    t0 = time.time()
    tris_before = len(o.data.polygons)
    # intact copy: UV/material transfer source AND the restore point on failure
    src = o.copy(); src.data = o.data.copy(); src.name = HERO + "_src"
    bpy.context.scene.collection.objects.link(src)

    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    # live object scale/rotation flips normals downstream; game-bake textures
    # are UV-mapped (transform-independent) so applying here is safe.
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # 1) voxel remesh -> manifold watertight shell. Density guard: huge voxel
    # outputs once blew the bridge timeout — re-voxel coarser until tractable.
    diag = float(np.linalg.norm(np.array(o.dimensions)))
    vox = max(diag / 120.0, 0.006)
    for _try in range(3):
        mod = o.modifiers.new("VoxRemesh", "REMESH")
        mod.mode = "VOXEL"
        mod.voxel_size = vox
        bpy.ops.object.modifier_apply(modifier=mod.name)
        if len(o.data.polygons) <= 90000:
            break
        vox *= 1.7
    vox_faces = len(o.data.polygons)

    # 2) hygiene: loose bits, doubles, degenerates, consistent normals
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.delete_loose()
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=1e-5)
    bpy.ops.mesh.dissolve_degenerate(threshold=1e-5)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    # 3) keep only the LARGEST island — voxel remesh emits interior shells
    # (cavities) and shard leftovers; they are invisible junk that also breaks
    # downstream global-orientation checks.
    import bmesh
    bm = bmesh.new(); bm.from_mesh(o.data); bm.verts.ensure_lookup_table()
    seen = set(); comps = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack = [v]; comp = set()
        while stack:
            u = stack.pop()
            if u.index in comp:
                continue
            comp.add(u.index)
            for e in u.link_edges:
                w = e.other_vert(u)
                if w.index not in comp:
                    stack.append(w)
        seen |= comp; comps.append(comp)
    islands = len(comps)
    if islands > 1:
        big = max(comps, key=len)
        doomed = [bm.verts[i] for c in comps if c is not big for i in c]
        bmesh.ops.delete(bm, geom=doomed, context="VERTS")
        bm.to_mesh(o.data); o.data.update()
    bm.free()

    # 4) QuadriFlow, BEST-EFFORT (see module docstring): keep voxel mesh on
    # CANCELLED — it already carries the keystone value.
    qf = "cancelled"
    try:
        ret = bpy.ops.object.quadriflow_remesh(mode="FACES",
                                               target_faces=int(TARGET_FACES),
                                               seed=7, use_mesh_symmetry=False)
        if "FINISHED" in ret and len(o.data.polygons) >= 500:
            qf = "ok"
    except Exception as _qe:
        qf = "exc: %s" % str(_qe)[:80]

    # 5) bring the texture across: UVs by nearest-face interp + materials.
    if not o.data.uv_layers:
        o.data.uv_layers.new(name="UVMap")
    dt = o.modifiers.new("XferUV", "DATA_TRANSFER")
    dt.object = src
    dt.use_loop_data = True
    dt.data_types_loops = {"UV"}
    dt.loop_mapping = "POLYINTERP_NEAREST"
    bpy.ops.object.datalayout_transfer(modifier=dt.name)
    bpy.ops.object.modifier_apply(modifier=dt.name)
    o.data.materials.clear()
    for m in src.data.materials:
        o.data.materials.append(m)
    bpy.ops.object.shade_smooth()

    bpy.data.objects.remove(src, do_unlink=True)
    out = {"ok": True, "tris_before": tris_before, "vox_faces": vox_faces,
           "faces_after": len(o.data.polygons), "islands": islands,
           "quadriflow": qf, "voxel": round(vox, 5),
           "secs": round(time.time() - t0, 1)}
except Exception as e:
    # RESTORE the original mesh data on any failure — the hero may already be
    # voxel-remeshed (UVs destroyed) when a later stage dies.
    try:
        if "src" in dir() and src and src.name in bpy.data.objects:
            _old = o.data
            o.data = src.data
            src.data = _old
            bpy.data.objects.remove(src, do_unlink=True)
    except Exception:
        pass
    out = {"ok": False, "reason": "%s: %s" % (type(e).__name__, e)}
__result__ = json.dumps(out)
'''


def enabled() -> bool:
    return os.environ.get("FS_RETOPO", "0") == "1"


def code(hero: str = "Hero", target_faces: int = 12000) -> str:
    return (RETOPO_CODE
            .replace("__HERO__", hero)
            .replace("__FACES__", str(int(target_faces))))


def run(hero: str = "Hero", target_faces: int = 12000, timeout: float = 420.0):
    """Execute the retopo pass over the bridge with a LONG timeout —
    QuadriFlow/voxel work is CPU-heavy and the registry's default 60 s once
    cut it off mid-crunch."""
    import json as _json
    from app.mcp import blender_bridge as _bb
    res = _bb.call("execute_python", {"code": code(hero, target_faces)},
                   timeout=timeout)
    raw = res.get("result") if isinstance(res, dict) else None
    try:
        return _json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return raw
