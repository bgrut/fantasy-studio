"""Texture V2 (Phase 60) — 1:1 reference texturing for CPU-generated heroes.

The v1 projection maps every vertex's UV from its length/height position —
a FLAT side projection. Flanks (surfaces facing the camera) sample the photo
sharply, but the FACE, chest and rump collapse onto a thin strip of photo
pixels and stretch across the whole surface: the "half-stretched face" the
owner reported on the polar bear and cat (the fox looked fine because it
kept a real TRELLIS-baked texture and never went through this projection).

V2 keeps the photo where it is trustworthy and synthesizes the rest:

  1. Smart-UV atlas — every surface point gets its OWN texel (no more
     many-to-one strip mapping).
  2. Numpy rasterizer bakes the atlas: each triangle samples the photo
     through the v1 projection UVs; its VALIDITY = |face normal . X| (how
     face-on the surface was to the reference camera).
  3. Texels below the validity floor (face/chest/rump smear zones) are
     INPAINTED from valid fur via pyramid pull-push diffusion; a blend band
     eases the transition.

Result: flanks stay 1:1 with the reference; forward/backward surfaces get
clean continuous fur instead of streaks. Runs entirely in the bridge (numpy,
no Cycles). Gate: FS_TEX_V2 (default ON); any failure keeps the v1 texture.
"""
from __future__ import annotations

import os

TEXTURE_V2_CODE = r'''
import bpy, json, time
import numpy as np
HERO = "__HERO__"; REF = r"__REF__"; REFRAW = r"__REFRAW__"
OUTPNG = r"__OUTPNG__"; S = __SIZE__
HI = 0.50; LO = 0.28
o = bpy.data.objects.get(HERO)
out = {"ok": False, "reason": ""}
try:
    t0 = time.time()
    if o is None or o.type != "MESH":
        raise RuntimeError("no hero mesh")
    me = o.data
    src_uvl = me.uv_layers.get("RefProj")
    if src_uvl is None:
        raise RuntimeError("no RefProj UVs (v1 projection must run first)")

    # ── 1) smart-UV atlas into its own layer ──
    for l in me.uv_layers:
        l.active = (l.name == "Atlas") if me.uv_layers.get("Atlas") else False
    atlas = me.uv_layers.get("Atlas") or me.uv_layers.new(name="Atlas")
    me.uv_layers.active = atlas
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.003)
    bpy.ops.object.mode_set(mode="OBJECT")
    # RE-FETCH layers: mode toggles free + reallocate UV layer data — the old
    # python references read garbage (98% NaN) while reporting FINISHED.
    src_uvl = me.uv_layers.get("RefProj")
    atlas = me.uv_layers.get("Atlas")

    # ── 2) gather geometry (loop triangles, both UV sets, world normals) ──
    me.calc_loop_triangles()
    nl = len(me.loops)
    lvi = np.empty(nl, dtype=np.int64)
    me.loops.foreach_get("vertex_index", lvi)
    suv = np.empty(nl * 2); src_uvl.data.foreach_get("uv", suv); suv = suv.reshape(nl, 2)
    auv = np.empty(nl * 2); atlas.data.foreach_get("uv", auv); auv = auv.reshape(nl, 2)
    nvv = len(me.vertices)
    co = np.empty(nvv * 3); me.vertices.foreach_get("co", co); co = co.reshape(nvv, 3)
    mw = np.array(o.matrix_world, dtype=np.float64)
    cow = co @ mw[:3, :3].T + mw[:3, 3]
    ntri = len(me.loop_triangles)
    tls = np.empty(ntri * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("loops", tls); tls = tls.reshape(ntri, 3)

    diag0 = float(np.linalg.norm(cow.max(0) - cow.min(0)))
    tv = lvi[tls]                                  # (ntri,3) vertex ids
    p0, p1, p2 = cow[tv[:, 0]], cow[tv[:, 1]], cow[tv[:, 2]]
    P3 = np.stack([p0, p1, p2], 1)                 # (ntri,3verts,3xyz)
    fn = np.cross(p1 - p0, p2 - p0)
    fl = np.linalg.norm(fn, axis=1); fl[fl < 1e-12] = 1.0
    validity = np.abs(fn[:, 0] / fl)               # |normal . X| (ref camera axis)

    # ── reference image pixels (background-FILLED copy for color) ──
    rimg = bpy.data.images.load(REF, check_existing=True)
    rw, rh = rimg.size
    rpx = np.empty(rw * rh * 4, dtype=np.float32)
    rimg.pixels.foreach_get(rpx)
    rpx = rpx.reshape(rh, rw, 4)[:, :, :3]         # bottom-up rows (matches UV V)

    # ── SILHOUETTE MASK from the RAW photo (Phase 62): geometric validity is
    # not enough — a face-on surface whose UV overreaches the subject samples
    # BACKGROUND and poisons the fill (the cat's blank patches). foreground =
    # saturated OR dark, border-trimmed (same detector the orient gate uses).
    mimg = bpy.data.images.load(REFRAW, check_existing=True)
    mw, mh = mimg.size
    mpx = np.empty(mw * mh * 4, dtype=np.float32)
    mimg.pixels.foreach_get(mpx)
    mpx = mpx.reshape(mh, mw, 4)[:, :, :3]
    _mx = mpx.max(2); _mn = mpx.min(2)
    _sat = (_mx - _mn) / (_mx + 1e-6)
    fgmask = (_sat > 0.18) | (_mx < 0.32)
    _by = int(mh * 0.04); _bx = int(mw * 0.04)
    _t = np.zeros_like(fgmask); _t[_by:mh-_by, _bx:mw-_bx] = fgmask[_by:mh-_by, _bx:mw-_bx]
    fgmask = _t

    def fg_at(uvs):
        x = np.clip((uvs[:, 0] * (mw - 1)).round().astype(np.int64), 0, mw - 1)
        y = np.clip((uvs[:, 1] * (mh - 1)).round().astype(np.int64), 0, mh - 1)
        return fgmask[y, x]

    def sample(uvs):
        x = np.clip(uvs[:, 0] * (rw - 1), 0, rw - 1)
        y = np.clip(uvs[:, 1] * (rh - 1), 0, rh - 1)
        x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64)
        x1 = np.minimum(x0 + 1, rw - 1); y1 = np.minimum(y0 + 1, rh - 1)
        fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
        return (rpx[y0, x0] * (1 - fx) * (1 - fy) + rpx[y0, x1] * fx * (1 - fy)
                + rpx[y1, x0] * (1 - fx) * fy + rpx[y1, x1] * fx * fy)

    # ── 3) rasterize the atlas (color + geo validity + foreground + world pos) ──
    color = np.zeros((S, S, 3), dtype=np.float32)
    val = np.full((S, S), -1.0, dtype=np.float32)
    fg = np.zeros((S, S), dtype=bool)              # source pixel inside subject?
    pos = np.zeros((S, S, 3), dtype=np.float32)    # world pos per texel (mirror)
    fg = np.zeros((S, S), dtype=bool)
    pos = np.zeros((S, S, 3), dtype=np.float32)     # world pos per texel (mirror fill)
    A = auv[tls] * (S - 1)                          # (ntri,3,2) atlas px coords
    SRC = suv[tls]                                  # (ntri,3,2) source UVs
    P3 = cow[tv]                                    # (ntri,3,3) world verts
    # degenerate faces can leave NaN UVs after smart_project — skip those tris
    tri_ok = np.isfinite(A).all(axis=(1, 2)) & np.isfinite(SRC).all(axis=(1, 2))
    for t in range(ntri):
        if not tri_ok[t]:
            continue
        a = A[t]; v = float(validity[t])
        xmin = max(int(np.floor(a[:, 0].min())), 0)
        xmax = min(int(np.ceil(a[:, 0].max())), S - 1)
        ymin = max(int(np.floor(a[:, 1].min())), 0)
        ymax = min(int(np.ceil(a[:, 1].max())), S - 1)
        if xmax < xmin or ymax < ymin:
            continue
        gx, gy = np.meshgrid(np.arange(xmin, xmax + 1), np.arange(ymin, ymax + 1))
        gx = gx.ravel().astype(np.float64); gy = gy.ravel().astype(np.float64)
        d = ((a[1, 1] - a[2, 1]) * (a[0, 0] - a[2, 0])
             + (a[2, 0] - a[1, 0]) * (a[0, 1] - a[2, 1]))
        if abs(d) < 1e-9:
            continue
        w0 = ((a[1, 1] - a[2, 1]) * (gx - a[2, 0]) + (a[2, 0] - a[1, 0]) * (gy - a[2, 1])) / d
        w1 = ((a[2, 1] - a[0, 1]) * (gx - a[2, 0]) + (a[0, 0] - a[2, 0]) * (gy - a[2, 1])) / d
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -0.001) & (w1 >= -0.001) & (w2 >= -0.001)
        if not inside.any():
            continue
        gxi = gx[inside].astype(np.int64); gyi = gy[inside].astype(np.int64)
        better = v > val[gyi, gxi]
        if not better.any():
            continue
        gxi = gxi[better]; gyi = gyi[better]
        wi = np.stack([w0[inside][better], w1[inside][better], w2[inside][better]], 1)
        suv_t = wi @ SRC[t]
        color[gyi, gxi] = sample(suv_t)
        val[gyi, gxi] = v
        fg[gyi, gxi] = fg_at(suv_t)                 # source pixel inside subject?
        pos[gyi, gxi] = (wi @ P3[t]).astype(np.float32)

    covered = val >= 0
    # SILHOUETTE VALIDITY (Phase 62): trustworthy = face-on AND foreground.
    # Background-sampling texels are never valid and never seed the fill.
    good = (val >= LO) & fg

    # ── 3.5) BILATERAL SYMMETRY FILL (Phase 62): before diffusing, each bad
    # texel tries the texel of its MIRRORED surface point (x -> 2*cx - x) via
    # a voxel-hash lookup — real fur pattern beats any flat fill, and it is a
    # prior that holds for virtually every creature.
    cxw = (float(cow[:, 0].min()) + float(cow[:, 0].max())) / 2.0
    diagm = float(np.linalg.norm(cow.max(0) - cow.min(0)))
    cell = max(diagm / 110.0, 1e-4)
    def _hash(q):
        return (q[:, 0] * 73856093) ^ (q[:, 1] * 19349663) ^ (q[:, 2] * 83492791)
    gy_i, gx_i = np.where(good)
    if len(gy_i) > 100:
        gq = np.floor(pos[gy_i, gx_i] / cell).astype(np.int64)
        gh = _hash(gq)
        order = np.argsort(gh)
        gh_s = gh[order]; gsrc = np.stack([gy_i, gx_i], 1)[order]
        by_i, bx_i = np.where(covered & ~good)
        if len(by_i):
            bp = pos[by_i, bx_i].copy()
            bp[:, 0] = 2.0 * cxw - bp[:, 0]         # mirror about the sagittal plane
            bq = np.floor(bp / cell).astype(np.int64)
            bh = _hash(bq)
            idx = np.searchsorted(gh_s, bh)
            idx = np.clip(idx, 0, len(gh_s) - 1)
            hit = gh_s[idx] == bh
            sy = gsrc[idx[hit], 0]; sx = gsrc[idx[hit], 1]
            color[by_i[hit], bx_i[hit]] = color[sy, sx]
            good[by_i[hit], bx_i[hit]] = True
            mirror_filled = int(hit.sum())
        else:
            mirror_filled = 0
    else:
        mirror_filled = 0

    # ── 4) pyramid pull-push inpaint of everything still bad (and gutters) ──
    levels = [(color * good[:, :, None], good.astype(np.float32))]
    size = S
    while size > 4:
        c, w = levels[-1]
        size //= 2
        c2 = c.reshape(size, 2, size, 2, 3).sum((1, 3))
        w2 = w.reshape(size, 2, size, 2).sum((1, 3))
        cc = np.zeros_like(c2)
        nz = w2 > 0
        cc[nz] = c2[nz] / w2[nz][:, None]
        levels.append((cc * (nz[:, :, None]), nz.astype(np.float32)))
    fill = levels[-1][0].copy()
    for li in range(len(levels) - 2, -1, -1):
        c, w = levels[li]
        up = np.repeat(np.repeat(fill, 2, 0), 2, 1)[:c.shape[0], :c.shape[1]]
        fill = np.where(w[:, :, None] > 0, c, up)
    # de-block the diffusion (nearest-neighbor pyramid upsampling reads as
    # flat quads on chests/necks): a couple of 3x3 box blurs on the fill.
    for _ in range(3):
        f = fill.copy()
        f[1:-1, 1:-1] = (fill[:-2, :-2] + fill[:-2, 1:-1] + fill[:-2, 2:]
                         + fill[1:-1, :-2] + fill[1:-1, 1:-1] + fill[1:-1, 2:]
                         + fill[2:, :-2] + fill[2:, 1:-1] + fill[2:, 2:]) / 9.0
        fill = f
    # blend band LO..HI on FOREGROUND texels only: photo where confident,
    # inpaint where smeared; background samples never blend back in, and
    # mirror-filled texels keep their copied fur at full strength.
    amap = np.clip((val - LO) / max(HI - LO, 1e-6), 0.0, 1.0)
    amap[~fg] = 0.0
    amap[good & ~(fg & (val >= LO))] = 1.0          # mirror-filled -> full
    a = amap[:, :, None]
    final = fill * (1 - a) + color * a
    final = np.clip(final, 0.0, 1.0)

    # ── 5) write image + rewire material to the Atlas UV ──
    img = bpy.data.images.new("AtlasTex", S, S, alpha=False)
    px = np.ones((S, S, 4), dtype=np.float32)
    px[:, :, :3] = final
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = OUTPNG
    img.file_format = "PNG"
    img.save()
    mat = bpy.data.materials.new("AtlasMat")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.6
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "Atlas"
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    me.materials.clear()
    me.materials.append(mat)
    for l in me.uv_layers:
        l.active_render = (l.name == "Atlas")
    me.uv_layers.active = atlas

    out = {"ok": True, "tris": int(ntri), "texels_covered": int(covered.sum()),
           "texels_confident": int(good.sum()), "mirror_filled": mirror_filled,
           "bg_rejected": int((covered & (val >= LO) & ~fg).sum()),
           "diffused_pct": round(100.0 * (1 - good.sum() / max(covered.sum(), 1)), 1),
           "secs": round(time.time() - t0, 1)}
except Exception as e:
    out = {"ok": False, "reason": "%s: %s" % (type(e).__name__, e)}
__result__ = json.dumps(out)
'''


def enabled() -> bool:
    return os.environ.get("FS_TEX_V2", "1") != "0"


def run(hero: str, ref_png: str, out_png: str, size: int = 1024,
        timeout: float = 600.0):
    """Bake the v2 atlas texture over the bridge (long timeout — the
    rasterizer walks every triangle).

    Colors sample the background-FILLED reference copy when one exists
    (silhouette-edge overreach lands on fur tone, not studio gray); the
    foreground MASK always comes from the RAW photo (fill would defeat it)."""
    import json as _json
    from pathlib import Path as _P
    from app.mcp import blender_bridge as _bb
    raw_p = _P(ref_png).resolve()
    fill_p = raw_p.with_name(raw_p.stem + "_fill" + raw_p.suffix)
    color_p = fill_p if fill_p.exists() else raw_p
    code = (TEXTURE_V2_CODE
            .replace("__HERO__", hero)
            .replace("__REFRAW__", str(raw_p.as_posix()))
            .replace("__REF__", str(color_p.as_posix()))
            .replace("__OUTPNG__", str(_P(out_png).resolve().as_posix()))
            .replace("__SIZE__", str(int(size))))
    res = _bb.call("execute_python", {"code": code}, timeout=timeout)
    raw = res.get("result") if isinstance(res, dict) else None
    try:
        return _json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return raw
