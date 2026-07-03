"""
Vehicle pattern — car, truck, bike, generic four-wheel.

Anatomy:
    chassis    — main body box
    cabin      — upper passenger box (cars only)
    wheel_fl, fr, bl, br — 4 cylinders rotated to lie flat
    headlight_l, r — small spheres on front

Style presets vary proportions for car/truck/sports/bike.
"""

import math
from typing import Any, Dict, List
from . import register_pattern


STYLE_PRESETS = {
    "car": {
        "chassis_scale": [2.4, 1.1, 0.55],
        "cabin_scale":   [1.3, 0.95, 0.55],
        "cabin_offset":  [0, 0, 0.55],
        "wheel_radius":  0.45,
        "wheel_width":   0.20,
        "wheel_dx":      1.05,
        "wheel_dy":      1.05,
        "wheel_z":       0.45,
        "has_cabin":     True,
        "has_headlights": True,
    },
    "truck": {
        "chassis_scale": [2.6, 1.30, 0.75],
        "cabin_scale":   [1.0, 1.15, 0.85],
        "cabin_offset":  [0.8, 0, 0.80],
        "wheel_radius":  0.60,
        "wheel_width":   0.25,
        "wheel_dx":      1.10,
        "wheel_dy":      1.25,
        "wheel_z":       0.60,
        "has_cabin":     True,
        "has_headlights": True,
    },
    "sports": {
        "chassis_scale": [2.6, 1.05, 0.40],
        "cabin_scale":   [1.1, 0.90, 0.38],
        "cabin_offset":  [-0.1, 0, 0.40],
        "wheel_radius":  0.42,
        "wheel_width":   0.22,
        "wheel_dx":      1.15,
        "wheel_dy":      1.00,
        "wheel_z":       0.42,
        "has_cabin":     True,
        "has_headlights": True,
    },
    "bike": {
        "chassis_scale": [1.4, 0.20, 0.30],
        "cabin_scale":   [0.30, 0.30, 0.80],
        "cabin_offset":  [-0.5, 0, 0.55],
        "wheel_radius":  0.45,
        "wheel_width":   0.18,
        "wheel_dx":      0.90,
        "wheel_dy":      0.0,
        "wheel_z":       0.45,
        "has_cabin":     False,  # no roof on bike
        "has_seat":      True,
        "has_headlights": True,
        "two_wheels":    True,
    },
}


def _style_for(slots: Dict[str, Any]) -> Dict[str, Any]:
    name = (slots["subject"].get("name") or "").lower()
    q = (slots["subject"].get("library_query") or "").lower()
    text = f"{name} {q}"
    if "bike" in text or "motorcycle" in text or "bicycle" in text:
        return STYLE_PRESETS["bike"]
    if "truck" in text or "lorry" in text or "pickup" in text:
        return STYLE_PRESETS["truck"]
    if "sport" in text or "racing" in text or "ferrari" in text or "lamborghini" in text:
        return STYLE_PRESETS["sports"]
    return STYLE_PRESETS["car"]


def instantiate(slots: Dict[str, Any]) -> List[Dict[str, Any]]:
    p = _style_for(slots)
    s = float(slots["subject"].get("scale", 1.0))
    parts: List[Dict[str, Any]] = []

    chassis_z = p["wheel_z"] + 0.10
    # ── CHASSIS
    parts.append({
        "name": "Chassis",
        "primitive": "cube",
        "location": [0, 0, chassis_z * s],
        "scale": [v * s for v in p["chassis_scale"]],
        "size": 1.0,
        "role": "body",
        "modifiers": [{"kind": "bevel", "settings": {"width": 0.08, "segments": 4}}],
    })

    # ── CABIN / passenger compartment
    if p.get("has_cabin"):
        co = p["cabin_offset"]
        parts.append({
            "name": "Cabin",
            "primitive": "cube",
            "location": [co[0] * s, co[1] * s, (chassis_z + co[2]) * s],
            "scale": [v * s for v in p["cabin_scale"]],
            "size": 1.0,
            "role": "frame",
            "modifiers": [{"kind": "bevel", "settings": {"width": 0.06, "segments": 4}}],
        })

    if p.get("has_seat"):
        parts.append({
            "name": "Seat",
            "primitive": "cube",
            "location": [-0.2 * s, 0, (chassis_z + 0.30) * s],
            "scale": [0.30 * s, 0.20 * s, 0.10 * s],
            "size": 1.0,
            "role": "detail",
        })

    # ── WHEELS — cylinders rotated 90° around X so they lie flat on Y axis
    wr = p["wheel_radius"]
    ww = p["wheel_width"]
    wheel_z = wr  # wheels sit on ground
    if p.get("two_wheels"):
        # Front + back (bike)
        for name, dx in (("Wheel_F", p["wheel_dx"]), ("Wheel_B", -p["wheel_dx"])):
            parts.append({
                "name": name,
                "primitive": "cylinder",
                "location": [dx * s, 0, wheel_z * s],
                "rotation": [math.pi / 2, 0, 0],
                "scale": [wr * s, wr * s, ww * 0.5 * s],
                "size": 1.0,
                "role": "wheel",
                "material_hint": "tire",
            })
    else:
        for name, dx, dy in (
            ("Wheel_FL",  p["wheel_dx"],  p["wheel_dy"]),
            ("Wheel_FR",  p["wheel_dx"], -p["wheel_dy"]),
            ("Wheel_BL", -p["wheel_dx"],  p["wheel_dy"]),
            ("Wheel_BR", -p["wheel_dx"], -p["wheel_dy"]),
        ):
            parts.append({
                "name": name,
                "primitive": "cylinder",
                "location": [dx * s, dy * s, wheel_z * s],
                "rotation": [math.pi / 2, 0, 0],
                "scale": [wr * s, wr * s, ww * 0.5 * s],
                "size": 1.0,
                "role": "wheel",
                "material_hint": "tire",
            })

    # ── HEADLIGHTS
    if p.get("has_headlights"):
        front_x = p["chassis_scale"][0] * 0.5 + 0.05
        for name, dy in (("Headlight_L", 0.35), ("Headlight_R", -0.35)):
            parts.append({
                "name": name,
                "primitive": "sphere",
                "location": [front_x * s, dy * s, (chassis_z + 0.05) * s],
                "scale": [0.12 * s, 0.12 * s, 0.12 * s],
                "size": 1.0,
                "role": "detail",
                "material_hint": "headlight",  # emissive white
            })

    return parts


register_pattern("vehicle", instantiate)
