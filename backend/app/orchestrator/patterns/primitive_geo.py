"""
Pass-through pattern: a single primitive. Mirrors current composer behavior
so the pattern dispatcher can treat ALL subjects uniformly.

This is what the LLM picks for "a cube", "a sphere", "a torus" etc.
"""

from typing import Any, Dict, List
from . import register_pattern


def instantiate(slots: Dict[str, Any]) -> List[Dict[str, Any]]:
    subj = slots["subject"]
    shape = subj.get("shape", "cube")
    location = subj.get("location", [0, 0, 1])
    scale = subj.get("scale", 1.0)

    return [{
        "name":      "Hero",
        "primitive": shape,
        "location":  location,
        "rotation":  [0, 0, 0],
        "scale":     [scale, scale, scale],
        "size":      2.0,
        "role":      "body",
        "modifiers": [{"kind": "subdivision", "settings": {"levels": 1, "render_levels": 1}}]
            if shape in ("sphere", "icosphere") else [],
    }]


register_pattern("primitive_geo", instantiate)
