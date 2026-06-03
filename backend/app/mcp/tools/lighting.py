"""Lighting tools — add lights, set world environment."""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="add_light",
    description=(
        "Add a light to the scene. Types: POINT (omnidirectional), SUN (directional, "
        "energy in W/m²), SPOT (cone), AREA (rectangle/disk). "
        "Energy units depend on type: POINT/SPOT/AREA use Watts (use 100-2000 for normal use); "
        "SUN uses W/m² (use 1-5 for normal use)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["POINT", "SUN", "SPOT", "AREA"],
                "default": "POINT",
            },
            "name": {"type": "string"},
            "location": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [0, 0, 5],
            },
            "rotation_euler": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "description": "Important for SUN/SPOT/AREA — these are directional",
            },
            "energy": {"type": "number", "default": 1000.0},
            "color": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [1.0, 1.0, 1.0],
                "description": "RGB 0-1",
            },
            "size": {"type": "number", "description": "AREA light size (default 1.0)"},
            "spot_size": {"type": "number", "description": "SPOT light cone angle in radians (default 60deg = 1.0472)"},
        },
        "additionalProperties": False,
    },
    category="lighting",
)
def add_light(params: dict) -> dict:
    return bridge.call("add_light", params)


@register_fn(
    name="set_hdri_environment",
    description=(
        "Load an HDRI (.hdr/.exr) image as the world environment. Provides realistic "
        "ambient lighting + reflections without manual light setup. Use this for "
        "photoreal scenes — it's the single biggest visual lift."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "hdri_path": {"type": "string", "description": "Absolute path to .hdr or .exr file"},
            "strength": {"type": "number", "default": 1.0},
            "rotation_z": {"type": "number", "default": 0.0, "description": "Radians; rotates environment around vertical axis"},
        },
        "required": ["hdri_path"],
        "additionalProperties": False,
    },
    category="lighting",
)
def set_hdri_environment(params: dict) -> dict:
    return bridge.call("set_hdri_environment", params)


@register_fn(
    name="boolean_union",
    description=(
        "Merge two objects via Boolean Union — the geometry is FUSED into one mesh "
        "(unlike just joining which leaves separate islands). Use for vehicle "
        "chassis+cabin merging or any case where you need a single continuous body."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Object that absorbs the merge"},
            "operand": {"type": "string", "description": "Object that gets merged in"},
            "delete_operand": {"type": "boolean", "default": True},
        },
        "required": ["target", "operand"],
        "additionalProperties": False,
    },
    category="primitives",
)
def boolean_union(params: dict) -> dict:
    return bridge.call("boolean_union", params)


@register_fn(
    name="add_fur",
    description=(
        "Add a hair-particle fur coat to a mesh. Produces real strands (not just texture). "
        "Use on quadruped hero meshes for cats, dogs, sheep, fox, lion. Costly — keep count "
        "below 10k for previews, up to ~30k for cinematic."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "object": {"type": "string", "description": "Target mesh name"},
            "count": {"type": "integer", "default": 5000},
            "length": {"type": "number", "default": 0.08, "description": "Strand length in metres"},
            "children": {"type": "integer", "default": 50},
            "root_radius": {"type": "number", "default": 1.0},
            "tip_radius": {"type": "number", "default": 0.05},
            "roughness": {"type": "number", "default": 0.8},
        },
        "required": ["object"],
        "additionalProperties": False,
    },
    category="materials",
)
def add_fur(params: dict) -> dict:
    return bridge.call("add_fur", params)


@register_fn(
    name="set_world_background",
    description=(
        "Set the world background color and strength. Use this for ambient lighting. "
        "For HDRI environments, use the hdri-loading tools (TODO future)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "color": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4,
                "description": "RGB or RGBA 0-1",
            },
            "strength": {"type": "number", "description": "Background light strength"},
        },
        "additionalProperties": False,
    },
    category="lighting",
)
def set_world_background(params: dict) -> dict:
    return bridge.call("set_world_background", params)


# ───────────────────────────────────────────────────────────────────────
# Lighting presets — high-level helpers that compose primitives
# ───────────────────────────────────────────────────────────────────────

@register_fn(
    name="apply_three_point_lighting",
    description=(
        "Drop a classic three-point lighting rig (key, fill, rim) on a target. "
        "Key is brightest, fill softens shadows from the opposite side, rim back-lights "
        "for separation. Returns the names of the three created lights."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [0, 0, 0],
                "description": "World position to light",
            },
            "key_energy": {"type": "number", "default": 1500},
            "fill_energy": {"type": "number", "default": 500},
            "rim_energy": {"type": "number", "default": 800},
            "color_temp": {"type": "string", "enum": ["warm", "neutral", "cool"], "default": "neutral"},
        },
        "additionalProperties": False,
    },
    category="lighting",
)
def apply_three_point_lighting(params: dict) -> dict:
    tx, ty, tz = params.get("target", [0, 0, 0])
    color_map = {
        "warm":    (1.0, 0.88, 0.72),
        "neutral": (1.0, 1.0, 1.0),
        "cool":    (0.72, 0.85, 1.0),
    }
    color = color_map[params.get("color_temp", "neutral")]

    # Key — front-right, higher
    key = bridge.call("add_light", {
        "type": "AREA", "name": "Key", "location": [tx + 4, ty - 4, tz + 5],
        "energy": params.get("key_energy", 1500), "color": list(color), "size": 2.0,
    })
    bridge.call("look_at", {"object": key["name"], "target": [tx, ty, tz]})

    # Fill — front-left, weaker, cooler
    fill = bridge.call("add_light", {
        "type": "AREA", "name": "Fill", "location": [tx - 4, ty - 3, tz + 3],
        "energy": params.get("fill_energy", 500), "color": list(color), "size": 3.0,
    })
    bridge.call("look_at", {"object": fill["name"], "target": [tx, ty, tz]})

    # Rim — behind subject
    rim = bridge.call("add_light", {
        "type": "AREA", "name": "Rim", "location": [tx, ty + 5, tz + 4],
        "energy": params.get("rim_energy", 800), "color": list(color), "size": 1.5,
    })
    bridge.call("look_at", {"object": rim["name"], "target": [tx, ty, tz]})

    return {"key": key["name"], "fill": fill["name"], "rim": rim["name"]}
