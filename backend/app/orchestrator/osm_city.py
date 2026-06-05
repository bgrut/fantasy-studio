"""Self-contained OpenStreetMap city backdrop.

Blosm loads on Blender 5.1 and fetches OSM fine, but its building-generation step
is unreliable headless (modal operator + needs a separate asset package). So we
reuse the proven OSM *data* path (download via Overpass) and build the geometry
ourselves: parse building footprints + road centerlines, project to local metres,
extrude. Fast, deterministic, no modal ops, no asset dependency.

Data: © OpenStreetMap contributors (ODbL) — attribution required for commercial use.
"""
from __future__ import annotations

import math
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

OVERPASS_SERVERS = [
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def fetch_osm(min_lat, min_lon, max_lat, max_lon, cache_path: Path, timeout=60) -> Path:
    """Download the OSM extent (buildings + highways) to cache_path; reuse if present."""
    cache_path = Path(cache_path)
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    query = (
        f"[out:xml][timeout:{timeout}];("
        f"way[building]({bbox});"
        f"way[highway]({bbox});"
        f");(._;>;);out body;"
    )
    last = None
    for server in OVERPASS_SERVERS:
        try:
            req = urllib.request.Request(server, data=query.encode("utf-8"),
                                         headers={"User-Agent": "FantasyStudio/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if len(data) > 1000:
                cache_path.write_bytes(data)
                return cache_path
        except Exception as e:  # try next server
            last = e
    raise RuntimeError(f"Overpass fetch failed on all servers: {last}")


def _project(lat, lon, lat0, lon0):
    x = (lon - lon0) * 111320.0 * math.cos(math.radians(lat0))
    y = (lat - lat0) * 110540.0
    return x, y


def parse_osm(osm_path: Path) -> Dict:
    """Parse buildings (footprint + height) and roads (centerline) into local metres."""
    import xml.etree.ElementTree as ET
    root = ET.parse(str(osm_path)).getroot()
    nodes: Dict[str, Tuple[float, float]] = {}
    lats, lons = [], []
    for n in root.findall("node"):
        la, lo = float(n.get("lat")), float(n.get("lon"))
        nodes[n.get("id")] = (la, lo)
        lats.append(la); lons.append(lo)
    if not lats:
        return {"buildings": [], "roads": [], "center": (0, 0)}
    lat0 = (min(lats) + max(lats)) / 2.0
    lon0 = (min(lons) + max(lons)) / 2.0

    buildings: List[Dict] = []
    roads: List[Dict] = []
    for w in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
        refs = [nd.get("ref") for nd in w.findall("nd")]
        pts = [_project(*nodes[r], lat0, lon0) for r in refs if r in nodes]
        if len(pts) < 2:
            continue
        if "building" in tags or "building:part" in tags:
            if len(pts) < 3:
                continue
            # close ring (drop duplicate last point)
            if pts[0] == pts[-1]:
                pts = pts[:-1]
            if len(pts) < 3:
                continue
            h = _building_height(tags)
            buildings.append({"footprint": pts, "height": h})
        elif "highway" in tags:
            roads.append({"path": pts, "width": _road_width(tags)})
    return {"buildings": buildings, "roads": roads, "center": (lat0, lon0)}


def _building_height(tags) -> float:
    try:
        if tags.get("height"):
            return max(3.0, float(str(tags["height"]).split()[0]))
    except Exception:
        pass
    try:
        if tags.get("building:levels"):
            return max(3.0, float(tags["building:levels"]) * 3.2)
    except Exception:
        pass
    return 9.0  # ~3 storeys default


def _road_width(tags) -> float:
    hw = tags.get("highway", "")
    return {"motorway": 12.0, "trunk": 10.0, "primary": 9.0, "secondary": 8.0,
            "tertiary": 7.0, "residential": 6.0, "service": 4.0,
            "footway": 2.0, "path": 1.5, "pedestrian": 4.0}.get(hw, 5.0)


# Well-known downtown centres (lat, lon) for named city settings.
CITY_CENTERS = {
    "new_york": (40.7549, -73.9840), "london": (51.5101, -0.1340),
    "tokyo": (35.6586, 139.7016), "paris": (48.8606, 2.3376),
    "chicago": (41.8826, -87.6233), "san_francisco": (37.7929, -122.4039),
}


def make_bbox(center_lat, center_lon, radius_m=350.0):
    dlat = radius_m / 110540.0
    dlon = radius_m / (111320.0 * math.cos(math.radians(center_lat)))
    return (center_lat - dlat, center_lon - dlon, center_lat + dlat, center_lon + dlon)


def build_city(runner, osm_data: Dict, work_dir, name="OsmCity", verbose=True):
    """Create the extruded-building city mesh in Blender from parsed OSM data.
    Returns the city extent {span, cx, cy, max_h} for camera/placement, or None.
    Building footprints + heights are written to a temp JSON the bridge reads
    (avoids a giant code string). Self-contained — no Blosm, no modal ops."""
    import json
    work_dir = Path(work_dir)
    buildings = osm_data.get("buildings", [])
    if not buildings:
        if verbose:
            print("[composer] osm_city: no buildings parsed → skip")
        return None
    jp = (work_dir / f"_citydata_{name}.json")
    jp.write_text(json.dumps({"buildings": buildings}), encoding="utf-8")
    code = (
        "import bpy, json\n"
        "data=json.load(open(r'" + str(jp.as_posix()) + "'))\n"
        "verts=[]; faces=[]\n"
        "for b in data['buildings']:\n"
        "    fp=b['footprint']; h=b['height']; N=len(fp)\n"
        "    base=len(verts)\n"
        "    for (x,y) in fp: verts.append((x,y,0.0))\n"
        "    for (x,y) in fp: verts.append((x,y,h))\n"
        "    for i in range(N):\n"
        "        j=(i+1)%N\n"
        "        faces.append((base+i, base+j, base+N+j, base+N+i))\n"
        "    faces.append(tuple(base+N+i for i in range(N)))\n"
        "me=bpy.data.meshes.new('" + name + "Mesh'); me.from_pydata(verts,[],faces); me.update()\n"
        "ob=bpy.data.objects.new('" + name + "',me); bpy.context.scene.collection.objects.link(ob)\n"
        "m=bpy.data.materials.new('Concrete'); m.use_nodes=True\n"
        "bs=m.node_tree.nodes.get('Principled BSDF')\n"
        "bs.inputs['Base Color'].default_value=(0.45,0.45,0.47,1); bs.inputs['Roughness'].default_value=0.85\n"
        "ob.data.materials.append(m)\n"
        "xs=[v[0] for v in verts]; ys=[v[1] for v in verts]; zs=[v[2] for v in verts]\n"
        "import json as _j\n"
        "__result__=_j.dumps({'cx':(min(xs)+max(xs))/2,'cy':(min(ys)+max(ys))/2,"
        "'span':max(max(xs)-min(xs),max(ys)-min(ys)),'max_h':max(zs),'n':len(data['buildings'])})\n"
    )
    try:
        res = runner.run("osm_city", "execute_python", {"code": code}, critical=False)
        raw = res.get("result") if isinstance(res, dict) else None
        ext = json.loads(raw) if isinstance(raw, str) else raw
        if verbose:
            print(f"[composer] osm_city: built {ext.get('n')} buildings "
                  f"(span {ext.get('span'):.0f}m, tallest {ext.get('max_h'):.0f}m)")
        return ext
    except Exception as e:
        if verbose:
            print(f"[composer] osm_city: build failed ({type(e).__name__}: {e})")
        return None
