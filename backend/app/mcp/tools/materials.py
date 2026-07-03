"""Material tools — create PBR materials, apply to objects."""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="create_material",
    description=(
        "Create a Principled BSDF material with base color, metallic, roughness, and "
        "optional emission. Returns the material name. Use apply_material next to assign it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "default": "Material"},
            "color": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4,
                "default": [0.8, 0.8, 0.8, 1.0],
                "description": "RGB or RGBA, 0-1 linear",
            },
            "metallic": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.0},
            "roughness": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
            "emission_color": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4,
                "description": "Glow color (optional)",
            },
            "emission_strength": {"type": "number", "default": 0.0},
        },
        "additionalProperties": False,
    },
    category="materials",
)
def create_material(params: dict) -> dict:
    return bridge.call("create_material", params)


@register_fn(
    name="apply_material",
    description="Assign an existing material to an object's first material slot.",
    input_schema={
        "type": "object",
        "properties": {
            "object": {"type": "string"},
            "material": {"type": "string"},
        },
        "required": ["object", "material"],
        "additionalProperties": False,
    },
    category="materials",
)
def apply_material(params: dict) -> dict:
    return bridge.call("apply_material", params)


# ───────────────────────────────────────────────────────────────────────
# Convenience presets matching existing backend builders
# ───────────────────────────────────────────────────────────────────────

@register_fn(
    name="create_emissive_material",
    description="Quick-create an emissive (glowing) material. Useful for neon, screens, sci-fi.",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "default": "Emissive"},
            "color": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [1.0, 0.4, 0.1],
            },
            "strength": {"type": "number", "default": 5.0},
        },
        "additionalProperties": False,
    },
    category="materials",
)
def create_emissive_material(params: dict) -> dict:
    color = params.get("color", [1.0, 0.4, 0.1])
    return bridge.call("create_material", {
        "name": params.get("name", "Emissive"),
        "color": list(color),
        "emission_color": list(color),
        "emission_strength": params.get("strength", 5.0),
        "metallic": 0.0,
        "roughness": 1.0,
    })


@register_fn(
    name="create_glass_material",
    description="Quick-create a glass material (transparent, IOR ~1.5).",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "default": "Glass"},
            "tint": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [1.0, 1.0, 1.0],
            },
        },
        "additionalProperties": False,
    },
    category="materials",
)
def create_glass_material(params: dict) -> dict:
    # Approximate glass via low roughness + Principled BSDF defaults
    return bridge.call("create_material", {
        "name": params.get("name", "Glass"),
        "color": list(params.get("tint", [1.0, 1.0, 1.0])),
        "roughness": 0.05,
        "metallic": 0.0,
    })


@register_fn(
    name="create_metal_material",
    description="Quick-create a metallic material (brushed/polished).",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "default": "Metal"},
            "color": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [0.7, 0.7, 0.75],
            },
            "polished": {"type": "boolean", "default": False, "description": "True = mirror-like (rough 0.05); False = brushed (0.3)"},
        },
        "additionalProperties": False,
    },
    category="materials",
)
def create_metal_material(params: dict) -> dict:
    return bridge.call("create_material", {
        "name": params.get("name", "Metal"),
        "color": list(params.get("color", [0.7, 0.7, 0.75])),
        "metallic": 1.0,
        "roughness": 0.05 if params.get("polished") else 0.3,
    })
