"""Take the metal off people and animals that the generator called metal (2026-10-08).

The generator's metal/roughness sheet said a woman, a scientist, a customer, a
photographer and others were 75 to 100 percent metal. The coat kept it as the
per-vertex attribute _MR (scripts/_clean_coat.py) and the runtime reads metal
from there, so their skin mirrored the scene and they played dark and muddy.

This edits each GLB in place, nothing else touched: the material's
metallicFactor goes to 0 and the _MR metal channel is capped at 0.15, straight
in the binary buffer. Plated kinds (robot, knight, astronaut...) keep their
metal (app/game_export/coat.py PLATED).

    python backend/tools/matte_fix.py [--dry] [files...]     # default: every *_anim.glb
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.game_export.coat import is_plated  # noqa: E402

CAP = 0.15


def fix(path: Path, dry: bool = False) -> str:
    data = path.read_bytes()
    magic, ver, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        return "not glb"
    jl, jt = struct.unpack_from("<II", data, 12)
    j = json.loads(data[20:20 + jl])
    off = 20 + jl
    bl, bt = struct.unpack_from("<II", data, off)
    binbuf = bytearray(data[off + 8: off + 8 + bl])
    changed = []
    for m in j.get("materials", []):
        pbr = m.setdefault("pbrMetallicRoughness", {})
        if pbr.get("metallicFactor", 1.0) > CAP:
            changed.append("metallicFactor %.2f" % pbr.get("metallicFactor", 1.0))
            pbr["metallicFactor"] = 0.0
    seen = set()
    for mesh in j.get("meshes", []):
        for prim in mesh.get("primitives", []):
            ai = prim.get("attributes", {}).get("_MR")
            if ai is None or ai in seen:
                continue
            seen.add(ai)
            acc = j["accessors"][ai]
            if acc.get("componentType") != 5126 or acc.get("type") not in ("VEC3", "VEC2"):
                continue
            bv = j["bufferViews"][acc["bufferView"]]
            nc = 3 if acc["type"] == "VEC3" else 2
            stride = bv.get("byteStride", 4 * nc)
            base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            n = acc["count"]
            idx = base + np.arange(n) * stride
            metal = np.frombuffer(bytes(binbuf), dtype=np.uint8)  # view for slicing
            vals = np.array([struct.unpack_from("<f", binbuf, int(i))[0] for i in idx], dtype=np.float32)
            hi = vals > CAP
            if hi.any():
                changed.append("_MR metal mean %.2f -> capped (%d%% over %.2f)" % (vals.mean(), 100 * hi.mean(), CAP))
                for i, v in zip(idx[hi], vals[hi]):
                    struct.pack_into("<f", binbuf, int(i), CAP)
            # keep the accessor's bounds honest
            if "max" in acc and len(acc["max"]) >= 1:
                acc["max"][0] = float(min(acc["max"][0], CAP))
    if not changed:
        return "already matte"
    if dry:
        return "would fix: " + "; ".join(changed)
    js = json.dumps(j, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    binb = bytes(binbuf); binb += b"\0" * ((4 - len(binb) % 4) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binb))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binb), 0x004E4942) + binb
    path.write_bytes(out)
    return "fixed: " + "; ".join(changed)


def main() -> int:
    dry = "--dry" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = [Path(a) for a in args] or sorted((BACKEND / "assets" / "library").glob("*_anim.glb")) + \
        sorted((BACKEND / "renders" / "_coat_backup_hdfront").glob("*_anim.glb"))
    for f in files:
        if is_plated(f.stem):
            print(f"{f.parent.name}/{f.name}: plated, kept")
            continue
        try:
            print(f"{f.parent.name}/{f.name}: {fix(f, dry)}")
        except Exception as e:  # noqa: BLE001
            print(f"{f.parent.name}/{f.name}: error {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
