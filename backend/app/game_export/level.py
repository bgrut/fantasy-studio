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
