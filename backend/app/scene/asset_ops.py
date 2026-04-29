from __future__ import annotations

from pathlib import Path


def append_collection_from_blend(bpy, blend_path: str, collection_name: str):
    blend_path = str(Path(blend_path))
    directory = blend_path + "\\Collection\\"
    filepath = directory + collection_name

    bpy.ops.wm.append(
        filepath=filepath,
        filename=collection_name,
        directory=directory,
    )


def append_material_from_blend(bpy, blend_path: str, material_name: str):
    blend_path = str(Path(blend_path))
    directory = blend_path + "\\Material\\"
    filepath = directory + material_name

    bpy.ops.wm.append(
        filepath=filepath,
        filename=material_name,
        directory=directory,
    )


def apply_material_to_object(obj, material):
    if obj is None or material is None:
        return
    if len(obj.data.materials) == 0:
        obj.data.materials.append(material)
    else:
        obj.data.materials[0] = material
