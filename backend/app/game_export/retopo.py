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


class _Whole(Exception):
    """The mesh is already one connected body: nothing here would improve it."""



HERO = "__HERO__"; TARGET_FACES = __FACES__
o = bpy.data.objects.get(HERO)
out = {"ok": False, "reason": ""}
try:
    if o is None or o.type != "MESH":
        raise RuntimeError("no hero mesh")
    t0 = time.time()
    tris_before = len(o.data.polygons)

    # A BODY THAT IS ALREADY WHOLE IS LEFT ALONE (2026-09-29). This pass
    # exists for a shredded shell; a mesh that is already one connected body
    # gains nothing from it and LOSES its texture, because a remesh has to be
    # re-textured and both ways of doing that cost something: a Cycles bake
    # leaves specks along every UV seam, and a nearest-face UV transfer
    # speckles anything whose atlas is a thousand small islands, which a
    # generated character's is. Measured on the shelf: a character optimized
    # at 80 k is 91 to 99 per cent one piece and needs nothing; the shredded
    # ones are all older 45 k bakes. So: count the islands first, and hand
    # back an untouched mesh with its original texture when it is whole.
    # WELD BEFORE COUNTING (2026-09-29). glTF splits a vertex at every UV
    # seam, and a generated atlas has a thousand of them, so raw edge
    # connectivity calls a perfectly closed body a thousand islands. Welding
    # by position first is what assetmeta does and what the question means:
    # is this ONE SURFACE. Positions are quantised to a tenth of a millimetre
    # of the body's size, then union-find runs over the edges.
    _nv = len(o.data.vertices)
    _co = np.empty(_nv * 3, dtype=np.float64); o.data.vertices.foreach_get("co", _co)
    _co = _co.reshape(-1, 3)
    _q = np.round(_co / max(float(np.linalg.norm(np.array(o.dimensions))) * 1e-4, 1e-6)).astype(np.int64)
    _, _weld = np.unique(_q, axis=0, return_inverse=True)
    _ne = len(o.data.edges)
    _ev = np.empty(_ne * 2, dtype=np.int64); o.data.edges.foreach_get("vertices", _ev)
    _ev = _weld[_ev.reshape(-1, 2)]
    _par = np.arange(len(_)); 
    def _find(x):
        while _par[x] != x:
            _par[x] = _par[_par[x]]; x = _par[x]
        return x
    for _a0, _b0i in _ev:
        _ra, _rb = _find(int(_a0)), _find(int(_b0i))
        if _ra != _rb:
            _par[_ra] = _rb
    _roots = np.array([_find(i) for i in range(len(_par))])
    _counts = np.bincount(_roots)
    _sizes0 = _counts[_counts > 0]
    _largest0 = float(_sizes0.max()) / max(1.0, float(_sizes0.sum()))
    # THE LAYERS UNDERNEATH (2026-09-25). A generated character is not a
    # surface, it is a stack: a coat over a shirt over a body, each modelled
    # whole, each crossing the others by a fraction of a millimetre all over.
    # Nothing of the inner layers should ever be seen, and almost none of it
    # is, but the fraction that pokes through paints its own colour where it
    # comes out, which is the rash of white and skin-coloured flecks on a dark
    # coat that survives every fix aimed at the texture. Rebuilding the body
    # as one hull does remove them, and costs the face: at any voxel size
    # coarse enough to bridge a collar, a nose is gone. So the inner layers
    # are deleted instead. A voxel hull is built as a RULER, never shipped,
    # and every face of the original sitting more than a hair inside it goes.
    # What pokes out is then cut by colour, below, and whatever is left
    # holding nothing falls away with the loose scraps. Measured on the
    # keeper, the skin-coloured share of the surface goes from 8.4% to 6.0%,
    # of which the face and the hands are about half: most of the rash goes,
    # a little stays. The surface that remains is the generated one, with the
    # UVs that made the reference look right.
    # A SHREDDED SHELL IS NOT CLEANED, IT IS REBUILT (2026-09-29). Everything
    # below removes what does not belong to the body, which only means
    # something when there IS a body: a mesh whose largest island already
    # carries four fifths of it. Run the same steps on a shell that arrived in
    # a thousand pieces and they remove the shell. That is the voxel remesh's
    # job, further down, and the test for which one runs has to be made HERE,
    # before anything is deleted, not afterwards when every survivor looks
    # like one island.
    if _largest0 >= 0.80:
        _main = int(np.argmax(_counts))
        _kill = np.nonzero(_roots[_weld] != _main)[0].tolist()
        import bmesh as _bm

        def _drop_verts(ob, ids):
            if not len(ids):
                return 0
            _b = _bm.new(); _b.from_mesh(ob.data); _b.verts.ensure_lookup_table()
            _bm.ops.delete(_b, geom=[_b.verts[int(i)] for i in ids], context="VERTS")
            _b.to_mesh(ob.data); _b.free(); ob.data.update()
            return len(ids)

        def _islands(ob):
            """welded island id per vertex, biggest first"""
            _n = len(ob.data.vertices)
            _c = np.empty(_n * 3, dtype=np.float64); ob.data.vertices.foreach_get("co", _c)
            _c = _c.reshape(-1, 3)
            _sp = max(float(np.linalg.norm(np.array(ob.dimensions))) * 1e-4, 1e-6)
            _, _w = np.unique(np.round(_c / _sp).astype(np.int64), axis=0, return_inverse=True)
            _w = _w.reshape(-1)
            _e = np.empty(len(ob.data.edges) * 2, dtype=np.int64)
            ob.data.edges.foreach_get("vertices", _e)
            _e = _w[_e.reshape(-1, 2)]
            _p = np.arange(int(_w.max()) + 1)

            def _f(x):
                while _p[x] != x:
                    _p[x] = _p[_p[x]]; x = _p[x]
                return x
            for _x, _y in _e:
                _rx, _ry = _f(int(_x)), _f(int(_y))
                if _rx != _ry:
                    _p[_rx] = _ry
            _r = np.array([_f(i) for i in range(len(_p))])
            return _w, _r, np.bincount(_r)

        _drop_verts(o, _kill)

        # WHAT POKES THROUGH (2026-09-25). The layers cross each other, so in
        # places a patch of shirt stands a fraction of a millimetre proud of the
        # coat. There it IS the outer surface, so no measurement of depth will
        # find it; what gives it away is that it is the wrong colour for where it
        # is. Every triangle is asked what colour it carries and what the
        # triangles around it carry, and one that disagrees with a neighbourhood
        # that agrees with itself is not part of this garment. It is cut out. The
        # coat behind it is still there, and where it is not, the hole is stitched
        # shut afterwards and takes its colour from the edges it closes.
        _flecked = 0
        try:
            _img = None
            for _mt in o.data.materials:
                if not (_mt and _mt.use_nodes):
                    continue
                for _nd in _mt.node_tree.nodes:
                    if _nd.type == "BSDF_PRINCIPLED":
                        _li = _nd.inputs["Base Color"].links
                        if _li and _li[0].from_node.type == "TEX_IMAGE":
                            _img = _li[0].from_node.image
                if _img is None:
                    for _nd in _mt.node_tree.nodes:
                        if (_nd.type == "TEX_IMAGE" and _nd.image
                                and (_nd.image.colorspace_settings.name or "").lower() in ("srgb", "")):
                            _img = _nd.image; break
                if _img is not None:
                    break
            if _img is not None and _img.size[0] >= 8 and o.data.uv_layers:
                _W, _H = _img.size
                _px = np.empty(_W * _H * 4, dtype=np.float32); _img.pixels.foreach_get(_px)
                _px = _px.reshape(_H, _W, 4)[:, :, :3]
                o.data.calc_loop_triangles()
                _lt = o.data.loop_triangles
                _nt = len(_lt)
                _tv = np.empty(_nt * 3, dtype=np.int32); _lt.foreach_get("vertices", _tv); _tv = _tv.reshape(-1, 3)
                _tl = np.empty(_nt * 3, dtype=np.int32); _lt.foreach_get("loops", _tl); _tl = _tl.reshape(-1, 3)
                _tf = np.empty(_nt, dtype=np.int32); _lt.foreach_get("polygon_index", _tf)
                _ua = np.empty(len(o.data.loops) * 2); o.data.uv_layers.active.data.foreach_get("uv", _ua)
                _cuv = _ua.reshape(-1, 2)[_tl].mean(axis=1)
                _sx = np.clip((_cuv[:, 0] % 1.0 * _W).astype(np.int64), 0, _W - 1)
                _sy = np.clip(((1.0 - _cuv[:, 1] % 1.0) * _H).astype(np.int64), 0, _H - 1)
                _col = _px[_sy, _sx] * 255.0
                _cc = np.empty(len(o.data.vertices) * 3); o.data.vertices.foreach_get("co", _cc)
                _cc = _cc.reshape(-1, 3)
                _sp = max(float(np.linalg.norm(np.array(o.dimensions))) * 1e-4, 1e-6)
                _, _wv = np.unique(np.round(_cc / _sp).astype(np.int64), axis=0, return_inverse=True)
                _wt = _wv.reshape(-1)[_tv]
                _e = np.sort(np.concatenate([_wt[:, [0, 1]], _wt[:, [1, 2]], _wt[:, [2, 0]]]), axis=1)
                _own = np.tile(np.arange(_nt), 3)
                _o2 = np.lexsort((_own, _e[:, 1], _e[:, 0]))
                _e, _own = _e[_o2], _own[_o2]
                _same = np.all(_e[1:] == _e[:-1], axis=1)
                if _same.any():
                    _pr = np.concatenate([np.stack([_own[:-1][_same], _own[1:][_same]], 1),
                                          np.stack([_own[1:][_same], _own[:-1][_same]], 1)])
                    # THE SIZE OF THE QUESTION (2026-09-25). A patch of shirt
                    # showing through a coat is not one triangle, it is thirty, so
                    # asking a triangle's immediate neighbours what colour it
                    # should be gets the answer "shirt" from the rest of the
                    # patch. The comparison has to reach past the whole intruder,
                    # and six rounds of averaging over the surface reach about a
                    # finger's width: far enough to find the garment, near enough
                    # that a sleeve is not asked to match a trouser leg.
                    _sm = _col.copy()
                    for _ in range(6):
                        _acc = np.zeros((_nt, 3), np.float32); _cnt = np.zeros(_nt, np.float32)
                        np.add.at(_acc, _pr[:, 0], _sm[_pr[:, 1]]); np.add.at(_cnt, _pr[:, 0], 1.0)
                        _sm = np.where(_cnt[:, None] > 0,
                                       (_acc + _sm) / (np.maximum(_cnt, 1) + 1)[:, None], _sm)
                    _off = np.abs(_col - _sm).max(axis=1)
                    _cand = _off > __FLECK__
                    # ... and what is cut has to be SMALL. The face and the hands
                    # disagree with the coat too, and they are meant to: they are
                    # whole regions of the body, not intruders. So the mismatched
                    # triangles are grouped, and only the little groups go.
                    _cut = []
                    if _cand.any():
                        _both = _cand[_pr[:, 0]] & _cand[_pr[:, 1]]
                        _par2 = np.arange(_nt)

                        def _f2(x):
                            while _par2[x] != x:
                                _par2[x] = _par2[_par2[x]]; x = _par2[x]
                            return x
                        for _x, _y in _pr[_both]:
                            _rx, _ry = _f2(int(_x)), _f2(int(_y))
                            if _rx != _ry:
                                _par2[_rx] = _ry
                        _lab = np.array([_f2(int(i)) if _cand[i] else -1 for i in range(_nt)])
                        _cl, _sz2 = np.unique(_lab[_lab >= 0], return_counts=True)
                        _small = set(_cl[_sz2 <= max(int(_nt * 0.004), 24)].tolist())
                        _cut = np.unique(_tf[np.array([l in _small for l in _lab])]).tolist() if _small else []
                    # the same restraint: a tenth of the body may be the wrong
                    # colour for where it sits, a quarter of it cannot be
                    if _cut and len(_cut) < len(o.data.polygons) * 0.10:
                        _b = _bm.new(); _b.from_mesh(o.data); _b.faces.ensure_lookup_table()
                        _bm.ops.delete(_b, geom=[_b.faces[int(i)] for i in _cut], context="FACES")
                        _b.to_mesh(o.data); _b.free(); o.data.update()
                        _flecked = len(_cut)
        except Exception as _fe:
            _flecked = -1

        _inner = 0
        try:
            # the ruler: a watertight hull of the whole stack, coarse enough to
            # bridge the gaps between layers and never shipped anywhere
            _hull = o.copy(); _hull.data = o.data.copy(); _hull.name = HERO + "_hull"
            bpy.context.scene.collection.objects.link(_hull)
            _vox = max(float(max(o.dimensions)) / 180.0, 1e-4)
            _rm = _hull.modifiers.new("Hull", "REMESH")
            _rm.mode = "VOXEL"; _rm.voxel_size = _vox; _rm.adaptivity = 0.0
            bpy.ops.object.select_all(action="DESELECT")
            bpy.context.view_layer.objects.active = _hull; _hull.select_set(True)
            bpy.ops.object.modifier_apply(modifier=_rm.name)
            from mathutils import Vector as _V
            from mathutils.bvhtree import BVHTree as _BVH
            _hv = np.empty(len(_hull.data.vertices) * 3); _hull.data.vertices.foreach_get("co", _hv)
            _hv = _hv.reshape(-1, 3)
            _hull.data.calc_loop_triangles()
            _hl = _hull.data.loop_triangles
            _hi = np.empty(len(_hl) * 3, dtype=np.int32); _hl.foreach_get("vertices", _hi)
            _bvhull = _BVH.FromPolygons([_V(x) for x in _hv.tolist()],
                                        [tuple(t) for t in _hi.reshape(-1, 3).tolist()],
                                        all_triangles=True)
            _nf = len(o.data.polygons)
            _fc = np.empty(_nf * 3); o.data.polygons.foreach_get("center", _fc)
            _fc = _fc.reshape(-1, 3).tolist()
            _deep = float(_vox) * 0.75            # a hair inside the hull is still the surface
            _inside = []
            _nearest = _bvhull.find_nearest
            for _i in range(_nf):
                _h = _nearest(_V(_fc[_i]))
                if _h is None or _h[0] is None:
                    continue
                _d = _V(_fc[_i]) - _h[0]
                if _d.length > _deep and _d.dot(_h[1]) < 0.0:
                    _inside.append(_i)
            # A BODY HAS FEW INNER FACES. If this test wants to delete a large
            # share of the mesh it has not found a shirt under a coat, it has
            # found a surface it cannot read, and deleting it would leave a
            # fragment. Above a sixth of the figure, nothing is cut.
            if _inside and len(_inside) < _nf * 0.16:
                _b = _bm.new(); _b.from_mesh(o.data); _b.faces.ensure_lookup_table()
                _bm.ops.delete(_b, geom=[_b.faces[int(i)] for i in _inside], context="FACES")
                _b.to_mesh(o.data); _b.free(); o.data.update()
                _inner = len(_inside)
            bpy.data.objects.remove(_hull, do_unlink=True)
        except Exception as _he:
            _inner = -1

        # whatever was left holding onto the inner layers is loose now
        _w2, _r2, _c2 = _islands(o)
        _keepers = int(np.argmax(_c2))
        _loose = np.nonzero(_r2[_w2] != _keepers)[0].tolist()
        _drop_verts(o, _loose)
        _w3, _r3, _c3 = _islands(o)
        _sz = _c3[_c3 > 0]
        _share = float(_sz.max()) / max(1.0, float(_sz.sum()))
        if len(o.data.polygons) > TARGET_FACES:
            raise _Whole("%d loose verts, %d flecked faces, %d inner faces, %d "
                         "stragglers removed; largest island %.3f"
                         % (len(_kill), _flecked, _inner, len(_loose), _share))

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
    # A BODY, NOT A BLOB (2026-09-27): diag/120 gave a 1.8 m figure 6,800
    # faces and no collar, hands or lapels; a half-centimetre voxel keeps
    # them (about 160 k quads on a figure), decimated to the target after.
    # a figure's diagonal is mostly its height; a long animal's is its length,
    # and diag/400 on a wolf blew the remesh past memory (2026-09-28): the
    # voxel is a fixed fraction of the LARGEST dimension instead, and coarser
    # for a body that is longer than tall
    _dims = sorted([float(o.dimensions.x), float(o.dimensions.y), float(o.dimensions.z)])
    _tall = _dims[2] > 0.9 * max(_dims[0], _dims[1]) and abs(float(o.dimensions.z) - _dims[2]) < 1e-6
    vox = max(_dims[2] / (360.0 if _tall else 220.0), 0.004)
    def _remesh(vx):
        mod = o.modifiers.new("VoxRemesh", "REMESH")
        mod.mode = "VOXEL"
        mod.voxel_size = vx
        bpy.ops.object.modifier_apply(modifier=mod.name)
    def _islands_of(obj):
        import bmesh as _bm
        bm = _bm.new(); bm.from_mesh(obj.data); bm.verts.ensure_lookup_table()
        seen = set(); sizes = []
        for v in bm.verts:
            if v.index in seen: continue
            stack = [v]; comp = set()
            while stack:
                u = stack.pop()
                if u.index in comp: continue
                comp.add(u.index)
                for e in u.link_edges:
                    w = e.other_vert(u)
                    if w.index not in comp: stack.append(w)
            seen |= comp; sizes.append(len(comp))
        bm.free()
        return len(sizes), (max(sizes) / max(1, sum(sizes)) if sizes else 0.0)
    # AN OPEN SHELL IS GIVEN A THICKNESS FIRST (2026-09-28): an animal's
    # surface has no inside, and the voxel remesh of a sheet is layered
    # slices; if the plain remesh comes out shredded the original is
    # solidified two voxels thick and remeshed again, which closes it.
    solidified = False
    for _try in range(3):
        _remesh(vox)
        if len(o.data.polygons) > 260000:
            o.data = src.data.copy(); vox *= 1.5; continue
        _isl, _kept = _islands_of(o)
        if (_isl > 40 or _kept < 0.6) and not solidified:
            o.data = src.data.copy()
            sm = o.modifiers.new("Solid", "SOLIDIFY"); sm.thickness = vox * 2.5; sm.offset = 0.0
            bpy.ops.object.modifier_apply(modifier=sm.name)
            solidified = True
            _remesh(vox)
        break
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
    big = max(comps, key=len) if comps else set()
    kept = len(big) / max(1, sum(len(c) for c in comps))
    if islands > 1:
        doomed = [bm.verts[i] for c in comps if c is not big for i in c]
        bmesh.ops.delete(bm, geom=doomed, context="VERTS")
        bm.to_mesh(o.data); o.data.update()
    bm.free()
    # THE SHELL MUST BE ONE BODY (2026-09-27): an open surface voxelizes into
    # layered slices, hundreds of islands with the largest a sliver of the
    # whole; that is not a body and the original is restored instead
    if islands > 40 or kept < 0.6:
        raise RuntimeError("shredded: %d islands, largest %.2f of the shell" % (islands, kept))

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

    # 4b) down to the budget: the voxel shell is dense and even, the game
    # wants about __TRIS__ triangles; collapse keeps the shape
    if qf != "ok":
        _tris_now = sum(len(pg.vertices) - 2 for pg in o.data.polygons)
        if _tris_now > int(__TRIS__):
            dm = o.modifiers.new("Dec", "DECIMATE"); dm.ratio = float(__TRIS__) / float(_tris_now)
            bpy.ops.object.modifier_apply(modifier=dm.name)

    # 5) THE TEXTURE IS THE ORIGINAL'S, CARRIED ACROSS (2026-09-29). A Cycles
    # bake onto fresh UVs RESAMPLES the whole figure: it leaves specks along
    # every UV seam and holes wherever a ray missed the old surface, and on a
    # human that reads as blotches and gaps. The dense shell sits within a
    # millimetre of the original, so nearest-face interpolation carries the
    # original UVs over exactly, texture and all, with nothing resampled.
    # The first trial's blocky transfer was the COARSE remesh's fault (6.8k
    # faces), not the method's: at 60k it is exact. The animals proved it,
    # their bakes failed and their fallback coats were the clean ones.
    # FACE-LOCKED UV TRANSFER (2026-09-25). Blender's POLYINTERP_NEAREST picks
    # a source polygon per LOOP, so the three corners of one new triangle can
    # land in three different islands of a 1300-island atlas. The triangle then
    # samples a path across the whole sheet and paints a fleck of somebody
    # else's colour: the speckle that reads as dirt on a coat and as gaps in a
    # face. Here the source triangle is chosen once per DESTINATION FACE, from
    # the nearest point on the original surface, and all of that face's corners
    # read their UV from that one triangle. Barycentric weights are clamped
    # into the triangle, so no corner can slide off its island into the black
    # gutter either. Nothing is resampled; the original atlas ships untouched.
    bake = "transfer"; nhead = 0
    try:
        from mathutils import Vector as _V
        from mathutils.bvhtree import BVHTree as _BVH
        sme, dme = src.data, o.data
        suv = sme.uv_layers.active
        if suv is None:
            raise RuntimeError("the original carried no UV map")
        sme.calc_loop_triangles()
        _lt = sme.loop_triangles
        _sv = np.empty(len(sme.vertices) * 3); sme.vertices.foreach_get("co", _sv)
        _sv = _sv.reshape(-1, 3)
        _ti = np.empty(len(_lt) * 3, dtype=np.int32); _lt.foreach_get("vertices", _ti)
        _tl = np.empty(len(_lt) * 3, dtype=np.int32); _lt.foreach_get("loops", _tl)
        _ti = _ti.reshape(-1, 3); _tl = _tl.reshape(-1, 3)
        _ua = np.empty(len(sme.loops) * 2); suv.data.foreach_get("uv", _ua)
        _tuv = _ua.reshape(-1, 2)[_tl]                       # (tri, corner, uv)
        _tp = _sv[_ti]                                       # (tri, corner, xyz)
        bvh = _BVH.FromPolygons([_V(x) for x in _sv.tolist()],
                                [tuple(t) for t in _ti.tolist()], all_triangles=True)

        _np_ = len(dme.polygons)
        _ps = np.empty(_np_, dtype=np.int32); dme.polygons.foreach_get("loop_start", _ps)
        _pt = np.empty(_np_, dtype=np.int32); dme.polygons.foreach_get("loop_total", _pt)
        if not (len(_ps) and _ps[0] == 0 and int(_ps[-1] + _pt[-1]) == len(dme.loops)):
            raise RuntimeError("loops are not laid out face by face")
        _cen = np.empty(_np_ * 3); dme.polygons.foreach_get("center", _cen)
        _cen = _cen.reshape(-1, 3)
        # WHICH SURFACE DID THIS FACE COME FROM (2026-09-25). A generated
        # character is layered, with a shirt under the coat and a body under
        # that, so the nearest point on the original is not always the one a
        # player would see. Standing off along the new face's own normal and
        # casting back in takes the FIRST surface the outside world can reach,
        # which is the garment every time. Only when nothing is hit does the
        # nearest point decide. Choosing once per FACE, rather than once per
        # corner as Blender's own transfer does, keeps a triangle from
        # sampling a path across an atlas whose neighbours are strangers.
        _pn = np.empty(_np_ * 3); dme.polygons.foreach_get("normal", _pn)
        _pn = _pn.reshape(-1, 3).tolist()
        _cl = _cen.tolist()
        _span = float(max(o.dimensions))
        _lift, _reach = _span * 0.02, _span * 0.06
        _pick = np.zeros(_np_, dtype=np.int64); _rays = 0
        _near, _cast = bvh.find_nearest, bvh.ray_cast
        for _i in range(_np_):
            _c, _n = _V(_cl[_i]), _V(_pn[_i])
            # the winding of a generated shell is not to be trusted, so the
            # hit is taken on position alone: first surface in, whichever way
            # its normal happens to face
            _r = _cast(_c + _n * _lift, -_n, _reach) if _n.length > 0.5 else None
            if _r is not None and _r[2] is not None:
                _rays += 1
            else:
                _r = _near(_c)
            if _r is not None and _r[2] is not None:
                _pick[_i] = _r[2]
        _miss = 0
        _lp = np.repeat(_pick, _pt.astype(np.int64))         # every loop takes its face's choice
        _lv = np.empty(len(dme.loops), dtype=np.int32); dme.loops.foreach_get("vertex_index", _lv)
        _dv = np.empty(len(dme.vertices) * 3); dme.vertices.foreach_get("co", _dv)
        P = _dv.reshape(-1, 3)[_lv]
        A, B, C = _tp[_lp, 0], _tp[_lp, 1], _tp[_lp, 2]
        e0, e1, d = B - A, C - A, P - A
        d00 = (e0 * e0).sum(1); d01 = (e0 * e1).sum(1); d11 = (e1 * e1).sum(1)
        d20 = (d * e0).sum(1); d21 = (d * e1).sum(1)
        den = d00 * d11 - d01 * d01
        den[np.abs(den) < 1e-20] = 1e-20
        b1 = np.clip((d11 * d20 - d01 * d21) / den, 0.0, 1.0)
        b2 = np.clip((d00 * d21 - d01 * d20) / den, 0.0, 1.0)
        _s = b1 + b2; _over = _s > 1.0
        b1[_over] /= _s[_over]; b2[_over] /= _s[_over]       # stay inside the triangle
        b0 = 1.0 - b1 - b2
        UV = (_tuv[_lp, 0] * b0[:, None] + _tuv[_lp, 1] * b1[:, None]
              + _tuv[_lp, 2] * b2[:, None])
        if not dme.uv_layers:
            dme.uv_layers.new(name="UVMap")
        dme.uv_layers.active.data.foreach_set("uv", UV.ravel())
        dme.update()
        o.data.materials.clear()
        for m in src.data.materials:
            o.data.materials.append(m)
        if not len(o.data.materials):
            raise RuntimeError("the original carried no material to hand over")
        bake = "transfer(outermost %d%%)" % round(100.0 * _rays / max(1, _np_))
    except Exception as _te:
        # the old per-loop transfer is still better than an untextured body
        try:
            if not o.data.uv_layers:
                o.data.uv_layers.new(name="UVMap")
            dt = o.modifiers.new("XferUV", "DATA_TRANSFER")
            dt.object = src
            dt.use_loop_data = True
            dt.data_types_loops = {"UV"}
            dt.loop_mapping = "POLYINTERP_NEAREST"
            bpy.ops.object.select_all(action="DESELECT")
            bpy.context.view_layer.objects.active = o; o.select_set(True)
            bpy.ops.object.datalayout_transfer(modifier=dt.name)
            bpy.ops.object.modifier_apply(modifier=dt.name)
            o.data.materials.clear()
            for m in src.data.materials:
                o.data.materials.append(m)
            bake = "transfer(per-loop fallback): %s" % str(_te)[:70]
        except Exception as _t2:
            bake = "transfer failed: %s" % str(_t2)[:90]
    bpy.ops.object.shade_smooth()

    bpy.data.objects.remove(src, do_unlink=True)
    out = {"ok": True, "tris_before": tris_before, "vox_faces": vox_faces,
           "faces_after": len(o.data.polygons), "islands": islands,
           "quadriflow": qf, "voxel": round(vox, 5), "bake": bake, "solidified": solidified, "head_faces": nhead,
           "secs": round(time.time() - t0, 1)}
except _Whole as _wh:
    out = {"ok": True, "skipped": "kept the original surface", "why": str(_wh),
           "faces_after": len(o.data.polygons),
           "tris_before": tris_before, "secs": round(time.time() - t0, 1)}
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
    # ON BY DEFAULT (2026-09-27): trialled on the scientist, the dense shell
    # with the baked texture deformed with no tears where the raw surface
    # tore at every joint; FS_RETOPO=0 turns it off.
    return os.environ.get("FS_RETOPO", "1") == "1"


def code(hero: str = "Hero", target_faces: int = 12000, target_tris: int = 80000) -> str:
    return (RETOPO_CODE
            .replace("__HERO__", hero)
            .replace("__FACES__", str(int(target_faces)))
            .replace("__FLECK__", os.environ.get("FS_RETOPO_FLECK", "56"))
            .replace("__TRIS__", str(int(target_tris))))


def run(hero: str = "Hero", target_faces: int = 12000, timeout: float = 900.0):
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
