from __future__ import annotations


def create_camera(bpy, scene, location=(0, -10, 5), rotation=(1.2, 0, 0)):
    bpy.ops.object.camera_add(location=location, rotation=rotation)
    cam = bpy.context.object
    scene.camera = cam
    return cam


def animate_dolly(cam, start_loc, end_loc, frame_end: int):
    cam.location = start_loc
    cam.keyframe_insert(data_path="location", frame=1)
    cam.location = end_loc
    cam.keyframe_insert(data_path="location", frame=frame_end)


def animate_orbit_y(obj, frame_end: int):
    obj.rotation_euler = (0, 0, 0)
    obj.keyframe_insert(data_path="rotation_euler", frame=1)
    obj.rotation_euler = (0, 0, 6.28318)
    obj.keyframe_insert(data_path="rotation_euler", frame=frame_end)
