"""Skin V2 (Phase 54) — quadruped skinning quality pass, flag-gated.

The stock quadruped skin is Euclidean point-to-bone distance soft-blended over
the 3 nearest bones. Its failure mode is the visible "morphing": an inner-thigh
vertex is *Euclidean*-close to the OTHER leg's bone, binds to it, and stretches
when the legs separate (harness: polar_bear p95 edge stretch 0.93).

This module supplies a prelude of helpers that the rig templates call behind
the __SKINV2__ flag, refining the SAME dmat/weight pipeline the stock code
already runs — the stock lines stay byte-identical and are the automatic
fallback (every helper call sits in a try/except):

  1. Same-side / same-end constraints — a left-leg bone can never claim a
     clearly-right-side vertex (and front/back likewise). Ported from the
     proven biped mocap skin (mocap_retarget.py).
  2. Geodesic surface distance for LEG bones — pure numpy+heapq multi-source
     Dijkstra over the mesh edge graph (the bridge Python has no scipy).
     Surface distance makes the inner thigh "far" from the other leg even
     though it is physically near, which is the root of the morph.
  3. Laplacian weight smoothing + max-4-influence clamp — erases stray weights
     that cause subtle warping (same idea the biped path already uses).

Toggle: FS_SKIN_V2=0 disables (stock behavior, bit-for-bit).
"""
from __future__ import annotations

import os

# Injected ahead of the rig template. Defines helpers only — no side effects
# until the template calls them behind its __SKINV2__ gate.
SKIN_V2_PRELUDE = r'''
# ── skin v2 helpers (Phase 54) — see app/game_export/skin_v2.py ──
import numpy as _s2np
_S2 = {}

def _s2_csr(o, V):
    """Undirected mesh edge graph in CSR arrays (python lists for loop speed).

    WELDED BY POSITION: glTF splits vertices along UV-island borders, and the
    atlas texturing (texture_v2) creates MANY islands — an unwelded graph is
    fragmented at every seam and the geodesic falls apart (cat morph regressed
    0.61->0.73 when the atlas landed). Connectivity must follow GEOMETRY, so
    co-located verts are merged into canonical nodes for the graph; per-vertex
    lookups map through `canon`."""
    me = o.data
    nv = len(V)
    # canonical node per unique (rounded) position
    key = _s2np.round(V * 1e5).astype(_s2np.int64)
    _, canon_first, canon = _s2np.unique(key, axis=0,
                                         return_index=True, return_inverse=True)
    canon = canon.astype(_s2np.int64)
    ncan = int(canon.max()) + 1 if nv else 0
    m = len(me.edges)
    E = _s2np.empty(m * 2, dtype=_s2np.int64)
    me.edges.foreach_get("vertices", E)
    E = canon[E.reshape(m, 2)]                      # edges between canonical nodes
    keep = E[:, 0] != E[:, 1]                       # drop degenerate self-edges
    E = E[keep]
    Vc = V[canon_first]                             # canonical positions
    w = _s2np.linalg.norm(Vc[E[:, 0]] - Vc[E[:, 1]], axis=1)
    src = _s2np.concatenate([E[:, 0], E[:, 1]])
    dst = _s2np.concatenate([E[:, 1], E[:, 0]])
    ww = _s2np.concatenate([w, w])
    order = _s2np.argsort(src, kind="stable")
    src, dst, ww = src[order], dst[order], ww[order]
    ptr = _s2np.zeros(ncan + 1, dtype=_s2np.int64)
    _s2np.add.at(ptr, src + 1, 1)
    ptr = _s2np.cumsum(ptr)
    _S2["csr"] = (dst, ww, ptr)
    _S2["csrL"] = (dst.tolist(), ww.tolist(), ptr.tolist())
    _S2["canon"] = canon
    _S2["ncan"] = ncan
    return _S2["csr"]

def _s2_dijkstra(ncan, seeds_can, seed_d, cap):
    """Multi-source Dijkstra over the CANONICAL CSR graph; inf where
    unreachable/beyond cap. Seeds and result are canonical-node indexed."""
    import heapq
    dstL, wwL, ptrL = _S2["csrL"]
    dist = [float("inf")] * ncan
    h = []
    for s, d0 in zip(seeds_can.tolist(), seed_d.tolist()):
        if d0 < dist[s]:
            dist[s] = d0
            h.append((d0, s))
    heapq.heapify(h)
    push, pop = heapq.heappush, heapq.heappop
    while h:
        d, u = pop(h)
        if d > dist[u] or d > cap:
            continue
        for k in range(ptrL[u], ptrL[u + 1]):
            v = dstL[k]
            nd = d + wwL[k]
            if nd < dist[v]:
                dist[v] = nd
                push(h, (nd, v))
    return _s2np.asarray(dist)

def _s2_refine_dmat(dmat, V, segs, names, o):
    """Constraints + geodesic distance for leg bones. Returns a refined COPY;
    any failure in the caller falls back to the original Euclidean dmat."""
    nv = len(V)
    X, Y = V[:, 0], V[:, 1]
    xmin, xmax = float(X.min()), float(X.max())
    ymin, ymax = float(Y.min()), float(Y.max())
    cx, ymid = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    Wd, Ld = xmax - xmin, ymax - ymin
    diag = float(_s2np.linalg.norm(V.max(0) - V.min(0)))
    out = dmat.copy()
    is_leg = [nm.startswith(("thigh_", "shin_")) for nm in names]
    # (1) same-side/same-end: leg bones never claim clearly-wrong-quadrant verts
    mx, my = 0.06 * Wd, 0.06 * Ld
    for bi, nm in enumerate(names):
        if not is_leg[bi]:
            continue
        key = nm.split("_", 1)[1]                 # FL / FR / BL / BR
        if "L" in key:
            out[X > cx + mx, bi] = 1e9
        if "R" in key:
            out[X < cx - mx, bi] = 1e9
        if "F" in key:
            out[Y < ymid - my, bi] = 1e9
        if "B" in key:
            out[Y > ymid + my, bi] = 1e9
    # (2) geodesic (surface) distance for leg bones (canonical graph — welded
    # by position so UV-seam vertex splits don't fragment connectivity)
    if "csr" not in _S2:
        _s2_csr(o, V)
    canon = _S2["canon"]; ncan = _S2["ncan"]
    cap = 0.5 * diag
    for bi, nm in enumerate(names):
        if not is_leg[bi]:
            continue
        col = out[:, bi]
        finite = col[col < 1e8]
        if not len(finite):
            continue
        r = max(float(finite.min()) * 1.6, 0.02 * diag)
        seeds = _s2np.where(col <= r)[0]
        if len(seeds) < 6:
            seeds = _s2np.argsort(col)[:6]
        geo_can = _s2_dijkstra(ncan, canon[seeds], col[seeds], cap)
        geo = geo_can[canon]                        # back to per-vertex
        ok = _s2np.isfinite(geo)
        # surface distance can only be >= straight-line; max() keeps the 1e9
        # constraints AND never lets a vert get CLOSER than Euclidean.
        col2 = col.copy()
        col2[ok] = _s2np.maximum(geo[ok], col[ok])
        out[:, bi] = col2
    return out

def _s2_smooth(wK, idxK, nb, V, o, iters=2, lam=0.5):
    """Laplacian-smooth the sparse weights over the CANONICAL mesh graph
    (position-welded), then re-sparsify to max 4 influences and renormalize.
    Also guarantees co-located seam-split verts get IDENTICAL weights."""
    nv = len(V)
    Wd = _s2np.zeros((nv, nb))
    _s2np.put_along_axis(Wd, idxK, wK, axis=1)
    if "csr" not in _S2:
        _s2_csr(o, V)
    dst, ww, ptr = _S2["csr"]
    canon = _S2["canon"]; ncan = _S2["ncan"]
    # collapse split verts to canonical nodes (mean of duplicates)
    Wc = _s2np.zeros((ncan, nb))
    cnt = _s2np.zeros(ncan)
    _s2np.add.at(Wc, canon, Wd)
    _s2np.add.at(cnt, canon, 1.0)
    Wc /= _s2np.maximum(cnt[:, None], 1.0)
    deg = _s2np.maximum(_s2np.diff(ptr), 1)
    src_rep = _s2np.repeat(_s2np.arange(ncan), _s2np.diff(ptr))
    for _ in range(iters):
        nb_sum = _s2np.zeros_like(Wc)
        _s2np.add.at(nb_sum, src_rep, Wc[dst])
        Wc = (1.0 - lam) * Wc + lam * (nb_sum / deg[:, None])
        Wc /= _s2np.maximum(Wc.sum(1, keepdims=True), 1e-9)
    Wd = Wc[canon]                                  # back to per-vertex
    K2 = min(4, nb)
    idx2 = _s2np.argsort(-Wd, axis=1)[:, :K2]
    w2 = _s2np.take_along_axis(Wd, idx2, 1)
    w2[w2 < 0.05] = 0.0
    w2 /= _s2np.maximum(w2.sum(1, keepdims=True), 1e-9)
    return w2, idx2
# ── end skin v2 helpers ──
'''


def enabled() -> bool:
    return os.environ.get("FS_SKIN_V2", "1") != "0"


def heat_enabled() -> bool:
    """Phase 71: bone-heat weights on a voxel-remeshed proxy, DataTransferred
    onto the hero. DEFAULT ON since 2026-07-15 — polar bear morph 0.702→0.326
    (−54%) with clean visual gait; falls back to manual weights on failure."""
    return os.environ.get("FS_SKIN_HEAT", "1") != "0"


def wrap(template: str) -> str:
    """Prepend the helper prelude and resolve the gate flags."""
    return SKIN_V2_PRELUDE + "\n" + template.replace(
        "__SKINV2__", "True" if enabled() else "False").replace(
        "__SKINHEAT__", "True" if heat_enabled() else "False")
