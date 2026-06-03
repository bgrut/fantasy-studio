"""
Modifier tools — bevel, subdivision, array, mirror, solidify, boolean, etc.

These are essential generative ops. A primitive cube becomes a stylized
crate via bevel + solidify; a single tree becomes a forest via array.
"""

from .. import blender_bridge as bridge
from ..registry import register_fn


_MOD_KINDS_DESC = {
    "subdivision": "Smooth/refine geometry. settings: {levels: 1-6, render_levels: 1-6}",
    "bevel":       "Round edges. settings: {width: float, segments: int, limit_method: 'NONE'|'ANGLE'}",
    "array":       "Duplicate along axis. settings: {count: int, relative_offset_displace: [x,y,z]}",
    "mirror":      "Mirror across axis. settings: {use_axis: [true,false,false]}",
    "solidify":    "Give thickness to faces. settings: {thickness: float}",
    "boolean":     "Union/diff/intersect with another object. settings: {operation: 'UNION'|'DIFFERENCE'|'INTERSECT', object: '<name>'}",
    "decimate":    "Reduce polycount. settings: {ratio: 0-1}",
    "wireframe":   "Convert to wire/edge geometry. settings: {thickness: float}",
    "smooth":      "Laplacian smoothing. settings: {factor: 0-1, iterations: int}",
    "displace":    "Displace verts along normals via texture",
    "screw":       "Revolve geometry around axis",
}


@register_fn(
    name="add_modifier",
    description=(
        "Add a modifier to an object. Supported kinds: " +
        ", ".join(f"{k} ({v})" for k, v in _MOD_KINDS_DESC.items()) +
        ". Modifiers stack in the order added; use them to procedurally enrich primitives."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "object": {"type": "string", "description": "Target object name"},
            "kind": {
                "type": "string",
                "enum": list(_MOD_KINDS_DESC.keys()),
            },
            "name": {"type": "string", "description": "Modifier name (default = kind capitalized)"},
            "settings": {
                "type": "object",
                "description": "Modifier-specific settings (e.g. {'levels': 2} for subdivision)",
                "additionalProperties": True,
            },
        },
        "required": ["object", "kind"],
        "additionalProperties": False,
    },
    category="modifiers",
)
def add_modifier(params: dict) -> dict:
    return bridge.call("add_modifier", params)
