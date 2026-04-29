from ..scene.lighting import add_point_light, setup_world_bg
from ..scene.camera_ops import create_camera, animate_dolly
from ..scene.layout_ops import add_atmosphere_box


def build_neon_news(bpy, manifest: dict, scene):
    setup_world_bg(scene, strength=0.025)

    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 4, 0))
    bg = bpy.context.object
    bg.rotation_euler = (1.5708, 0, 0)

    bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, -1.5))

    bpy.ops.object.text_add(location=(-4.2, 0, 1.5), rotation=(1.5708, 0, 0))
    txt = bpy.context.object
    txt.data.body = f"{manifest.get('title_text', 'NEWS')}\n{manifest.get('subject', '')[:72]}"
    txt.data.extrude = 0.02
    txt.scale = (0.42, 0.42, 0.42)

    add_point_light(bpy, location=(-5, -2, 4), energy=2600, color=(0.2, 0.8, 1.0))
    add_point_light(bpy, location=(5, -2, 4), energy=2600, color=(1.0, 0.2, 0.8))

    # Neon haze — enhances glow from colored lights
    add_atmosphere_box(
        bpy, location=(0, 2, 1.5), scale=(12, 6, 4),
        density=0.008, color=(0.60, 0.65, 0.80, 1.0),
        name="NeonNewsAtmo",
    )

    cam = create_camera(bpy, scene, location=(0, -9, 0.4), rotation=(1.5708, 0, 0))
    animate_dolly(cam, (0, -10, 0.4), (0, -6.7, 0.4), scene.frame_end)

    txt.location = (-4.2, 0, 1.0)
    txt.keyframe_insert(data_path="location", frame=1)
    txt.location = (-4.2, 0, 1.5)
    txt.keyframe_insert(data_path="location", frame=scene.frame_end)

    return {"camera": cam}

