"""
Escape hatch — execute arbitrary Python in Blender.

This is the "I need something the curated tools don't expose" lever.
Mirrors blender-mcp's execute_blender_code. Use sparingly — every use of
this is a signal that we should add a proper curated tool.

Convention: assign the value you want returned to __result__.
"""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="execute_python",
    description=(
        "Execute arbitrary Python inside Blender. Available globals: bpy, mathutils, math. "
        "Assign the value to return to a variable named __result__. "
        "USE SPARINGLY — if you find yourself reaching for this, propose a new curated tool. "
        "Returns: {'result': <value-or-repr>}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code. Set __result__ = <value> to return data.",
            },
        },
        "required": ["code"],
        "additionalProperties": False,
    },
    category="escape_hatch",
)
def execute_python(params: dict) -> dict:
    # BLENDER SCRIPTS TAKE THEIR TIME (2026-10-02): rigging, retargeting and
    # optimising a half-million-face generated mesh run for minutes, and the
    # bridge's 60 s default timed every one out (the new ranger was
    # registered raw three times). Scripts get ten minutes unless the caller
    # names its own with "_timeout".
    params = dict(params or {})
    t = float(params.pop("_timeout", 600.0))
    return bridge.call("execute_python", params, timeout=t)
