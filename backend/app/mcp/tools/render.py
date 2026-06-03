"""Render tools — settings + single-frame and animation renders."""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="set_render_settings",
    description=(
        "Configure renderer: engine ('CYCLES'|'BLENDER_EEVEE'|'BLENDER_EEVEE_NEXT'), "
        "resolution, samples (Cycles only), fps, output filepath. "
        "Call once at the start of a pipeline to lock settings."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "engine": {"type": "string", "enum": ["CYCLES", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"]},
            "resolution_x": {"type": "integer"},
            "resolution_y": {"type": "integer"},
            "samples": {"type": "integer", "description": "Cycles only — try 64 (preview), 256 (final)"},
            "fps": {"type": "integer"},
            "filepath": {"type": "string"},
        },
        "additionalProperties": False,
    },
    category="render",
)
def set_render_settings(params: dict) -> dict:
    return bridge.call("set_render_settings", params)


@register_fn(
    name="render_frame",
    description=(
        "Render a single still frame. Blocking — returns when render finishes. "
        "Provide filepath (e.g. '/tmp/out.png') and optionally a specific frame number."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filepath": {"type": "string"},
            "frame": {"type": "integer", "description": "Defaults to current scene frame"},
        },
        "required": ["filepath"],
        "additionalProperties": False,
    },
    category="render",
)
def render_frame(params: dict) -> dict:
    return bridge.call("render_frame", params)


@register_fn(
    name="render_animation",
    description=(
        "Render the scene's frame range as a PNG sequence (frame_0001.png, frame_0002.png, ...). "
        "Use this for MOTION prompts — anything with keywords like 'rotating', 'orbiting', "
        "'moving', 'running', 'flying', 'walking', 'animating'. "
        "BEFORE calling this, you must: (1) call set_frame_range to set frame_start/frame_end, "
        "(2) set keyframes on objects/cameras to define the motion, (3) ensure the scene has an "
        "active camera. AFTER this, call encode_video to stitch the PNGs into MP4."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "output_dir": {
                "type": "string",
                "description": "Directory to write PNG sequence into. The orchestrator pre-creates one for you and passes it via context as 'animation_dir'.",
            },
            "frame_start": {"type": "integer", "description": "Optional — defaults to scene.frame_start"},
            "frame_end": {"type": "integer", "description": "Optional — defaults to scene.frame_end"},
            "fps": {"type": "integer", "default": 24},
        },
        "required": ["output_dir"],
        "additionalProperties": False,
    },
    category="render",
)
def render_animation(params: dict) -> dict:
    # Long timeout — multi-frame renders can take 5-15 minutes on consumer GPUs.
    return bridge.call("render_animation", params, timeout=1800.0)


@register_fn(
    name="render_frame_long",
    description="Same as render_frame but with a longer client timeout (for high-sample renders).",
    input_schema={
        "type": "object",
        "properties": {"filepath": {"type": "string"}, "frame": {"type": "integer"}},
        "required": ["filepath"],
        "additionalProperties": False,
    },
    category="render",
)
def render_frame_long(params: dict) -> dict:
    return bridge.call("render_frame", params, timeout=600.0)
