from ..scene.lighting import add_area_light, add_point_light, setup_world_bg
from ..scene.camera_ops import create_camera, animate_dolly, animate_orbit_y
from ..scene.layout_ops import add_atmosphere_box


def build_product_pedestal(bpy, manifest: dict, scene):
    setup_world_bg(scene, strength=0.03)

    bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, -1.5))

    bpy.ops.mesh.primitive_cylinder_add(radius=2.5, depth=1.2, location=(0, 0, -0.9))
    pedestal = bpy.context.object

    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.5, location=(0, 0, 1.3))
    hero = bpy.context.object

    add_area_light(bpy, location=(0, -5, 6), energy=6000, size=6)
    add_point_light(bpy, location=(3, 3, 5), energy=2200, color=(1.0, 0.95, 0.9))
    add_point_light(bpy, location=(-3, 3, 4), energy=1800, color=(0.85, 0.9, 1.0))

    # Subtle studio haze for depth
    add_atmosphere_box(
        bpy, location=(0, 0, 1.0), scale=(8, 6, 4),
        density=0.003, color=(0.85, 0.85, 0.90, 1.0),
        name="PedestalAtmo",
    )

    cam = create_camera(bpy, scene, location=(0, -9, 2.0), rotation=(1.38, 0, 0))
    animate_dolly(cam, (0, -10, 2.0), (0, -7.2, 2.0), scene.frame_end)
    animate_orbit_y(hero, scene.frame_end)

    return {"camera": cam}

