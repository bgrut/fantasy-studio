"""Phase 32 — Level Designer: seeded LevelPlan with intent.

A level is no longer a flat plane with random scatter: it has TERRAIN
(seeded value-noise hills), a PATH from spawn to a GOAL beacon (corridor
flattened and kept clear of props), objectives placed ALONG the route, and
LANDMARKS at scenic points. All derived deterministically from the world
seed — "New level" rerolls the whole design; a favorite seed reproduces it.

Computed in Python (one source of truth), injected into the runtime as
world.level. The video side reuses the landmark placement through the shared
dressing pass (terrain-under-hero stays OFF for video until foot-IK lands —
video motion assumes flat ground).
"""
from __future__ import annotations

import math
import random


def _value_noise_grid(rng: random.Random, n: int, octaves=((6, 1.0), (12, 0.35))) -> list[list[float]]:
    """n x n heightfield in [0,1] from bilinearly-upsampled random lattices."""
    out = [[0.0] * n for _ in range(n)]
    total_amp = sum(a for _, a in octaves)
    for res, amp in octaves:
        lat = [[rng.random() for _ in range(res + 1)] for _ in range(res + 1)]
        for i in range(n):
            fi = i / (n - 1) * res
            i0 = min(int(fi), res - 1); ti = fi - i0
            for j in range(n):
                fj = j / (n - 1) * res
                j0 = min(int(fj), res - 1); tj = fj - j0
                v = (lat[i0][j0] * (1 - ti) * (1 - tj) + lat[i0 + 1][j0] * ti * (1 - tj)
                     + lat[i0][j0 + 1] * (1 - ti) * tj + lat[i0 + 1][j0 + 1] * ti * tj)
                out[i][j] += v * amp
    return [[v / total_amp for v in row] for row in out]


def _seg_dist(px, pz, ax, az, bx, bz) -> float:
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / L2))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz))


# ── SEMANTIC LAYOUT (2026-08-25, critique-loop phase 2) ────────────────────
# WorldClaw's layout stage, done locally and deterministically: spatial
# language in the prompt ("a lake in the north, a village on its southern
# shore") becomes REGIONS — organic blobs rasterized onto the same grid the
# heightfield lives on. Terrain, ground paint and vegetation all read them.
# No model in the loop: a parser and a noise-warped distance field give the
# controllable 80% of what their GPT-Image-2 layout map provides, and a
# neural map can slot in behind the same region schema later.

_REGION_KINDS = {
    "lake": "water", "pond": "water", "lagoon": "water", "bay": "water",
    "forest": "forest", "woods": "forest", "woodland": "forest",
    "pines": "forest", "pine forest": "forest", "grove": "forest",
    "village": "village", "town": "village", "hamlet": "village",
    "settlement": "village",
    "meadow": "meadow", "field": "meadow", "plains": "meadow",
    "clearing": "meadow",
    "rocks": "rock", "cliffs": "rock", "crags": "rock", "boulders": "rock",
    "quarry": "rock",
    "beach": "sand", "dunes": "sand", "desert": "sand",
    "hills": "hill", "hill": "hill", "mountain": "hill", "ridge": "hill",
}
_REGION_RADII = {"water": 0.30, "forest": 0.38, "village": 0.20,
                 "meadow": 0.32, "rock": 0.28, "sand": 0.32, "hill": 0.32}
_DIRS = {
    "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
    "northeast": (0.7, -0.7), "northwest": (-0.7, -0.7),
    "southeast": (0.7, 0.7), "southwest": (-0.7, 0.7),
    "center": (0, 0), "centre": (0, 0), "middle": (0, 0),
}


def parse_regions(prompt: str) -> list[dict]:
    """Spatial language -> [{kind, name, dir:(ux,uz)}]. Deterministic; an
    empty list means the prompt asked for nothing spatial and the world
    builds exactly as it always did."""
    import re as _re
    low = (prompt or "").lower()
    out: list[dict] = []
    kind_pat = "|".join(sorted(_REGION_KINDS, key=len, reverse=True))
    dir_pat = "|".join(sorted(_DIRS, key=len, reverse=True))
    # "<kind> in/to/at/toward(s) the <dir>"
    for m in _re.finditer(
            rf"\b({kind_pat})\b[^.,;!?]{{0,26}}?\b(?:in|to|at|towards?|on)\s+the\s+"
            rf"({dir_pat})(?:ern)?\b", low):
        out.append({"kind": _REGION_KINDS[m.group(1)], "name": m.group(1),
                    "dir": _DIRS[m.group(2)]})
    # "<dir>ern <kind>" ("the northern lake")
    for m in _re.finditer(rf"\b({dir_pat})(?:ern)?\s+({kind_pat})\b", low):
        if not any(r["name"] == m.group(2) for r in out):
            out.append({"kind": _REGION_KINDS[m.group(2)], "name": m.group(2),
                        "dir": _DIRS[m.group(1)]})
    # "<kind> on its/the <dir>(ern) shore/bank/edge/side" — relative to the
    # most recent water region; falls back to the direction alone
    for m in _re.finditer(
            rf"\b({kind_pat})\b[^.,;!?]{{0,18}}?\bon\s+(?:its|the)\s+"
            rf"({dir_pat})(?:ern)?\s+(?:shore|bank|edge|side)\b", low):
        kind = _REGION_KINDS[m.group(1)]
        if any(r["name"] == m.group(1) for r in out):
            continue
        anchor = next((r for r in reversed(out) if r["kind"] == "water"), None)
        out.append({"kind": kind, "name": m.group(1),
                    "dir": _DIRS[m.group(2)], "shore_of": bool(anchor)})
    # dedupe by (kind, dir): "lake in the north ... the northern lake" is one
    seen, ded = set(), []
    for r in out:
        key = (r["kind"], r["dir"])
        if key in seen:
            continue
        seen.add(key)
        ded.append(r)
    return ded[:5]                        # a valley is not an atlas


def _rasterize_regions(regions: list[dict], grid_n: int, size_m: float,
                       seed: int, path: list[list[float]]) -> dict | None:
    """Region seeds -> per-cell (id, weight) on the heights grid. Blob
    boundaries are warped by value noise so nothing reads as a circle."""
    if not regions:
        return None
    rng = random.Random(seed * 17 + 3)
    half = size_m / 2.0

    def _pdist(x, z):
        return min(_seg_dist(x, z, *path[k], *path[k + 1])
                   for k in range(len(path) - 1))

    seeds = []
    prev_water = None
    for r in regions:
        ux, uz = r["dir"]
        if r.get("shore_of") and prev_water:
            # sit at the water blob's rim, on the stated side of it
            wx, wz, wrad = prev_water
            ax, az = wx + ux * wrad * 1.25, wz + uz * wrad * 1.25
        else:
            ax, az = ux * half * 0.55, uz * half * 0.55
        rad = _REGION_RADII.get(r["kind"], 0.3) * half
        # candidate seeds: water flees the mission path (a causeway through a
        # lake is a defect), a village hugs it (a village nobody passes is
        # scenery, not a place)
        best, best_score = (ax, az), None
        for _ in range(12):
            cx = max(-half * 0.8, min(half * 0.8,
                                      ax + rng.uniform(-0.16, 0.16) * half))
            cz = max(-half * 0.8, min(half * 0.8,
                                      az + rng.uniform(-0.16, 0.16) * half))
            d = _pdist(cx, cz)
            if r["kind"] == "water":
                score = d
            elif r["kind"] == "village":
                score = -abs(d - 14.0)    # near the path, not ON it
            else:
                score = 0 if best_score is None else best_score
            if best_score is None or score > best_score:
                best, best_score = (cx, cz), score
        seeds.append((best[0], best[1], rad, r["kind"]))
        if r["kind"] == "water":
            prev_water = (best[0], best[1], rad)

    wx_g = _value_noise_grid(rng, grid_n)
    wz_g = _value_noise_grid(rng, grid_n)
    grid, weights = [], []
    for i in range(grid_n):
        z = (i / (grid_n - 1) - 0.5) * size_m
        for j in range(grid_n):
            x = (j / (grid_n - 1) - 0.5) * size_m
            # domain warp: ±14% of half, enough to break every circle
            px = x + (wx_g[i][j] - 0.5) * 0.28 * half
            pz = z + (wz_g[i][j] - 0.5) * 0.28 * half
            bid, bw = -1, 0.0
            for si, (sx, sz, rad, _k) in enumerate(seeds):
                t = 1.0 - math.hypot(px - sx, pz - sz) / rad
                if t <= 0.04:
                    continue
                w = min(1.0, t * 1.4)
                w = w * w * (3 - 2 * w)   # smoothstep falloff
                if w > bw:
                    bid, bw = si, w
            grid.append(bid)
            weights.append(round(bw, 2))
    return {"grid": grid,
            "w": weights,
            "palette": [{"kind": k, "x": round(sx, 1), "z": round(sz, 1),
                         "r": round(rad, 1)}
                        for (sx, sz, rad, k) in seeds]}


def _cell_kind(raster: dict, grid_n: int, size_m: float,
               x: float, z: float) -> str | None:
    """Region kind at a world position, or None outside every region."""
    j = max(0, min(grid_n - 1, int((x / size_m + 0.5) * (grid_n - 1) + 0.5)))
    i = max(0, min(grid_n - 1, int((z / size_m + 0.5) * (grid_n - 1) + 0.5)))
    rid = raster["grid"][i * grid_n + j]
    return None if rid < 0 else raster["palette"][rid]["kind"]


def build_level(seed: int, size_m: float, n_objectives: int = 0,
                amplitude_m: float = 2.4, grid_n: int = 48,
                regions: list[dict] | None = None) -> dict:
    """Deterministic LevelPlan. Returns a JSON-safe dict for the runtime."""
    rng = random.Random(seed)

    # ── zones: spawn at origin; goal at a far edge; corridor between ────────
    half = size_m / 2.0
    ang = rng.uniform(0, 2 * math.pi)
    goal_r = half * rng.uniform(0.62, 0.80)
    goal = [math.cos(ang) * goal_r, math.sin(ang) * goal_r]

    # path: spawn -> two jittered midpoints -> goal (a walk, not a beeline)
    path = [[0.0, 0.0]]
    for f in (0.35, 0.68):
        mx, mz = goal[0] * f, goal[1] * f
        # jitter perpendicular to the spawn->goal axis
        px, pz = -goal[1] / max(goal_r, 1e-6), goal[0] / max(goal_r, 1e-6)
        j = rng.uniform(-0.22, 0.22) * goal_r
        path.append([mx + px * j, mz + pz * j])
    path.append(list(goal))
    corridor = 5.5                                   # flattened, prop-free (m)

    # ── terrain: hills, flattened along the corridor + zones ────────────────
    raster = _rasterize_regions(regions or [], grid_n, size_m, seed, path)
    has_water = bool(raster) and any(
        p["kind"] == "water" for p in raster["palette"])
    hgrid = _value_noise_grid(rng, grid_n)
    heights: list[float] = []
    for i in range(grid_n):
        z = (i / (grid_n - 1) - 0.5) * size_m
        for j in range(grid_n):
            x = (j / (grid_n - 1) - 0.5) * size_m
            h = (hgrid[i][j] - 0.45) * 2.0 * amplitude_m
            # MICRO-RELIEF (Phase 93): a second, higher-frequency octave —
            # real ground undulates at the metre scale, not only in big
            # hills. Mesh + collider share these heights, so feet/wheels
            # track the detail for free.
            i2, j2 = (i * 3) % grid_n, (j * 3) % grid_n
            h += (hgrid[i2][j2] - 0.5) * 0.5 * min(amplitude_m, 1.2)
            # REGION MODULATION, before the corridor flattens the path: the
            # route must stay walkable whatever the layout asked for, so the
            # corridor always has the last word.
            if raster is not None:
                _rid = raster["grid"][i * grid_n + j]
                if _rid >= 0:
                    _w = raster["w"][i * grid_n + j]
                    _rk = raster["palette"][_rid]["kind"]
                    if _rk == "water":
                        # basin: sharpen the weight so the bed is flat and
                        # the shore is a real slope, not a 40m ramp
                        _wb = _w ** 0.65
                        h = h * (1 - _wb) + (-2.6) * _wb
                    elif _rk == "hill":
                        h += _w * max(3.4, amplitude_m * 1.6)
                    elif _rk == "rock":
                        h += _w * 1.6 + (hgrid[i2][j2] - 0.5) * _w * 1.8
                    elif _rk in ("village", "meadow"):
                        h *= (1 - _w * 0.75)
                if has_water and h < -0.35 and (
                        _rid < 0 or raster["palette"][_rid]["kind"] != "water"):
                    h = -0.35            # nothing but the lake dips below water
            d = min(_seg_dist(x, z, *path[k], *path[k + 1]) for k in range(len(path) - 1))
            d = min(d, math.hypot(x, z), math.hypot(x - goal[0], z - goal[1]))
            if d < corridor:
                h = 0.0
            elif d < corridor * 2.2:                 # smooth shoulder
                t = (d - corridor) / (corridor * 1.2)
                h *= t * t * (3 - 2 * t)
            edge = max(abs(x), abs(z)) / half        # settle flat at the walls
            if edge > 0.92:
                h *= max(0.0, (1.0 - edge) / 0.08)
            heights.append(round(h, 3))

    # ── objectives along the route (progress-ordered, lateral jitter) ───────
    collect_points = []
    for k in range(n_objectives):
        f = (k + 1) / (n_objectives + 1)
        # position along the polyline at fraction f
        seg = min(int(f * (len(path) - 1)), len(path) - 2)
        t = f * (len(path) - 1) - seg
        x = path[seg][0] + (path[seg + 1][0] - path[seg][0]) * t
        z = path[seg][1] + (path[seg + 1][1] - path[seg][1]) * t
        px, pz = -(path[seg + 1][1] - path[seg][1]), (path[seg + 1][0] - path[seg][0])
        m = math.hypot(px, pz) or 1.0
        j = rng.uniform(-corridor * 0.5, corridor * 0.5)
        collect_points.append([round(x + px / m * j, 2), round(z + pz / m * j, 2)])

    # ── landmarks: 2 scenic giants off the path ─────────────────────────────
    landmarks = []
    for _ in range(2):
        for _try in range(24):
            la = rng.uniform(0, 2 * math.pi)
            lr = half * rng.uniform(0.35, 0.75)
            lx, lz = math.cos(la) * lr, math.sin(la) * lr
            d = min(_seg_dist(lx, lz, *path[k], *path[k + 1]) for k in range(len(path) - 1))
            if raster is not None and _cell_kind(raster, grid_n, size_m, lx, lz) == "water":
                continue                  # a 30m tree in a lake is a defect
            if d > corridor * 2.0:
                landmarks.append([round(lx, 2), round(lz, 2), round(rng.uniform(2.2, 3.2), 2)])
                break

    # ── POINTS OF INTEREST (moon plan 2.1): 3-5 templated micro-locations
    # off the mission path — a ruined tower, a campsite, a shrine, a stone
    # circle, a lumber camp. Each is a prop cluster + a reward spot. This is
    # what makes open worlds read as DESIGNED: players route POI to POI.
    _POI_KINDS = ["ruin", "camp", "shrine", "circle", "lumber"]
    pois = []
    for _pk in range(rng.randint(3, 5)):
        for _try in range(30):
            pa = rng.uniform(0, 2 * math.pi)
            pr = half * rng.uniform(0.30, 0.78)
            px2, pz2 = math.cos(pa) * pr, math.sin(pa) * pr
            d = min(_seg_dist(px2, pz2, *path[k], *path[k + 1])
                    for k in range(len(path) - 1))
            far_others = all(math.hypot(px2 - q["x"], pz2 - q["z"]) > 18
                             for q in pois)
            if raster is not None and _cell_kind(raster, grid_n, size_m, px2, pz2) == "water":
                continue
            if d > corridor * 1.8 and far_others:
                pois.append({"kind": rng.choice(_POI_KINDS),
                             "x": round(px2, 2), "z": round(pz2, 2),
                             "rot": round(rng.uniform(0, 6.28), 2)})
                break
    if raster is not None:
        for pal in raster["palette"]:
            if pal["kind"] == "village":
                # the flattened clearing gets its settlement — prepended so
                # the camp props cluster at the village heart, not randomly
                pois.insert(0, {"kind": "camp", "x": pal["x"], "z": pal["z"],
                                "rot": round(rng.uniform(0, 6.28), 2)})
    out_level = {
        "pois": pois,
        "grid_n": grid_n, "size_m": size_m, "amplitude_m": amplitude_m,
        "heights": heights,                    # row-major, z rows then x cols
        "path": [[round(a, 2), round(b, 2)] for a, b in path],
        "corridor_m": corridor,
        "goal": [round(goal[0], 2), round(goal[1], 2)],
        "collect_points": collect_points,
        "landmarks": landmarks,                # [x, z, scale]
    }
    if raster is not None:
        out_level["regions"] = raster
        out_level["regions_src"] = regions     # edits re-parse from here
        if has_water:
            out_level["water_suggest"] = -0.8  # lake level; bed is at -2.6
    return out_level


def landmark_spots(seed: int, size_m: float) -> list[list[float]]:
    """Video-side flow-back: the SAME landmark placement for set dressing."""
    return build_level(seed, size_m)["landmarks"]


# ── REAL CITIES (shared with the video pipeline's OSM system) ────────────────
_CITY_ALIASES = {
    "new york": "new_york", "manhattan": "new_york", "nyc": "new_york",
    "london": "london", "tokyo": "tokyo", "paris": "paris",
    "chicago": "chicago", "san francisco": "san_francisco", "sf ": "san_francisco",
}


def detect_place(prompt: str) -> str | None:
    t = (prompt or "").lower()
    for alias, key in _CITY_ALIASES.items():
        if alias in t:
            return key
    return None


def _road_route(roads: list[dict], half: float) -> list[list[float]] | None:
    """Longest drivable route through the road graph, starting from the point
    nearest the city center. Dijkstra over snapped polyline nodes; the race
    path (and every vehicle NPC) follows REAL streets, not a random walk."""
    key = lambda p: (round(p[0] / 3.0), round(p[1] / 3.0))
    adj: dict = {}
    coord: dict = {}
    for r in roads:
        pts = r["pts"]
        for a, b in zip(pts, pts[1:]):
            ka, kb = key(a), key(b)
            if ka == kb:
                continue
            coord.setdefault(ka, a)
            coord.setdefault(kb, b)
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            adj.setdefault(ka, []).append((kb, d))
            adj.setdefault(kb, []).append((ka, d))
    if not adj:
        return None
    start = min(coord, key=lambda k: coord[k][0] ** 2 + coord[k][1] ** 2)
    import heapq
    dist = {start: 0.0}
    prev: dict = {}
    pq = [(0.0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    # farthest reachable node, capped so the route fits the world
    target_len = half * 1.5
    end = max(dist, key=lambda k: min(dist[k], target_len))
    chain = [end]
    while chain[-1] != start:
        chain.append(prev[chain[-1]])
    chain.reverse()
    route, acc = [list(coord[start])], 0.0
    for k in chain[1:]:
        p = coord[k]
        acc += math.hypot(p[0] - route[-1][0], p[1] - route[-1][1])
        route.append([p[0], p[1]])
        if acc >= target_len:
            break
    if acc < 40.0:                       # too short to race — keep procedural path
        return None
    # resample to ~10m spacing (waypoint AI cuts corners on sparse polylines),
    # capped at 40 points (runtime pathDist cost)
    dense = [route[0]]
    for a, b in zip(route, route[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        for k in range(1, int(seg // 10) + 1):
            t = k * 10 / seg
            dense.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
        dense.append(list(b))
    step = max(1, len(dense) // 40)
    thinned = dense[::step]
    if thinned[-1] != dense[-1]:
        thinned.append(dense[-1])
    return [[round(x, 1), round(z, 1)] for x, z in thinned]


def build_osm_city(place: str, size_m: float, max_buildings: int = 500) -> dict | None:
    """Real building footprints + roads for `place` (video pipeline's OSM
    fetch/parse, shared cache). The whole district is SHIFTED so the road
    route starts at the player spawn (origin). Returns None on any failure —
    the procedural city recipe stays the fallback."""
    try:
        from pathlib import Path
        from app.orchestrator import osm_city
        center = osm_city.CITY_CENTERS.get(place)
        if not center:
            return None
        cache = Path(__file__).resolve().parents[2] / "renders" / "_osm_cache" / f"{place}_{int(size_m)}.osm"
        cache.parent.mkdir(parents=True, exist_ok=True)
        bb = osm_city.make_bbox(*center, radius_m=size_m / 2.0)
        # RESILIENCE (2026-07-29 Tokyo report): Overpass hiccups are common —
        # one retry after a beat before giving up on the real city
        try:
            osm_city.fetch_osm(*bb, cache_path=cache)
        except Exception:
            import time as _t
            _t.sleep(3)
            try:
                osm_city.fetch_osm(*bb, cache_path=cache)
            except Exception:
                # r15 CACHE FALLBACK (Tokyo report): a different world size
                # misses the size-keyed cache and a live Overpass failure
                # then silently dropped the REAL city. Any cached scan of
                # this place beats the procedural fallback — use the
                # largest one we have.
                others = sorted(cache.parent.glob(f"{place}_*.osm"),
                                key=lambda p: p.stat().st_size, reverse=True)
                if not others:
                    raise
                cache = others[0]
        data = osm_city.parse_osm(cache)
        half = size_m / 2.0
        blds = []
        for b in data.get("buildings", []):
            pts = [(round(float(x), 1), round(float(y), 1)) for x, y in b["footprint"]]
            if not pts:
                continue
            cx = sum(p[0] for p in pts) / len(pts)
            cz = sum(p[1] for p in pts) / len(pts)
            if abs(cx) > half or abs(cz) > half:
                continue
            blds.append({"pts": pts, "h": round(float(b.get("height", 9.0)), 1),
                         "use": str(b.get("use") or "")[:24],
                         "d": cx * cx + cz * cz})
        blds.sort(key=lambda b: b["d"])
        for b in blds:
            b.pop("d", None)
        roads = []
        for r in data.get("roads", [])[:120]:
            pts = [(round(float(x), 1), round(float(y), 1)) for x, y in r.get("path", [])]
            if len(pts) >= 2:
                roads.append({"pts": pts, "w": round(float(r.get("width", 7.0)), 1)})
        if len(blds) < 10:
            return None

        # ROUTE: longest street chain from the district center; shift the whole
        # district so the route STARTS at the player spawn (origin).
        route = _road_route(roads, half)
        sx, sz = (route[0][0], route[0][1]) if route else (0.0, 0.0)
        if sx or sz:
            for b in blds:
                b["pts"] = [(round(x - sx, 1), round(z - sz, 1)) for x, z in b["pts"]]
            for r in roads:
                r["pts"] = [(round(x - sx, 1), round(z - sz, 1)) for x, z in r["pts"]]
            if route:
                route = [[round(x - sx, 1), round(z - sz, 1)] for x, z in route]
        # re-filter to world bounds after the shift
        def _inside(pts):
            cx = sum(p[0] for p in pts) / len(pts)
            cz = sum(p[1] for p in pts) / len(pts)
            return abs(cx) < half * 0.95 and abs(cz) < half * 0.95
        blds = [b for b in blds if _inside(b["pts"])]
        if route:                        # truncate the route at the walls
            clipped = []
            for p in route:
                if abs(p[0]) >= half * 0.85 or abs(p[1]) >= half * 0.85:
                    break
                clipped.append(p)
            route = clipped if len(clipped) >= 3 else None
        out = {"place": place, "buildings": blds[:max_buildings], "roads": roads}
        if route:
            out["route"] = route
        return out
    except Exception:
        return None

def build_interior(seed: int, kind: str = "castle") -> dict:
    """Room-plan for INTERIOR levels (Phase 95): a hall plus side chambers,
    doorway gaps, furniture placements and torch lights — the geometry the
    runtime turns into textured walls with colliders. Deterministic per seed.

    kind: castle | house | dungeon — picks wall/floor texture + furniture mix.
    """
    import random as _random
    rng = _random.Random(seed * 31 + 7)
    H = 4.2 if kind in ("castle",) else 3.0          # wall height (m)
    T = 0.5                                          # wall thickness
    rooms = []                                       # [cx, cz, w, d]
    # PER-KIND LAYOUT (2026-07-23: 'the viking dungeon was the same style as
    # the mansion') — a castle is a grand pillared hall, a house is cosy
    # small rooms, a dungeon is a long narrow corridor-hall with cells.
    if kind == "shop":
        # A store is one wide room you can see across the moment you step in
        # — shallow, no processional hall, with a back-of-house behind it.
        hall_w = rng.uniform(13, 17)
        hall_d = rng.uniform(11, 15)
    elif kind == "office":
        # A tower's floor plate is WIDE and shallow with a service core, not a
        # long processional hall. Walking into a skyscraper and finding a
        # pillared mansion was the loudest thing wrong with the city heist.
        hall_w = rng.uniform(20, 26)
        hall_d = rng.uniform(20, 26)
    elif kind == "castle":
        hall_w = rng.uniform(17, 22)
        hall_d = rng.uniform(32, 42)
    elif kind == "dungeon":
        hall_w = rng.uniform(7.5, 9.5)               # narrow corridor spine
        hall_d = rng.uniform(38, 48)
    else:                                            # house
        hall_w = rng.uniform(9, 12)
        hall_d = rng.uniform(16, 22)
    rooms.append([0.0, 0.0, hall_w, hall_d])
    n_side = {"castle": rng.randint(2, 3), "dungeon": rng.randint(4, 6),
              "office": rng.randint(3, 4), "shop": rng.randint(1, 2)}.get(
                  kind, rng.randint(2, 4))
    for k in range(n_side):
        side = 1 if k % 2 == 0 else -1
        if kind == "dungeon":                        # cells off the corridor
            rw = rng.uniform(4.5, 6.5)
            rd = rng.uniform(4.5, 6.5)
        elif kind == "shop":                         # stock room / back office
            rw = rng.uniform(4.5, 6.5)
            rd = rng.uniform(4, 6)
        elif kind == "office":                       # meeting rooms off the floor
            rw = rng.uniform(6.5, 9)
            rd = rng.uniform(6, 8.5)
        elif kind == "house":
            rw = rng.uniform(5.5, 8)
            rd = rng.uniform(5.5, 9)
        else:
            rw = rng.uniform(8, 12)
            rd = rng.uniform(8, 13)
        cz = -hall_d / 2 + (k + 0.5 + rng.uniform(0, 0.3)) * (hall_d / n_side)
        rooms.append([side * (hall_w / 2 + rw / 2), cz, rw, rd])
    walls = []                                       # [cx, cz, len, rotY(0|90), doorAt(-1 none | 0..1)]
    def _wall(cx, cz, ln, rot, door=-1.0):
        walls.append([round(cx, 2), round(cz, 2), round(ln, 2), rot, round(door, 2)])
    hw, hd = hall_w / 2, hall_d / 2
    # hall perimeter; door gaps where side rooms attach + entry at one end
    _wall(0, -hd, hall_w, 0, 0.5)                    # entry door (south)
    _wall(0, hd, hall_w, 0, -1)
    for i, (cx, cz, rw, rd) in enumerate(rooms[1:]):
        side = 1 if cx > 0 else -1
        # hall wall segment sharing this room gets a door at the room center
        door_t = (cz + hd) / hall_d
        _wall(side * hw, 0, hall_d, 90, door_t)
        # room's outer three walls
        _wall(cx + side * rw / 2, cz, rd, 90, -1)
        _wall(cx, cz - rd / 2, rw, 0, -1)
        _wall(cx, cz + rd / 2, rw, 0, -1)
    # dedupe shared hall-side walls (one per side, keep the FIRST with door)
    seen_side = {}
    ded = []
    for w in walls:
        key = (w[0], w[1], w[3]) if w[3] == 90 else None
        if key and key in seen_side:
            continue
        if key:
            seen_side[key] = True
        ded.append(w)
    walls = ded
    # any hall side with NO room still needs its wall
    for side in (1, -1):
        if not any(w[3] == 90 and abs(w[0] - side * hw) < 0.1 for w in walls):
            _wall(side * hw, 0, hall_d, 90, -1)
    # furniture: name + position + yaw; runtime resolves to props
    FURN = {
        "castle": ["table", "chair", "chair", "barrel", "crate", "bookshelf"],
        "house":  ["table", "chair", "chair", "bed", "bookshelf", "crate"],
        "dungeon": ["barrel", "crate", "crate", "barrel", "table"],
        # desks and filing cabinets, expressed in props that already exist —
        # a new interior kind must not also become an asset dependency
        "office": ["table", "chair", "chair", "bookshelf", "table", "crate"],
        # shelving and stock: the runtime draws the real fittings, these are
        # only the scatter that keeps the floor from reading as empty
        "shop": ["bookshelf", "crate", "table", "crate", "bookshelf"],
    }[kind if kind in ("castle", "house", "dungeon", "office", "shop") else "castle"]
    furniture = []
    for cx, cz, rw, rd in rooms:
        for name in rng.sample(FURN, k=min(3, len(FURN))):
            fx = cx + rng.uniform(-rw / 2 + 1.2, rw / 2 - 1.2)
            fz = cz + rng.uniform(-rd / 2 + 1.2, rd / 2 - 1.2)
            furniture.append([name, round(fx, 2), round(fz, 2),
                              round(rng.uniform(0, 6.28), 2)])
    # torches on the hall walls + one per room
    torches = []
    for k in range(4):
        tz = -hd + (k + 0.5) * (hall_d / 4)
        for side in (1, -1):
            torches.append([round(side * (hw - 0.3), 2), round(tz, 2)])
    for cx, cz, rw, rd in rooms[1:]:
        torches.append([round(cx, 2), round(cz - rd / 2 + 0.4, 2)])
    # castle/temple grandeur: two rows of pillars down the hall
    pillars = []
    if kind == "castle":
        px = hall_w / 4
        n_pil = max(2, int(hall_d // 7))
        for k in range(n_pil):
            pz = -hall_d / 2 + (k + 0.5) * (hall_d / n_pil)
            pillars.append([round(px, 2), round(pz, 2)])
            pillars.append([round(-px, 2), round(pz, 2)])
    # MULTI-FLOOR (moon plan 2.4): castles and houses get a second story
    # reached by real stairs (dungeons stay single-level crawls)
    floors = 2 if kind in ("castle", "house") else 1
    return {
        "kind": kind, "wall_h": H, "wall_t": T, "pillars": pillars,
        "floors": floors,
        "rooms": [[round(v, 2) for v in r] for r in rooms],
        "walls": walls, "furniture": furniture, "torches": torches,
        "bounds": [round(hall_w + 26, 1), round(hall_d + 8, 1)],
    }


# ── MULTI-BUILDING HEIST (2026-08-05) ───────────────────────────────────────
# A city heist is a ROUTE, not a room: pick a handful of real OSM footprints,
# give each one its own interior plan parked past the map edge, and put a
# glowing door on the street face of each. The player works the block —
# in, steal, out, next door. Selection has to agree with the runtime's own
# building cull or a door ends up floating where no building was drawn, so
# the chosen footprints are TAGGED (`enter`) and the runtime keeps them.

def _poly_exit_point(pts, cx, cz, ux, uz) -> tuple[float, float]:
    """Where the ray (c + t*u) last leaves the footprint polygon."""
    best = 0.0
    n = len(pts)
    for i in range(n):
        ax, az = pts[i]
        bx, bz = pts[(i + 1) % n]
        ex, ez = bx - ax, bz - az
        den = ux * ez - uz * ex
        if abs(den) < 1e-9:
            continue
        t = ((ax - cx) * ez - (az - cz) * ex) / den
        s = ((ax - cx) * uz - (az - cz) * ux) / den
        if t > best and -0.001 <= s <= 1.001:
            best = t
    return cx + ux * best, cz + uz * best


def _road_dist(roads, x, z) -> float:
    best = 1e9
    for r in roads:
        p = r["pts"]
        for i in range(len(p) - 1):
            d = _seg_dist(x, z, p[i][0], p[i][1], p[i + 1][0], p[i + 1][1])
            if d < best:
                best = d
                if best < 1.0:
                    return best
    return best


def _nearest_road_point(roads, x, z) -> tuple[float, float]:
    best, bp = 1e9, (x + 1.0, z)
    for r in roads:
        p = r["pts"]
        for i in range(len(p) - 1):
            ax, az, bx, bz = p[i][0], p[i][1], p[i + 1][0], p[i + 1][1]
            dx, dz = bx - ax, bz - az
            L2 = dx * dx + dz * dz
            t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / L2))
            qx, qz = ax + t * dx, az + t * dz
            d = math.hypot(x - qx, z - qz)
            if d < best:
                best, bp = d, (qx, qz)
    return bp


def nearest_road_yaw(roads, x, z) -> float | None:
    """Heading (degrees, runtime yaw convention) of the road segment nearest
    (x, z), or None when there are no roads.

    A dropped shopfront that ignores the street reads as a mistake even when
    it lands exactly where the user aimed (2026-08-06): real buildings face
    the road they front onto. Returning the SEGMENT direction rather than the
    bearing to the road lets callers align a facade parallel to the kerb.
    """
    best, ang = 1e9, None
    for r in roads or []:
        p = r.get("pts") or []
        for i in range(len(p) - 1):
            ax, az, bx, bz = p[i][0], p[i][1], p[i + 1][0], p[i + 1][1]
            dx, dz = bx - ax, bz - az
            L2 = dx * dx + dz * dz
            if L2 < 1e-9:
                continue
            t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / L2))
            qx, qz = ax + t * dx, az + t * dz
            d = math.hypot(x - qx, z - qz)
            if d < best:
                best = d
                ang = math.degrees(math.atan2(dx, dz))
    return None if ang is None else round(ang % 360.0, 1)


def plan_enterables(osm: dict, level: dict, seed: int, size_m: float,
                    want: int = 4) -> list[dict]:
    """Choose `want` OSM buildings to make enterable and plan each interior.

    Returns [{plan, door, ox, label, kind, center}] — `ox` is the x-offset the
    runtime builds that building's rooms at (far past the map edge, one lane
    each so two interiors can never share a wall). Tags the chosen footprints
    in `osm` with `enter` so the runtime's path/spawn cull spares them.
    """
    blds = osm.get("buildings") or []
    roads = osm.get("roads") or []
    if not blds or not roads:
        return []
    path = level.get("path") or []
    corr = (level.get("corridor_m") or 5.5) + 1.5
    goal = level.get("goal") or [1e9, 1e9]
    half = size_m / 2.0

    def _path_dist(x, z) -> float:
        if len(path) < 2:
            return 1e9
        return min(_seg_dist(x, z, path[k][0], path[k][1],
                             path[k + 1][0], path[k + 1][1])
                   for k in range(len(path) - 1))

    def _sweep(min_side, min_r, max_r, sep):
        cands = []
        for b in blds:
            pts = b["pts"]
            xs = [p[0] for p in pts]
            zs = [p[1] for p in pts]
            w, d = max(xs) - min(xs), max(zs) - min(zs)
            cx, cz = (max(xs) + min(xs)) / 2, (max(zs) + min(zs)) / 2
            r = math.hypot(cx, cz)
            if not (min_side <= w <= 80.0 and min_side <= d <= 80.0):
                continue                              # too thin to read as a venue
            if not (min_r <= r <= max_r):             # a walk, but not a hike
                continue
            if math.hypot(cx - goal[0], cz - goal[1]) < 14.0:
                continue                              # runtime skips these
            if _path_dist(cx, cz) < corr + max(w, d) / 2 + 1.0:
                continue
            if _road_dist(roads, cx, cz) > 30.0:      # no street, no burglary
                continue
            cands.append((r, b, cx, cz, w, d))
        cands.sort(key=lambda c: c[0])                # nearest first: a block walk
        out2 = []
        for c in cands:
            if any(math.hypot(c[2] - p[2], c[3] - p[3]) < sep for p in out2):
                continue                              # spread across the block
            out2.append(c)
            if len(out2) >= want:
                break
        return out2

    # A REAL OSM DISTRICT IS THINNER THAN IT LOOKS (2026-08-05): the cached
    # 360 m Manhattan scan carries 46 footprints, and the handsome-venue
    # filter left three. Sweep once for the ideal block, then relax the
    # radius and the spacing rather than shipping a one-door "multi" heist.
    picked = _sweep(11.0, 24.0, half * 0.62, 34.0)
    if len(picked) < min(want, 3):
        picked = _sweep(8.0, 15.0, half * 0.88, 22.0)
    if len(picked) < 2:
        return []

    _LABELS = ["the brownstone", "the corner gallery", "the townhouse",
               "the old bank", "the loft building", "the counting house"]
    out = []
    ox = size_m * 2.2
    for k, (r, b, cx, cz, w, d) in enumerate(picked):
        h = float(b.get("h") or 9.0)
        area = w * d
        # 2026-08-07: every low venue was a "house", so walking into a shop
        # on a commercial street gave you somebody's sitting room. Ground
        # floors on a street are retail; a house is what you get when the
        # footprint is big and set back enough to be one.
        kind = ("office" if h >= 20.0
                else "dungeon" if area > 1600
                else "shop" if h < 14.0
                else "house")
        # NO TWO VENUES IN A ROW LOOK ALIKE (2026-08-05 playtest): the block's
        # two towers both scored `castle` and the second break-in was the
        # first one repeated — same stone, same red runner, same pillars. The
        # kind drives ALL of a room's identity, so rotate off a repeat.
        if out and out[-1]["kind"] == kind:
            kind = {"castle": "house", "house": "shop", "shop": "house",
                    "dungeon": "office", "office": "shop"}[kind]
        plan = build_interior(seed + 101 + k * 37, kind)
        # ONE STOREY PER VENUE in a city heist: four two-storey plans is four
        # extra ceilings, four staircases and eight more point lights, and the
        # WebGL2 light budget is the thing that renders a black room rather
        # than warning you. The stairs stay for single-building heists.
        plan["floors"] = 1
        b["enter"] = k                                # runtime must not cull it
        # the door goes on the street face: ride the centroid->nearest-road
        # direction out through the footprint, then a step clear of the wall
        rx, rz = _nearest_road_point(roads, cx, cz)
        ux, uz = rx - cx, rz - cz
        m = math.hypot(ux, uz) or 1.0
        ux, uz = ux / m, uz / m
        ex, ez = _poly_exit_point(b["pts"], cx, cz, ux, uz)
        door = [round(ex + ux * 1.1, 2), round(ez + uz * 1.1, 2)]
        out.append({
            "plan": plan, "door": door, "ox": round(ox, 1),
            "label": _LABELS[k % len(_LABELS)], "kind": kind,
            "center": [round(cx, 2), round(cz, 2)],
        })
        ox += plan["bounds"][0] + 30.0
    return out


def spread_loot(enterables: list[dict], n: int, seed: int) -> list[list[float]]:
    """`n` collect points spread ACROSS the enterable buildings' rooms.

    Round-robin by building so a 4-jewel heist really is four break-ins, and
    never in a hall's entry strip (rooms[0]) where the player lands.
    """
    import random as _random
    rng = _random.Random(seed * 17 + 3)
    pts = []
    for i in range(n):
        e = enterables[i % len(enterables)]
        rooms = e["plan"]["rooms"]
        pool = rooms[1:] if len(rooms) > 1 else rooms
        cx, cz, rw, rd = pool[(i // len(enterables)) % len(pool)]
        pts.append([round(e["ox"] + cx + rng.uniform(-rw / 2 + 1.2, rw / 2 - 1.2), 2),
                    round(cz + rng.uniform(-rd / 2 + 1.2, rd / 2 - 1.2), 2)])
    return pts

