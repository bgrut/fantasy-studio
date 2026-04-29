"""
Fantasy Studio — Cinematic 3-Point Lighting
============================================

Mood-based lighting rig that reads the scene_recipe lighting sub-recipe
and places key/fill/rim lights aimed at the hero's world-space center.

Usage from render_from_manifest.py:
    from app.scene.cinematic_lighting import apply_cinematic_lighting
    apply_cinematic_lighting(bpy, scene, manifest, hero_objects)
"""

from __future__ import annotations

from typing import Optional


# ── Mood → color temperature presets ────────────────────────────────────
_MOOD_LIGHTING = {
    "warm": {
        "key_color":  (1.0, 0.85, 0.65),
        "fill_color": (0.75, 0.82, 1.0),
        "rim_color":  (0.60, 0.75, 1.0),
        "key_energy": 4000,
    },
    "cool": {
        "key_color":  (0.72, 0.82, 1.0),
        "fill_color": (0.55, 0.65, 0.95),
        "rim_color":  (0.85, 0.75, 1.0),
        "key_energy": 3200,
    },
    "neutral": {
        "key_color":  (1.0, 0.96, 0.88),
        "fill_color": (0.85, 0.90, 1.0),
        "rim_color":  (1.0, 0.95, 0.80),
        "key_energy": 3500,
    },
    "dramatic": {
        "key_color":  (1.0, 0.78, 0.55),
        "fill_color": (0.50, 0.55, 0.80),
        "rim_color":  (0.85, 0.75, 1.0),
        "key_energy": 5000,
    },
    "ethereal": {
        "key_color":  (0.88, 0.92, 1.0),
        "fill_color": (0.80, 0.85, 1.0),
        "rim_color":  (0.95, 0.90, 1.0),
        "key_energy": 2800,
    },
}

# ── Time-of-day energy multipliers ────────────────────────────────────
_TOD_ENERGY = {
    "night":       0.35,
    "dusk":        0.55,
    "dawn":        0.70,
    "sunset":      0.85,
    "golden_hour": 0.85,
    "morning":     1.0,
    "midday":      1.0,
    "day":         1.0,
}

# ── Lighting style ratios ──────────────────────────────────────────────
_STYLE_RATIOS = {
    "three_point": {"fill_ratio": 0.35, "rim_ratio": 0.55},
    "high_key":    {"fill_ratio": 0.80, "rim_ratio": 0.30},
    "low_key":     {"fill_ratio": 0.15, "rim_ratio": 0.75},
    "rembrandt":   {"fill_ratio": 0.25, "rim_ratio": 0.60},
    "butterfly":   {"fill_ratio": 0.50, "rim_ratio": 0.40},
}


def _find_hero_center(bpy, hero_objects=None):
    """Compute the world-space bounding-box center of hero objects."""
    try:
        from mathutils import Vector
    except ImportError:
        return (0.0, 0.0, 1.0)

    candidates = hero_objects or []
    if not candidates:
        skip = ("ground", "floor", "plane", "world_", "atmosphere", "sky",
                "environment", "backdrop", "road", "street", "contactshadow")
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            if any(t in obj.name.lower() for t in skip):
                continue
            candidates.append(obj)

    if not candidates:
        return (0.0, 0.0, 1.0)

    coords = []
    for obj in candidates:
        try:
            for corner in obj.bound_box:
                coords.append(obj.matrix_world @ Vector(corner))
        except Exception:
            continue

    if not coords:
        return (0.0, 0.0, 1.0)

    xs = [c.x for c in coords]
    ys = [c.y for c in coords]
    zs = [c.z for c in coords]
    return (
        (min(xs) + max(xs)) / 2.0,
        (min(ys) + max(ys)) / 2.0,
        (min(zs) + max(zs)) / 2.0,
    )


def _aim_light_at(light_obj, target_pos):
    """Rotate light so its -Z axis points at target position."""
    try:
        from mathutils import Vector
        direction = Vector(target_pos) - light_obj.location
        if direction.length < 0.001:
            return
        light_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    except Exception:
        pass


def apply_cinematic_lighting(
    bpy,
    scene,
    manifest: dict,
    hero_objects=None,
) -> dict:
    """
    Apply mood-based 3-point cinematic lighting aimed at the hero.

    Reads from ``manifest["scene_recipe"]["lighting"]`` when available,
    falls back to mood inference from ``manifest["_scene_plan"]``.

    Returns a dict with details of what was placed.
    """
    result = {"lights_added": 0, "mood": "neutral", "style": "three_point"}

    try:
        # ── Resolve mood and style from recipe / plan ──────────────────
        recipe = manifest.get("scene_recipe") or {}
        lighting_recipe = recipe.get("lighting") or {}
        plan = manifest.get("_scene_plan") or {}

        mood = (
            lighting_recipe.get("mood")
            or plan.get("mood")
            or "neutral"
        ).lower()
        if mood not in _MOOD_LIGHTING:
            mood = "neutral"

        style = (
            lighting_recipe.get("style")
            or "three_point"
        ).lower()
        if style not in _STYLE_RATIOS:
            style = "three_point"

        tod = (plan.get("time_of_day") or "day").lower()
        tod_mult = _TOD_ENERGY.get(tod, 1.0)

        preset = _MOOD_LIGHTING[mood]
        ratios = _STYLE_RATIOS[style]
        base_energy = lighting_recipe.get("key_energy") or preset["key_energy"]
        key_energy = base_energy * tod_mult
        fill_energy = key_energy * ratios["fill_ratio"]
        rim_energy = key_energy * ratios["rim_ratio"]

        result["mood"] = mood
        result["style"] = style

        # ── Find hero center ───────────────────────────────────────────
        cx, cy, cz = _find_hero_center(bpy, hero_objects)
        from mathutils import Vector
        hero_pos = Vector((cx, cy, cz))

        # ── KEY light: front-right, 45° up ─────────────────────────────
        bpy.ops.object.light_add(
            type="AREA",
            location=(cx + 5.0, cy - 4.0, cz + 5.0),
        )
        key = bpy.context.object
        key.name = "Cinematic_Key"
        key.data.energy = key_energy
        key.data.size = 3.0
        try:
            key.data.color = preset["key_color"]
            key.data.shape = "DISK"
        except Exception:
            pass
        _aim_light_at(key, (cx, cy, cz))
        result["lights_added"] += 1

        # ── FILL light: front-left, lower, wider ──────────────────────
        bpy.ops.object.light_add(
            type="AREA",
            location=(cx - 5.0, cy - 3.0, cz + 2.0),
        )
        fill = bpy.context.object
        fill.name = "Cinematic_Fill"
        fill.data.energy = fill_energy
        fill.data.size = 5.0
        try:
            fill.data.color = preset["fill_color"]
            fill.data.shape = "DISK"
        except Exception:
            pass
        _aim_light_at(fill, (cx, cy, cz))
        result["lights_added"] += 1

        # ── RIM light: behind, up high ─────────────────────────────────
        bpy.ops.object.light_add(
            type="AREA",
            location=(cx - 3.5, cy + 5.0, cz + 4.5),
        )
        rim = bpy.context.object
        rim.name = "Cinematic_Rim"
        rim.data.energy = rim_energy
        rim.data.size = 3.0
        try:
            rim.data.color = preset["rim_color"]
            rim.data.shape = "DISK"
        except Exception:
            pass
        _aim_light_at(rim, (cx, cy, cz))
        result["lights_added"] += 1

        print(
            f"[LIGHTING] cinematic 3-point: mood={mood} style={style} "
            f"tod={tod} key={key_energy:.0f} fill={fill_energy:.0f} "
            f"rim={rim_energy:.0f} at ({cx:.1f}, {cy:.1f}, {cz:.1f})",
            flush=True,
        )

    except Exception as e:
        print(f"[LIGHTING] cinematic lighting failed (non-fatal): {e}", flush=True)

    return result
