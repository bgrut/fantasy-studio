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
