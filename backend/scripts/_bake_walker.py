"""One-time WALKER bake (2026-07-30): man_anim.glb is 49MB (70k tris, 4K
textures) — far too heavy to clone 8x as city pedestrians. This bakes a
lightweight ambient-walker variant: decimate skinned meshes (weights
survive the modifier), downscale every image to 512px, strip normal maps,
keep the animation set.

Usage: blender --background --python _bake_walker.py -- in.glb out.glb
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)

# decimate every mesh to ~22% (70k -> ~15k tris total) — collapse keeps
# vertex groups so the rig still drives it
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    mod = o.modifiers.new("dec", "DECIMATE")
    mod.ratio = 0.22
    # applying modifiers on multi-user meshes fails silently — make single
    o.data = o.data.copy()
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier="dec")

# 512px textures + drop normal maps (ambient walkers are never inspected)
for img in list(bpy.data.images):
    n = (img.name or "").lower()
    if "normal" in n:
        img.user_clear()
        continue
    if img.size[0] > 512:
        img.scale(512, 512)

bpy.ops.export_scene.gltf(filepath=dst, export_yup=True,
                          export_image_format="JPEG", export_jpeg_quality=70)
print("WALKER-BAKED", dst)
