from __future__ import annotations

from .materials import make_emissive_material, assign_material


def add_simple_billboard(bpy, location=(0, 0, 2), scale=(1.5, 0.1, 1.0), color=(1.0, 0.0, 1.0, 1.0), strength=8.0):
    bpy.ops.mesh.primitive_plane_add(location=location)
    board = bpy.context.object
    board.scale = scale

    mat = make_emissive_material(
        bpy,
        name=f"Billboard_{location[0]}_{location[1]}",
        color=color,
        strength=strength
    )
    assign_material(board, mat)
    return board
