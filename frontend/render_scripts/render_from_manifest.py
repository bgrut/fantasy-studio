import bpy
import json
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

    for block_collection in [
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.curves,
        bpy.data.lights,
    ]:
        for block in list(block_collection):
            block_collection.remove(block)


def load_manifest(path_str: str):
    p = Path(path_str)
    return json.loads(p.read_text(encoding="utf-8"))


def build_city_loop(manifest, scene):
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, -1.5))

    positions = [(-8, 8), (-4, 10), (0, 9), (4, 11), (8, 8), (-10, -4), (-5, -6), (5, -7), (10, -5)]
    heights = [8, 11, 10, 13, 9, 7, 9, 8, 7]
    for (x, y), h in zip(positions, heights):
        bpy.ops.mesh.primitive_cube_add(location=(x, y, h / 2 - 1.5))
        b = bpy.context.object
        b.scale = (1.6, 1.6, h / 2)

    for loc, energy in [((-6, -4, 6), 3000), ((6, -4, 5), 3000), ((0, 10, 10), 5000)]:
        bpy.ops.object.light_add(type='POINT', location=loc)
        light = bpy.context.object
        light.data.energy = energy

    bpy.ops.object.camera_add(location=(0, -18, 6), rotation=(1.2, 0, 0))
    cam = bpy.context.object
    scene.camera = cam

    cam.location = (0, -20, 6)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (0, -12, 7)
    cam.keyframe_insert(data_path="location", frame=scene.frame_end)


def build_product_pedestal(manifest, scene):
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -1.5))
    bpy.ops.mesh.primitive_cylinder_add(radius=2.2, depth=1.2, location=(0, 0, -0.9))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.4, location=(0, 0, 1.2))
    hero = bpy.context.object

    bpy.ops.object.light_add(type='AREA', location=(0, -4, 5))
    key = bpy.context.object
    key.data.energy = 5000

    bpy.ops.object.camera_add(location=(0, -8, 1.5), rotation=(1.4, 0, 0))
    cam = bpy.context.object
    scene.camera = cam

    hero.rotation_euler = (0, 0, 0)
    hero.keyframe_insert(data_path="rotation_euler", frame=1)
    hero.rotation_euler = (0, 0, 6.28318)
    hero.keyframe_insert(data_path="rotation_euler", frame=scene.frame_end)


def build_neon_news(manifest, scene):
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 4, 0))
    bg = bpy.context.object
    bg.rotation_euler = (1.5708, 0, 0)

    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -1.5))

    bpy.ops.object.text_add(location=(-3.8, 0, 1.4), rotation=(1.5708, 0, 0))
    txt = bpy.context.object
    txt.data.body = f"{manifest.get('title_text', 'NEWS')}\n{manifest.get('subject', '')[:64]}"
    txt.data.extrude = 0.02
    txt.scale = (0.45, 0.45, 0.45)

    bpy.ops.object.light_add(type='POINT', location=(-4, -2, 4))
    left = bpy.context.object
    left.data.energy = 2500

    bpy.ops.object.light_add(type='POINT', location=(4, -2, 4))
    right = bpy.context.object
    right.data.energy = 2500

    bpy.ops.object.camera_add(location=(0, -8, 0.5), rotation=(1.5708, 0, 0))
    cam = bpy.context.object
    scene.camera = cam

    cam.location = (0, -9, 0.5)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (0, -6.5, 0.5)
    cam.keyframe_insert(data_path="location", frame=scene.frame_end)


def main():
    output_path_str, manifest_path_str = args_after_double_dash()
    output_path = Path(output_path_str)
    manifest = load_manifest(manifest_path_str)

    clear_scene()

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = manifest["output_resolution"]["width"]
    scene.render.resolution_y = manifest["output_resolution"]["height"]
    scene.render.fps = int(manifest.get("fps", 24))
    scene.frame_start = 1
    scene.frame_end = int(manifest.get("duration_seconds", 12)) * scene.render.fps

    output_dir = output_path.parent / output_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output_dir / "frame_")
    scene.render.image_settings.file_format = 'PNG'

    template = str(manifest.get("template_name", "neon_news")).lower()

    if template == "city_loop":
        build_city_loop(manifest, scene)
    elif template == "product_pedestal":
        build_product_pedestal(manifest, scene)
    else:
        build_neon_news(manifest, scene)

    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
