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
            if d > corridor * 1.8 and far_others:
                pois.append({"kind": rng.choice(_POI_KINDS),
                             "x": round(px2, 2), "z": round(pz2, 2),
                             "rot": round(rng.uniform(0, 6.28), 2)})
                break
    return {
        "pois": pois,
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
    if kind == "castle":
        hall_w = rng.uniform(17, 22)
        hall_d = rng.uniform(32, 42)
    elif kind == "dungeon":
        hall_w = rng.uniform(7.5, 9.5)               # narrow corridor spine
        hall_d = rng.uniform(38, 48)
    else:                                            # house
        hall_w = rng.uniform(9, 12)
        hall_d = rng.uniform(16, 22)
    rooms.append([0.0, 0.0, hall_w, hall_d])
    n_side = {"castle": rng.randint(2, 3), "dungeon": rng.randint(4, 6)}.get(
        kind, rng.randint(2, 4))
    for k in range(n_side):
        side = 1 if k % 2 == 0 else -1
        if kind == "dungeon":                        # cells off the corridor
            rw = rng.uniform(4.5, 6.5)
            rd = rng.uniform(4.5, 6.5)
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
    }[kind if kind in ("castle", "house", "dungeon") else "castle"]
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

