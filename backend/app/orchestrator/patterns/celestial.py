"""
Celestial pattern — moon, earth, planet, sun, star.

A sphere with a procedural surface texture matching the specific body type.
The texture is baked in via the material_hint mechanism — composer reads it
and applies the right procedural shader (crater for moon, continent for
earth, etc).

Style presets:
    moon    — gray + crater shader, large bumpy surface
    earth   — blue/green continents on sphere
    mars    — red/rust voronoi terrain
    sun     — bright yellow emissive with noise
    planet  — generic gas-giant style (noise bands)
    star    — emissive white sphere
"""

from typing import Any, Dict, List
from . import register_pattern


STYLE_PRESETS = {
    "moon": {
        "color":   [0.55, 0.55, 0.53, 1.0],
        "texture": "crater",
        "texture_scale": 4.5,
        "texture_contrast": 0.9,
        "metallic": 0.0,
        "roughness": 0.95,
        "emissive": False,
        "size_mult": 1.0,
    },
    "earth": {
        "color":   [0.18, 0.40, 0.65, 1.0],
        "texture": "continent",
        "texture_scale": 3.0,
        "texture_contrast": 0.8,
        "metallic": 0.0,
        "roughness": 0.75,
        "emissive": False,
        "size_mult": 1.0,
    },
    "mars": {
        "color":   [0.62, 0.32, 0.18, 1.0],
        "texture": "voronoi",
        "texture_scale": 5.0,
        "texture_contrast": 0.7,
        "metallic": 0.0,
        "roughness": 0.85,
        "emissive": False,
        "size_mult": 1.0,
    },
    "sun": {
        "color":   [1.0, 0.85, 0.30, 1.0],
        "texture": "noise",
        "texture_scale": 6.0,
        "texture_contrast": 0.4,
        "metallic": 0.0,
        "roughness": 0.85,
        "emissive": True,
        "emission_strength": 25.0,
        "size_mult": 1.4,
    },
    "star": {
        "color":   [1.0, 0.95, 0.85, 1.0],
        "texture": "noise",
        "texture_scale": 8.0,
        "texture_contrast": 0.3,
        "metallic": 0.0,
        "roughness": 0.7,
        "emissive": True,
        "emission_strength": 30.0,
        "size_mult": 1.0,
    },
    "planet": {
        "color":   [0.45, 0.55, 0.65, 1.0],
        "texture": "noise",
        "texture_scale": 4.0,
        "texture_contrast": 0.7,
        "metallic": 0.0,
        "roughness": 0.75,
        "emissive": False,
        "size_mult": 1.0,
    },
}


def _style_for(slots: Dict[str, Any]) -> Dict[str, Any]:
    text = " ".join([
        (slots["subject"].get("name") or "").lower(),
        (slots["subject"].get("library_query") or "").lower(),
    ])
    for key in ("moon", "earth", "mars", "sun", "star", "planet"):
        if key in text:
            return STYLE_PRESETS[key]
    return STYLE_PRESETS["planet"]


def instantiate(slots: Dict[str, Any]) -> List[Dict[str, Any]]:
    p = _style_for(slots)
    overall_scale = float(slots["subject"].get("scale", 1.0)) * p["size_mult"]

    return [{
        "name": "Hero",
        "primitive": "icosphere",   # nicer subdivision than UV sphere for celestial
        "location": slots["subject"].get("location", [0, 0, 1]),
        "rotation": [0, 0, 0],
        "scale": [overall_scale, overall_scale, overall_scale],
        "size": 2.0,
        "role": "body",
        # The composer reads material_hint and uses these texture params
        "material_hint": "celestial",
        "_celestial_params": {
            "color": p["color"],
            "texture_pattern": p["texture"],
            "texture_scale": p["texture_scale"],
            "texture_contrast": p["texture_contrast"],
            "metallic": p["metallic"],
            "roughness": p["roughness"],
            "emissive": p["emissive"],
            "emission_strength": p.get("emission_strength", 0.0),
        },
        "modifiers": [{"kind": "subdivision", "settings": {"levels": 3, "render_levels": 4}}],
    }]


register_pattern("celestial", instantiate)
