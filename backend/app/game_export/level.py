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


def build_level(seed: int, size_m: float, n_objectives: int = 0,
                amplitude_m: float = 2.4, grid_n: int = 48) -> dict:
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
            if d > corridor * 2.0:
                landmarks.append([round(lx, 2), round(lz, 2), round(rng.uniform(2.2, 3.2), 2)])
                break

    return {
        "grid_n": grid_n, "size_m": size_m, "amplitude_m": amplitude_m,
        "heights": heights,                    # row-major, z rows then x cols
        "path": [[round(a, 2), round(b, 2)] for a, b in path],
        "corridor_m": corridor,
        "goal": [round(goal[0], 2), round(goal[1], 2)],
        "collect_points": collect_points,
        "landmarks": landmarks,                # [x, z, scale]
    }


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


def build_osm_city(place: str, size_m: float, max_buildings: int = 320) -> dict | None:
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
        osm_city.fetch_osm(*bb, cache_path=cache)
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
