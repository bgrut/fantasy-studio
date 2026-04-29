"""
app.services.camera_director
============================
V1.3.3 — closed-loop hero-camera placement.

The director is the ONLY authoritative source of hero-camera placement.
Earlier versions used a multiplier table tuned by hand per hero size.
V1.3.3 replaces that with closed-loop math: given a target subject-fill
fraction (config constant per shot profile), the actual lens FOV, and
the actual hero bbox, solve for camera distance directly.

Pure function — no bpy imports, no side effects — so it can be unit
tested without Blender and reused from the render script or API tier.

Public surface:
    place_hero_camera(hero_bbox, shot_profile, aspect_ratio) -> CameraPlacement

Output is a dataclass with .location, .rotation, .lens_mm, .framing_notes,
.subject_fill_pct, .distance.  Callers with bpy access should re-aim
rotation via Vector.to_track_quat for sub-degree alignment.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


# ════════════════════════════════════════════════════════════════════════
# CONFIG CONSTANTS — top of file per V1.3.3 spec, no hidden tuning
# ════════════════════════════════════════════════════════════════════════

# Target subject-fill fraction per shot profile.  This is the single
# directorial decision per profile: how much of the frame's vertical
# extent should the hero occupy?  Higher = closer / more dominant.
# Lower = more environment context.
TARGET_FILL: dict[str, float] = {
    "hero_push_in":             0.70,
    "intimate_three_quarter":   0.65,
    "low_orbit":                0.60,
    "low_wide_dramatic":        0.55,
    "wide_establishing":        0.50,
    "epic_pullback":            0.40,
    "default":                  0.55,
}

# Sensor + render geometry assumptions.  Blender camera defaults are
# 36×24mm; sensor_fit=AUTO uses the height (24mm) when render aspect
# is portrait (< sensor aspect 1.5), height (24mm) when landscape too
# (since vertical FOV is the dominant framing direction for film).
SENSOR_HEIGHT_MM = 24.0
SENSOR_WIDTH_MM  = 36.0  # used only for FOV cross-checks

# Distance clamps as multiples of hero bounding-box diagonal.  Lower
# bound prevents the camera from sitting inside the hero; upper bound
# catches pathological inputs (zero-sized bbox, negative dims).
DISTANCE_FLOOR_FACTOR = 0.8
DISTANCE_CEIL_FACTOR  = 50.0

# Lens defaults.  The director picks lens by hero size (very large
# subjects need a wider lens to keep distance reasonable).
LENS_DEFAULT_MM = 50
LENS_WIDE_MM    = 35   # for hero_max_dim >= 7m
LENS_TIGHT_MM   = 85   # reserved for explicit tight-close profiles


# ════════════════════════════════════════════════════════════════════════
# Shot profiles — direction vector (unit) + lens hint
# ════════════════════════════════════════════════════════════════════════
# Direction is a 3-vector relative to hero center pointing AT the camera.
# By convention: -Y is the front of the subject, +X is the subject's
# right side, +Z is up.  Magnitude doesn't matter — direction is
# normalized before use.

_SHOT_PROFILES: dict[str, dict] = {
    "hero_push_in":             {"direction": (0.30, -1.00, 0.25), "lens_hint": LENS_DEFAULT_MM},
    "low_orbit":                {"direction": (0.45, -0.90, 0.12), "lens_hint": LENS_DEFAULT_MM},
    "wide_establishing":        {"direction": (0.25, -1.00, 0.35), "lens_hint": LENS_WIDE_MM},
    "epic_pullback":            {"direction": (0.20, -1.00, 0.45), "lens_hint": LENS_WIDE_MM},
    "intimate_three_quarter":   {"direction": (0.35, -1.00, 0.18), "lens_hint": LENS_DEFAULT_MM},
    "low_wide_dramatic":        {"direction": (0.40, -0.90, 0.08), "lens_hint": LENS_WIDE_MM},
    "default":                  {"direction": (0.30, -1.00, 0.25), "lens_hint": LENS_DEFAULT_MM},
}


# ────────────────────────────────────────────────────────────────────────
# Result dataclass
# ────────────────────────────────────────────────────────────────────────

@dataclass
class CameraPlacement:
    location: tuple[float, float, float]
    rotation: tuple[float, float, float]   # Euler XYZ in radians
    lens_mm: float
    framing_notes: str
    subject_fill_pct: int
    distance: float


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────

def _parse_aspect(aspect: Any) -> tuple[float, float, str]:
    if isinstance(aspect, str):
        s = aspect.strip().lower().replace("×", "x")
        for sep in (":", "x", "/", " "):
            if sep in s:
                a, b = s.split(sep, 1)
                try:
                    return float(a), float(b), f"{int(float(a))}:{int(float(b))}"
                except ValueError:
                    pass
        return 9.0, 16.0, "9:16"
    if isinstance(aspect, (tuple, list)) and len(aspect) >= 2:
        w, h = float(aspect[0]), float(aspect[1])
        return w, h, f"{int(w)}:{int(h)}"
    return 9.0, 16.0, "9:16"


def _parse_bbox(bbox: Any) -> tuple[tuple[float, float, float],
                                     tuple[float, float, float],
                                     tuple[float, float, float],
                                     tuple[float, float, float]]:
    if isinstance(bbox, dict):
        mn = bbox.get("min") or [0.0, 0.0, 0.0]
        mx = bbox.get("max") or [0.0, 0.0, 0.0]
        return _parse_bbox((tuple(mn), tuple(mx)))
    if isinstance(bbox, (tuple, list)) and len(bbox) == 2:
        mn, mx = bbox
        mn = tuple(float(v) for v in mn)
        mx = tuple(float(v) for v in mx)
        center = tuple((mn[i] + mx[i]) * 0.5 for i in range(3))
        size = tuple(max(mx[i] - mn[i], 0.0) for i in range(3))
        return mn, mx, center, size
    try:
        w, d, h = (float(x) for x in bbox[:3])
    except Exception:
        w, d, h = 1.0, 1.0, 1.5
    mn = (-w / 2.0, -d / 2.0, 0.0)
    mx = (w / 2.0, d / 2.0, h)
    center = ((mn[0] + mx[0]) * 0.5, (mn[1] + mx[1]) * 0.5, (mn[2] + mx[2]) * 0.5)
    return mn, mx, center, (w, d, h)


def _pick_lens(hero_w: float, hero_d: float, hero_h: float,
               hero_max_dim: float, profile: dict) -> int:
    """Pick lens such that wide-flat subjects (cars, sleds) and very large
    heroes get a wider lens, otherwise use the profile's hint."""
    base = int(profile.get("lens_hint", LENS_DEFAULT_MM))
    apparent_horiz = max(hero_w, hero_d)
    if hero_h > 0.01:
        flat_ratio = apparent_horiz / hero_h
    else:
        flat_ratio = 1.0
    # Very wide-flat — vehicles in profile, snakes, dolphins viewed from side
    if flat_ratio > 3.0:
        return min(base, 28)
    # Wide-flat — most cars and trucks at 3/4 view
    if flat_ratio > 1.8:
        return min(base, 35)
    # Very large hero — pull back via wider FOV rather than absurd distance
    if hero_max_dim >= 7.0:
        return min(base, LENS_WIDE_MM)
    return base


def solve_distance_for_fill(
    hero_h_m: float,
    hero_w_m: float,
    lens_mm: float,
    target_fill: float,
    aspect_w: float,
    aspect_h: float,
) -> tuple[float, float, float]:
    """Closed-loop solver: compute camera distance such that the hero
    fills ``target_fill`` of frame HEIGHT.

    Returns ``(distance, fov_v_rad, fov_h_rad)``.  Distance is the raw
    geometric solution — caller is responsible for clamping.

    Per V1.3.3 spec: target_fill is fraction of frame HEIGHT (vertical).
    Wide subjects (cars, trucks) will overflow the frame horizontally
    at this distance; that is the intended cinematographic behaviour
    (subject dominates frame).  Lens picker compensates by switching
    to wider lens for very-flat subjects so they fit horizontally too.
    """
    if hero_h_m <= 0.001:
        hero_h_m = 0.5
    if lens_mm <= 1.0:
        lens_mm = float(LENS_DEFAULT_MM)
    target_fill = max(0.05, min(0.95, target_fill))

    fov_v = 2.0 * math.atan(SENSOR_HEIGHT_MM / (2.0 * lens_mm))
    aspect_ratio = aspect_w / max(aspect_h, 1.0)
    fov_h = 2.0 * math.atan(math.tan(fov_v / 2.0) * aspect_ratio)

    # Solve d such that hero_h / frame_h_at_d = target_fill
    # frame_h_at_d = 2 * d * tan(fov_v/2)
    # => d = hero_h / (2 * target_fill * tan(fov_v/2))
    distance = hero_h_m / (2.0 * target_fill * math.tan(fov_v / 2.0))
    return distance, fov_v, fov_h


def _aim_euler(cam_loc: tuple[float, float, float],
               target: tuple[float, float, float]) -> tuple[float, float, float]:
    """Best-effort Euler hint.  Callers with bpy should re-derive via
    Vector.to_track_quat for precise alignment."""
    dx = target[0] - cam_loc[0]
    dy = target[1] - cam_loc[1]
    dz = target[2] - cam_loc[2]
    dist_xy = math.sqrt(dx * dx + dy * dy)
    rx = math.atan2(dist_xy, dz) if dist_xy > 1e-6 else 0.0
    rz = math.atan2(dx, -dy) if (abs(dx) + abs(dy)) > 1e-6 else 0.0
    return (rx, 0.0, rz)


# ────────────────────────────────────────────────────────────────────────
# Public entry point
# ────────────────────────────────────────────────────────────────────────

def place_hero_camera(
    hero_bbox: Any,
    shot_profile: str = "hero_push_in",
    aspect_ratio: Any = "9:16",
) -> CameraPlacement:
    """Closed-loop authoritative camera placement.

    Distance is solved from ``TARGET_FILL[profile]`` against the hero's
    actual height + width and the actual lens FOV.  No multiplier
    table.  Result is then clamped to ``[hero_diag * DISTANCE_FLOOR_FACTOR,
    hero_diag * DISTANCE_CEIL_FACTOR]``.

    Pure function — no bpy.
    """
    profile_key = (shot_profile or "default").strip().lower()
    profile = _SHOT_PROFILES.get(profile_key) or _SHOT_PROFILES["default"]
    target_fill = TARGET_FILL.get(profile_key, TARGET_FILL["default"])

    mn, mx, center, size = _parse_bbox(hero_bbox)
    hero_w, hero_d, hero_h = size
    hero_max_dim = max(hero_w, hero_d, hero_h, 0.1)
    hero_diag = math.sqrt(hero_w * hero_w + hero_d * hero_d + hero_h * hero_h)
    if hero_diag < 0.1:
        hero_diag = 0.1

    aspect_w, aspect_h, aspect_label = _parse_aspect(aspect_ratio)

    lens_mm = _pick_lens(hero_w, hero_d, hero_h, hero_max_dim, profile)

    # Closed-loop distance solve
    raw_distance, fov_v, fov_h = solve_distance_for_fill(
        hero_h_m=max(hero_h, hero_max_dim * 0.3),  # for very flat heroes use 30% max as fill height
        hero_w_m=max(hero_w, hero_d, hero_max_dim * 0.3),
        lens_mm=lens_mm,
        target_fill=target_fill,
        aspect_w=aspect_w,
        aspect_h=aspect_h,
    )

    # Clamp to [hero_diag * 0.8, hero_diag * 50]
    floor = hero_diag * DISTANCE_FLOOR_FACTOR
    ceil  = hero_diag * DISTANCE_CEIL_FACTOR
    distance = raw_distance
    clamp_note = ""
    if distance < floor:
        clamp_note = f" (clamped from {distance:.2f} to floor {floor:.2f})"
        distance = floor
    elif distance > ceil:
        clamp_note = f" (clamped from {distance:.2f} to ceil {ceil:.2f})"
        distance = ceil

    # Place camera at hero_center + direction * distance
    dir_vec = profile["direction"]
    dir_len = math.sqrt(sum(v * v for v in dir_vec)) or 1.0
    dir_unit = tuple(v / dir_len for v in dir_vec)
    cam_loc = (
        center[0] + dir_unit[0] * distance,
        center[1] + dir_unit[1] * distance,
        center[2] + dir_unit[2] * distance,
    )
    if cam_loc[2] < 0.3:
        cam_loc = (cam_loc[0], cam_loc[1], 0.3)

    target = (center[0], center[1], center[2] + hero_h * 0.15)
    rot = _aim_euler(cam_loc, target)

    # Subject-fill estimate (vertical)
    if distance > 0.001:
        frame_h_at_dist = 2.0 * distance * math.tan(fov_v / 2.0)
        fill_pct = int(round(100.0 * hero_h / max(frame_h_at_dist, 0.001)))
    else:
        fill_pct = 0
    fill_pct = max(0, min(999, fill_pct))

    notes = (
        f"profile={profile_key} aspect={aspect_label} "
        f"target_fill={target_fill:.0%} hero={hero_w:.2f}x{hero_d:.2f}x{hero_h:.2f}m "
        f"lens={lens_mm}mm fov_v={math.degrees(fov_v):.1f}deg "
        f"raw_dist={raw_distance:.2f}m -> dist={distance:.2f}m"
        f"{clamp_note} fill~{fill_pct}%"
    )
    return CameraPlacement(
        location=cam_loc,
        rotation=rot,
        lens_mm=float(lens_mm),
        framing_notes=notes,
        subject_fill_pct=fill_pct,
        distance=distance,
    )
