from __future__ import annotations


def setup_world_bg(scene, strength=0.03):
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    nodes = scene.world.node_tree.nodes
    bg = nodes.get("Background")
    if bg:
        bg.inputs[1].default_value = strength


def add_point_light(bpy, location=(0, 0, 5), energy=1000, color=(1, 1, 1)):
    bpy.ops.object.light_add(type='POINT', location=location)
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    return light


def add_area_light(bpy, location=(0, 0, 5), energy=1000, color=(1, 1, 1), size=5):
    bpy.ops.object.light_add(type='AREA', location=location)
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    light.data.shape = 'SQUARE'
    light.data.size = size
    return light
