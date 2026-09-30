"""A triangle rasteriser in plain PyTorch, standing in for nvdiffrast (2026-09-30).

TRELLIS.2 (MIT) bakes its texture with nvdiffrast, whose NVIDIA Source Code
License allows non-commercial use only: every model the studio generated
passed through software that may not be used to make things for sale. The
bake needs very little of it: rasterise the mesh's triangles in UV space so
every texel knows which triangle it lies in and where, then interpolate the
3D positions. This module does exactly that with ordinary tensor operations
(BSD-licensed PyTorch), and `install()` registers it under the names
`nvdiffrast` and `nvdiffrast.torch`, so TRELLIS.2 runs unmodified without
NVIDIA's library ever being imported.

Same conventions as nvdiffrast, so callers need no change:
  rasterize(ctx, pos[1,V,4] clip space, tri[F,3], resolution=[H,W])
      -> (rast[1,H,W,4] = (u, v, z/w, triangle_id + 1), None)
     row 0 is clip y = -1; pixel centres at half-integers; barycentrics are
     perspective-correct, with an attribute = u*a0 + v*a1 + (1-u-v)*a2; the
     nearest z/w wins where triangles overlap; 0 in the last channel is empty.
  interpolate(attr[1,V,C] or [V,C], rast, tri) -> (out[1,H,W,C], None)
"""
from __future__ import annotations

import sys
import types

import torch


class RasterizeCudaContext:                     # nvdiffrast's context, which holds nothing here
    def __init__(self, device=None, **_):
        self.device = device


RasterizeGLContext = RasterizeCudaContext


def rasterize(ctx, pos, tri, resolution, ranges=None, grad_db=True):
    H, W = int(resolution[0]), int(resolution[1])
    p = pos[0] if pos.dim() == 3 else pos
    dev = p.device
    t = tri.long()
    wclip = p[:, 3].clamp(min=1e-8)
    xs = (p[:, 0] / wclip * 0.5 + 0.5) * W - 0.5
    ys = (p[:, 1] / wclip * 0.5 + 0.5) * H - 0.5
    zs = p[:, 2] / wclip
    X, Y, Z, Wc = xs[t], ys[t], zs[t], wclip[t]                     # (F, 3)
    x0 = torch.ceil(X.min(1).values).clamp(0, W - 1).long()
    x1 = torch.floor(X.max(1).values).clamp(0, W - 1).long()
    y0 = torch.ceil(Y.min(1).values).clamp(0, H - 1).long()
    y1 = torch.floor(Y.max(1).values).clamp(0, H - 1).long()
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    off_screen = (X.max(1).values < 0) | (X.min(1).values > W - 1) | (Y.max(1).values < 0) | (Y.min(1).values > H - 1)
    size = torch.maximum(bw, bh)
    live = (bw > 0) & (bh > 0) & ~off_screen

    lins, deps, fids, us, vs = [], [], [], [], []
    lo = 0
    B = 1
    while True:
        sel = live & (size > lo) & (size <= B)
        idx = torch.nonzero(sel).flatten()
        if idx.numel():
            oy, ox = torch.meshgrid(torch.arange(B, device=dev), torch.arange(B, device=dev), indexing="ij")
            ox, oy = ox.reshape(-1), oy.reshape(-1)
            chunk = max(1, 6_000_000 // (B * B))
            for c in range(0, idx.numel(), chunk):
                f = idx[c:c + chunk]
                px = x0[f, None] + ox[None]
                py = y0[f, None] + oy[None]
                inb = (px <= x1[f, None]) & (py <= y1[f, None])
                ax, ay = X[f, 0:1], Y[f, 0:1]
                bx, by = X[f, 1:2], Y[f, 1:2]
                cx, cy = X[f, 2:3], Y[f, 2:3]
                den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
                ok = den.abs() > 1e-12
                den = torch.where(ok, den, torch.ones_like(den))
                pxf, pyf = px.float(), py.float()
                w0 = ((by - cy) * (pxf - cx) + (cx - bx) * (pyf - cy)) / den
                w1 = ((cy - ay) * (pxf - cx) + (ax - cx) * (pyf - cy)) / den
                w2 = 1.0 - w0 - w1
                eps = -1e-6
                inside = inb & ok & (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
                if not inside.any():
                    continue
                # perspective-correct weights (identity when w = 1, as in a UV bake)
                q0, q1, q2 = w0 / Wc[f, 0:1], w1 / Wc[f, 1:2], w2 / Wc[f, 2:3]
                qs = (q0 + q1 + q2).clamp(min=1e-12)
                u, v = q0 / qs, q1 / qs
                d = w0 * Z[f, 0:1] + w1 * Z[f, 1:2] + w2 * Z[f, 2:3]
                fid = f[:, None].expand_as(px)
                lins.append((py * W + px)[inside]); deps.append(d[inside])
                fids.append(fid[inside]); us.append(u[inside]); vs.append(v[inside])
        if B >= max(H, W) or not bool((live & (size > B)).any()):
            break
        lo, B = B, B * 2

    rast = torch.zeros((1, H, W, 4), device=dev, dtype=torch.float32)
    if lins:
        lin = torch.cat(lins); dep = torch.cat(deps); fid = torch.cat(fids)
        u = torch.cat(us); v = torch.cat(vs)
        # nearest first, then by texel: the first entry of each texel is the one seen
        o1 = torch.argsort(dep, stable=True)
        o2 = torch.argsort(lin[o1], stable=True)
        order = o1[o2]
        ls = lin[order]
        first = torch.ones_like(ls, dtype=torch.bool)
        first[1:] = ls[1:] != ls[:-1]
        win = order[first]
        flat = rast.view(-1, 4)
        flat[lin[win]] = torch.stack([u[win], v[win], dep[win], (fid[win] + 1).float()], dim=1)
    return rast, None


def interpolate(attr, rast, tri, rast_db=None, diff_attrs=None):
    a = attr[0] if attr.dim() == 3 else attr
    r = rast[0]
    H, W = r.shape[0], r.shape[1]
    fid = r[..., 3].long() - 1
    mask = fid >= 0
    out = torch.zeros((H, W, a.shape[-1]), device=a.device, dtype=a.dtype)
    if mask.any():
        t = tri.long()[fid[mask]]
        u = r[..., 0][mask].to(a.dtype)[:, None]
        v = r[..., 1][mask].to(a.dtype)[:, None]
        out[mask] = u * a[t[:, 0]] + v * a[t[:, 1]] + (1 - u - v) * a[t[:, 2]]
    return out[None], None


def install():
    """Register this module as nvdiffrast, before anything imports the real one."""
    torch_mod = types.ModuleType("nvdiffrast.torch")
    for name in ("RasterizeCudaContext", "RasterizeGLContext", "rasterize", "interpolate"):
        setattr(torch_mod, name, globals()[name])
    pkg = types.ModuleType("nvdiffrast")
    pkg.torch = torch_mod
    pkg.__path__ = []                              # a package, so "import nvdiffrast.torch" resolves
    sys.modules["nvdiffrast"] = pkg
    sys.modules["nvdiffrast.torch"] = torch_mod
    return torch_mod
