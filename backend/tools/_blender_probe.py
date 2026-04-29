"""
_blender_probe.py
=================
Blender-side helper called by ``tools/curate_asset.py``. Runs inside a
headless ``blender -b --python`` subprocess. Given a 3D file path, it:

  1. Imports the file into a fresh Blender scene.
  2. Measures the world-space bounding box across all mesh objects.
  3. Detects armatures, their actions, and the likely forward axis.
  4. Counts faces, materials, textures.
  5. Optionally normalises origin + scale + rotation.
  6. Optionally exports a normalised .glb to a target path.
  7. Writes a JSON probe report to the path given by ``--report``.

CLI (after Blender's ``--``):
    blender -b --python tools/_blender_probe.py -- \\
        --input path/to/model.gltf \\
        --report path/to/report.json \\
        [--export path/to/normalized.glb] \\
        [--target-height 1.0] \\
        [--no-normalize]

Nothing in this file is imported by the backend. It is called only as
a standalone Blender script, which is why all helper functions live at
module scope rather than in the app package.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


# ═══════════════════════════════════════════════════════════════════════════
# Argument parsing (Blender passes script args after ``--``)
# ═══════════════════════════════════════════════════════════════════════════

def _script_argv() -> list[str]:
    if "--" not in sys.argv:
        return []
    idx = sys.argv.index("--")
    return sys.argv[idx + 1:]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe a 3D asset inside Blender")
    parser.add_argument("--input", required=True, help="Path to the 3D model file")
    parser.add_argument("--report", required=True, help="Path to write JSON probe report")
    parser.add_argument("--export", default=None,
                        help="If set, export the normalised scene as .glb to this path")
    parser.add_argument("--target-height", type=float, default=None,
                        help="If set, uniformly scale so the bounding height equals this value")
    parser.add_argument("--no-normalize", action="store_true",
                        help="Skip origin/scale/rotation normalisation")
    return parser.parse_args(_script_argv())


# ═══════════════════════════════════════════════════════════════════════════
# Scene prep
# ═══════════════════════════════════════════════════════════════════════════

def _clear_scene() -> None:
    """Nuke everything so the import is the only thing in the scene."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.armatures):
        for item in list(block):
            try:
                block.remove(item, do_unlink=True)
            except RuntimeError:
                pass


def _import_file(path: Path) -> list:
    """Import the given file, returning the list of newly-created objects."""
    before = set(bpy.data.objects)
    suffix = path.suffix.lower()
    if suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif suffix == ".blend":
        with bpy.data.libraries.load(str(path)) as (data_from, data_to):
            data_to.objects = data_from.objects
        for obj in data_to.objects:
            if obj is not None:
                bpy.context.scene.collection.objects.link(obj)
    else:
        raise RuntimeError(f"Unsupported file type: {suffix}")
    return [o for o in bpy.data.objects if o not in before]


# ═══════════════════════════════════════════════════════════════════════════
# Measurement
# ═══════════════════════════════════════════════════════════════════════════

def _world_bbox(objs) -> tuple[Vector, Vector] | None:
    mins = Vector(( float("inf"),  float("inf"),  float("inf")))
    maxs = Vector((-float("inf"), -float("inf"), -float("inf")))
    found = False
    for obj in objs:
        if obj.type != "MESH":
            continue
        try:
            mw = obj.matrix_world
            for corner in obj.bound_box:
                v = mw @ Vector(corner)
                mins.x = min(mins.x, v.x); maxs.x = max(maxs.x, v.x)
                mins.y = min(mins.y, v.y); maxs.y = max(maxs.y, v.y)
                mins.z = min(mins.z, v.z); maxs.z = max(maxs.z, v.z)
            found = True
        except Exception:
            continue
    if not found:
        return None
    return (mins, maxs)


def _detect_forward_axis(objs) -> str:
    """
    Heuristic: if there's an armature, use its forward from bone layout.
    Otherwise measure the mesh bbox — the shorter horizontal axis is
    generally "forward" for four-legged creatures and vehicles.
    """
    box = _world_bbox(objs)
    if not box:
        return "Y"
    mins, maxs = box
    width = max(maxs.x - mins.x, 0.001)
    depth = max(maxs.y - mins.y, 0.001)
    # Tall-and-narrow = humanoid → forward is Y; long-and-low = quadruped or car → forward is Y.
    # Use the LONGER horizontal axis as forward (matches how Sketchfab tends to author).
    return "Y" if depth >= width else "X"


def _armature_info(objs) -> list[dict]:
    info = []
    for obj in objs:
        if obj.type != "ARMATURE":
            continue
        actions: list[str] = []
        if obj.animation_data and obj.animation_data.action:
            actions.append(obj.animation_data.action.name)
        for track in (obj.animation_data.nla_tracks if obj.animation_data else []):
            for strip in track.strips:
                if strip.action and strip.action.name not in actions:
                    actions.append(strip.action.name)
        # Also scan all actions whose fcurves reference this armature
        for action in bpy.data.actions:
            if action.name in actions:
                continue
            for fc in action.fcurves:
                if fc.data_path.startswith("pose.bones"):
                    actions.append(action.name)
                    break
        info.append({
            "name": obj.name,
            "bone_count": len(obj.data.bones) if obj.data else 0,
            "actions": actions,
        })
    return info


def _face_count(objs) -> int:
    total = 0
    for obj in objs:
        if obj.type == "MESH" and obj.data:
            total += len(obj.data.polygons)
    return total


def _material_and_texture_count(objs) -> tuple[int, int]:
    materials: set[str] = set()
    textures: set[str] = set()
    for obj in objs:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            if slot.material:
                materials.add(slot.material.name)
                if slot.material.use_nodes:
                    for n in slot.material.node_tree.nodes:
                        if n.bl_idname == "ShaderNodeTexImage" and n.image:
                            textures.add(n.image.name)
    return (len(materials), len(textures))


# ═══════════════════════════════════════════════════════════════════════════
# Normalisation
# ═══════════════════════════════════════════════════════════════════════════

def _normalize(objs, target_height: float | None) -> dict:
    """
    Center the object on X/Y, sit it on Z=0, optionally rescale so the
    bbox height is ``target_height``. Returns the applied transform.
    """
    box = _world_bbox(objs)
    if not box:
        return {"centered": False, "scaled_by": 1.0}
    mins, maxs = box
    center_xy = Vector(((mins.x + maxs.x) / 2.0, (mins.y + maxs.y) / 2.0, 0.0))
    floor_z = mins.z

    # Pick a root to move. Prefer an armature if one exists.
    root = None
    for obj in objs:
        if obj.type == "ARMATURE" and obj.parent is None:
            root = obj
            break
    if root is None:
        for obj in objs:
            if obj.parent is None:
                root = obj
                break
    if root is None:
        return {"centered": False, "scaled_by": 1.0}

    root.location.x -= center_xy.x
    root.location.y -= center_xy.y
    root.location.z -= floor_z

    scale_factor = 1.0
    if target_height is not None and target_height > 0:
        height = max(maxs.z - mins.z, 0.001)
        scale_factor = target_height / height
        root.scale = (
            root.scale.x * scale_factor,
            root.scale.y * scale_factor,
            root.scale.z * scale_factor,
        )

    return {
        "centered": True,
        "scaled_by": scale_factor,
        "target_height": target_height,
    }


def _export_glb(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        bpy.ops.export_scene.gltf(
            filepath=str(path),
            export_format="GLB",
            export_animations=True,
            export_skins=True,
            export_morph=True,
            export_apply=False,
        )
        return True
    except Exception as e:
        print(f"[PROBE] GLB export failed: {e}", flush=True)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    args = _parse_args()
    input_path = Path(args.input).resolve()
    report_path = Path(args.report).resolve()
    export_path = Path(args.export).resolve() if args.export else None

    if not input_path.exists():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"ok": False, "error": f"input not found: {input_path}"}),
            encoding="utf-8",
        )
        return 1

    _clear_scene()

    try:
        imported = _import_file(input_path)
    except Exception as e:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"ok": False, "error": f"import failed: {e}"}),
            encoding="utf-8",
        )
        return 2

    if not imported:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"ok": False, "error": "no objects imported"}),
            encoding="utf-8",
        )
        return 3

    # Collect metrics on the as-imported scene.
    box = _world_bbox(imported)
    raw_bbox: dict | None = None
    if box:
        mins, maxs = box
        raw_bbox = {
            "width":  maxs.x - mins.x,
            "depth":  maxs.y - mins.y,
            "height": maxs.z - mins.z,
            "center": [
                (mins.x + maxs.x) / 2.0,
                (mins.y + maxs.y) / 2.0,
                (mins.z + maxs.z) / 2.0,
            ],
            "floor_z": mins.z,
        }

    armatures = _armature_info(imported)
    face_count = _face_count(imported)
    mat_count, tex_count = _material_and_texture_count(imported)
    forward_axis = _detect_forward_axis(imported)

    # Optional normalisation pass.
    normalize_report: dict | None = None
    if not args.no_normalize:
        normalize_report = _normalize(imported, target_height=args.target_height)

    # Re-measure after normalisation for the final bbox.
    box_after = _world_bbox(imported)
    final_bbox: dict | None = None
    if box_after:
        mins, maxs = box_after
        final_bbox = {
            "width":  maxs.x - mins.x,
            "depth":  maxs.y - mins.y,
            "height": maxs.z - mins.z,
            "center": [
                (mins.x + maxs.x) / 2.0,
                (mins.y + maxs.y) / 2.0,
                (mins.z + maxs.z) / 2.0,
            ],
            "floor_z": mins.z,
        }

    exported = False
    if export_path is not None:
        exported = _export_glb(export_path)

    report = {
        "ok": True,
        "input": str(input_path),
        "imported_object_count": len(imported),
        "mesh_count": sum(1 for o in imported if o.type == "MESH"),
        "face_count": face_count,
        "material_count": mat_count,
        "texture_count": tex_count,
        "armatures": armatures,
        "has_armature": bool(armatures),
        "forward_axis": forward_axis,
        "raw_bbox": raw_bbox,
        "final_bbox": final_bbox,
        "normalize": normalize_report,
        "exported": exported,
        "export_path": str(export_path) if export_path else None,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[PROBE] report written -> {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
