"""
Pattern Library — anatomical and structural blueprints.

This is the "3D artist's vocabulary." Each pattern is a Python function that
takes parameters from the LLM-extracted slots and returns a list of `Part`
dicts. The composer then instantiates each part as a Blender primitive.

The KEY insight (Sora-style architecture):
    The LLM doesn't compose primitives one-by-one — that's brittle and slow.
    Instead the LLM picks ONE pattern from this library and customizes it
    via parameters. We get the LLM's semantic knowledge ("a cat is a small
    quadruped") + the reliability of a hand-tuned blueprint.

A `Part` dict has:
    {
        "name":       str,            # unique part name (becomes Blender object name)
        "primitive":  str,            # "cube" | "sphere" | "cylinder" | "cone" | ...
        "location":   [x, y, z],
        "rotation":   [rx, ry, rz],   # radians
        "scale":      [sx, sy, sz],
        "size":       float,          # base size (overridden by scale)
        "role":       str,            # "body" | "head" | "limb" | "detail" | "frame" | "wheel" | ...
        "material_hint": str | None,  # optional override (e.g. "eyes" wants black-glossy)
        "modifiers":  [...],          # optional Blender modifiers to apply
    }

The composer treats `role: "body"` as the hero for HERO_VERIFY tagging.

Available patterns (this file is the registry):
    quadruped       — cat, dog, fox, rabbit, sheep, horse, lion
    biped           — human, character, robot, alien
    vehicle         — car, truck, bike, plane (wheel-based for now)
    tree            — branching organic structure
    building        — house, tower, castle (block-based)
    celestial       — planet, moon, star (sphere variants with rings)
    primitive_geo   — pass-through to single primitive (existing behavior)
"""

from typing import Any, Callable, Dict, List, Optional


# Each pattern module exports an `instantiate(slots: dict) -> List[Part]` callable
_PATTERN_REGISTRY: Dict[str, Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = {}


def register_pattern(name: str, fn: Callable[[Dict[str, Any]], List[Dict[str, Any]]]) -> None:
    _PATTERN_REGISTRY[name] = fn


def get_pattern(name: str) -> Optional[Callable]:
    return _PATTERN_REGISTRY.get(name)


def available_patterns() -> List[str]:
    return sorted(_PATTERN_REGISTRY.keys())


def instantiate(pattern_name: str, slots: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Resolve and call a pattern by name. Returns the parts list."""
    fn = get_pattern(pattern_name)
    if fn is None:
        raise KeyError(f"unknown pattern '{pattern_name}'. available: {available_patterns()}")
    parts = fn(slots)
    # Normalize each part with defaults so the composer never crashes on missing keys
    return [_normalize_part(p) for p in parts]


def _normalize_part(p: Dict[str, Any]) -> Dict[str, Any]:
    """Fill defaults so every Part dict is uniform.

    Preserves ANY additional keys the pattern wants to pass through (like
    _celestial_params, _face_features, etc) so future patterns can extend
    without modifying this normalizer.
    """
    out = dict(p)  # preserve unknown extension keys
    out["name"] = p.get("name", "Part")
    out["primitive"] = p.get("primitive", "cube")
    out["location"] = list(p.get("location", [0, 0, 0]))
    out["rotation"] = list(p.get("rotation", [0, 0, 0]))
    out["scale"] = list(p.get("scale", [1, 1, 1]))
    out["size"] = float(p.get("size", 1.0))
    out["role"] = p.get("role", "part")
    out["material_hint"] = p.get("material_hint")
    out["modifiers"] = list(p.get("modifiers", []))
    return out


# ───────────────────────────────────────────────────────────────────────
# Auto-load all bundled patterns on import
# ───────────────────────────────────────────────────────────────────────

def _load_all() -> None:
    from . import quadruped       # noqa: F401
    from . import biped           # noqa: F401
    from . import vehicle         # noqa: F401
    from . import tree            # noqa: F401
    from . import celestial       # noqa: F401
    from . import primitive_geo   # noqa: F401


_load_all()
