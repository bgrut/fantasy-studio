"""Measure the holes in an exported asset: open edges, loops, islands.

    python backend/tools/meshaudit.py assets/library/scientist_anim.glb
    python backend/tools/meshaudit.py --all            # every rig in the library

A character reads as "gappy" for two different reasons and they need different
repairs, so the first job is to tell them apart with a number.

  * An OPEN EDGE is a triangle edge no second triangle shares. The surface
    simply stops there, and the camera sees the unlit inside of the body: the
    dark wedge under a collar, the hollow of a sleeve. Generated shells are
    full of these; a real game character has none.
  * An ISLAND is a connected piece of surface, counted after welding
    positions (glTF splits one vertex into several at every UV seam, so the
    raw vertex graph always over-counts). A body that arrives as one island
    is whole and must not be remeshed; a body in forty pieces has loose
    parts that will swim when the skeleton moves.

Both are reported against the mesh's own size so the numbers compare across a
mouse and a whale: open edge length is given as a share of the bounding box
diagonal, island size as a share of the triangles.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.game_export.glbedit import _chunks, _acc, health  # noqa: E402

_CT = {5120: "i1", 5121: "u1", 5122: "i2", 5123: "u2", 5125: "u4", 5126: "f4"}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _read(g: dict, binb: bytes, idx: int) -> np.ndarray:
    """One accessor as an array, honouring the byte stride."""
    acc = g["accessors"][idx]
    nc, dt = _NC[acc["type"]], np.dtype(_CT[acc["componentType"]])
    bv = g["bufferViews"][acc["bufferView"]]
    base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride") or nc * dt.itemsize
    if stride == nc * dt.itemsize:
        out = np.frombuffer(binb, dtype=dt, count=acc["count"] * nc, offset=base)
        return out.reshape(acc["count"], nc)
    rows = np.frombuffer(binb, dtype=np.uint8, count=acc["count"] * stride, offset=base)
    rows = rows.reshape(acc["count"], stride)[:, :nc * dt.itemsize]
    return np.frombuffer(rows.copy().tobytes(), dtype=dt).reshape(acc["count"], nc)


def geometry(path: Path):
    """Every primitive's positions and triangles, merged into one mesh."""
    g, binb = _chunks(Path(path).read_bytes())
    binb = bytes(binb)
    vs, fs, n = [], [], 0
    for mesh in g.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
                continue
            p = _read(g, binb, prim["attributes"]["POSITION"]).astype(np.float64)
            if "indices" in prim:
                i = _read(g, binb, prim["indices"]).reshape(-1).astype(np.int64)
            else:
                i = np.arange(len(p), dtype=np.int64)
            vs.append(p)
            fs.append(i.reshape(-1, 3) + n)
            n += len(p)
    if not vs:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.concatenate(vs), np.concatenate(fs)


def _weld(v: np.ndarray, tol_scale: float = 1e-4) -> np.ndarray:
    """Vertices at the same place are the same vertex, whatever glTF says."""
    span = float(np.linalg.norm(v.max(axis=0) - v.min(axis=0))) if len(v) else 1.0
    q = np.round(v / max(span * tol_scale, 1e-9)).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    return inv.reshape(-1)


def audit(path: Path) -> dict:
    v, f = geometry(path)
    if not len(f):
        return {"file": Path(path).name, "tris": 0}
    w = _weld(v)
    wf = w[f]
    span = float(np.linalg.norm(v.max(axis=0) - v.min(axis=0)))

    # --- open edges: an edge used by exactly one triangle has nothing on the far side
    e = np.concatenate([wf[:, [0, 1]], wf[:, [1, 2]], wf[:, [2, 0]]])
    e = np.sort(e, axis=1)
    e = e[e[:, 0] != e[:, 1]]                       # a degenerate triangle is not a hole
    uniq, cnt = np.unique(e, axis=0, return_counts=True)
    open_e = uniq[cnt == 1]
    vw = np.zeros((w.max() + 1, 3))
    vw[w] = v                                        # one position per welded vertex
    open_len = float(np.linalg.norm(vw[open_e[:, 0]] - vw[open_e[:, 1]], axis=1).sum()) if len(open_e) else 0.0

    # --- loops: chain the open edges, so a hundred edges around one armhole count once
    loops = 0
    if len(open_e):
        adj: dict[int, list[int]] = {}
        for a, b in open_e:
            adj.setdefault(int(a), []).append(int(b))
            adj.setdefault(int(b), []).append(int(a))
        seen: set[int] = set()
        for s in adj:
            if s in seen:
                continue
            loops += 1
            stack = [s]
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                stack.extend(y for y in adj[x] if y not in seen)

    # --- islands, over the welded graph
    n = int(w.max()) + 1
    par = np.arange(n)

    def find(x: int) -> int:
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for a, b in uniq:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            par[ra] = rb
    roots = np.array([find(int(x)) for x in wf[:, 0]])
    _, sizes = np.unique(roots, return_counts=True)
    sizes = np.sort(sizes)[::-1]

    extra = {}
    try:
        extra = health(path)
    except Exception:
        extra = {"blend": -1, "normals_off": -1.0}
    return {
        "file": Path(path).name,
        "tris": int(len(f)),
        "verts": int(n),
        "islands": int(len(sizes)),
        "largest": round(float(sizes[0]) / len(f), 4),
        "open_edges": int(len(open_e)),
        "holes": loops,
        "open_span": round(open_e.size and open_len / max(span, 1e-9) or 0.0, 4),
        "whole": bool(len(open_e) == 0),
        **extra,
    }


def _fmt(r: dict) -> str:
    if not r.get("tris"):
        return "%-34s no triangles" % r["file"]
    return ("%-30s %7d tris %4d islands (largest %5.1f%%) %6d open edges "
            "%5.1f%% normals adrift %s%s" % (
                r["file"], r["tris"], r["islands"], r["largest"] * 100,
                r["open_edges"], (r.get("normals_off") or 0) * 100,
                "see-through " if r.get("blend") else "",
                "WHOLE" if r["whole"] else ""))


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent.parent
    args = [a for a in argv if not a.startswith("--")]
    if "--all" in argv:
        args = sorted(str(p) for p in (here / "assets/library").glob("*_anim.glb"))
    if not args:
        print(__doc__)
        return 2
    for a in args:
        p = Path(a)
        if not p.is_absolute():
            p = here / a
        if not p.exists():
            print("%-34s missing" % p.name)
            continue
        try:
            print(_fmt(audit(p)), flush=True)
        except Exception as exc:                      # a broken export must not stop the sweep
            print("%-34s failed: %s" % (p.name, exc), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
