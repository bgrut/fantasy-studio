def build_product_pedestal(bpy, manifest: dict, scene):
    # Floor
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -1.5))

    # Pedestal
    bpy.ops.mesh.primitive_cylinder_add(radius=2.2, depth=1.2, location=(0, 0, -0.9))
    pedestal = bpy.context.object

    # Hero object placeholder
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.4, location=(0, 0, 1.2))
    hero = bpy.context.object

    # Lights
    bpy.ops.object.light_add(type='AREA', location=(0, -4, 5))
    key = bpy.context.object
    key.data.energy = 5000

    bpy.ops.object.light_add(type='POINT', location=(3, 3, 4))
    rim = bpy.context.object
    rim.data.energy = 2000

    # Camera
    bpy.ops.object.camera_add(location=(0, -8, 1.5), rotation=(1.4, 0, 0))
    cam = bpy.context.object
    scene.camera = cam

    # Animation
    hero.rotation_euler = (0, 0, 0)
    hero.keyframe_insert(data_path="rotation_euler", frame=1)
    hero.rotation_euler = (0, 0, 6.28318)
    hero.keyframe_insert(data_path="rotation_euler", frame=scene.frame_end)

    cam.location = (0, -9, 1.7)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (0, -7, 1.7)
    cam.keyframe_insert(data_path="location", frame=scene.frame_end)

    return {"camera": cam}
