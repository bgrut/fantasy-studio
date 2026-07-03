"""Camera tools — create, position, aim."""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="create_camera",
    description=(
        "Create a new camera and (by default) make it the active scene camera. "
        "Use rotation_euler in radians OR call look_at after to aim it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "default": "Camera"},
            "location": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [7, -7, 5],
            },
            "rotation_euler": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "description": "Radians (Blender XYZ Euler). Default points at origin.",
            },
            "lens": {"type": "number", "default": 50.0, "description": "Focal length in mm"},
            "set_active": {"type": "boolean", "default": True},
        },
        "additionalProperties": False,
    },
    category="camera",
)
def create_camera(params: dict) -> dict:
    return bridge.call("create_camera", params)


@register_fn(
    name="look_at",
    description=(
        "Aim an object (typically the camera) at a target. Target is either a "
        "world location [x,y,z] OR an object reference {'object': '<name>'}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "object": {"type": "string", "description": "Name of object to rotate"},
            "target": {
                "oneOf": [
                    {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    {"type": "object", "properties": {"object": {"type": "string"}}, "required": ["object"]},
                ],
                "description": "World location or {'object': '<name>'}",
            },
        },
        "required": ["object", "target"],
        "additionalProperties": False,
    },
    category="camera",
)
def look_at(params: dict) -> dict:
    return bridge.call("look_at", params)
