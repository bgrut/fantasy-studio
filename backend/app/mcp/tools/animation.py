"""
Animation tools — keyframes, frame range, common animation helpers.

For the orchestrator: most animations are 2-3 keyframes on location/rotation.
animate_property gives a one-call shortcut. set_keyframe is the primitive.
"""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="set_keyframe",
    description=(
        "Insert a single keyframe on a property. data_path is the bpy property name: "
        "'location', 'rotation_euler', 'scale', or any animatable property path. "
        "Optionally sets the value before inserting (so you don't have to transform first)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "object": {"type": "string"},
            "data_path": {"type": "string", "description": "e.g. 'location', 'rotation_euler', 'scale'"},
            "value": {
                "description": "Optional — sets the property to this value before keyframing",
            },
            "frame": {"type": "integer"},
            "index": {"type": "integer", "default": -1, "description": "Axis index for vector props (0/1/2), or -1 for all"},
        },
        "required": ["object", "data_path", "frame"],
        "additionalProperties": False,
    },
    category="animation",
)
def set_keyframe(params: dict) -> dict:
    return bridge.call("set_keyframe", params)


@register_fn(
    name="set_frame_range",
    description="Set scene frame_start, frame_end, and/or frame_current.",
    input_schema={
        "type": "object",
        "properties": {
            "frame_start": {"type": "integer"},
            "frame_end": {"type": "integer"},
            "frame_current": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    category="animation",
)
def set_frame_range(params: dict) -> dict:
    return bridge.call("set_frame_range", params)


@register_fn(
    name="animate_property",
    description=(
        "Convenience: keyframe a property at two frames in one call (start + end). "
        "Equivalent to two set_keyframe calls. Use for simple linear-style transitions; "
        "for ease curves, use set_keyframe + an external f-curve interpolation step."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "object": {"type": "string"},
            "data_path": {"type": "string", "description": "e.g. 'location', 'rotation_euler', 'scale'"},
            "start_value": {"description": "Value at start_frame"},
            "end_value": {"description": "Value at end_frame"},
            "start_frame": {"type": "integer", "default": 1},
            "end_frame": {"type": "integer", "default": 120},
        },
        "required": ["object", "data_path", "start_value", "end_value"],
        "additionalProperties": False,
    },
    category="animation",
)
def animate_property(params: dict) -> dict:
    obj = params["object"]
    dp = params["data_path"]
    sf = params.get("start_frame", 1)
    ef = params.get("end_frame", 120)

    bridge.call("set_keyframe", {
        "object": obj, "data_path": dp, "value": params["start_value"], "frame": sf,
    })
    bridge.call("set_keyframe", {
        "object": obj, "data_path": dp, "value": params["end_value"], "frame": ef,
    })
    return {
        "object": obj, "data_path": dp,
        "keyframes": [{"frame": sf, "value": params["start_value"]},
                      {"frame": ef, "value": params["end_value"]}],
    }


@register_fn(
    name="orbit_camera_around",
    description=(
        "Animate a camera in a circular orbit around a target point. "
        "Creates an empty at the target, parents the camera to it, "
        "keyframes the empty's Z-rotation. Returns the empty's name."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "camera": {"type": "string", "description": "Camera object name"},
            "target": {
                "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                "default": [0, 0, 0],
            },
            "radius": {"type": "number", "default": 8.0},
            "height": {"type": "number", "default": 3.0, "description": "Camera height above target"},
            "duration_frames": {"type": "integer", "default": 120},
            "revolutions": {"type": "number", "default": 1.0},
        },
        "required": ["camera"],
        "additionalProperties": False,
    },
    category="animation",
)
def orbit_camera_around(params: dict) -> dict:
    import math
    cam = params["camera"]
    tx, ty, tz = params.get("target", [0, 0, 0])
    radius = params.get("radius", 8.0)
    height = params.get("height", 3.0)
    duration = params.get("duration_frames", 120)
    revs = params.get("revolutions", 1.0)

    # We achieve orbit by keyframing the camera's location on a circle.
    # Skip parenting/empty for simplicity in MVP — orchestrator can refine later.
    steps = max(8, int(duration // 4))  # one keyframe every ~4 frames
    for i in range(steps + 1):
        t = i / steps
        angle = t * revs * 2 * math.pi
        x = tx + radius * math.cos(angle)
        y = ty + radius * math.sin(angle)
        z = tz + height
        frame = 1 + int(t * (duration - 1))
        bridge.call("set_keyframe", {
            "object": cam, "data_path": "location", "value": [x, y, z], "frame": frame,
        })
        # Aim at target each keyframe
        bridge.call("look_at", {"object": cam, "target": [tx, ty, tz]})
        bridge.call("set_keyframe", {
            "object": cam, "data_path": "rotation_euler", "frame": frame,
        })

    return {
        "camera": cam,
        "keyframes": steps + 1,
        "duration_frames": duration,
        "target": [tx, ty, tz],
    }
