"""Real-world terrain backdrops from elevation data (the "Blosm for landscapes").

Uses AWS Terrain Tiles (Terrarium PNG, public, NO API key) — decodes elevation
and builds a displaced grid mesh. Real DEM = real mountains/mesas/canyons.

  height_m = (R * 256 + G + B / 256) - 32768

Data: AWS Terrain Tiles (Mapzen/Tilezen, open) — SRTM/ASTER/etc. blended.
"""
from __future__ import annotations

import math
import urllib.request
from pathlib import Path
from typing import Tuple

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

# A few dramatic desert/terrain spots (lat, lon).
TERRAIN_PRESETS = {
    "monument_valley": (36.98, -110.10),
    "grand_canyon": (36.10, -112.10),
    "vermilion_cliffs": (36.80, -111.60),
    "sahara_dunes": (23.50, 12.50),
    "namib_desert": (-24.70, 15.30),
    "mountains_alps": (46.55, 8.00),
}


def deg2tile(lat: float, lon: float, z: int) -> Tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def meters_per_pixel(lat: float, z: int) -> float:
    return (40075016.686 * math.cos(math.radians(lat))) / (2 ** z) / 256.0


def fetch_terrain_tile(lat: float, lon: float, z: int, cache_dir: Path, timeout=40) -> Path:
    x, y = deg2tile(lat, lon, z)
    cache_dir = Path(cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    dst = cache_dir / f"terr_{z}_{x}_{y}.png"
    if dst.exists() and dst.stat().st_size > 500:
        return dst
    url = TILE_URL.format(z=z, x=x, y=y)
    req = urllib.request.Request(url, headers={"User-Agent": "FantasyStudio/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dst.write_bytes(r.read())
    return dst


def decode_heightmap(tile_png: Path):
    from PIL import Image
    import numpy as np
    a = np.asarray(Image.open(tile_png).convert("RGB"), dtype=np.float64)
    return (a[:, :, 0] * 256.0 + a[:, :, 1] + a[:, :, 2] / 256.0) - 32768.0


def build_terrain(runner, lat: float, lon: float, work_dir, z: int = 12,
                  crop: int = 96, target_span_m: float = 600.0,
                  verbose: bool = True):
    """Build a desert/mountain terrain mesh from a DEM tile, centred at origin and
    scaled so the visible patch spans ~target_span_m. Returns extent info or None.
    """
    import json
    import numpy as np
    work_dir = Path(work_dir)
    try:
        tile = fetch_terrain_tile(lat, lon, z, work_dir / "_dem_cache")
        H = decode_heightmap(tile)
    except Exception as e:
        if verbose:
            print(f"[composer] dem_terrain: fetch/decode failed ({type(e).__name__}: {e})")
        return None
    n = H.shape[0]
    c0 = (n - crop) // 2
    patch = H[c0:c0 + crop, c0:c0 + crop].copy()
    # real-world metres per pixel, then scale so the patch spans target_span_m
    mpp = meters_per_pixel(lat, z)
    real_span = crop * mpp
    scale = target_span_m / max(real_span, 1.0)
    cell = mpp * scale
    patch = (patch - float(np.median(patch))) * scale  # centre heights, scale Z too

    # write heightmap to JSON the bridge reads
    jp = work_dir / "_dem_data.json"
    jp.write_text(json.dumps({"h": patch.round(2).tolist(), "cell": cell,
                              "crop": crop}), encoding="utf-8")

    code = (
        "import bpy, json\n"
        "import numpy as np\n"
        "D=json.load(open(r'" + str(jp.as_posix()) + "'))\n"
        "h=np.array(D['h']); cell=D['cell']; n=h.shape[0]\n"
        "ox=-(n-1)*cell/2; oy=-(n-1)*cell/2\n"
        "verts=[]; faces=[]\n"
        "for r in range(n):\n"
        "    for cc in range(n):\n"
        "        verts.append((ox+cc*cell, oy+r*cell, float(h[r,cc])))\n"
        "for r in range(n-1):\n"
        "    for cc in range(n-1):\n"
        "        a=r*n+cc; b=r*n+cc+1; d=(r+1)*n+cc; e=(r+1)*n+cc+1\n"
        "        faces.append((a,b,e,d))\n"
        "me=bpy.data.meshes.new('TerrainMesh'); me.from_pydata(verts,[],faces); me.update()\n"
        "for p in me.polygons: p.use_smooth=True\n"
        "ob=bpy.data.objects.new('Terrain',me); bpy.context.scene.collection.objects.link(ob)\n"
        "import json as _j\n"
        "zs=[v[2] for v in verts]\n"
        "__result__=_j.dumps({'span':(n-1)*cell,'min_z':min(zs),'max_z':max(zs)})\n"
    )
    try:
        res = runner.run("dem_terrain", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        ext = json.loads(raw) if isinstance(raw, str) else raw
        if verbose:
            print(f"[composer] dem_terrain: built {crop}x{crop} grid, "
                  f"span {ext.get('span'):.0f}m, relief "
                  f"{ext.get('max_z')-ext.get('min_z'):.0f}m")
        return ext
    except Exception as e:
        if verbose:
            print(f"[composer] dem_terrain: build failed ({type(e).__name__}: {e})")
        return None
