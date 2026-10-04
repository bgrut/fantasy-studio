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
4. The embossed normal map goes with the sheet: the geometry's own smooth
   normals light it. Metal and roughness are read from the metal-roughness
   sheet like the colour and ship per vertex as the attribute _MR (the game
   runtime reads it; the material's single values are the body's averages).

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


def read_sheets(me):
    """Every material slot's colour: its sheet as stored (sRGB), or a flat colour."""
    out = []
    for mslot in me.materials:
        im = base_image(mslot)
        if im is not None and im.size[0] > 0:
            a_ = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
            im.pixels.foreach_get(a_)
            out.append(("img", a_.reshape(im.size[1], im.size[0], 4)[:, :, :3]))
        else:
            col = (0.6, 0.6, 0.6)
            try:
                bs = next(n for n in mslot.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                lc = np.array(bs.inputs["Base Color"].default_value[:3])
                col = tuple(np.where(lc <= 0.0031308, lc * 12.92, 1.055 * lc ** (1 / 2.4) - 0.055))
            except Exception:
                pass
            out.append(("flat", np.array(col)))
    return out


# METAL STAYS METAL (2026-10-03). The coat shipped one roughness (0.8) and no
# metal for every character, so a knight's steel, whose colour map is a
# bright metal grey, came out as pale matte plaster. Each material's
# metal-roughness sheet is read too (glTF: metal in blue, roughness in green),
# sampled and cleaned exactly like the colour, and shipped per vertex as the
# custom attribute _MR (the runtime reads it); the material's single values
# are the body's averages, for anything that does not.
def _upstream_image(sock):
    seen, todo = set(), [l.from_node for l in sock.links]
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        if n.type == "TEX_IMAGE" and n.image is not None:
            return n.image
        for i in n.inputs:
            todo.extend(l.from_node for l in i.links)
    return None


def read_mr(me):
    """Every material slot's (metal, rough): its sheet as (H, W, 2), or flat values."""
    out = []
    for mslot in me.materials:
        metal, rough, im = 0.0, 0.8, None
        try:
            bs = next(n for n in mslot.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            metal = float(bs.inputs["Metallic"].default_value)
            rough = float(bs.inputs["Roughness"].default_value)
            im = _upstream_image(bs.inputs["Metallic"]) or _upstream_image(bs.inputs["Roughness"])
        except Exception:
            pass
        if im is not None and im.size[0] > 0:
            a_ = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
            im.pixels.foreach_get(a_)
            px = a_.reshape(im.size[1], im.size[0], 4)
            out.append(("img", np.stack([px[:, :, 2], px[:, :, 1]], -1)))
        else:
            out.append(("flat", np.array([metal, rough])))
    return out


def sample_mr(mrs, which, uv):
    res = np.zeros((len(uv), 2)); res[:, 1] = 0.8
    for si, (kind, sheet) in enumerate(mrs):
        sel = which == si
        if not sel.any():
            continue
        if kind == "flat":
            res[sel] = sheet
            continue
        Hs, Ws = sheet.shape[0], sheet.shape[1]
        x = np.clip((uv[sel, 0] % 1.0) * Ws, 0, Ws - 1).astype(np.int64)
        y = np.clip((uv[sel, 1] % 1.0) * Hs, 0, Hs - 1).astype(np.int64)
        res[sel] = sheet[y, x]
    return res


def read_alpha(me):
    """Every material slot's transparency sheet, or None where the slot has none."""
    out = []
    for mslot in me.materials:
        im = base_image(mslot)
        if im is None or im.size[0] == 0 or im.depth != 32:
            out.append(None); continue
        a_ = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
        im.pixels.foreach_get(a_)
        al = a_.reshape(im.size[1], im.size[0], 4)[:, :, 3]
        out.append(al if (al < 0.5).any() else None)
    return out


def sample_alpha(alphas, which, uv):
    """Transparency at uv (n,2) from sheet index which (n,); 1.0 where there is no sheet."""
    res = np.ones(len(uv))
    for si, al in enumerate(alphas):
        sel = which == si
        if al is None or not sel.any():
            continue
        Hs, Ws = al.shape
        x = np.clip((uv[sel, 0] % 1.0) * Ws, 0, Ws - 1).astype(np.int64)
        y = np.clip((uv[sel, 1] % 1.0) * Hs, 0, Hs - 1).astype(np.int64)
        res[sel] = al[y, x]
    return res


def sample(sheets, which, uv):
    """Colours at uv (n,2) from sheet index which (n,)."""
    res = np.zeros((len(uv), 3))
    for si, (kind, sheet) in enumerate(sheets):
        sel = which == si
        if not sel.any():
            continue
        if kind == "flat":
            res[sel] = sheet
            continue
        Hs, Ws = sheet.shape[0], sheet.shape[1]
        x = np.clip((uv[sel, 0] % 1.0) * Ws, 0, Ws - 1).astype(np.int64)
        y = np.clip((uv[sel, 1] % 1.0) * Hs, 0, Hs - 1).astype(np.int64)
        res[sel] = sheet[y, x]
    return res


# THE SOURCE'S COLOUR (2026-09-30). Eight animals (the tiger, the cheetah, the
# ice wolf, the gazelle...) played as black silhouettes: the rig bake had
# written a near-black sheet, while the model it was rigged from still has
# its full coat. With --from=<static.glb> the coat can be read from that
# source instead, surface to surface: the rigged mesh's rest shape is the
# source's shape moved, scaled and turned, so both are normalised, the
# axis-aligned turn under which they coincide is found, and each face reads
# the source's texture at the nearest point of the source's surface. It is
# used when the rig's own sheet is far darker than the source's.
FROM = next((a.split("=", 1)[1] for a in argv if a.startswith("--from=")), None)
SRC = None
if FROM:
    from mathutils.bvhtree import BVHTree
    before = set(bpy.data.objects)
    acts_before = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=FROM)
    new_objs = [ob for ob in bpy.data.objects if ob not in before]
    # a source that is itself animated brings its clips with it; only its
    # surface is wanted, so they go before the export can pick them up
    for act in [a for a in bpy.data.actions if a not in acts_before]:
        bpy.data.actions.remove(act)
    tris, tuv, tsh, ssheets, salpha, smr = [], [], [], [], [], []
    for so in [ob for ob in new_objs if ob.type == "MESH"]:
        base = len(ssheets)
        ssheets.extend(read_sheets(so.data))
        salpha.extend(read_alpha(so.data))
        smr.extend(read_mr(so.data))
        bm = bmesh.new(); bm.from_mesh(so.data)
        bm.transform(so.matrix_world)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        uvl = bm.loops.layers.uv.active
        if uvl is None:
            bm.free(); continue
        for f in bm.faces:
            tris.append([l.vert.co[:] for l in f.loops])
            tuv.append([l[uvl].uv[:] for l in f.loops])
            tsh.append(base + f.material_index)
        bm.free()
    for ob in new_objs:
        bpy.data.objects.remove(ob, do_unlink=True)
    if tris and any(k == "img" for k, _ in ssheets):
        T = np.array(tris); U = np.array(tuv)
        flat = T.reshape(-1, 3)
        SRC = {"tris": T, "uv": U, "sheet": np.array(tsh, dtype=np.int64), "sheets": ssheets, "alpha": salpha, "mr": smr,
               "bvh": BVHTree.FromPolygons([Vector(p) for p in flat.tolist()],
                                           [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(T))],
                                           all_triangles=True),
               "verts": flat}


def cube_rotations():
    import itertools
    rots = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            R = np.zeros((3, 3))
            for r, (c, s) in enumerate(zip(perm, signs)):
                R[r, c] = s
            if np.linalg.det(R) > 0:
                rots.append(R)
    return rots


def align(A):
    """The turn under which points A (world) lie on the source: (gap, map to the source's frame)."""
    S = SRC["verts"]
    cA, sA = (A.min(0) + A.max(0)) / 2, float(np.linalg.norm(A.max(0) - A.min(0))) or 1.0
    cS, sS = (S.min(0) + S.max(0)) / 2, float(np.linalg.norm(S.max(0) - S.min(0))) or 1.0
    kdS = KDTree(min(len(S), 30000))
    step = max(1, len(S) // 30000)
    for i, v in enumerate(((S[::step][:30000] - cS) / sS).tolist()):
        kdS.insert(v, i)
    kdS.balance()
    probe = ((A[:: max(1, len(A) // 2500)] - cA) / sA)
    best = None
    for R in cube_rotations():
        d = float(np.mean([kdS.find(p)[2] for p in (probe @ R.T).tolist()]))
        if best is None or d < best[0]:
            best = (d, R)
    R = best[1]
    return best[0], (lambda Pw: ((Pw - cA) / sA) @ R.T * sS + cS)


def source_colours(world_pts):
    """Colour of the source's surface nearest each point (already in the source's frame)."""
    which, out_uv = source_uv(world_pts)
    return sample(SRC["sheets"], which, out_uv)


def source_uv(world_pts):
    """Sheet index and uv of the source's surface nearest each point (in the source's frame)."""
    T, U, bvh = SRC["tris"], SRC["uv"], SRC["bvh"]
    out_uv = np.zeros((len(world_pts), 2)); which = np.zeros(len(world_pts), dtype=np.int64)
    for i, p in enumerate(world_pts.tolist()):
        hit = bvh.find_nearest(Vector(p))
        if hit is None or hit[2] is None:
            continue
        ti = hit[2]; q = np.array(hit[0][:])
        a_, b_, c_ = T[ti]
        v0, v1, v2 = b_ - a_, c_ - a_, q - a_
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01 or 1e-12
        w1 = (d11 * d20 - d01 * d21) / den; w2 = (d00 * d21 - d01 * d20) / den
        w1, w2 = min(max(w1, 0.0), 1.0), min(max(w2, 0.0), 1.0)
        if w1 + w2 > 1.0:
            s_ = w1 + w2; w1 /= s_; w2 /= s_
        out_uv[i] = U[ti, 0] * (1 - w1 - w2) + U[ti, 1] * w1 + U[ti, 2] * w2
        which[i] = SRC["sheet"][ti]
    return which, out_uv


nv_all = nf_all = 0
for o in meshes:
    me = o.data
    # EVERY MATERIAL ITS OWN SHEET: a hero carries a head material beside the
    # body's, and sampling every face from the first sheet painted the faces
    # with a patch of hair. Each slot is read from its own image, or its flat
    # colour when it has none.
    sheets = read_sheets(me)
    mrs = read_mr(me)
    if (not any(k == "img" for k, _ in sheets) or not me.uv_layers) and SRC is None:
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
    # NOTHING THE TEXTURE HID (2026-09-30). The black lines standing over the
    # horse were its mane's fringe: sheets of geometry the generator draws and
    # then makes invisible with its texture's transparency, 14,000 of the
    # horse's 75,000 faces. A textured model hides them; the coat has no
    # texture, so it painted them solid. A face the texture shows as clear is
    # removed. The rig bake writes its sheet without transparency, so a rigged
    # model reads it from the model it was rigged from, like its colour.
    n_clear = 0
    own_a = read_alpha(me)
    has_own = any(a_ is not None for a_ in own_a) and bmw.loops.layers.uv.active is not None
    has_src = SRC is not None and any(a_ is not None for a_ in SRC["alpha"])
    if has_own or has_src:
        bmw.faces.ensure_lookup_table()
        fl = list(bmw.faces)
        pick = [(0, 1, min(2, len(f.loops) - 1)) for f in fl]
        W4 = ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6))
        fa = None
        if has_own:
            uvw = bmw.loops.layers.uv.active
            tuv_ = np.array([[f.loops[i][uvw].uv[:] for i in p] for f, p in zip(fl, pick)])
            fm_ = np.array([f.material_index for f in fl], dtype=np.int64)
            fa = np.median([sample_alpha(own_a, fm_, tuv_[:, 0] * wa + tuv_[:, 1] * wb + tuv_[:, 2] * wc)
                            for wa, wb, wc in W4], axis=0)
        else:
            Mw = np.array(o.matrix_world)
            wco = lambda P: P @ Mw[:3, :3].T + Mw[:3, 3]
            gap_a, map_a = align(wco(np.array([v.co[:] for v in bmw.verts])))
            if gap_a < 0.03:
                tco_ = np.array([[f.loops[i].vert.co[:] for i in p] for f, p in zip(fl, pick)])
                fa = np.median([sample_alpha(SRC["alpha"], *source_uv(map_a(wco(
                    tco_[:, 0] * wa + tco_[:, 1] * wb + tco_[:, 2] * wc)))) for wa, wb, wc in W4], axis=0)
        if fa is not None:
            clear = [f for f, a_ in zip(fl, fa) if a_ < 0.5]
            # a model that is mostly clear is not this problem: leave it
            if 0 < len(clear) < 0.35 * len(fl):
                bmesh.ops.delete(bmw, geom=clear, context="FACES")
                n_clear = len(clear)
                print("CLEAR cut %d of %d" % (n_clear, len(fl)))
    # NO SLIVERS (2026-09-30): the old optimiser stretched thin hair sheets
    # into triangles as long as the animal (611 on the moose, the black lines
    # over the horse). The same cut the optimiser now makes: a triangle longer
    # than a few percent of the model and many times thinner than it is long
    # is removed, twice, stricter the second time; then what it left floating.
    n_cut = 0
    for _L, _R in ((0.06, 20.0), (0.025, 15.0)):
        bmw.faces.ensure_lookup_table()
        kill = []
        for f in bmw.faces:
            es = [e.calc_length() for e in f.edges]; Lf = max(es); A = f.calc_area()
            if Lf > _L * _span0 and Lf / max(2.0 * A / max(Lf, 1e-12), 1e-12) > _R:
                kill.append(f)
        if len(kill) > 0.2 * len(bmw.faces):
            break
        bmesh.ops.delete(bmw, geom=kill, context="FACES")
        n_cut += len(kill)
    if n_cut or n_clear:
        bmw.faces.ensure_lookup_table()
        seen = set(); small = []
        minp = max(40, int(0.005 * len(bmw.faces)))
        for f in bmw.faces:
            if f.index in seen:
                continue
            st = [f]; comp = []
            while st:
                g = st.pop()
                if g.index in seen:
                    continue
                seen.add(g.index); comp.append(g)
                for e in g.edges:
                    for h in e.link_faces:
                        if h.index not in seen:
                            st.append(h)
            if len(comp) < minp:
                small.extend(comp)
        if len(small) < 0.3 * len(bmw.faces):
            bmesh.ops.delete(bmw, geom=small, context="FACES")
        bmesh.ops.delete(bmw, geom=[v for v in bmw.verts if not v.link_faces], context="VERTS")
        if n_cut:
            print("SLIVERS cut %d" % n_cut)
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
    tri_uv = np.zeros((nf, 3, 2)); tri_co = np.zeros((nf, 3, 3)); lv_l = []; lt_l = []
    fmat = np.array([f.material_index for f in bm0.faces], dtype=np.int64)
    for fi, f in enumerate(bm0.faces):
        ls_ = f.loops
        k = len(ls_)
        for ci, li in enumerate((0, 1, min(2, k - 1))):
            if uvl0 is not None:
                tri_uv[fi, ci] = ls_[li][uvl0].uv
            tri_co[fi, ci] = ls_[li].vert.co
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
    face_mr = np.median(np.stack([sample_mr(mrs, fmat, a * wa + b * wb + c * wc)
                                  for wa, wb, wc in ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6))], 0), axis=0)
    # how far a face's own seven points agree: a face inside a clean chart of
    # fur or cloth agrees with itself; a face mapped into the atlas's confetti
    # is a scatter of unrelated colours and is not to be believed
    face_var = ((stack - face_col[None]) ** 2).sum(2).mean(0)

    if SRC is not None:
        # the rigged rest shape in the source's frame: normalise both, and keep
        # the axis-aligned turn under which the two surfaces coincide
        M = np.array(o.matrix_world)
        gap, _map = align(co @ M[:3, :3].T + M[:3, 3])
        best = (gap,)
        print("ALIGN mean gap %.4f of the size" % gap)

        def to_src(P):
            return _map(P @ M[:3, :3].T + M[:3, 3])
        spts, smrs = [], []
        for wa, wb, wc in ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6)):
            _w, _uv = source_uv(to_src(tri_co[:, 0] * wa + tri_co[:, 1] * wb + tri_co[:, 2] * wc))
            spts.append(sample(SRC["sheets"], _w, _uv))
            smrs.append(sample_mr(SRC["mr"], _w, _uv))
        sstack = np.stack(spts, 0)
        s_col = np.median(sstack, axis=0)
        lum = lambda x: float((x @ np.array([0.2126, 0.7152, 0.0722])).mean())
        own_l, src_l = lum(face_col), lum(s_col)
        print("LUMINANCE own %.3f, source %.3f" % (own_l, src_l))
        if best[0] < 0.03 and all(k == "flat" for k, _ in mrs):
            face_mr = np.median(np.stack(smrs, 0), axis=0)     # the rig carries no metal sheet; the source does
        if best[0] < 0.03 and (own_l < 0.55 * src_l or not any(k == "img" for k, _ in sheets)):
            print("FROM SOURCE")
            face_col = s_col
            face_mr = np.median(np.stack(smrs, 0), axis=0)
            face_var = ((sstack - s_col[None]) ** 2).sum(2).mean(0)

    # 2. onto the vertices, then cleaned in space
    lf = np.repeat(np.arange(nf), lt)
    acc = np.zeros((nv, 3)); cnt = np.zeros(nv); vvar = np.zeros(nv); acc_mr = np.zeros((nv, 2))
    np.add.at(acc, lv, face_col[lf]); np.add.at(cnt, lv, 1); np.add.at(vvar, lv, face_var[lf])
    np.add.at(acc_mr, lv, face_mr[lf])
    vcol = acc / np.maximum(cnt, 1)[:, None]
    vmr = acc_mr / np.maximum(cnt, 1)[:, None]
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
    vcol = np.concatenate([vcol, vmr], axis=1)   # metal and roughness ride along as two more channels
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
    vmr = vcol[:, 3:5]; vcol = vcol[:, :3]
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
    mra = me.attributes.new(name="_MR", type="FLOAT_VECTOR", domain="POINT")
    mra.data.foreach_set("vector", np.concatenate([vmr, np.zeros((nv, 1))], axis=1).astype(np.float32).ravel())
    bsdf.inputs["Roughness"].default_value = float(np.clip(vmr[:, 1].mean(), 0.3, 1.0))
    bsdf.inputs["Metallic"].default_value = float(np.clip(vmr[:, 0].mean(), 0.0, 1.0))
    print("MR metal mean %.2f (%.0f%% over 0.5), rough mean %.2f" % (vmr[:, 0].mean(), 100 * (vmr[:, 0] > 0.5).mean(), vmr[:, 1].mean()))
    me.materials.clear(); me.materials.append(coat)
    while len(me.uv_layers):                     # no UVs: the runtime's auto-texturer leaves it alone
        me.uv_layers.remove(me.uv_layers[0])
    nv_all += nv; nf_all += nf

bpy.ops.export_scene.gltf(filepath=dst, export_yup=True, export_vertex_color="ACTIVE", export_attributes=True)
print("COAT %d %d %.1f" % (nv_all, nf_all, time.time() - t0))
