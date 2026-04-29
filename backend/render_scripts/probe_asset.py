"""
probe_asset.py
==============
Run headless in Blender to extract metadata from a 3D asset file.

Usage:
    blender --background --python probe_asset.py -- input.glb

Outputs a single line starting with ``PROBE_RESULT:`` followed by JSON.
The calling Python process parses that line.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy  # type: ignore
from mathutils import Vector  # type: ignore


def _args_after_dd():
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError("Missing args after --")
    return argv[argv.index("--") + 1:]


def _clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _import(path_str: str):
    low = path_str.lower()
    if low.endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path_str)
    elif low.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path_str)
    elif low.endswith(".obj"):
        try:
            bpy.ops.wm.obj_import(filepath=path_str)
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=path_str)
    elif low.endswith(".blend"):
        # Link all objects from the .blend
        with bpy.data.libraries.load(path_str, link=False) as (src, dst):
            dst.objects = src.objects
        for obj in dst.objects:
            if obj is not None:
                bpy.context.collection.objects.link(obj)
    else:
        print(f"PROBE_ERROR:unsupported format {path_str}", flush=True)
        return


def _classify(meta: dict) -> str:
    """Infer asset type from probed metadata."""
    bone_names_lower = " ".join(meta.get("armature_bone_names", [])).lower()
    mesh_names_lower = " ".join(meta.get("mesh_names", [])).lower()
    all_names = bone_names_lower + " " + mesh_names_lower

    # Vehicle detection
    vehicle_kw = ["wheel", "tire", "chassis", "bumper", "hood", "door",
                  "engine", "car", "vehicle", "exhaust", "headlight"]
    if sum(1 for k in vehicle_kw if k in all_names) >= 2:
        return "vehicle"

    # Humanoid detection (bones)
    humanoid_bones = ["spine", "hip", "head", "neck", "shoulder", "arm",
                      "leg", "hand", "foot", "pelvis", "thigh", "calf"]
    if sum(1 for b in humanoid_bones if b in bone_names_lower) >= 4:
        return "humanoid"

    # Animal detection
    animal_bones = ["tail", "paw", "jaw", "ear", "snout", "hind", "fore",
                    "muzzle", "claw"]
    if meta.get("has_armature") and any(b in bone_names_lower for b in animal_bones):
        return "animal"

    # Generic rigged character
    if meta.get("has_armature"):
        return "character"

    # Size-based for static objects
    bbox_size = meta.get("bounding_box", {}).get("size", [1, 1, 1])
    max_dim = max(bbox_size) if bbox_size else 1.0
    if max_dim < 0.3:
        return "product"
    elif max_dim < 2.0:
        return "prop"
    else:
        return "environment"


def main():
    input_path = _args_after_dd()[0]
    _clear()
    _import(input_path)

    meta = {
        "objects": [],
        "has_armature": False,
        "has_animations": False,
        "armature_bone_names": [],
        "mesh_names": [],
        "material_names": [],
        "bounding_box": {"min": [0, 0, 0], "max": [0, 0, 0], "size": [0, 0, 0]},
        "total_vertices": 0,
        "total_faces": 0,
        "animation_actions": [],
    }

    all_min = [float("inf")] * 3
    all_max = [float("-inf")] * 3

    for obj in bpy.data.objects:
        meta["objects"].append({"name": obj.name, "type": obj.type})

        if obj.type == "ARMATURE":
            meta["has_armature"] = True
            for bone in obj.data.bones:
                meta["armature_bone_names"].append(bone.name)

        if obj.type == "MESH":
            meta["mesh_names"].append(obj.name)
            mesh = obj.data
            meta["total_vertices"] += len(mesh.vertices)
            meta["total_faces"] += len(mesh.polygons)

            # World-space bounding box
            for corner in obj.bound_box:
                world_v = obj.matrix_world @ Vector(corner)
                for i in range(3):
                    all_min[i] = min(all_min[i], world_v[i])
                    all_max[i] = max(all_max[i], world_v[i])

        # Materials
        if hasattr(obj, "data") and hasattr(getattr(obj, "data", None) or object(), "materials"):
            for mat in (obj.data.materials or []):
                if mat and mat.name not in meta["material_names"]:
                    meta["material_names"].append(mat.name)

    # Animations
    for action in bpy.data.actions:
        meta["animation_actions"].append(action.name)
        meta["has_animations"] = True

    # Bounding box
    if all_min[0] != float("inf"):
        meta["bounding_box"] = {
            "min": [round(v, 4) for v in all_min],
            "max": [round(v, 4) for v in all_max],
            "size": [round(all_max[i] - all_min[i], 4) for i in range(3)],
        }

    meta["inferred_type"] = _classify(meta)

    print("PROBE_RESULT:" + json.dumps(meta), flush=True)


if __name__ == "__main__":
    main()
