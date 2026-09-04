"""Import Poly Haven CC0 nature models as single self-contained GLB props.

Poly Haven ships glTF as a .gltf plus an external .bin plus loose texture
JPEGs. Everything else in this pipeline expects ONE .glb per prop, so this
packs them: the original .bin becomes the GLB's binary chunk, each texture is
appended to it as a bufferView, and every uri reference is rewritten to point
inside the file.

These are photogrammetry — high-poly with real textures — which is why they
are the wrong choice for stylised scatter at 200 instances and the RIGHT one
for a realistic world at 40. Kenney covers the stylised lane.

Run:  python tools/phimport.py            # the curated set
      python tools/phimport.py --res 2k   # sharper, ~4x the bytes
"""
from __future__ import annotations

import json
import struct
import sys
import urllib.request
from pathlib import Path

API = "https://api.polyhaven.com"
UA = {"User-Agent": "FantasyStudio/1.0 (CC0 asset import)"}
OUT = Path(__file__).resolve().parent.parent / "assets" / "props"

# chosen against the archetypes that need them, not just "looks nice"
CURATED = [
    "boulder_01", "moon_rock_01", "moon_rock_02",        # canyon / mesa debris
    "coastal_cliff_01", "coast_land_rocks_02",           # cliff faces
    "dead_tree_trunk", "dead_quiver_trunk",              # dead wood, canyon
    "dry_branches_medium_01",                            # ground litter
    "fir_tree_01",                                       # peaks
    "island_tree_01", "island_tree_02",                  # plain / archipelago
    "fern_02", "grass_medium_01", "flower_gazania",      # undergrowth
]


def api(path: str):
    req = urllib.request.Request(API + path, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=90))


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=180).read()


def pack_glb(gltf: dict, binblob: bytes, textures: dict[str, bytes]) -> bytes:
    """One buffer, textures appended as bufferViews, no external uris left."""
    blob = bytearray(binblob)
    for img in gltf.get("images", []):
        uri = img.pop("uri", None)
        if not uri:
            continue
        key = uri.split("/")[-1]
        data = textures.get(key)
        if data is None:
            img["uri"] = uri            # leave it rather than lie about it
            continue
        while len(blob) % 4:
            blob += b"\x00"
        gltf.setdefault("bufferViews", []).append(
            {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob += data
        img["bufferView"] = len(gltf["bufferViews"]) - 1
        img["mimeType"] = "image/png" if key.lower().endswith(".png") else "image/jpeg"
    gltf["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    blob += b"\x00" * ((4 - len(blob) % 4) % 4)
    body = (struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def import_one(name: str, res: str) -> tuple[bool, str]:
    files = api(f"/files/{name}")
    g = (files.get("gltf") or {}).get(res)
    if not g:
        return False, f"no gltf at {res}"
    entry = next(iter(g.values()))
    gltf = json.loads(fetch(entry["url"]).decode("utf-8"))
    inc = entry.get("include") or {}
    binblob, textures = b"", {}
    for rel, meta in inc.items():
        data = fetch(meta["url"])
        (textures.__setitem__(rel.split("/")[-1], data)
         if not rel.endswith(".bin") else None)
        if rel.endswith(".bin"):
            binblob = data
    dst = OUT / f"ph_{name}.glb"
    dst.write_bytes(pack_glb(gltf, binblob, textures))
    return True, f"{dst.stat().st_size / 1e6:.1f} MB"


def main() -> int:
    res = "1k"
    if "--res" in sys.argv:
        res = sys.argv[sys.argv.index("--res") + 1]
    OUT.mkdir(parents=True, exist_ok=True)
    ok = 0
    for n in CURATED:
        try:
            good, msg = import_one(n, res)
        except Exception as e:  # noqa: BLE001
            good, msg = False, f"{type(e).__name__}: {e}"
        print(f"  {'ok  ' if good else 'FAIL'} ph_{n:26} {msg}", flush=True)
        ok += good
    print(f"\n{ok}/{len(CURATED)} imported at {res} -> {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
