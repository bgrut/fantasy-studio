"""
_healer_blender_inspector.py
============================
Headless Blender subprocess invoked by asset_healer.heal_asset().

Loads an asset, measures world-space bbox / centroid / per-mesh dims,
checks for missing textures + empty material slots, then writes a JSON
result to the output path.  NEVER writes to the original asset.

Invoked as:
    blender -b --factory-startup --python _healer_blender_inspector.py -- <asset_path> <output_json>
"""
import json
import os
import sys


def _write_error(out_path: str, msg: str) -> None:
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"error": msg}, f)
    except Exception:
        pass


def main() -> None:
    try:
        sep = sys.argv.index("--")
    except ValueError:
        print("[HEALER_INSPECTOR] missing -- separator", flush=True)
        sys.exit(2)
    argv = sys.argv[sep + 1:]
    if len(argv) < 2:
        print("[HEALER_INSPECTOR] need <asset_path> <output_json>", flush=True)
        sys.exit(2)

    asset_path = argv[0]
    output_json = argv[1]

    try:
        import bpy  # type: ignore
    except Exception as e:
        _write_error(output_json, f"bpy import failed: {e}")
        sys.exit(1)

    # Clean scene
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    except Exception:
        # best effort
        for coll in list(bpy.data.collections):
            try:
                bpy.data.collections.remove(coll)
            except Exception:
                pass
        for obj in list(bpy.data.objects):
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass

    ext = os.path.splitext(asset_path)[1].lower()
    try:
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=asset_path)
        elif ext == ".blend":
            with bpy.data.libraries.load(asset_path, link=False) as (src, dst):
                dst.objects = list(src.objects)
            for obj in dst.objects:
                if obj is not None:
                    bpy.context.scene.collection.objects.link(obj)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=asset_path)
        elif ext == ".obj":
            # Blender 4.x uses wm.obj_import; 3.x uses import_scene.obj
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=asset_path)
            else:
                bpy.ops.import_scene.obj(filepath=asset_path)
        else:
            _write_error(output_json, f"unsupported format: {ext}")
            sys.exit(1)
    except Exception as e:
        _write_error(output_json, f"import failed: {e}")
        sys.exit(1)

    # Force transforms to be up-to-date before reading matrix_world
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]

    per_mesh_dims: list[list[float]] = []
    all_world_coords: list[tuple[float, float, float]] = []
    total_verts = 0

    for m in meshes:
        try:
            mw = m.matrix_world
            # Walk vertices in world space
            verts = m.data.vertices if m.data else []
            world_coords = [mw @ v.co for v in verts]
            if not world_coords:
                continue
            xs = [c.x for c in world_coords]
            ys = [c.y for c in world_coords]
            zs = [c.z for c in world_coords]
            per_mesh_dims.append([
                float(max(xs) - min(xs)),
                float(max(ys) - min(ys)),
                float(max(zs) - min(zs)),
            ])
            all_world_coords.extend((c.x, c.y, c.z) for c in world_coords)
            total_verts += len(world_coords)
        except Exception:
            continue

    if all_world_coords:
        xs = [c[0] for c in all_world_coords]
        ys = [c[1] for c in all_world_coords]
        zs = [c[2] for c in all_world_coords]
        bbox_min = [float(min(xs)), float(min(ys)), float(min(zs))]
        bbox_max = [float(max(xs)), float(max(ys)), float(max(zs))]
        n = len(all_world_coords)
        centroid = [
            float(sum(xs) / n),
            float(sum(ys) / n),
            float(sum(zs) / n),
        ]
    else:
        bbox_min = [0.0, 0.0, 0.0]
        bbox_max = [0.0, 0.0, 0.0]
        centroid = [0.0, 0.0, 0.0]

    bbox_dims = [bbox_max[i] - bbox_min[i] for i in range(3)]

    # Material sanity
    material_issues: list[str] = []
    for m in meshes:
        try:
            for slot in m.material_slots:
                if slot.material is None:
                    material_issues.append(f"empty material slot on {m.name!r}")
                    continue
                mat = slot.material
                if mat.use_nodes and mat.node_tree is not None:
                    for node in mat.node_tree.nodes:
                        if node.type == "TEX_IMAGE" and node.image is not None:
                            fp = node.image.filepath
                            if fp:
                                try:
                                    abs_fp = bpy.path.abspath(fp)
                                    if abs_fp and not os.path.exists(abs_fp):
                                        material_issues.append(
                                            f"missing texture: {os.path.basename(abs_fp)}"
                                        )
                                except Exception:
                                    pass
        except Exception:
            continue
    # Dedup + cap
    material_issues = list(dict.fromkeys(material_issues))[:10]

    result = {
        "bbox_min":       bbox_min,
        "bbox_max":       bbox_max,
        "bbox_dims":      bbox_dims,
        "centroid":       centroid,
        "per_mesh_dims":  per_mesh_dims,
        "mesh_count":     len(meshes),
        "vertex_count":   total_verts,
        "has_armature":   len(armatures) > 0,
        "material_issues": material_issues,
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
