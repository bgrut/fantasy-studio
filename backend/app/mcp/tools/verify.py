"""
HERO_VERIFY as a tool — the orchestrator's feedback loop.

After each composition step, the orchestrator calls hero_verify(). The
addon-side handler walks the scene, runs the 7 checks, returns a structured
report:

{
    "passed": True/False,
    "checks": {
        "has_hero_tag":     {"ok": bool, "detail": str},
        "bbox_sane":        {"ok": bool, "diag": float, "min": [x,y,z], "max": [x,y,z]},
        "in_frustum":       {"ok": bool, "detail": str},
        "fill_ok":          {"ok": bool, "fill_pct": float, "detail": str},
        "not_primitive":    {"ok": bool, "max_polys": int},
        "oriented_correctly": {"ok": bool, "detail": str},
        "grounded":         {"ok": bool, "delta_z": float},
    },
    "abort_reasons": [...],
    "warnings": [...],
}

If the orchestrator gets passed=False, it reads the failing checks and
self-corrects (e.g. fill_pct too low → move camera closer; not_primitive
fails → swap for a real asset).
"""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="hero_verify",
    description=(
        "Run the HERO_VERIFY 7-check gate on the current scene. Returns a structured "
        "report: which checks passed, which failed, and diagnostic data (bbox diagonal, "
        "fill percentage, max polygons, etc). Use this AFTER any scene modification to "
        "see if the hero meets render-quality standards. Self-correct based on which "
        "checks fail."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "min_bbox_diag":  {"type": "number", "default": 0.2, "description": "Smallest acceptable hero diagonal (m)"},
            "max_bbox_diag":  {"type": "number", "default": 50.0, "description": "Largest acceptable hero diagonal (m)"},
            "min_fill_pct":   {"type": "number", "default": 0.35, "description": "Min frame fill (0-1)"},
            "max_fill_pct":   {"type": "number", "default": 0.70, "description": "Max frame fill (0-1)"},
            "min_polys":      {"type": "integer", "default": 100, "description": "Reject defaults like raw cubes"},
            "ground_tolerance": {"type": "number", "default": 0.5, "description": "Max delta-Z for 'grounded'"},
        },
        "additionalProperties": False,
    },
    category="verify",
    side_effects=False,
)
def hero_verify(params: dict) -> dict:
    return bridge.call("hero_verify", params)
