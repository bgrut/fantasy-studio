"""Asset I/O tools — import generated meshes, save .blend files.

Phase 17 wiring. The orchestrator uses these as the final step in the
asset-driven pipeline.
"""

from .. import blender_bridge as bridge
from ..registry import register_fn


@register_fn(
    name="import_mesh_file",
    description=(
        "Import a GLB/GLTF/OBJ/FBX mesh into the scene. Used by Phase 17 "
        "asset-driven pipeline (mesh generated outside Blender by TripoSR/"
        "InstantMesh from a reference image). Optionally normalizes scale "
        "and grounds to z=0 so existing camera/lighting logic just works."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filepath": {"type": "string", "description": "Absolute path to .glb/.gltf/.obj/.fbx"},
            "name": {"type": "string", "default": "Hero"},
            "normalize_size": {
                "type": ["number", "null"],
                "default": 2.0,
                "description": "Scale uniformly so longest bbox axis = this metres. null to keep raw.",
            },
            "ground_to_z0": {"type": "boolean", "default": True},
            "join": {"type": "boolean", "default": True, "description": "Join multi-mesh imports into one"},
        },
        "required": ["filepath"],
        "additionalProperties": False,
    },
    category="asset",
)
def import_mesh_file(params: dict) -> dict:
    return bridge.call("import_mesh_file", params)


@register_fn(
    name="save_blend_file",
    description=(
        "Save the current scene to a .blend file. Phase 17 deliverable: every "
        "render ships with an editable .blend the user can open and tweak."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "filepath": {"type": "string"},
            "compress": {"type": "boolean", "default": True},
        },
        "required": ["filepath"],
        "additionalProperties": False,
    },
    category="asset",
)
def save_blend_file(params: dict) -> dict:
    return bridge.call("save_blend_file", params)
