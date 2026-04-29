from __future__ import annotations


def add_world_fog(scene, density=0.02, anisotropy=0.2):
    world = scene.world
    if world is None:
        return

    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()

    bg = nodes.new(type='ShaderNodeBackground')
    bg.inputs[0].default_value = (0.01, 0.015, 0.03, 1.0)
    bg.inputs[1].default_value = 0.1

    volume = nodes.new(type='ShaderNodeVolumeScatter')
    volume.inputs["Color"].default_value = (0.3, 0.4, 0.6, 1.0)
    volume.inputs["Density"].default_value = density
    volume.inputs["Anisotropy"].default_value = anisotropy

    out = nodes.new(type='ShaderNodeOutputWorld')

    links.new(bg.outputs[0], out.inputs["Surface"])
    links.new(volume.outputs[0], out.inputs["Volume"])
