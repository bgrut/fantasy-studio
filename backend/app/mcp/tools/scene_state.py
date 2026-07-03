"""Scene state — read-only introspection. Orchestrator calls these to see what's in the scene."""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="reset_scene",
    description=(
        "Wipe the scene clean — delete all objects, lights, cameras, and orphan data. "
        "Reset world background to neutral. Use this at the START of every new render "
        "to guarantee a clean slate (otherwise leftover objects from a previous render "
        "will pollute the new scene)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "keep_default_cube": {"type": "boolean", "default": False},
            "keep_default_light": {"type": "boolean", "default": False},
            "keep_default_camera": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
    category="scene_state",
    side_effects=True,
)
def reset_scene(params: dict) -> dict:
    return bridge.call("reset_scene", params)


@register_fn(
    name="get_scene_info",
    description=(
        "Snapshot of the current Blender scene: name, frame range, render settings "
        "(engine/resolution/samples/fps), object count, active camera, world. "
        "Call this at the start of orchestration to know what state you're entering."
    ),
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    category="scene_state",
    side_effects=False,
)
def get_scene_info(params: dict) -> dict:
    return bridge.call("get_scene_info", params)


@register_fn(
    name="list_objects",
    description=(
        "List objects in the scene with location, rotation, scale, dimensions. "
        "Optional filters: type (MESH/LIGHT/CAMERA/EMPTY/...), name_prefix."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "type": {"type": "string", "description": "Filter by Blender object type, e.g. 'MESH', 'LIGHT', 'CAMERA'"},
            "name_prefix": {"type": "string", "description": "Only return objects whose name starts with this"},
        },
        "additionalProperties": False,
    },
    category="scene_state",
    side_effects=False,
)
def list_objects(params: dict) -> list:
    return bridge.call("list_objects", params)


@register_fn(
    name="get_object_info",
    description=(
        "Detailed info on a single object — geometry stats (verts/edges/polys for meshes), "
        "material slots, parent/children, custom properties."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Object name"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    category="scene_state",
    side_effects=False,
)
def get_object_info(params: dict) -> dict:
    return bridge.call("get_object_info", params)
