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

    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        bpy.data.materials.remove(block)
    for block in bpy.data.cameras:
        bpy.data.cameras.remove(block)
    for block in bpy.data.curves:
        bpy.data.curves.remove(block)
    for block in bpy.data.lights:
        bpy.data.lights.remove(block)


def main():
    output_path_str, topic, template_name = args_after_double_dash()
    output_path = Path(output_path_str)

    clear_scene()

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
    scene.render.resolution_x = 720
    scene.render.resolution_y = 1280
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 144
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.filepath = str(output_path)

    # Camera
    bpy.ops.object.camera_add(location=(0, -8, 0), rotation=(1.5708, 0, 0))
    cam = bpy.context.object
    scene.camera = cam

    # Light
    bpy.ops.object.light_add(type='AREA', location=(0, -3, 4))
    light = bpy.context.object
    light.data.energy = 4000

    # Text
    bpy.ops.object.text_add(location=(-2.8, 0, 1.2), rotation=(1.5708, 0, 0))
    txt = bpy.context.object
    txt.data.body = f"{template_name.upper()}\\n{topic[:55]}"
    txt.data.extrude = 0.02
    txt.scale = (0.55, 0.55, 0.55)

    # Plane backdrop
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -1.4))
    plane = bpy.context.object

    # Animate camera push-in
    cam.location = (0, -9, 0)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (0, -6.5, 0)
    cam.keyframe_insert(data_path="location", frame=144)

    # Animate text slight rise
    txt.location = (-2.8, 0, 0.9)
    txt.keyframe_insert(data_path="location", frame=1)
    txt.location = (-2.8, 0, 1.2)
    txt.keyframe_insert(data_path="location", frame=144)

    bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()