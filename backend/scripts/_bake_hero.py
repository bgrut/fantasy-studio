"""HERO bake (2026-08-07): re-encode a character's embedded textures as JPEG.

Characters whose GLB embeds PNG render UNTEXTURED in the web runtime —
detective_anim and man_anim both do, and both showed up as white/grey
mannequins, while walker.glb (JPEG, from _bake_walker.py) was always fine.
Same loader, same rig, same clips; the only difference is the image codec.

Unlike the walker bake this keeps FULL geometry and 2048px maps, including
normal maps: the hero is the one character the camera gets close to. It is
only a codec change plus a size cap.

Usage: blender --background --python _bake_hero.py -- in.glb out.glb
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)

for img in list(bpy.data.images):
    if img.size[0] > 2048:
        img.scale(2048, 2048)

bpy.ops.export_scene.gltf(filepath=dst, export_yup=True,
                          export_image_format="JPEG", export_jpeg_quality=92)
print("HERO-BAKED", dst)
