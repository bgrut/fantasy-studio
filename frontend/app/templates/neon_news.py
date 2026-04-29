def build_neon_news(bpy, manifest: dict, scene):
    # Background plane
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 4, 0))
    bg = bpy.context.object
    bg.rotation_euler = (1.5708, 0, 0)

    # Floor
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -1.5))

    # Text
    bpy.ops.object.text_add(location=(-3.8, 0, 1.4), rotation=(1.5708, 0, 0))
    txt = bpy.context.object
    txt.data.body = f"{manifest.get('title_text', 'NEWS')}\n{manifest.get('subject', '')[:64]}"
    txt.data.extrude = 0.02
    txt.scale = (0.45, 0.45, 0.45)

    # Accent lights
    for loc, energy in [((-4, -2, 4), 2500), ((4, -2, 4), 2500)]:
        bpy.ops.object.light_add(type='POINT', location=loc)
        light = bpy.context.object
        light.data.energy = energy

    bpy.ops.object.camera_add(location=(0, -8, 0.5), rotation=(1.5708, 0, 0))
    cam = bpy.context.object
    scene.camera = cam

    cam.location = (0, -9, 0.5)
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = (0, -6.5, 0.5)
    cam.keyframe_insert(data_path="location", frame=scene.frame_end)

    txt.location = (-3.8, 0, 1.0)
    txt.keyframe_insert(data_path="location", frame=1)
    txt.location = (-3.8, 0, 1.4)
    txt.keyframe_insert(data_path="location", frame=scene.frame_end)

    return {"camera": cam}
