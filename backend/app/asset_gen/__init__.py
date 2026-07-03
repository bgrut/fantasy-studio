"""
Fantasy Studio — Phase 17 asset generation layer.

This is the architectural pivot: instead of refining a procedural blob into
a polished video, we use diffusion + image-to-3D to BUILD the scene assets
first, then let Blender do what Blender is good at — animate, light, render.

Pipeline:
    LLM → slots
        ↓
    asset_gen.reference: SDXL text-to-image → reference PNG of the subject
        ↓
    asset_gen.mesh: TripoSR / InstantMesh → GLB mesh
        ↓
    Blender imports mesh → existing camera/light/HDRI flow → render → .blend + .mp4

Modules:
    reference     — text-to-image (SDXL) producing a clean studio shot
    mesh          — image-to-3D producing a GLB
    (texture)     — future: multi-view texture projection
"""

from .reference import generate_reference, is_t2i_available, REFERENCE_STYLES
from .mesh import generate_mesh, is_mesh_gen_available, MESH_ENGINES

__all__ = [
    "generate_reference", "is_t2i_available", "REFERENCE_STYLES",
    "generate_mesh", "is_mesh_gen_available", "MESH_ENGINES",
]
