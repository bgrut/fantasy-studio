"""One clean coat for a generated character (2026-09-29).

The fox and the guide came out mottled, in colour and in light. A TRELLIS
character's atlas is about 1,300 islands, most a few texels across, so
neighbouring faces read colour from unrelated fragments of the sheet and the
gutters between them bleed in at every mip level; the normal map was embossed
from that same sheet, so every island edge is a bump; and an animal's body
carries a skin of loose flakes, hundreds of separate little patches, each its
own colour. Re-baking onto better UVs does not fix any of that: the colour is
patchy on the surface itself.

So the coat is rebuilt on the surface, where neighbours really are
neighbours, and carried by the vertices instead of a sheet:

1. Every face's colour is the median of seven points inside it, so a face is
   what most of it shows, not a speck.
2. Each vertex takes the colour of the faces around it, then the median of
   everything within a small radius of it in space (not along edges, so the
   loose flakes are outvoted by the body they sit on), twice, then a few
   gentle distance-weighted averages. Wide changes (a white chest, dark legs,
   a coat against trousers) survive; speckle and flakes do not.
3. The model ships that colour as vertex colour (glTF COLOR_0) and no texture:
   no islands, no gutters, no mip level that can reach a stranger's colour,
   and colour that can only change smoothly across the body.
4. The embossed normal map and the roughness map go with the sheet: the
   geometry's own smooth normals light it, with one roughness, evenly.

The armature, the weights and the animations are not touched.

Usage: blender --background --python _clean_coat.py -- in.glb out.glb
Prints COAT <vertices> <faces> <secs> on success.
"""
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

t0 = time.time()
argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv[0], argv[1]
MEASURE = "--measure" in argv            # print the blotchiness and stop
SPECK_MIN = 0.0                          # set from the library's own spread once measured

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]


def base_image(mat):
    if not mat or not mat.node_tree:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            link = n.inputs["Base Color"].links
            if link and link[0].from_node.type == "TEX_IMAGE":
                return link[0].from_node.image
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image is not None:
            return n.image
    return None


nv_all = nf_all = 0
for o in meshes:
    me = o.data
    # EVERY MATERIAL ITS OWN SHEET: a hero carries a head material beside the
    # body's, and sampling every face from the first sheet painted the faces
    # with a patch of hair. Each slot is read from its own image, or its flat
    # colour when it has none.
    sheets = []
    for mslot in me.materials:
        im = base_image(mslot)
        if im is not None and im.size[0] > 0:
            a_ = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
            im.pixels.foreach_get(a_)
            sheets.append(("img", a_.reshape(im.size[1], im.size[0], 4)[:, :, :3]))
        else:
            col = (0.6, 0.6, 0.6)
            try:
                bs = next(n for n in mslot.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                lc = np.array(bs.inputs["Base Color"].default_value[:3])
                col = tuple(np.where(lc <= 0.0031308, lc * 12.92, 1.055 * lc ** (1 / 2.4) - 0.055))
            except Exception:
                pass
            sheets.append(("flat", np.array(col)))
    if not any(k == "img" for k, _ in sheets) or not me.uv_layers:
        continue

    # ONE SURFACE, FACING OUT: glTF splits a mesh at every UV seam, so a body
    # arrives as hundreds of pieces with their own normals, and a generated
    # shell's winding is not to be trusted; the dark specks along seams were
    # shading. The coat carries no UVs, so the seams can close: duplicates are
    # welded (their weights are the same), faces are turned to face out, and
    # the imported custom normals give way to smooth ones from the geometry.
    bmw = bmesh.new(); bmw.from_mesh(me)
    _span0 = max((max(v.co[k] for v in bmw.verts) - min(v.co[k] for v in bmw.verts)) for k in range(3)) or 1.0
    bmesh.ops.remove_doubles(bmw, verts=bmw.verts[:], dist=_span0 * 2e-5)
    # (the winding is kept as generated: recalculating it on a layered,
    # non-manifold shell turned whole patches of a guide inside out)
    bmw.to_mesh(me); bmw.free()
    try:
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = o; o.select_set(True)
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except Exception:
        pass
    try:
        me.shade_smooth()
    except Exception:
        for pg in me.polygons:
            pg.use_smooth = True

    # read through bmesh: in Blender 5.1 a UV layer's foreach_get on an
    # imported mesh throws inside the attribute storage and takes Blender down
    bm0 = bmesh.new(); bm0.from_mesh(me)
    uvl0 = bm0.loops.layers.uv.active
    nf = len(bm0.faces); nv = len(bm0.verts)
    tri_uv = np.empty((nf, 3, 2)); lv_l = []; lt_l = []
    fmat = np.array([f.material_index for f in bm0.faces], dtype=np.int64)
    for fi, f in enumerate(bm0.faces):
        ls_ = f.loops
        k = len(ls_)
        for ci, li in enumerate((0, 1, min(2, k - 1))):
            tri_uv[fi, ci] = ls_[li][uvl0].uv
        lv_l.extend(l.vert.index for l in ls_); lt_l.append(k)
    co = np.array([v.co[:] for v in bm0.verts])
    bm0.free()
    lv = np.array(lv_l, dtype=np.int64); lt = np.array(lt_l, dtype=np.int64)

    # 1. every face's colour: the median of seven points inside it
    a, b, c = tri_uv[:, 0], tri_uv[:, 1], tri_uv[:, 2]
    pts = []
    for wa, wb, wc in ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6),
                       (0.45, 0.45, 0.1), (0.1, 0.45, 0.45), (0.45, 0.1, 0.45)):
        p = a * wa + b * wb + c * wc
        smp = np.zeros((nf, 3))
        for si, (kind, sheet) in enumerate(sheets):
            sel = fmat == si
            if not sel.any():
                continue
            if kind == "flat":
                smp[sel] = sheet
                continue
            Hs, Ws = sheet.shape[0], sheet.shape[1]
            x = np.clip((p[sel, 0] % 1.0) * Ws, 0, Ws - 1).astype(np.int64)
            y = np.clip((p[sel, 1] % 1.0) * Hs, 0, Hs - 1).astype(np.int64)
            smp[sel] = sheet[y, x]
        pts.append(smp)
    stack = np.stack(pts, 0)                     # (7, faces, 3)
    face_col = np.median(stack, axis=0)
    # how far a face's own seven points agree: a face inside a clean chart of
    # fur or cloth agrees with itself; a face mapped into the atlas's confetti
    # is a scatter of unrelated colours and is not to be believed
    face_var = ((stack - face_col[None]) ** 2).sum(2).mean(0)

    # 2. onto the vertices, then cleaned in space
    lf = np.repeat(np.arange(nf), lt)
    acc = np.zeros((nv, 3)); cnt = np.zeros(nv); vvar = np.zeros(nv)
    np.add.at(acc, lv, face_col[lf]); np.add.at(cnt, lv, 1); np.add.at(vvar, lv, face_var[lf])
    vcol = acc / np.maximum(cnt, 1)[:, None]
    vvar = vvar / np.maximum(cnt, 1)

    span = float(np.ptp(co, axis=0).max()) or 1.0
    ext = np.ptp(co, axis=0)
    # a standing figure (taller than it is wide or long) has a face, hands and
    # buttons to keep: its coat is evened over a smaller reach than an animal's
    upright = ext[2] > 1.4 * max(ext[0], ext[1])
    R = (0.010 if upright else 0.018) * span     # about 2 cm on a person, 1 cm on a fox
    kd = KDTree(nv)
    for i, v in enumerate(co.tolist()):
        kd.insert(v, i)
    kd.balance()
    KMAX = 28
    nbr = np.full((nv, KMAX), -1, dtype=np.int64)
    dist = np.zeros((nv, KMAX))
    for i, v in enumerate(co.tolist()):
        hits = kd.find_range(Vector(v), R)
        if len(hits) < 6:                        # a sparse spot: take the nearest few instead
            hits = kd.find_n(Vector(v), 6)
        hits.sort(key=lambda h: h[2])
        hits = hits[:KMAX]
        for k, (_, j, d) in enumerate(hits):
            nbr[i, k] = j; dist[i, k] = d
    # THE CLEAN SURFACE VOTES (2026-09-29). Much of a generated fox maps into
    # the atlas's confetti: noise whose average is a dull grey-brown, and it
    # outvoted the fur (the fox went grey). A vertex whose faces disagree with
    # themselves is not a source; it is filled from the reliable surface around
    # it, reaching further each pass, the way a hole in a photo is inpainted.
    idx = np.where(nbr >= 0, nbr, 0)
    has = nbr >= 0
    # HOW BLOTCHY IS IT (2026-09-29): a clean sheet varies smoothly, so a
    # vertex agrees with the median of the surface around it; confetti does
    # not. A model that is already clean keeps its texture and its detail
    # (the detective hero's face): the coat is for the mottled ones only.
    _ring0 = np.where(has[:, :, None], vcol[idx], np.nan)
    speck = float(np.median(np.abs(vcol - np.nanmedian(_ring0, axis=1)).sum(1)))
    print("SPECK %.4f" % speck)
    if MEASURE or speck < SPECK_MIN:
        print("CLEAN %.4f" % speck)
        sys.exit(0)
    thr = max(0.006, float(np.quantile(vvar, 0.25)))
    good = vvar <= thr
    if good.mean() < 0.25:                       # a noisy sheet everywhere: trust the calmest quarter
        good = vvar <= float(np.quantile(vvar, 0.25))
    print("RELIABLE %.0f%% of the surface (spread <= %.4f)" % (100.0 * good.mean(), thr))
    # the fill is for a coat the atlas's confetti has taken over (half the
    # fox); on a model that is mostly sound, the few faces that disagree with
    # themselves are detail (an eye, a mouth, a buckle) and are kept
    if good.mean() >= 0.7:
        good[:] = True
    known = good.copy()
    for _ in range(80):
        if known.all():
            break
        kn = has & known[idx]
        cnt_k = kn.sum(1)
        grow = (~known) & (cnt_k > 0)
        if not grow.any():
            break
        s = (np.where(kn[:, :, None], vcol[idx], 0.0)).sum(1) / np.maximum(cnt_k, 1)[:, None]
        vcol[grow] = s[grow]
        known = known | grow
    valid = has
    for _ in range(2):                           # flakes and flecks out: the neighbourhood's median
        ring = np.where(valid[:, :, None], vcol[idx], np.nan)
        vcol = np.nanmedian(ring, axis=1)
    w = np.where(valid, np.exp(-(dist / (0.6 * R)) ** 2), 0.0)
    for _ in range(3):                           # then even it
        vcol = (w[:, :, None] * vcol[idx]).sum(1) / np.maximum(w.sum(1), 1e-9)[:, None]
    vcol = np.clip(vcol, 0.0, 1.0)
    lin = np.where(vcol <= 0.04045, vcol / 12.92, ((vcol + 0.055) / 1.055) ** 2.4)

    # 3. the coat: vertex colour, no sheet, no UVs, one roughness
    ca = me.attributes.new(name="Coat", type="FLOAT_COLOR", domain="POINT")
    ca.data.foreach_set("color", np.concatenate([lin, np.ones((nv, 1))], axis=1).astype(np.float32).ravel())
    me.color_attributes.active_color = ca
    coat = bpy.data.materials.new("Coat")
    try:
        coat.use_nodes = True
    except Exception:
        pass
    ct = coat.node_tree
    bsdf = next(n for n in ct.nodes if n.type == "BSDF_PRINCIPLED")
    vc = ct.nodes.new("ShaderNodeVertexColor"); vc.layer_name = "Coat"
    ct.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    # one-sided, like the originals: a generated shell has pinholes, and a
    # double-sided coat shows its own dark inside through every one of them
    coat.use_backface_culling = True
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Metallic"].default_value = 0.0
    me.materials.clear(); me.materials.append(coat)
    while len(me.uv_layers):                     # no UVs: the runtime's auto-texturer leaves it alone
        me.uv_layers.remove(me.uv_layers[0])
    nv_all += nv; nf_all += nf

bpy.ops.export_scene.gltf(filepath=dst, export_yup=True, export_vertex_color="ACTIVE")
print("COAT %d %d %.1f" % (nv_all, nf_all, time.time() - t0))
