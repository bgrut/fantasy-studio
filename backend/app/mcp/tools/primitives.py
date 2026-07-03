"""
Primitive geometry — generative ops that fill the gap audit identified.

These let the orchestrator BUILD objects, not just place pre-made ones.
A "low-poly castle" prompt might decompose into:
    create_primitive(cube, size=4, location=[0,0,2])   # keep
    create_primitive(cone, size=2, location=[0,0,5])   # roof
    add_modifier(keep, bevel, {width: 0.1, segments: 3})
    ...
"""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="create_primitive",
    description=(
        "Spawn a primitive mesh (cube, sphere, icosphere, cylinder, cone, torus, plane, monkey). "
        "Returns the new object's name — use that to reference it in follow-up ops. "
        "Use this to BUILD geometry from scratch when no library asset fits."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["cube", "sphere", "icosphere", "cylinder", "cone", "torus", "plane", "monkey"],
                "default": "cube",
            },
            "name": {"type": "string", "description": "Custom name; auto-named if omitted"},
            "location": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [0, 0, 0],
            },
            "rotation": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [0, 0, 0],
                "description": "XYZ euler in radians",
            },
            "size": {"type": "number", "default": 2.0, "description": "Edge length / diameter"},
            "depth": {"type": "number", "description": "For cylinder/cone — height. Defaults to size."},
        },
        "additionalProperties": False,
    },
    category="primitives",
)
def create_primitive(params: dict) -> dict:
    return bridge.call("create_primitive", params)


@register_fn(
    name="delete_object",
    description="Remove an object from the scene by name.",
    input_schema={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
    category="primitives",
)
def delete_object(params: dict) -> dict:
    return bridge.call("delete_object", params)


@register_fn(
    name="create_metaball_blob",
    description=(
        "Create a metaball object — multiple blob elements that auto-blend into ONE "
        "continuous surface. The right tool for organic creatures (cats, dogs, humans). "
        "Body + head + ears + legs all FUSE naturally, no gaps, no floating pieces. "
        "Returns the final mesh object's name."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "default": "Blob"},
            "resolution": {"type": "number", "default": 0.08, "description": "Mesh detail (smaller = finer)"},
            "threshold": {"type": "number", "default": 0.6, "description": "How strongly blobs blend (lower = more melting)"},
            "elements": {
                "type": "array",
                "description": "List of metaball elements (each is a blob that blends with others)",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["BALL", "ELLIPSOID", "CAPSULE", "CUBE", "PLANE"], "default": "ELLIPSOID"},
                        "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                        "rotation": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                        "size_x": {"type": "number"},
                        "size_y": {"type": "number"},
                        "size_z": {"type": "number"},
                        "radius": {"type": "number"},
                        "stiffness": {"type": "number", "default": 2.0},
                    },
                    "required": ["location"],
                },
            },
            "convert_to_mesh": {"type": "boolean", "default": True},
        },
        "required": ["elements"],
        "additionalProperties": False,
    },
    category="primitives",
)
def create_metaball_blob(params: dict) -> dict:
    return bridge.call("create_metaball_blob", params)


@register_fn(
    name="transform_object",
    description=(
        "Set location / rotation / scale on an existing object. "
        "Any field omitted is left unchanged. Scale can be a single number (uniform) or [sx,sy,sz]."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            "rotation_euler": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            "scale": {
                "oneOf": [
                    {"type": "number"},
                    {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                ],
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    category="primitives",
)
def transform_object(params: dict) -> dict:
    return bridge.call("transform_object", params)
