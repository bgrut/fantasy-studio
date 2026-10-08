"""A sharp face and front from the reference photo (2026-10-08).

The clean coat (_clean_coat.py) carries a character's colour on its
vertices: smooth and consistent, but a vertex is a few centimetres across,
so faces, seams, buckles and gloves went soft, and close-ups read blurry
(the user: "some close ups on those characters were blurry"). _hd_skin.py
tried the generator's own atlas for the fine detail and found confetti.

Every generated character was made FROM a clean studio photograph, its
reference (renders/_actor_cache/<key>_ref.png), front-on and in the very pose
of the mesh's rest shape. That photo is the sharp source:

1. The coated rig gets one clean UV layout (smart project) and three bakes on
   it: the coat as shipped, and each texel's rest-pose position and normal.
2. The photo is projected from the front onto every texel that faces it and
   that a front camera would actually see (a depth buffer splatted from the
   texels themselves keeps an arm's photo off the chest behind it). Its
   weight eases from full where the surface faces the camera to nothing at
   the sides, where the coat carries on alone.
3. The alignment is measured, not assumed. The coat was itself made from this
   photo, so the projection that agrees best with it is the right one: which
   way the body faces, whether the photo is mirrored, and a small scale and
   offset are searched by that agreement.
4. The character ships the sheet as its base colour (JPEG) on the new UVs,
   with no vertex colour, and keeps _MR, the armature, the weights and every
   animation.

Usage: blender --background --python _hd_front.py -- coated.glb ref.png out.glb [--res 2048]
Prints HDF <meshes> <res> <agreement> <front> <secs> on success, HDFAIL otherwise.
"""
import math
import sys
import time

import bpy
import numpy as np

t0 = time.time()
argv = sys.argv[sys.argv.index("--") + 1:]
coated, refpng, dst = argv[0], argv[1], argv[2]
RES = int(argv[argv.index("--res") + 1]) if "--res" in argv else 2048

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.engine = "CYCLES"
scn.cycles.samples = 1
scn.cycles.device = "CPU"

before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=coated)
objs = [o for o in bpy.data.objects if o not in before]
for o in objs:
    if o.type == "ARMATURE":
        o.data.pose_position = "REST"
targets = [o for o in objs if o.type == "MESH"]
if not targets:
    print("HDFAIL no meshes"); sys.exit(2)
bpy.context.view_layer.update()


def select_only(sel, active):
    bpy.ops.object.select_all(action="DESELECT")
    for o in sel:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active


def new_image(name, res, flt=True):
    im = bpy.data.images.new(name, res, res, alpha=True, float_buffer=flt)
    im.generated_color = (0, 0, 0, 0)
    return im


def pixels(im):
    a = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    return a.reshape(im.size[1], im.size[0], 4)


def dilate(img, mask, n=12):
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


to_s = lambda x: np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.clip(x, 0, None), 1 / 2.4) - 0.055)

# the reference: sRGB pixels, top row first, and where the figure stands on its plain backdrop
ref_img = bpy.data.images.load(refpng)
RW, RH = ref_img.size
R = np.empty(RW * RH * 4, dtype=np.float32); ref_img.pixels.foreach_get(R)
R = R.reshape(RH, RW, 4)[::-1, :, :3]                       # Blender stores bottom row first
R = np.clip(to_s(R), 0, 1) if ref_img.colorspace_settings.name != "sRGB" else R
# the studio backdrop is a gradient (a lit wall falling to a paler floor), so the
# background is judged row by row from that row's own left and right margins
EDGE = max(24, RW // 16)
bg_row = np.median(np.concatenate([R[:, :EDGE], R[:, -EDGE:]], axis=1), axis=1)      # (H, 3)
fig = np.linalg.norm(R - bg_row[:, None, :], axis=2) > 0.11
# a floor shadow is darker but not a figure: keep only pixels in rows/cols that hold enough figure
fig &= (fig.sum(1, keepdims=True) > 3) & (fig.sum(0, keepdims=True) > 3)
rows, cols = np.where(fig.any(1))[0], np.where(fig.any(0))[0]
if len(rows) < 10 or len(cols) < 10:
    print("HDFAIL no figure in the reference"); sys.exit(3)
ys, xs = np.where(fig)
by0, by1 = np.percentile(ys, 0.3), np.percentile(ys, 99.7)
bx0, bx1 = np.percentile(xs, 0.3), np.percentile(xs, 99.7)


def sample(img, px, py):
    """Bilinear sample of img (H, W, C) at float pixel coords."""
    H, W = img.shape[:2]
    px = np.clip(px, 0, W - 1.001); py = np.clip(py, 0, H - 1.001)
    x0 = np.floor(px).astype(int); y0 = np.floor(py).astype(int); fx = (px - x0)[:, None]; fy = (py - y0)[:, None]
    a = img[y0, x0]; b = img[y0, x0 + 1]; c = img[y0 + 1, x0]; d = img[y0 + 1, x0 + 1]
    if a.ndim == 1:
        a, b, c, d = a[:, None], b[:, None], c[:, None], d[:, None]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


bakes = []
for ti, tob in enumerate(targets):
    me = tob.data
    for uvl in list(me.uv_layers):
        me.uv_layers.remove(uvl)
    uv = me.uv_layers.new(name="HD")
    me.uv_layers.active = uv
    select_only([tob], tob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0025, area_weight=0.0, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    if not me.materials:
        print("HDSKIP no material on", tob.name); continue
    nodes = []
    for mat in me.materials:
        mat.use_nodes = True
        tn = mat.node_tree.nodes.new("ShaderNodeTexImage"); mat.node_tree.nodes.active = tn; nodes.append((mat, tn))

    def bake_into(name, kind):
        im = new_image("%s_%d" % (name, ti), RES)
        for mat, tn in nodes:
            tn.image = im
        select_only([tob], tob)
        scn.render.bake.use_selected_to_active = False
        scn.render.bake.margin = 0
        if kind == "coat":
            bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_clear=True)
        else:
            # position / normal: an emission of the geometry, read back as floats
            saved = []
            for mat, tn in nodes:
                nt = mat.node_tree
                out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
                old = [l.from_socket for l in out.inputs["Surface"].links]
                geo = nt.nodes.new("ShaderNodeNewGeometry"); em = nt.nodes.new("ShaderNodeEmission")
                # an emission may not go negative: positions and normals are carried as v * k + 0.5
                ma = nt.nodes.new("ShaderNodeVectorMath"); ma.operation = "MULTIPLY_ADD"
                k = 0.05 if kind == "pos" else 0.5
                ma.inputs[1].default_value = (k, k, k); ma.inputs[2].default_value = (0.5, 0.5, 0.5)
                nt.links.new(geo.outputs["Position" if kind == "pos" else "Normal"], ma.inputs[0])
                nt.links.new(ma.outputs[0], em.inputs["Color"])
                nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
                saved.append((nt, out, old, geo, em, ma))
            bpy.ops.object.bake(type="EMIT", use_clear=True)
            for nt, out, old, geo, em, ma in saved:
                nt.nodes.remove(geo); nt.nodes.remove(em); nt.nodes.remove(ma)
                for s in old:
                    nt.links.new(s, out.inputs["Surface"])
            px = pixels(im)
            px[..., :3] = (px[..., :3] - 0.5) / (0.05 if kind == "pos" else 0.5)
            return px
        return pixels(im)

    C = bake_into("coat", "coat")
    P = bake_into("pos", "pos")
    N = bake_into("nrm", "nrm")
    bakes.append((tob, nodes, C, P, N))

if not bakes:
    print("HDFAIL nothing baked"); sys.exit(4)

# every texel of every mesh, together: the projection is one camera over the whole body
allP = np.concatenate([b[3][b[2][..., 3] > 0.5][:, :3] for b in bakes])
allN = np.concatenate([b[4][b[2][..., 3] > 0.5][:, :3] for b in bakes])
allC = np.concatenate([to_s(b[2][b[2][..., 3] > 0.5][:, :3]) for b in bakes])
size = float(np.linalg.norm(allP.max(0) - allP.min(0)))
lum = lambda c: c @ np.array([0.299, 0.587, 0.114])
rng = np.random.default_rng(7)
sub = rng.choice(len(allP), size=min(len(allP), 160000), replace=False)


# the body's own frame: its height and its middle, in metres
zmid = float(np.percentile(allP[:, 2], 50)); xmid = float(np.percentile(allP[:, 0], 50))
Hm = float(np.percentile(allP[:, 2], 99.7) - np.percentile(allP[:, 2], 0.3))


def project(Pt, view, mirror, k, cx, cy):
    """Texel positions -> reference pixels: a front camera on `view` (+1 looks from +Y, -1 from -Y),
    `mirror` flips left and right, k pixels to the metre, the body's middle at (cx, cy)."""
    a = (Pt[:, 0] - xmid) * (-view * mirror)
    b = Pt[:, 2] - zmid
    return cx + a * k, cy - b * k, Pt[:, 1] * view


def weights(Nt, view, px, py, depth, zbuf, zscale):
    facing = Nt[:, 1] * view
    w = np.clip((facing - 0.25) / 0.45, 0, 1)
    ix = np.clip((px * zscale).astype(int), 0, zbuf.shape[1] - 1); iy = np.clip((py * zscale).astype(int), 0, zbuf.shape[0] - 1)
    vis = depth >= zbuf[iy, ix] - 0.012 * size
    inb = (px > 1) & (px < RW - 2) & (py > 1) & (py < RH - 2)
    return w * vis * inb


def zbuffer(px, py, depth, zscale):
    H, W = int(RH * zscale) + 1, int(RW * zscale) + 1
    z = np.full((H, W), -1e9, np.float32)
    ix = np.clip((px * zscale).astype(int), 0, W - 1); iy = np.clip((py * zscale).astype(int), 0, H - 1)
    np.maximum.at(z, (iy, ix), depth)
    zz = z.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            zz = np.maximum(zz, np.roll(z, (dy, dx), (0, 1)))
    return zz


# the search runs on surfaces squarely facing each candidate camera (those are
# visible in a T- or A-pose almost everywhere), a cheap stand-in for the depth test
small = rng.choice(len(allP), size=min(len(allP), 30000), replace=False)
Ps, Ns, Cs = allP[small], allN[small], allC[small]
Cl = lum(Cs)


def agreement(view, mirror, k, cx, cy):
    m = Ns[:, 1] * view > 0.6
    px, py, _ = project(Ps[m], view, mirror, k, cx, cy)
    inb = (px > 1) & (px < RW - 2) & (py > 1) & (py < RH - 2)
    if inb.sum() < 300:
        return -1.0
    ph = sample(R, px[inb], py[inb])
    # colour agreement: the three channels, each correlated
    c = Cs[m][inb]
    return float(np.mean([np.corrcoef(ph[:, i], c[:, i])[0, 1] for i in range(3)]))


# Every baked biped stands the same way round (its front on glTF -Z, Blender +Y:
# the facing probe measures it in every game), and a photograph is never
# mirrored. Leaving both free let a symmetric suit agree nearly as well with
# the photo laid on its back; they are fixed, and only scale and place are searched.
VIEWS = [(int(argv[argv.index("--view") + 1]), 1)] if "--view" in argv else [(1, 1)]
best = (-2.0, None)
for view, mirror in VIEWS:
    if True:
        for f in np.arange(0.62, 0.99, 0.04):
            k = f * RH / Hm
            for cx in np.arange(0.40, 0.61, 0.025) * RW:
                for cy in np.arange(0.38, 0.63, 0.025) * RH:
                    sc = agreement(view, mirror, k, cx, cy)
                    if sc > best[0]:
                        best = (sc, (view, mirror, k, cx, cy))
view, mirror, k, cx, cy = best[1]
for it in range(3):                       # refine: halve the steps around the best
    dk, dc = 0.02 * RH / Hm / (it + 1), 0.0125 * RW / (it + 1)
    for k2 in (k - dk, k, k + dk):
        for cx2 in (cx - dc, cx, cx + dc):
            for cy2 in (cy - dc, cy, cy + dc):
                sc = agreement(view, mirror, k2, cx2, cy2)
                if sc > best[0]:
                    best = (sc, (view, mirror, k2, cx2, cy2))
    view, mirror, k, cx, cy = best[1]
score = best[0]
if score < 0.42:
    print("HDFAIL the photo does not agree with the body (r=%.2f)" % score); sys.exit(5)

pxA, pyA, dA = project(allP, view, mirror, k, cx, cy)
if "--debug" in argv:
    _dbg = argv[argv.index("--debug") + 1]
    np.savez_compressed(_dbg, px=pxA[sub], py=pyA[sub], z=allP[sub][:, 2], fy=allN[sub][:, 1] * view, box=np.array([k, cx, cy, Hm]))
zs = 0.5
zbA = zbuffer(pxA, pyA, dA, zs)

for tob, nodes, C, P, N in bakes:
    mc = C[..., 3] > 0.5
    Pt, Nt = P[mc][:, :3], N[mc][:, :3]
    px, py, depth = project(Pt, view, mirror, k, cx, cy)
    w = weights(Nt, view, px, py, depth, zbA, zs)
    cs = to_s(C[..., :3])
    photo = sample(R, px, py)
    base = cs[mc]
    # the photo's own studio light differs a little from the coat: carry its
    # detail at the coat's tone where the two disagree broadly
    out_m = base * (1 - w[:, None]) + photo * w[:, None]
    out = cs.copy(); out[mc] = out_m
    out = dilate(np.clip(out, 0, 1), mc, 16)
    rgba = np.concatenate([out, np.ones(out.shape[:2] + (1,), np.float32)], axis=2)
    im_out = bpy.data.images.new("%s_skin" % tob.name, RES, RES, alpha=False)
    im_out.colorspace_settings.name = "sRGB"
    im_out.pixels.foreach_set(rgba.astype(np.float32).ravel())
    im_out.pack()
    for mat, tn in nodes:
        tn.image = im_out
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue
        for l in list(bsdf.inputs["Base Color"].links):
            nt.links.remove(l)
        nt.links.new(tn.outputs["Color"], bsdf.inputs["Base Color"])
    for ca in list(tob.data.color_attributes):
        tob.data.color_attributes.remove(ca)
    print("MESH %s photo %.2f of the surface" % (tob.name, float((w > 0.5).mean())))

for o in objs:
    if o.type == "ARMATURE":
        o.data.pose_position = "POSE"
bpy.ops.export_scene.gltf(filepath=dst, export_yup=True, export_vertex_color="NONE", export_attributes=True,
                          export_image_format="JPEG", export_jpeg_quality=92)
print("HDF %d %d %.3f %s %.1f" % (len(bakes), RES, score, "%+d%+d" % (view, mirror), time.time() - t0))
