"""Cut the ground plate a generated creature was standing on.

    python backend/tools/deplate.py assets/library/bee.glb [--dry]

TRELLIS.2 rebuilds what the reference photo shows, and a creature photographed
standing on a surface comes back fused to a slab of that surface: the bee of
2026-10-07 flew with a dark board twice its size bolted to its side, which
read in the meadow as one big black wing. The plate is the one large flat
region of the mesh that everything else lies on one side of. Its faces are
dropped by rewriting the index list in place, so every texture, UV and
normal in the file stays exactly as it was. The original is kept in
assets/library/_retired.
"""
from __future__ import annotations

import json
import shutil
import struct
import sys
import time
from pathlib import Path

import numpy as np

COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _read(path: Path):
    b = bytearray(path.read_bytes())
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    bin0 = 20 + jl + 8
    return b, j, bin0


def _acc(b, j, bin0, i):
    a = j["accessors"][i]; bv = j["bufferViews"][a["bufferView"]]
    off = bin0 + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    dt = COMP[a["componentType"]]; n = a["count"] * NCOMP[a["type"]]
    return np.frombuffer(bytes(b[off:off + n * np.dtype(dt).itemsize]), dtype=dt).reshape(a["count"], NCOMP[a["type"]]), off, dt


def find_plate(V: np.ndarray, F: np.ndarray, rng=np.random.default_rng(7)):
    """(normal, offset, mask of plate faces) or None."""
    P = V[F]; C = P.mean(1)
    N = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]); area = np.linalg.norm(N, axis=1) * 0.5
    Nn = N / np.maximum(area[:, None] * 2, 1e-12)
    diag = np.linalg.norm(V.max(0) - V.min(0)); tol = diag * 0.012
    best = None
    w = area / area.sum()
    for _ in range(400):
        i = rng.choice(len(F), p=w)
        n = Nn[i]; d = n @ C[i]
        on = (np.abs(C @ n - d) < tol) & (np.abs(Nn @ n) > 0.9)
        a = area[on].sum()
        if best is None or a > best[2]:
            best = (n, d, a, on)
    n, d, a, on = best
    if a < area.sum() * 0.12:
        return None
    # a ground plate lies flat under the creature; a cat's flank (flat-ish,
    # a quarter of its faces, facing sideways) is the false hit this refuses
    if abs(n[1]) < 0.9:
        return None
    # everything that is not plate lies on one side of it
    s = C[~on] @ n - d
    side = np.sign(np.median(s))
    if (np.sign(s) == side).mean() < 0.97:
        return None
    # the plate is a board, not a film: take its thickness on the far side too
    slab = ((C @ n - d) * side < diag * 0.03) | on
    return n * side, d * side, slab


def main(argv):
    path = Path(argv[0]); dry = "--dry" in argv
    b, j, bin0 = _read(path)
    total = 0
    edits = []
    for mesh in j["meshes"]:
        for prim in mesh["primitives"]:
            V, _, _ = _acc(b, j, bin0, prim["attributes"]["POSITION"])
            I, ioff, idt = _acc(b, j, bin0, prim["indices"])
            F = I.reshape(-1, 3)
            hit = find_plate(V.astype(np.float64), F)
            if hit is None:
                print(f"{path.name}: no plate found")
                continue
            n, d, mask = hit
            keep = F[~mask]
            print(f"{path.name}: plate normal {np.round(n, 2)}, {mask.sum()} of {len(F)} faces ({mask.mean():.0%}) cut")
            edits.append((prim["indices"], keep, ioff, idt))
            total += int(mask.sum())
    if dry or not edits:
        return 0
    keepdir = path.parent / "_retired"; keepdir.mkdir(exist_ok=True)
    shutil.copy2(path, keepdir / f"{path.stem}_{time.strftime('%Y%m%d')}_plated{path.suffix}")
    for ai, keep, ioff, idt in edits:
        flat = keep.astype(idt).ravel().tobytes()
        b[ioff:ioff + len(flat)] = flat
        j["accessors"][ai]["count"] = int(keep.size)
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    old_jl = struct.unpack("<I", b[12:16])[0]
    out = bytearray(b[:12]) + struct.pack("<I", len(js)) + b"JSON" + js + b[20 + old_jl:]
    out[8:12] = struct.pack("<I", len(out))
    path.write_bytes(bytes(out))
    print(f"{path.name}: written, {total} faces cut; the original is in _retired")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
