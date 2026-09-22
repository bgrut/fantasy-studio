"""Measure every library asset in WORLD space and write the asset manifest.

Two questions this answers that nothing else in the pipeline could:

  HOW BIG IS IT, in metres, as the runtime will see it. Without this the
  coder guesses, and a guess is how a 49MB walker became a background NPC
  and how a boat got scaled by a "height" that was really its mast.

  IS IT STANDING UP. A model's own root node can bake a rotation that lays
  it on its side, and the naive check -- "is local +Y still up" -- is WRONG
  here, because the many Z-up assets in this library carry a legitimate
  90-degree Z-up-to-Y-up conversion on exactly that node. The world-space
  bounding box is the only thing that tells the truth: a sailboat measured
  1.0 wide, 0.96 long and 0.26 TALL, and nothing whose mast is its shortest
  dimension is upright.

Run:  python tools/assetmeta.py            # table + write manifest
      python tools/assetmeta.py --check    # exit 1 if any character is down
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "assets" / "library"
OUT = ROOT / "assets" / "library_manifest.json"


def glb_chunks(path: Path):
    """(json, bin bytes or None) for a GLB."""
    with open(path, "rb") as f:
        magic, _ver, total = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            raise ValueError("not a GLB")
        clen, ctype = struct.unpack("<II", f.read(8))
        if ctype != 0x4E4F534A:
            raise ValueError("first chunk is not JSON")
        g = json.loads(f.read(clen))
        binb = None
        rest = f.read()
        if len(rest) >= 8:
            blen, btype = struct.unpack("<II", rest[:8])
            if btype == 0x004E4942:
                binb = rest[8:8 + blen]
        return g, binb


def _accessor(g: dict, binb: bytes, idx: int):
    """A numpy view of an accessor (POSITION or indices) in the BIN chunk."""
    import numpy as np
    acc = g["accessors"][idx]
    bv = g["bufferViews"][acc["bufferView"]]
    ctype = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}[acc["componentType"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[acc["type"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    itemsize = np.dtype(ctype).itemsize * ncomp
    if stride and stride != itemsize:
        raw = np.frombuffer(binb, dtype=np.uint8, count=stride * (acc["count"] - 1) + itemsize, offset=start)
        rows = np.lib.stride_tricks.as_strided(raw, shape=(acc["count"], itemsize), strides=(stride, 1))
        return np.ascontiguousarray(rows).view(ctype).reshape(acc["count"], ncomp)
    return np.frombuffer(binb, dtype=ctype, count=acc["count"] * ncomp, offset=start).reshape(acc["count"], ncomp)


def mesh_quality(g: dict, binb, rec: dict) -> dict:
    """THE QUALITY GATE (2026-09-23). Reads the mesh itself: the share of
    triangles in the largest welded component (a mangled generation is many
    shards), the count of real fragments, the share of degenerate triangles,
    whether the textures decode, and for a car which end is the nose."""
    import numpy as np
    out = {"tris": 0, "largest_share": 0.0, "fragments": 0, "degenerate": 0.0, "textures": 0, "textures_ok": True}
    if binb is None:
        out["error"] = "no BIN chunk"
        return out
    faces_all, verts_all, base = [], [], 0
    for mesh in g.get("meshes", []):
        for pr in mesh.get("primitives", []):
            pi = pr.get("attributes", {}).get("POSITION")
            if pi is None or pr.get("mode", 4) != 4:
                continue
            try:
                pos = _accessor(g, binb, pi).astype(np.float64)
                if "indices" in pr:
                    idx = _accessor(g, binb, pr["indices"]).reshape(-1).astype(np.int64)
                else:
                    idx = np.arange(pos.shape[0], dtype=np.int64)
            except Exception:
                continue
            idx = idx[: (idx.shape[0] // 3) * 3].reshape(-1, 3)
            faces_all.append(idx + base)
            verts_all.append(pos)
            base += pos.shape[0]
    if not faces_all:
        out["error"] = "no triangles"
        return out
    F = np.concatenate(faces_all)
    V = np.concatenate(verts_all)
    out["tris"] = int(F.shape[0])
    # weld by position: generated meshes are unwelded, so every triangle would be its own island
    ext = float(np.max(np.ptp(V, axis=0))) or 1.0
    q = np.round(V / (ext * 2e-4)).astype(np.int64)
    _, weld = np.unique(q, axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    Fw = weld[F]
    # degenerate: near-zero area against the model's scale
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    out["degenerate"] = round(float(np.mean(area < (ext * ext) * 1e-9)), 4)
    # connected components over welded vertices, union-find vectorised by label propagation
    nverts = int(weld.max()) + 1
    label = np.arange(nverts)
    for _ in range(64):
        m = np.minimum.reduce([label[Fw[:, 0]], label[Fw[:, 1]], label[Fw[:, 2]]])
        new = label.copy()
        np.minimum.at(new, Fw[:, 0], m); np.minimum.at(new, Fw[:, 1], m); np.minimum.at(new, Fw[:, 2], m)
        new = new[new]
        if np.array_equal(new, label):
            break
        label = new
    comp = label[Fw[:, 0]]
    _, counts = np.unique(comp, return_counts=True)
    out["largest_share"] = round(float(counts.max() / F.shape[0]), 4)
    out["fragments"] = int(np.sum(counts >= max(40, F.shape[0] * 0.002)))
    # textures: every image decodes
    imgs = g.get("images", [])
    out["textures"] = len(imgs)
    try:
        from PIL import Image
        import io
        for im in imgs:
            if "bufferView" not in im:
                continue
            bv = g["bufferViews"][im["bufferView"]]
            data = binb[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
            Image.open(io.BytesIO(data)).verify()
    except Exception:
        out["textures_ok"] = False
    # the nose of a car: the roofline peaks over the cabin, which sits behind the
    # bonnet, so the nose is the end farther from the tallest bin along the length
    dims = rec.get("dims_m") or {}
    axis = "xyz".index(rec.get("tallest_axis", "x")) if False else int(np.argmax([dims.get("x", 0), dims.get("y", 0), dims.get("z", 0)]))
    if axis in (0, 2) and dims.get("y", 0) > 0:
        coord = V[:, axis]
        lo, hi = float(coord.min()), float(coord.max())
        bins = np.clip(((coord - lo) / max(hi - lo, 1e-6) * 10).astype(int), 0, 9)
        top = np.zeros(10)
        for bi in range(10):
            sel = V[bins == bi, 1]
            top[bi] = float(np.percentile(sel, 98)) if sel.size else 0.0
        peak = int(np.argmax(top))
        out["nose"] = ("-" if peak >= 5 else "+") + "xyz"[axis]
        out["roof_peak_bin"] = peak
    return out


def quality_score(rec: dict) -> tuple[float, str]:
    """A number and a verdict from the measurements: good, fair or poor.

    CONSERVATIVE BY DESIGN (2026-09-23). The first calibration called 70 of
    153 assets poor, every hero character among them: this pipeline's meshes
    are unwelded shards by construction, so the largest-component share does
    not separate a good corvette (0.10) from a mangled ferrari (0.09). Only
    clear failures are poor: textures that do not decode, a swarm of
    degenerate triangles, a character lying down, a car with the proportions
    of a brick, or a mesh that is dust. A well-joined mesh is good; the rest
    is fair, and a fair model is used but never preferred over a parametric
    build. Telling a good generation from a mangled one needs a rendered
    check against its own reference image, which is the next tool."""
    mq = rec.get("mesh") or {}
    if mq.get("error"):
        return 0.0, "poor"
    reasons = []
    # THE RENDER CHECK (2026-09-24): assetview.mjs renders each kind shaded and
    # measures the dark share of its silhouette (torn generations show black
    # where faces point inward or the texture never landed). Merged when the
    # render file exists; a torn model is poor, a patchy one fair.
    rd = _render_record(rec.get("file", ""))
    if rd:
        rec["render"] = {k: rd[k] for k in ("looks_like", "looks_like_best", "damage_share", "dark_share", "cull_loss", "solidity", "edges", "coverage") if k in rd}
        # THE JUDGE (assetjudge.py): a vision model's belief that the shaded
        # render is the kind it claims, against torn debris. Pixel statistics
        # could not tell a mangled ferrari from a good corvette; this can.
        if "looks_like" in rd:
            # one half is a coin toss, and a coin-toss scientist was a garish
            # anatomy figure: below a half is poor, below six tenths doubtful
            if rd["looks_like"] < 0.5:
                reasons.append("does not look like it")
            elif rd["looks_like"] < 0.6:
                reasons.append("doubtful")
        # a torn ferrari still reads as a ferrari to the judge; what gives it
        # away is that three quarters of its silhouette renders black
        if rd.get("dark_share", 0.0) > 0.45:
            reasons.append("mostly dark")
    if not mq.get("textures_ok", True):
        reasons.append("textures")
    if mq.get("degenerate", 0.0) > 0.05:
        reasons.append("degenerate")
    if is_characterish(rec) and not rec.get("upright", True):
        reasons.append("lying down")
    nm = rec.get("file", "").lower()
    dims = rec.get("dims_m") or {}
    if any(k in nm for k in CAR_NAMES) and dims:
        length = max(dims.get("x", 0), dims.get("z", 0)); height = dims.get("y", 1e-6)
        if not (1.6 <= length / max(height, 1e-6) <= 4.5):
            reasons.append("proportions")
    if mq.get("largest_share", 1.0) < 0.02 and mq.get("tris", 0) > 2000:
        reasons.append("dust")
    # dust and proportions are suspicions, not proof (a scaled mesh defeats the
    # weld, a Z-up car defeats the height): they mark the model fair with a
    # reason, and only what cannot be right marks it poor
    hard = [r for r in reasons if r in ("textures", "degenerate", "lying down", "does not look like it")]
    if reasons:
        rec["quality_reasons"] = reasons
    if hard:
        return 0.2, "poor"
    if reasons:
        return 0.5, "fair"
    share = mq.get("largest_share", 1.0)
    looks = rd.get("looks_like") if rd else None
    if looks is not None:
        # with a judge, the verdict is the judge's: good when the render is
        # believed and not mostly dark, fair otherwise; the geometry informs
        q = 0.4 + 0.6 * looks
        return round(q, 2), ("good" if (looks >= 0.6 and "mostly dark" not in reasons) else "fair")
    q = 0.55 + 0.45 * min(1.0, share / 0.6)
    return round(q, 2), ("good" if share >= 0.6 else "fair")


_RENDER: dict | None = None


def _render_record(file: str) -> dict:
    """assetview.mjs's measurements for a library file, by file name."""
    global _RENDER
    if _RENDER is None:
        _RENDER = {}
        p = ROOT / "assets" / "library_render.json"
        try:
            _RENDER = {k.lower(): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
        except Exception:
            _RENDER = {}
    return _RENDER.get((file or "").lower(), {})


CAR_NAMES = ("car", "corvette", "ferrari", "taxi", "truck", "sedan", "van", "pickup", "jeep", "coupe")


def glb_json(path: Path) -> dict:
    with open(path, "rb") as f:
        magic, _ver, total = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            raise ValueError("not a GLB")
        clen, ctype = struct.unpack("<II", f.read(8))
        if ctype != 0x4E4F534A:
            raise ValueError("first chunk is not JSON")
        return json.loads(f.read(clen))


def mat_identity():
    return [1.0 if i % 5 == 0 else 0.0 for i in range(16)]


def mat_mul(a, b):
    """Column-major 4x4 multiply, glTF convention: result = a * b."""
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
    return out


def node_matrix(n: dict):
    if "matrix" in n:
        return list(n["matrix"])
    t = n.get("translation", [0.0, 0.0, 0.0])
    r = n.get("rotation", [0.0, 0.0, 0.0, 1.0])
    s = n.get("scale", [1.0, 1.0, 1.0])
    x, y, z, w = r
    m = [
        (1 - 2 * (y * y + z * z)) * s[0], (2 * (x * y + z * w)) * s[0], (2 * (x * z - y * w)) * s[0], 0.0,
        (2 * (x * y - z * w)) * s[1], (1 - 2 * (x * x + z * z)) * s[1], (2 * (y * z + x * w)) * s[1], 0.0,
        (2 * (x * z + y * w)) * s[2], (2 * (y * z - x * w)) * s[2], (1 - 2 * (x * x + y * y)) * s[2], 0.0,
        t[0], t[1], t[2], 1.0,
    ]
    return m


def xform(m, p):
    x, y, z = p
    return (
        m[0] * x + m[4] * y + m[8] * z + m[12],
        m[1] * x + m[5] * y + m[9] * z + m[13],
        m[2] * x + m[6] * y + m[10] * z + m[14],
    )


def world_box(g: dict):
    """Union of every mesh primitive's corners, through the node hierarchy."""
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    acc = g.get("accessors", [])
    meshes = g.get("meshes", [])
    nodes = g.get("nodes", [])
    scenes = g.get("scenes", [])
    roots = scenes[g.get("scene", 0)].get("nodes", []) if scenes else range(len(nodes))

    def walk(ni, parent):
        n = nodes[ni]
        m = mat_mul(parent, node_matrix(n))
        if "mesh" in n:
            for pr in meshes[n["mesh"]].get("primitives", []):
                ai = pr.get("attributes", {}).get("POSITION")
                if ai is None:
                    continue
                a = acc[ai]
                if "min" not in a or "max" not in a:
                    continue
                mn, mx = a["min"], a["max"]
                for cx in (mn[0], mx[0]):
                    for cy in (mn[1], mx[1]):
                        for cz in (mn[2], mx[2]):
                            wp = xform(m, (cx, cy, cz))
                            for i in range(3):
                                lo[i] = min(lo[i], wp[i])
                                hi[i] = max(hi[i], wp[i])
        for c in n.get("children", []):
            walk(c, m)

    for r in roots:
        walk(r, mat_identity())
    if lo[0] is math.inf:
        return None
    return [round(hi[i] - lo[i], 4) for i in range(3)], [round(v, 4) for v in lo]


def measure(path: Path) -> dict:
    g = glb_json(path)
    wb = world_box(g)
    rec = {"file": path.name}
    if not wb:
        rec["error"] = "no positions"
        return rec
    dims, mins = wb
    rec["dims_m"] = {"x": dims[0], "y": dims[1], "z": dims[2]}
    rec["min_y"] = mins[1]
    rec["skinned"] = bool(g.get("skins"))
    rec["clips"] = [a.get("name", "?") for a in g.get("animations", [])]
    rec["bones"] = sum(len(s.get("joints", [])) for s in g.get("skins", []))
    nm = path.name.lower()
    # THE RIG OUTRANKS THE NAME. cat_burglar_anim is a CAT, and matching
    # "burglar" called it a biped and then called it broken for being
    # longer than it is tall. When an asset is actually skinned its joint
    # count is ground truth; names only fill in for unrigged meshes.
    rec["biped"] = (rec["bones"] >= 15 if rec["skinned"]
                    else any(k in nm for k in BIPED_NAMES))
    biggest = max(range(3), key=lambda i: dims[i])
    rec["tallest_axis"] = "xyz"[biggest]
    rec["aspect"] = {"w_h": round(dims[0] / max(dims[1], 1e-6), 3),
                     "d_h": round(dims[2] / max(dims[1], 1e-6), 3)}
    # UPRIGHTNESS IS NOT ONE RULE. A biped is taller than it is wide or long,
    # and "tallest axis is Y" catches a capsized one immediately. A wolf is
    # legitimately LONGER than it is tall, so the same rule flags the whole
    # zoo as broken -- the first run of this tool called 20 assets lying down
    # and 18 of them were simply quadrupeds. What a four-legged animal must
    # not be is FLAT: standing on its legs, its height is a real fraction of
    # its length, and a fallen one collapses toward the floor. The rigs
    # separate themselves cleanly -- bipeds carry 19-20 joints here, the
    # quadrupeds 12 -- so the classifier costs nothing.
    tallest = max(dims[0], dims[1], dims[2]) or 1e-6
    if rec["biped"]:
        rec["upright"] = (biggest == 1)
    else:
        rec["upright"] = (dims[1] / tallest) >= 0.35
    rec["height_ratio"] = round(dims[1] / tallest, 3)
    try:
        _g2, binb = glb_chunks(path)
        rec["mesh"] = mesh_quality(_g2, binb, rec)
    except Exception as e:  # noqa: BLE001
        rec["mesh"] = {"error": f"{type(e).__name__}: {e}"[:120]}
    rec["quality"], rec["verdict"] = quality_score(rec)
    return rec


BIPED_NAMES = ("man", "woman", "knight", "wizard", "hunter", "soldier",
               "ranger", "samurai", "viking", "detective", "goblin", "burglar",
               "courier", "guide", "rival", "scientist", "thug", "walker",
               "bender", "king", "penguin")


def is_characterish(rec: dict) -> bool:
    return bool(rec.get("skinned") or rec.get("biped"))


def main() -> int:
    check = "--check" in sys.argv
    recs = []
    for p in sorted(LIB.glob("*.glb")):
        try:
            recs.append(measure(p))
        except Exception as e:
            recs.append({"file": p.name, "error": f"{type(e).__name__}: {e}"})

    down = [r for r in recs
            if is_characterish(r) and "dims_m" in r and not r["upright"]]

    print(f"{'asset':34} {'x':>7} {'y':>7} {'z':>7}  {'bones':>5} clips  flag")
    for r in sorted(recs, key=lambda r: r["file"]):
        if "dims_m" in r:
            d = r["dims_m"]
            flag = ""
            if is_characterish(r) and not r["upright"]:
                kind = "biped" if r.get("biped") else "quadruped"
                flag = (f"LYING DOWN ({kind}, tallest axis = {r['tallest_axis']},"
                        f" height ratio {r.get('height_ratio')})")
            print(f"{r['file'][:34]:34} {d['x']:7.2f} {d['y']:7.2f} {d['z']:7.2f}"
                  f"  {r.get('bones', 0):5} {len(r.get('clips', [])):5}  {flag}")
        else:
            print(f"{r['file'][:34]:34} {'--':>7} {'--':>7} {'--':>7}"
                  f"  {'':5} {'':5}  {r.get('error', '')}")

    OUT.write_text(json.dumps({"assets": recs}, indent=1), encoding="utf-8")
    print(f"\n{len(recs)} assets measured -> {OUT.relative_to(ROOT)}")
    print(f"characters lying down: {len(down)}")
    for r in down:
        print("   ", r["file"], r["dims_m"])
    return 1 if (check and down) else 0


if __name__ == "__main__":
    raise SystemExit(main())
