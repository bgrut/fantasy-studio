"""A sharp skin over the clean coat (2026-10-05).

The clean coat (_clean_coat.py) fixed the generated characters' mottling by
carrying colour on the vertices, smooth and consistent, and it is: but a
vertex is a few centimetres across, so a face, a buckle, a seam, the weave of
a jacket all went soft. The user: "character skinning ... right now it's very
blurry".

The blotches and the detail live at different scales. The atlas's confetti is
patches: neighbouring faces reading unrelated colours, a few texels to a few
centimetres wide. The detail that makes a character sharp is finer than
that, and the coat already holds everything broader. So:

1. The coated rig gets one clean UV layout (smart project) and a sheet.
2. Two bakes onto it: the coat itself (the smooth base, exactly as shipped)
   and the ORIGINAL model's colour (the pre-coat backup, the same body in the
   same rest pose), surface to surface.
3. The sheet is the coat plus only the finest band of the original: its
   difference from a few-texel blur, clamped, so an eye, a stitch or a strap
   edge comes back and a patch of confetti (wider than the band, and clamped
   where it is not) does not.
4. The model ships that sheet as its base colour (JPEG) on the new UVs, no
   vertex colour (it would multiply the sheet), and keeps the per-vertex
   metal-roughness attribute _MR, the armature, weights and animations.

Usage: blender --background --python _hd_skin.py -- coated.glb original.glb out.glb [--res 2048]
Prints HD <meshes> <res> <coverage> <secs> on success.
"""
import math
import sys
import time

import bpy
import numpy as np

t0 = time.time()
argv = sys.argv[sys.argv.index("--") + 1:]
coated, original, dst = argv[0], argv[1], argv[2]
RES = int(argv[argv.index("--res") + 1]) if "--res" in argv else 2048
FINE = float(argv[argv.index("--fine") + 1]) if "--fine" in argv else 3.0      # texels: the detail band's width
CLAMP = float(argv[argv.index("--clamp") + 1]) if "--clamp" in argv else 0.16  # how far detail may move a colour

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.engine = "CYCLES"
scn.cycles.samples = 1
scn.cycles.device = "CPU"


def imported(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


tgt_objs = imported(coated)
src_objs = imported(original)
for o in tgt_objs + src_objs:
    if o.type == "ARMATURE":
        o.data.pose_position = "REST"          # both bodies in their rest shape, where they coincide
targets = [o for o in tgt_objs if o.type == "MESH"]
sources = [o for o in src_objs if o.type == "MESH"]
if not targets or not sources:
    print("HDFAIL no meshes"); sys.exit(2)
bpy.context.view_layer.update()

# the body's size sets the ray reach
pts = np.concatenate([np.array([o.matrix_world @ v.co for v in o.data.vertices]) for o in targets])
size = float(np.linalg.norm(pts.max(0) - pts.min(0)))


def select_only(objs, active):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def new_image(name, res):
    im = bpy.data.images.new(name, res, res, alpha=True, float_buffer=True)
    im.generated_color = (0, 0, 0, 0)
    return im


def pixels(im):
    a = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    return a.reshape(im.size[1], im.size[0], 4)


def blur(img, mask, r):
    """Mask-normalised blur: three box passes of radius r (close to a gaussian)."""
    def box(a, rr):
        if rr < 1:
            return a
        out = a
        for ax in (0, 1):
            c = np.cumsum(np.pad(out, [(rr + 1, rr) if i == ax else (0, 0) for i in range(out.ndim)], mode="edge"), axis=ax)
            hi = np.take(c, np.arange(2 * rr + 1, c.shape[ax]), axis=ax)
            lo = np.take(c, np.arange(0, c.shape[ax] - 2 * rr - 1), axis=ax)
            out = (hi - lo) / (2 * rr + 1)
        return out
    rr = max(1, int(round(r)))
    num, den = img * mask[..., None], mask.astype(np.float32)
    for _ in range(3):
        num, den = box(num, rr), box(den, rr)
    return num / np.maximum(den[..., None], 1e-6)


def dilate(img, mask, n=12):
    """Spread island edges outward so mip levels never read the empty sheet."""
    img, m = img.copy(), mask.copy()
    for _ in range(n):
        acc = np.zeros_like(img); cnt = np.zeros(m.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sm = np.roll(m, (dy, dx), (0, 1)); si = np.roll(img, (dy, dx), (0, 1))
            acc += si * sm[..., None]; cnt += sm
        grow = (~m) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow][:, None]
        m = m | grow
    return img


cover_all = []
for ti, tob in enumerate(targets):
    me = tob.data
    # 1. one clean layout
    for uvl in list(me.uv_layers):
        me.uv_layers.remove(uvl)
    uv = me.uv_layers.new(name="HD")
    me.uv_layers.active = uv
    select_only([tob], tob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0025, area_weight=0.0, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode="OBJECT")

    mat = me.materials[0] if len(me.materials) else None
    if mat is None:
        print("HDSKIP no material on", tob.name); continue
    mat.use_nodes = True
    nt = mat.node_tree
    tex_node = nt.nodes.new("ShaderNodeTexImage")
    nt.nodes.active = tex_node

    # 2a. the coat, as shipped (the material reads the vertex colour)
    im_coat = new_image("coat_%d" % ti, RES)
    tex_node.image = im_coat
    select_only([tob], tob)
    scn.render.bake.use_selected_to_active = False
    scn.render.bake.margin = 0
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_clear=True)

    # 2b. the original's colour, surface to surface
    im_src = new_image("src_%d" % ti, RES)
    tex_node.image = im_src
    select_only(sources + [tob], tob)
    scn.render.bake.use_selected_to_active = True
    scn.render.bake.cage_extrusion = 0.012 * size
    scn.render.bake.max_ray_distance = 0.04 * size
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_clear=True)

    C = pixels(im_coat); S = pixels(im_src)
    mc = C[..., 3] > 0.5
    ms = (S[..., 3] > 0.5) & mc
    cov = float(ms.sum()) / max(1, int(mc.sum()))
    cover_all.append(cov)
    # work in a perceptual space: the eye judges detail in sRGB, not light
    to_s = lambda x: np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.clip(x, 0, None), 1 / 2.4) - 0.055)
    to_l = lambda x: np.where(x <= 0.04045, x / 12.92, np.power((np.clip(x, 0, None) + 0.055) / 1.055, 2.4))
    cs, ss = to_s(C[..., :3]), to_s(S[..., :3])
    # 3. the coat plus the original's finest band, clamped
    fine = ss - blur(ss, ms, FINE)
    fine = np.clip(fine, -CLAMP, CLAMP) * ms[..., None]
    out = np.clip(cs + fine, 0, 1)
    out = dilate(out, mc, 16)
    rgba = np.concatenate([out, np.ones(out.shape[:2] + (1,), np.float32)], axis=2)
    im_out = bpy.data.images.new("%s_skin" % tob.name, RES, RES, alpha=False)
    im_out.colorspace_settings.name = "sRGB"
    im_out.pixels.foreach_set(rgba.astype(np.float32).ravel())
    im_out.pack()

    # 4. the material: the sheet as base colour on the new layout; no vertex colour
    tex_node.image = im_out
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    for l in list(bsdf.inputs["Base Color"].links):
        nt.links.remove(l)
    nt.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
    for ca in list(me.color_attributes):
        me.color_attributes.remove(ca)
    print("MESH %s coverage %.3f" % (tob.name, cov))

# the original's meshes leave before export
for o in src_objs:
    bpy.data.objects.remove(o, do_unlink=True)
for o in tgt_objs:
    if o.type == "ARMATURE":
        o.data.pose_position = "POSE"
bpy.ops.export_scene.gltf(filepath=dst, export_yup=True, export_vertex_color="NONE", export_attributes=True,
                          export_image_format="JPEG", export_jpeg_quality=92)
print("HD %d %d %.3f %.1f" % (len(targets), RES, float(np.mean(cover_all)) if cover_all else 0.0, time.time() - t0))
