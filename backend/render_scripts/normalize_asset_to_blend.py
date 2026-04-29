import bpy
import sys
from pathlib import Path


def args_after_double_dash():
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError("Missing args after --")
    return argv[argv.index("--") + 1:]


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def import_asset(path_str: str):
    low = path_str.lower()
    if low.endswith(".glb") or low.endswith(".gltf"):
        bpy.ops.import_scene.gltf(filepath=path_str)
    elif low.endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=path_str)
    else:
        raise RuntimeError(f"Unsupported normalize input: {path_str}")


def normalize_objects():
    objs = [o for o in bpy.context.scene.objects if o.type in {"MESH", "EMPTY", "CURVE"}]
    if not objs:
        return

    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]

    # simple normalize
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    for o in objs:
        o.location = (0, 0, 0)


def main():
    input_asset, output_blend = args_after_double_dash()
    clear_scene()
    import_asset(input_asset)
    normalize_objects()
    Path(output_blend).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=output_blend)


if __name__ == "__main__":
    main()