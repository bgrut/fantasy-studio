"""
Tree pattern — branching organic structure.

Built from:
    trunk             — vertical cylinder
    branch_*          — smaller cylinders at angles from trunk
    canopy            — large sphere(s) on top, or per-branch foliage spheres

Style presets:
    "deciduous"   — single rounded canopy (oak, maple)
    "conifer"     — tall conic canopy (pine, fir)
    "palm"        — bare trunk + radial fronds on top
    "branchy"     — explicit branch sub-cylinders + small foliage spheres
"""

import math
import random
from typing import Any, Dict, List
from . import register_pattern


STYLE_PRESETS = {
    "deciduous": {
        "trunk_height": 2.0, "trunk_radius": 0.18,
        "canopy_style": "single_sphere",
        "canopy_radius": 1.3,
        "canopy_height_offset": 1.8,
        "branch_count": 0,
    },
    "conifer": {
        "trunk_height": 2.5, "trunk_radius": 0.15,
        "canopy_style": "cone_stack",
        "canopy_radius": 1.1,
        "canopy_height_offset": 1.2,
        "branch_count": 0,
    },
    "palm": {
        "trunk_height": 3.0, "trunk_radius": 0.15,
        "canopy_style": "fronds",
        "canopy_radius": 1.4,
        "canopy_height_offset": 2.8,
        "branch_count": 0,
        "frond_count": 7,
    },
    "branchy": {
        "trunk_height": 1.8, "trunk_radius": 0.16,
        "canopy_style": "clusters",
        "canopy_radius": 0.5,
        "canopy_height_offset": 1.5,
        "branch_count": 5,
    },
}


def _style_for(slots: Dict[str, Any]) -> str:
    text = " ".join([
        (slots["subject"].get("name") or "").lower(),
        (slots["subject"].get("library_query") or "").lower(),
    ])
    if "pine" in text or "fir" in text or "conifer" in text or "spruce" in text:
        return "conifer"
    if "palm" in text or "coconut" in text:
        return "palm"
    if "branch" in text or "bare" in text or "winter" in text:
        return "branchy"
    return "deciduous"


def instantiate(slots: Dict[str, Any]) -> List[Dict[str, Any]]:
    style_name = _style_for(slots)
    p = STYLE_PRESETS[style_name]
    s = float(slots["subject"].get("scale", 1.0))

    parts: List[Dict[str, Any]] = []
    rng = random.Random(42)  # deterministic — same prompt → same tree

    # ── TRUNK
    parts.append({
        "name": "Trunk",
        "primitive": "cylinder",
        "location": [0, 0, p["trunk_height"] * 0.5 * s],
        "scale": [p["trunk_radius"] * s, p["trunk_radius"] * s, p["trunk_height"] * 0.5 * s],
        "size": 1.0,
        "role": "body",
        "material_hint": "wood",
    })

    style = p["canopy_style"]
    canopy_z = (p["trunk_height"] + p["canopy_height_offset"]) * 0.5

    if style == "single_sphere":
        parts.append({
            "name": "Canopy",
            "primitive": "sphere",
            "location": [0, 0, canopy_z * s],
            "scale": [p["canopy_radius"] * s, p["canopy_radius"] * s, p["canopy_radius"] * s],
            "size": 1.0,
            "role": "detail",
            "material_hint": "foliage",
            "modifiers": [{"kind": "subdivision", "settings": {"levels": 1, "render_levels": 2}}],
        })

    elif style == "cone_stack":
        # Three stacked cones, decreasing in size
        for i, (z_off, r) in enumerate([
            (-0.6, 1.2), (0.3, 0.95), (1.1, 0.6),
        ]):
            parts.append({
                "name": f"Canopy_{i+1}",
                "primitive": "cone",
                "location": [0, 0, (canopy_z + z_off) * s],
                "scale": [r * s, r * s, 0.9 * s],
                "size": 1.0,
                "role": "detail",
                "material_hint": "foliage",
            })

    elif style == "fronds":
        # Radial cylinders pointing outward-and-down from top of trunk
        frond_count = p.get("frond_count", 7)
        for i in range(frond_count):
            angle = (i / frond_count) * 2 * math.pi
            tilt = 1.0  # angled down
            length = p["canopy_radius"]
            parts.append({
                "name": f"Frond_{i+1}",
                "primitive": "cylinder",
                "location": [
                    length * 0.4 * math.cos(angle) * s,
                    length * 0.4 * math.sin(angle) * s,
                    canopy_z * s - 0.1 * s,
                ],
                "rotation": [tilt * math.sin(angle), tilt * math.cos(angle), 0],
                "scale": [0.04 * s, 0.04 * s, length * 0.5 * s],
                "size": 1.0,
                "role": "detail",
                "material_hint": "foliage",
            })

    elif style == "clusters":
        # Spheres scattered at branch tips
        for i in range(p["branch_count"]):
            angle = rng.uniform(0, 2 * math.pi)
            radius = rng.uniform(0.6, 1.1)
            z_jitter = rng.uniform(-0.4, 0.4)
            parts.append({
                "name": f"Cluster_{i+1}",
                "primitive": "sphere",
                "location": [
                    radius * math.cos(angle) * s,
                    radius * math.sin(angle) * s,
                    (canopy_z + z_jitter) * s,
                ],
                "scale": [p["canopy_radius"] * s, p["canopy_radius"] * s, p["canopy_radius"] * s],
                "size": 1.0,
                "role": "detail",
                "material_hint": "foliage",
            })

    return parts


register_pattern("tree", instantiate)
