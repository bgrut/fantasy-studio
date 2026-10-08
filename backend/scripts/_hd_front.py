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
MID = np.median(allP, axis=0); zmid = float(MID[2])
Hm = float(np.percentile(allP[:, 2], 99.7) - np.percentile(allP[:, 2], 0.3))

# THE CAMERAS (2026-10-08). A person's photo is front-on: one camera on the
# front (Blender +Y, the way every baked biped faces). An animal's photo is a
# side view: two cameras, one on each flank (+X and -X), the far one seeing the
# photo mirrored; which way the animal faces in the photo is searched (a
# generated photo puts the head on either side).
SIDE = "--side" in argv
def cams(mir):
    if SIDE:
        return [(np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0]), mir),
                (np.array([0.0, -1.0, 0.0]), np.array([-1.0, 0.0, 0.0]), -mir)]
    v = int(argv[argv.index("--view") + 1]) if "--view" in argv else 1
    return [(np.array([-float(v), 0.0, 0.0]), np.array([0.0, float(v), 0.0]), mir)]


HEADFIX = None


def project(Pt, cam, k, cx, cy):
    """Texel positions -> reference pixels for one camera (right R, toward-camera D, mirror),
    k pixels to the metre, the body's middle at (cx, cy); and each texel's depth toward it.
    Above the neck the head's own fit (HEADFIX) takes over, eased in across the neck."""
    Rv, Dv, mir = cam
    a = ((Pt - MID) @ Rv) * mir
    b = Pt[:, 2] - zmid
    px, py = cx + a * k, cy - b * k
    if HEADFIX is not None:
        a0, b0, s, dx, dy, zlo, zhi = HEADFIX
        t = np.clip((Pt[:, 2] - zlo) / (zhi - zlo), 0, 1); t = t * t * (3 - 2 * t)
        hx = cx + dx + (a0 + (a - a0) * s) * k; hy = cy + dy - (b0 + (b - b0) * s) * k
        px = px + (hx - px) * t; py = py + (hy - py) * t
    return px, py, Pt @ Dv


def weights(Nt, cam, px, py, depth, zbuf, zscale):
    facing = Nt @ cam[1]
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


# the search runs on surfaces squarely facing the first camera, a cheap
# stand-in for the depth test
small = rng.choice(len(allP), size=min(len(allP), 30000), replace=False)
Ps, Ns, Cs = allP[small], allN[small], allC[small]


def agreement(cam, k, cx, cy):
    m = Ns @ cam[1] > 0.6
    px, py, _ = project(Ps[m], cam, k, cx, cy)
    inb = (px > 1) & (px < RW - 2) & (py > 1) & (py < RH - 2)
    if inb.sum() < 300:
        return -1.0
    ph = sample(R, px[inb], py[inb])
    c = Cs[m][inb]
    return float(np.mean([np.corrcoef(ph[:, i], c[:, i])[0, 1] for i in range(3)]))


# AN ANIMAL IS ALIGNED BY ITS OUTLINE (2026-10-08): a generated elephant came
# out brown from a grey photo, and colour agreement found a wrong fit. Side-on,
# the outline (legs, trunk, ears, tail) is the strong signal: the body's
# projected silhouette is matched to the photo's figure, judged against each
# row's own backdrop with a threshold set by the backdrop's grain.
if SIDE:
    _E = max(24, RW // 16)
    _bg = np.median(np.concatenate([R[:, :_E], R[:, -_E:]], axis=1), axis=1)
    _d = np.linalg.norm(R - _bg[:, None, :], axis=2)
    _noise = float(np.median(np.abs(_d[:, :_E])) + 3 * np.std(_d[:, :_E]))
    _m = _d > max(0.08, _noise)
    QS = 4
    PM = _m[:RH // QS * QS, :RW // QS * QS].reshape(RH // QS, QS, RW // QS, QS).mean(axis=(1, 3)) > 0.5
    _sil = allP[rng.choice(len(allP), size=min(len(allP), 60000), replace=False)]

    def agreement(cam, k, cx, cy):
        px, py, _ = project(_sil, cam, k, cx, cy)
        ix = (px / QS).astype(int); iy = (py / QS).astype(int)
        ok = (ix >= 0) & (ix < PM.shape[1]) & (iy >= 0) & (iy < PM.shape[0])
        if ok.sum() < len(ix) * 0.9:
            return -1.0
        M = np.zeros(PM.shape, bool); M[iy[ok], ix[ok]] = True
        M = M | np.roll(M, 1, 0) | np.roll(M, 1, 1) | np.roll(M, -1, 0) | np.roll(M, -1, 1)
        inter = float((M & PM).sum()); uni = float((M | PM).sum())
        return inter / max(uni, 1.0)

# a person's photo is never mirrored; an animal's head may face either way
MIRS = (1, -1) if SIDE else (1,)
best = (-2.0, None)
for mir in MIRS:
    cam0 = cams(mir)[0]
    for f in np.arange(0.40 if SIDE else 0.62, 0.99, 0.04):
        k = f * RH / Hm
        for cx in np.arange(0.40, 0.61, 0.025) * RW:
            for cy in np.arange(0.38, 0.63, 0.025) * RH:
                sc = agreement(cam0, k, cx, cy)
                if sc > best[0]:
                    best = (sc, (mir, k, cx, cy))
mir, k, cx, cy = best[1]
for it in range(3):                       # refine: halve the steps around the best
    dk, dc = 0.02 * RH / Hm / (it + 1), 0.0125 * RW / (it + 1)
    for k2 in (k - dk, k, k + dk):
        for cx2 in (cx - dc, cx, cx + dc):
            for cy2 in (cy - dc, cy, cy + dc):
                sc = agreement(cams(mir)[0], k2, cx2, cy2)
                if sc > best[0]:
                    best = (sc, (mir, k2, cx2, cy2))
    mir, k, cx, cy = best[1]
score = best[0]
FRONT_OFF = False
if score < (0.5 if SIDE else 0.42):
    if "--extra" not in argv:
        print("HDFAIL the photo does not agree with the body (r=%.2f)" % score); sys.exit(5)
    # (2026-10-08) the repainted views still stand: the photo is left out, not the job
    FRONT_OFF = True
    print("HDNOTE the photo does not agree with the body (r=%.2f): views only" % score)
CAMS = cams(mir)
# THE HEAD HAS ITS OWN FIT (2026-10-08). One scale and centre for the whole
# body leaves the head a few pixels off wherever the generated head's
# proportions differ from the photo's: a woman's hair fell across her cheek
# and the dark edge of her jaw lay on her neck. The front-facing head texels
# search their own scale and offset about the head's middle, by the same
# colour agreement, and the fit eases in over the neck. Kept only if it
# agrees clearly better than the body's fit did.
if not SIDE and not FRONT_OFF:
    try:
        ztop = float(np.percentile(allP[:, 2], 99.7))
        hm = (allP[:, 2] > ztop - 0.125 * Hm) & (allN @ CAMS[0][1] > 0.45)
        hidx = np.where(hm)[0]
        if len(hidx) > 400:
            hidx = rng.choice(hidx, size=min(len(hidx), 20000), replace=False)
            Ph, Ch = allP[hidx], allC[hidx]
            Rv0 = CAMS[0][0]
            ah = ((Ph - MID) @ Rv0) * CAMS[0][2]; bh = Ph[:, 2] - zmid
            a0, b0 = float(np.median(ah)), float(np.median(bh))

            def hscore(s, dx, dy):
                px = cx + dx + (a0 + (ah - a0) * s) * k; py = cy + dy - (b0 + (bh - b0) * s) * k
                ok = (px > 1) & (px < RW - 2) & (py > 1) & (py < RH - 2)
                if ok.sum() < 300:
                    return -1.0
                ph = sample(R, px[ok], py[ok]); c = Ch[ok]
                return float(np.mean([np.corrcoef(ph[:, i], c[:, i])[0, 1] for i in range(3)]))

            base_h = hscore(1.0, 0.0, 0.0)
            hpx = 0.125 * Hm * k                      # the head's height in photo pixels
            hb = (base_h, (1.0, 0.0, 0.0))
            for s in np.arange(0.86, 1.15, 0.04):
                for dx in np.arange(-0.12, 0.121, 0.02) * hpx:
                    for dy in np.arange(-0.12, 0.121, 0.02) * hpx:
                        sc = hscore(s, dx, dy)
                        if sc > hb[0]:
                            hb = (sc, (s, dx, dy))
            s, dx, dy = hb[1]
            for it in range(2):
                ds, dd = 0.02 / (it + 1), 0.01 * hpx / (it + 1)
                for s2 in (s - ds, s, s + ds):
                    for dx2 in (dx - dd, dx, dx + dd):
                        for dy2 in (dy - dd, dy, dy + dd):
                            sc = hscore(s2, dx2, dy2)
                            if sc > hb[0]:
                                hb = (sc, (s2, dx2, dy2))
                s, dx, dy = hb[1]
            if hb[0] > base_h + 0.02:
                HEADFIX = (a0, b0, s, dx, dy, ztop - 0.17 * Hm, ztop - 0.125 * Hm)
                print("HDHEAD r %.3f -> %.3f scale %.3f shift %.1f %.1f px" % (base_h, hb[0], s, dx, dy))
            else:
                print("HDHEAD kept the body's fit (r %.3f, best %.3f)" % (base_h, hb[0]))
    except Exception as _hx:
        print("HDHEAD skipped (%s)" % type(_hx).__name__)
view = 1 if not SIDE else 0
zs = 1.0                                  # the depth test at the photo's own resolution: at half, the line under the jaw stepped (2026-10-08)
ZB = []
for cam in CAMS:
    pxA, pyA, dA = project(allP, cam, k, cx, cy)
    ZB.append(zbuffer(pxA, pyA, dA, zs))
if "--debug" in argv:
    _dbg = argv[argv.index("--debug") + 1]
    pxA, pyA, _ = project(allP, CAMS[0], k, cx, cy)
    np.savez_compressed(_dbg, px=pxA[sub], py=pyA[sub], z=allP[sub][:, 2], fy=allN[sub] @ CAMS[0][1], box=np.array([k, cx, cy, Hm]))

# THE FACE AT ITS OWN SIZE (2026-10-08): tools/hd_views.py passes the photo's
# head, cropped and repainted at 1024 as a close-up, with its box in the
# photo's pixels (--headhr <png>|x0|y0|x1|y1). Wherever the front camera lands
# inside that box the close-up is sampled instead, fading to the photo over
# the box's outer eighth, so a face gets twenty times the pixels it had.
HEAD = None
if "--headhr" in argv:
    try:
        _hp, _x0, _y0, _x1, _y1 = argv[argv.index("--headhr") + 1].split("|")
        _hi = bpy.data.images.load(_hp); _HW, _HH = _hi.size
        _HA = np.empty(_HW * _HH * 4, dtype=np.float32); _hi.pixels.foreach_get(_HA)
        _HA = _HA.reshape(_HH, _HW, 4)[::-1, :, :3]
        if _hi.colorspace_settings.name != "sRGB":
            _HA = np.clip(to_s(_HA), 0, 1)
        HEAD = (_HA, float(_x0), float(_y0), float(_x1), float(_y1))
    except Exception as _he:
        print("HDNOTE head close-up unreadable (%s)" % type(_he).__name__)


def sample_photo(px, py):
    base_ = sample(R, px, py)
    if HEAD is None:
        return base_
    A_, x0_, y0_, x1_, y1_ = HEAD
    u_ = (px - x0_) / (x1_ - x0_); v_ = (py - y0_) / (y1_ - y0_)
    edge_ = np.minimum(np.minimum(u_, 1 - u_), np.minimum(v_, 1 - v_))
    f_ = np.clip(edge_ / 0.125, 0, 1); f_ = f_ * f_ * (3 - 2 * f_)
    if not (f_ > 0).any():
        return base_
    hi_ = sample(A_, np.clip(u_, 0, 1) * (A_.shape[1] - 1), np.clip(v_, 0, 1) * (A_.shape[0] - 1))
    return base_ * (1 - f_[:, None]) + hi_ * f_[:, None]


# EXTRA VIEWS (2026-10-08, the user: "improve character skinning too"). The
# front came from the reference photo; the back and the flanks, which the
# chase camera sees most, were still the soft coat. tools/hd_views.py renders
# the coated body straight-on from those sides (orthographic, the camera
# written to a JSON), repaints each render photographically with SDXL
# img2img, and passes them here as --extra <png>|<json>|<view>. The camera is
# known, so they project exactly; where the repaint's broad colour agrees with
# the coat it is laid on whole, and where it does not (the repaint moved a
# hood's edge) only its fine detail is, at the coat's own colour.
import json as _json
EXTRA = []
for i_a, a_ in enumerate(argv):
    if a_ == "--extra" and i_a + 1 < len(argv):
        png, js, vname = argv[i_a + 1].split("|")          # <png>|<json>|<view>
        meta = _json.load(open(js))
        vimg = bpy.data.images.load(png)
        VW, VH = vimg.size
        A = np.empty(VW * VH * 4, dtype=np.float32); vimg.pixels.foreach_get(A)
        A = A.reshape(VH, VW, 4)[::-1, :, :3]
        if vimg.colorspace_settings.name != "sRGB":
            A = np.clip(to_s(A), 0, 1)
        vv = meta["views"][vname]
        cam_e = {"img": A, "low": None, "dir": np.array(vv["dir"]), "right": np.array(vv["right"]), "up": np.array(vv["up"]),
                 "centre": np.array(meta["centre"]), "ortho": float(meta["ortho"]), "W": VW, "H": VH}
        # its broad colour: a box blur a few percent of the frame wide
        rr_ = max(2, VW // 96)
        def _box(img, r):
            out = img
            for ax in (0, 1):
                c_ = np.cumsum(np.pad(out, [(r + 1, r) if i == ax else (0, 0) for i in range(out.ndim)], mode="edge"), axis=ax)
                out = (np.take(c_, np.arange(2 * r + 1, c_.shape[ax]), axis=ax) - np.take(c_, np.arange(0, c_.shape[ax] - 2 * r - 1), axis=ax)) / (2 * r + 1)
            return out
        cam_e["low"] = _box(_box(A, rr_), rr_)
        EXTRA.append(cam_e)


def project_extra(Pt, e):
    q = Pt - e["centre"]
    px = (q @ e["right"]) / e["ortho"] * e["W"] + e["W"] / 2
    py = e["H"] / 2 - (q @ e["up"]) / e["ortho"] * e["H"]
    return px, py, Pt @ e["dir"]


for e in EXTRA:
    _px, _py, _d = project_extra(allP, e)
    H_, W_ = e["H"] // 2 + 1, e["W"] // 2 + 1
    zz_ = np.full((H_, W_), -1e9, np.float32)
    np.maximum.at(zz_, (np.clip((_py / 2).astype(int), 0, H_ - 1), np.clip((_px / 2).astype(int), 0, W_ - 1)), _d)
    z2 = zz_.copy()
    for dy_ in (-1, 0, 1):
        for dx_ in (-1, 0, 1):
            z2 = np.maximum(z2, np.roll(zz_, (dy_, dx_), (0, 1)))
    e["zb"] = z2

for tob, nodes, C, P, N in bakes:
    mc = C[..., 3] > 0.5
    Pt, Nt = P[mc][:, :3], N[mc][:, :3]
    cs = to_s(C[..., :3])
    base = cs[mc]
    # each camera paints what faces it; where two reach the same texel (a flank's
    # edge) their photos blend by how squarely each sees it
    wsum = np.zeros(len(Pt), np.float32); acc = np.zeros((len(Pt), 3), np.float32)
    for cam, zb in zip(CAMS, ZB):
        px, py, depth = project(Pt, cam, k, cx, cy)
        wc = weights(Nt, cam, px, py, depth, zb, zs)
        acc += sample_photo(px, py) * wc[:, None]; wsum += wc
    photo = acc / np.maximum(wsum, 1e-6)[:, None]
    w = np.zeros_like(wsum) if FRONT_OFF else np.clip(wsum, 0, 1)
    # the photo's own studio light differs a little from the coat: carry its
    # detail at the coat's tone where the two disagree broadly
    out_m = base * (1 - w[:, None]) + photo * w[:, None]
    for e in EXTRA:
        px, py, depth = project_extra(Pt, e)
        facing = Nt @ e["dir"]
        we = np.clip((facing - 0.2) / 0.45, 0, 1)
        we *= depth >= e["zb"][np.clip((py / 2).astype(int), 0, e["zb"].shape[0] - 1), np.clip((px / 2).astype(int), 0, e["zb"].shape[1] - 1)] - 0.012 * size
        we *= (px > 1) & (px < e["W"] - 2) & (py > 1) & (py < e["H"] - 2)
        we *= (1 - w)                                   # the true photo keeps what it covers
        rep = sample(e["img"], px, py); low = sample(e["low"], px, py)
        agree = np.exp(-np.sum((low - out_m) ** 2, axis=1) / 0.03)[:, None]
        detail = np.clip(rep - low, -0.25, 0.25)
        paint = out_m + agree * (rep - out_m) + (1 - agree) * detail
        out_m = out_m * (1 - we[:, None]) + np.clip(paint, 0, 1) * we[:, None]
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
print("HDF %d %d %.3f %s %.1f" % (len(bakes), RES, score, ("side%+d" % mir) if SIDE else ("views" if FRONT_OFF else "front"), time.time() - t0))
