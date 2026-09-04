"""Stand a fallen asset back up, by measurement rather than by guess.

assetmeta.py finds models whose world-space box says they are lying down.
This applies the correction: it tries the handful of axis-aligned rotations
a bad export can differ by, measures the world box under each, and keeps the
one that puts the model's height on +Y. Nothing here reasons about what the
asset IS -- it only asks which rotation makes it stand.

Run:  python tools/assetfix.py guide.glb rival.glb        # fix named assets
      python tools/assetfix.py --all                       # every flagged one
      python tools/assetfix.py --dry guide.glb             # report only
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assetmeta import LIB, glb_json, world_box, node_matrix, mat_mul, is_characterish, measure  # noqa: E402

HALF = math.sqrt(0.5)
# (label, quaternion xyzw) -- the rotations a bad axis convention differs by
CANDIDATES = [
    ("identity",   [0.0, 0.0, 0.0, 1.0]),
    ("-90 X",      [-HALF, 0.0, 0.0, HALF]),
    ("+90 X",      [HALF, 0.0, 0.0, HALF]),
    ("-90 Z",      [0.0, 0.0, -HALF, HALF]),
    ("+90 Z",      [0.0, 0.0, HALF, HALF]),
    ("180 X",      [1.0, 0.0, 0.0, 0.0]),
]


def read_chunks(p: Path):
    d = p.read_bytes()
    magic, _ver, total = struct.unpack("<III", d[:12])
    assert magic == 0x46546C67, "not a GLB"
    off, chunks = 12, []
    while off < total:
        clen, ctype = struct.unpack("<II", d[off:off + 8])
        chunks.append([ctype, d[off + 8:off + 8 + clen]])
        off += 8 + clen
    return chunks


def write_chunks(p: Path, chunks):
    out = b""
    for ctype, data in chunks:
        pad = (4 - len(data) % 4) % 4
        data = data + (b" " if ctype == 0x4E4F534A else b"\x00") * pad
        out += struct.pack("<II", len(data), ctype) + data
    p.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(out)) + out)


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz]


def try_rotation(g: dict, q) -> list:
    """World-box dims with q pre-applied to every scene root."""
    import copy
    g2 = copy.deepcopy(g)
    scenes = g2.get("scenes", [])
    roots = scenes[g2.get("scene", 0)].get("nodes", []) if scenes else []
    if not roots:
        roots = list(range(len(g2.get("nodes", []))))
    for ri in roots:
        n = g2["nodes"][ri]
        if "matrix" in n:                 # normalise to TRS so we can compose
            return None
        cur = n.get("rotation", [0.0, 0.0, 0.0, 1.0])
        n["rotation"] = qmul(q, cur)
    wb = world_box(g2)
    return wb[0] if wb else None


def fix(name: str, dry: bool) -> bool:
    p = LIB / name
    if not p.exists():
        print(f"  {name}: NOT FOUND")
        return False
    chunks = read_chunks(p)
    g = json.loads(chunks[0][1].decode("utf-8"))
    before = world_box(g)[0]
    best = None
    for label, q in CANDIDATES:
        dims = try_rotation(g, q)
        if not dims:
            continue
        tallest = max(dims) or 1e-6
        score = dims[1] / tallest          # how much of the size is height
        if best is None or score > best[2]:
            best = (label, q, score, dims)
    if not best:
        print(f"  {name}: cannot compose (baked matrix) -- skipped")
        return False
    label, q, score, dims = best
    print(f"  {name}: {before} -> {dims}   [{label}, height ratio {score:.3f}]")
    if score < 0.35:
        print(f"     no rotation stands it up; the mesh itself is flat -- not touched")
        return False
    if label == "identity":
        print("     already the best orientation -- not touched")
        return False
    if dry:
        return False
    scenes = g.get("scenes", [])
    roots = scenes[g.get("scene", 0)].get("nodes", []) if scenes else list(range(len(g["nodes"])))
    for ri in roots:
        n = g["nodes"][ri]
        n["rotation"] = qmul(q, n.get("rotation", [0.0, 0.0, 0.0, 1.0]))
    chunks[0][1] = json.dumps(g, separators=(",", ":")).encode("utf-8")
    write_chunks(p, chunks)
    print("     written")
    return True


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    if "--all" in sys.argv:
        args = [r["file"] for r in
                (measure(p) for p in sorted(LIB.glob("*.glb")))
                if is_characterish(r) and "dims_m" in r and not r["upright"]]
    if not args:
        print("nothing to do (pass asset names, or --all)")
        return 0
    print(f"{'':2}{len(args)} asset(s):")
    for a in args:
        fix(a, dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
