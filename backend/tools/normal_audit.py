"""Stored vertex normals against the geometry's own (2026-10-11).

The man's left eye read milky under a light but clean in a flat albedo
render, with a normal socket in the depth: the surface's stored normals,
not its paint or its shape. This compares each stored NORMAL with the
area-weighted normal of the faces round its position (vertices welded by
position, so UV seams do not count), reports how many disagree and where,
and with --fix writes the geometry's normals back into the GLB in place
(nothing else in the file changes).

usage: python tools/normal_audit.py man woman ...   [--fix] [--deg 35]
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np

LIB = Path(__file__).resolve().parents[1] / "assets" / "library"
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _load(p: Path):
    b = bytearray(p.read_bytes())
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    bin_off = 20 + jl + 8
    return b, j, bin_off


def _acc(b, j, bin_off, i):
    a = j["accessors"][i]
    bv = j["bufferViews"][a["bufferView"]]
    off = bin_off + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    n, c, dt = a["count"], NC[a["type"]], CT[a["componentType"]]
    stride = bv.get("byteStride", 0)
    item = np.dtype(dt).itemsize * c
    if stride and stride != item:
        raw = np.frombuffer(bytes(b[off:off + stride * n]), np.uint8).reshape(n, stride)[:, :item]
        return np.frombuffer(raw.tobytes(), dt).reshape(n, c), off, stride
    return np.frombuffer(bytes(b[off:off + item * n]), dt).reshape(n, c).copy(), off, stride


def audit(kind: str, fix: bool = False, deg: float = 35.0) -> dict:
    p = LIB / f"{kind.replace(' ', '_')}_anim.glb"
    b, j, bo = _load(p)
    res = {"kind": kind, "prims": []}
    for mi, m in enumerate(j["meshes"]):
        for pi, pr in enumerate(m["primitives"]):
            at = pr["attributes"]
            if "NORMAL" not in at or "indices" not in pr:
                continue
            P, _, _ = _acc(b, j, bo, at["POSITION"])
            N, noff, nstride = _acc(b, j, bo, at["NORMAL"])
            I, _, _ = _acc(b, j, bo, pr["indices"])
            I = I.reshape(-1, 3).astype(np.int64)
            # weld by position (UV seams split vertices that share a place)
            key = np.round(P / 1e-5).astype(np.int64)
            _, wid = np.unique(key, axis=0, return_inverse=True)
            wid = wid.ravel()
            fn = np.cross(P[I[:, 1]] - P[I[:, 0]], P[I[:, 2]] - P[I[:, 0]])      # area-weighted
            acc = np.zeros((wid.max() + 1, 3))
            for c in range(3):
                np.add.at(acc, wid[I[:, c]], fn)
            G = acc[wid]
            G /= np.linalg.norm(G, axis=1, keepdims=True) + 1e-12
            Ns = N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)
            ang = np.degrees(np.arccos(np.clip((G * Ns).sum(1), -1, 1)))
            bad = ang > deg
            z = P[:, 1]                                   # glTF is Y-up
            top = z > z.min() + 0.87 * (z.max() - z.min())   # the head
            res["prims"].append({"mesh": mi, "verts": len(P), "bad": int(bad.sum()), "bad_pct": round(100 * bad.mean(), 2),
                                 "head_bad_pct": round(100 * bad[top].mean(), 2) if top.any() else None,
                                 "flipped": int(((G * Ns).sum(1) < -0.5).sum())})
            if fix:
                # where the stored normal is far from the surface's, take the surface's
                out = Ns.copy(); out[bad] = G[bad]
                out = out.astype(np.float32)
                if nstride and nstride != 12:
                    for k in range(len(out)):
                        b[noff + k * nstride:noff + k * nstride + 12] = out[k].tobytes()
                else:
                    b[noff:noff + out.nbytes] = out.tobytes()
    if fix:
        p.write_bytes(bytes(b))
        res["fixed"] = True
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    fix = "--fix" in a
    deg = float(a[a.index("--deg") + 1]) if "--deg" in a else 35.0
    kinds = [x for x in a if not x.startswith("--") and not x.replace(".", "").isdigit()]
    for k in kinds:
        print(json.dumps(audit(k, fix, deg)), flush=True)
