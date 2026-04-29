def build_city_loop(bpy, manifest: dict, scene):
    # Ground
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, -1.5))
    ground = bpy.context.object

    # Buildings
    positions = [(-8, 8), (-4, 10), (0, 9), (4, 11), (8, 8), (-10, -4), (-5, -6), (5, -7), (10, -5)]
    heights = [8, 11, 10, 13, 9, 7, 9, 8, 7]
    for (x, y), h in zip(positions, heights):
        bpy.ops.mesh.primitive_cube_add(location=(x, y, h / 2 - 1.5))
        b = bpy.context.object
        b.scale = (1.6, 1.6, h / 2)

    # Hero neon tower
    bpy.ops.mesh.primitive_cube_add(location=(0, 14, 8))
    hero = bpy.context.object
    hero.scale = (2.2, 2.2, 8)

    # Lights
    for loc, color, energy in [
        ((-6, -4, 6), (0.1, 0.8, 1.0), 3000),
        ((6, -4, 5), (1.0, 0.1, 0.8), 3000),
        ((0, 10, 10), (0.4, 0.6, 1.0), 5000),
    ]:
        bpy.ops.object.light_add(type='POINT', location=loc)
        light = bpy.context.object
        light.data.energy = energy
        try:
            light.data.color = color
        except Exception:
            pass

    # Camera
    bpy.ops.object.camera_add(location=(0, -18, 6), rotation=(1.2, 0, 0))
    cam = bpy.context.object
    scene.camera = cam

    # Camera motion
    cam.location = (0, -20, 6)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (0, -12, 7)
    cam.keyframe_insert(data_path="location", frame=scene.frame_end)

    return {"camera": cam}
