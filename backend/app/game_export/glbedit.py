"""Repair the texture side of a generated GLB, from the file itself.

Nothing here needs Blender. Every fix is a rewrite of the glTF container:
the studio calls it at the end of a bake, and `backend/tools/texpad.py`
calls the same functions from the command line for assets already on disk.

    gutters   a generated atlas is small islands with bare black between
              them; every mip level averages that black into the island's
              edge, which reads as dirt on a coat and as gaps in a face
    specks    isolated texels that differ wildly from a flat neighbourhood
    solidity  a character arrives with alphaMode BLEND and a not-quite-solid
              alpha channel, so the camera sees through the odd patch of
              cheek into the inside of the head
"""
from __future__ import annotations

import io
import json
import struct
from pathlib import Path


def _chunks(data: bytes):
    assert data[:4] == b"glTF", "not a binary glTF"
    n = 12
    js = bin_ = None
    while n < len(data):
        ln, ty = struct.unpack_from("<II", data, n)
        body = data[n + 8:n + 8 + ln]
        if ty == 0x4E4F534A:
            js = body
        elif ty == 0x004E4942:
            bin_ = body
        n += 8 + ln
    return json.loads(js), bytearray(bin_ or b"")


def _pack(g: dict, binb: bytes) -> bytes:
    js = json.dumps(g, separators=(",", ":")).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    binb = bytes(binb) + b"\x00" * ((4 - len(binb) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(binb)
    return (b"glTF" + struct.pack("<II", 2, total)
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(binb), 0x004E4942) + binb)


def pad_image(im, threshold: int = 6, radius: int = 24):
    """Fill the unused (near-black) texels near an island with its colour.

    Only the band within `radius` of real content is filled. That band is
    everything a mip chain can reach, and stopping there keeps an atlas that
    is mostly empty from being flooded edge to edge, which would bloat the
    file for texels no triangle ever samples.
    """
    import numpy as np
    a = np.asarray(im.convert("RGB")).astype(np.uint8)
    used = a.max(axis=2) > threshold
    share = float(used.mean())
    if used.all() or not used.any():
        return im, share, 0
    try:
        from scipy.ndimage import distance_transform_edt
        dist, (yi, xi) = distance_transform_edt(~used, return_indices=True)
        out = a.copy()
        band = (~used) & (dist <= radius)
        out[band] = a[yi, xi][band]
        filled = int(band.sum())
    except Exception:
        # no scipy: eight rounds of nearest-neighbour dilation reach far
        # enough for every mip level a player sees
        out = a.copy(); m = used.copy()
        for _ in range(8):
            if m.all():
                break
            acc = np.zeros(a.shape, np.float32); cnt = np.zeros(m.shape, np.float32)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                sh = np.roll(out, (dy, dx), (0, 1)); sm = np.roll(m, (dy, dx), (0, 1))
                acc += sh * sm[..., None]; cnt += sm
            fill = (~m) & (cnt > 0)
            out[fill] = (acc[fill] / cnt[fill][..., None]).astype(np.uint8)
            m |= fill
        filled = int((m & ~used).sum())
    from PIL import Image
    return Image.fromarray(out), share, filled


def despeckle(im, thresh: int = 44):
    """Take the salt and pepper out of a generated texture.

    TRELLIS writes a few isolated bright or dark texels into otherwise flat
    cloth; on a dark coat they read as lint and on a face as pores that are
    not there. A pixel that differs from its own neighbourhood's median by
    more than `thresh`, in a neighbourhood that is otherwise flat, is noise
    and takes the median's value. A real edge has a spread neighbourhood, so
    the flatness test leaves it alone.
    """
    import numpy as np
    from PIL import Image
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    try:
        from scipy.ndimage import median_filter, maximum_filter, minimum_filter
    except Exception:
        return im, 0
    med = median_filter(a, size=(3, 3, 1))
    diff = np.abs(a - med).max(axis=2)
    spread = (maximum_filter(med, size=(3, 3, 1)) - minimum_filter(med, size=(3, 3, 1))).max(axis=2)
    noisy = (diff > thresh) & (spread < thresh)
    if not noisy.any():
        return im, 0
    out = a.copy(); out[noisy] = med[noisy]
    return Image.fromarray(out.astype(np.uint8)), int(noisy.sum())


def _compact(g: dict, binb: bytearray) -> bytearray:
    """Rewrite the binary chunk with nothing but the live buffer views.

    Replacing an image appends the new bytes and repoints its view, which
    leaves the old blob stranded in the middle of the buffer: the file grows
    by the size of every texture it no longer uses. Copying the views out in
    order, four-byte aligned, drops whatever nothing points at.
    """
    zero = bytes(1)
    out = bytearray()
    for bv in g.get("bufferViews", []):
        off, ln = bv.get("byteOffset", 0), bv["byteLength"]
        out.extend(zero * ((4 - len(out) % 4) % 4))
        bv["byteOffset"] = len(out)
        out.extend(bytes(binb[off:off + ln]))
    g["buffers"][0]["byteLength"] = len(out)
    return out


def image_roles(g: dict) -> dict:
    """Which image is the colour, and which is data.

    Only the base colour map has gutters worth filling. A roughness or
    occlusion map is legitimately black over most of its area (nothing on a
    cloth coat is metal), and flooding that black with a neighbour's value
    would turn the whole costume glossy. A normal map's flat blue is likewise
    content, not void. So resolve each image's job through the materials and
    touch the colour maps only.
    """
    roles: dict[int, str] = {}

    def mark(tex: dict | None, role: str) -> None:
        if not tex or "index" not in tex:
            return
        src = g.get("textures", [])[tex["index"]].get("source")
        if src is None:
            return
        roles.setdefault(src, role)
        if role == "color":
            roles[src] = "color"          # colour wins over any other use

    for mt in g.get("materials", []):
        pbr = mt.get("pbrMetallicRoughness", {})
        mark(pbr.get("baseColorTexture"), "color")
        mark(pbr.get("metallicRoughnessTexture"), "rough")
        mark(mt.get("normalTexture"), "normal")
        mark(mt.get("occlusionTexture"), "occlusion")
        mark(mt.get("emissiveTexture"), "emissive")
    return roles


_CT = {5120: "i1", 5121: "u1", 5122: "i2", 5123: "u2", 5125: "u4", 5126: "f4"}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _acc(g: dict, binb: bytes, idx: int):
    """One accessor as an array, plus where to write it back."""
    import numpy as np
    a = g["accessors"][idx]
    nc, dt = _NC[a["type"]], np.dtype(_CT[a["componentType"]])
    bv = g["bufferViews"][a["bufferView"]]
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride") or nc * dt.itemsize
    if stride == nc * dt.itemsize:
        arr = np.frombuffer(binb, dtype=dt, count=a["count"] * nc, offset=base).reshape(a["count"], nc)
        return arr, base, stride, dt, nc
    rows = np.frombuffer(binb, dtype=np.uint8, count=a["count"] * stride, offset=base).reshape(a["count"], stride)
    arr = np.frombuffer(rows[:, :nc * dt.itemsize].copy().tobytes(), dtype=dt).reshape(a["count"], nc)
    return arr, base, stride, dt, nc


def renormal(g: dict, binb: bytearray, tol_scale: float = 1e-4,
             smooth_deg: float = 40.0) -> int:
    """Recompute every vertex normal from the shape itself.

    A generated mesh ships normals that disagree with its own triangles, a
    few in every hundred pointing somewhere of their own. Each of those
    catches the light as a bright speck, and since the relief map is derived
    from the shaded result the speck is baked in twice. On a dark coat they
    read as a rash of white flecks, which is the blotchiness that survives
    every texture fix, because it was never in the texture. Area-weighted
    normals over positions welded across the UV seams give the smooth
    surface the silhouette always implied.

    A corner whose own triangle points more than `smooth_deg` away from that
    average is a hard edge, not a speck, and keeps its triangle's normal: a
    crate stays a crate. A generated BODY has no hard edges to protect and a
    chaotic surface full of corners that would qualify, and each one kept
    catches the light as a bright facet, which is the speck this function
    exists to remove: pass 180 for anything organic and let it all smooth.
    """
    import numpy as np
    fixed = 0
    for mesh in g.get("meshes", []):
        for prim in mesh.get("primitives", []):
            at = prim.get("attributes", {})
            if prim.get("mode", 4) != 4 or "POSITION" not in at or "NORMAL" not in at:
                continue
            pos, _, _, _, _ = _acc(g, bytes(binb), at["POSITION"])
            pos = pos.astype(np.float64)
            if "indices" in prim:
                idx, _, _, _, _ = _acc(g, bytes(binb), prim["indices"])
                idx = idx.reshape(-1).astype(np.int64)
            else:
                idx = np.arange(len(pos), dtype=np.int64)
            tri = idx.reshape(-1, 3)
            span = float(np.linalg.norm(pos.max(axis=0) - pos.min(axis=0))) or 1.0
            q = np.round(pos / max(span * tol_scale, 1e-9)).astype(np.int64)
            _, weld = np.unique(q, axis=0, return_inverse=True)
            weld = weld.reshape(-1)
            a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
            fn = np.cross(b - a, c - a)               # length is twice the area: the weight
            acc = np.zeros((int(weld.max()) + 1, 3))
            for k in range(3):
                np.add.at(acc, weld[tri[:, k]], fn)
            ln = np.linalg.norm(acc, axis=1, keepdims=True)
            acc = np.divide(acc, np.maximum(ln, 1e-20))
            out = acc[weld].astype(np.float64)
            fnn = fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-20)
            lim = float(np.cos(np.radians(smooth_deg)))
            for k in range(3):                       # a hard edge keeps its own face
                corner = tri[:, k]
                hard = (out[corner] * fnn).sum(axis=1) < lim
                if hard.any():
                    out[corner[hard]] = fnn[hard]
            out = out.astype(np.float32)
            nrm, base, stride, dt, nc = _acc(g, bytes(binb), at["NORMAL"])
            if dt != np.dtype("f4") or nc != 3:
                continue
            if stride == 12:
                binb[base:base + out.nbytes] = out.tobytes()
            else:
                raw = out.tobytes()
                for i in range(len(out)):
                    o0 = base + i * stride
                    binb[o0:o0 + 12] = raw[i * 12:(i + 1) * 12]
            fixed += len(out)
    return fixed


def health(path) -> dict:
    """What the file says about itself, beside its shape.

    Two things ruin a generated character before anyone looks at the texture.
    Its normals disagree with its own triangles, so the light finds specks
    that are not there; and its material says BLEND with an alpha channel
    that is nearly but not quite solid, so the camera sees through the odd
    patch of cheek into the inside of the head. Both are reported as numbers
    here so a sweep can say which assets need the repair pass.
    """
    import numpy as np
    g, binb = _chunks(Path(path).read_bytes())
    binb = bytes(binb)
    blend = sum(1 for m in g.get("materials", [])
                if m.get("alphaMode", "OPAQUE") != "OPAQUE")
    worst = 0.0
    for mesh in g.get("meshes", []):
        for prim in mesh.get("primitives", []):
            at = prim.get("attributes", {})
            if prim.get("mode", 4) != 4 or "NORMAL" not in at or "POSITION" not in at:
                continue
            pos, _, _, _, _ = _acc(g, binb, at["POSITION"])
            nrm, _, _, _, _ = _acc(g, binb, at["NORMAL"])
            pos = np.asarray(pos, dtype=np.float64); nrm = np.asarray(nrm, dtype=np.float64)
            if "indices" in prim:
                idx, _, _, _, _ = _acc(g, binb, prim["indices"])
                tri = np.asarray(idx, dtype=np.int64).reshape(-1, 3)
            else:
                tri = np.arange(len(pos), dtype=np.int64).reshape(-1, 3)
            span = float(np.linalg.norm(pos.max(axis=0) - pos.min(axis=0))) or 1.0
            q = np.round(pos / max(span * 1e-4, 1e-9)).astype(np.int64)
            _, w = np.unique(q, axis=0, return_inverse=True)
            w = w.reshape(-1)
            a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
            fn = np.cross(b - a, c - a)
            acc = np.zeros((int(w.max()) + 1, 3))
            for k in range(3):
                np.add.at(acc, w[tri[:, k]], fn)
            acc /= np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-20)
            have = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-20)
            dot = np.clip((acc[w] * have).sum(axis=1), -1.0, 1.0)
            worst = max(worst, float((dot < 0.7).mean()))     # more than 45 degrees out
    return {"blend": blend, "normals_off": round(worst, 4)}


def shrink_images(g: dict, binb: bytearray, budget_mb: float = 1.5) -> dict:
    """Stop a character weighing forty megabytes.

    Blender writes PNG for every texture it exports, and a 4096 square PNG of
    generated noise is eighteen megabytes on its own: a rig that was six grew
    to forty over one rebake, all of it in maps nobody looks at directly. A
    colour or roughness map compresses to a tenth of that as JPEG with no
    visible difference on a surface this soft. Normal maps keep their PNG,
    because a compression artefact in a normal is a dent in the light, and so
    does anything carrying transparency.
    """
    from PIL import Image
    roles = image_roles(g)
    out = {"shrunk": 0, "saved": 0}
    for ix, img in enumerate(g.get("images", [])):
        if "bufferView" not in img or roles.get(ix) == "normal":
            continue
        bv = g["bufferViews"][img["bufferView"]]
        off, ln = bv.get("byteOffset", 0), bv["byteLength"]
        if ln < budget_mb * 1e6:
            continue
        im = Image.open(io.BytesIO(bytes(binb[off:off + ln])))
        if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
            alpha = im.convert("RGBA").split()[-1]
            if alpha.getextrema()[0] < 255:
                continue                              # real transparency stays lossless
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=92, subsampling=0, optimize=True)
        blob = buf.getvalue()
        if len(blob) >= ln:
            continue
        bv["byteOffset"] = len(binb)
        bv["byteLength"] = len(blob)
        binb.extend(blob)
        binb.extend(bytes((4 - len(binb) % 4) % 4))
        img["mimeType"] = "image/jpeg"
        out["shrunk"] += 1
        out["saved"] += ln - len(blob)
    return out


def make_opaque(g: dict) -> int:
    """Stop a character being see-through.

    A generated character arrives with alphaMode BLEND and an alpha channel
    that is mostly but not entirely solid. The stray transparent texels land
    wherever they like, and where they land on a cheek the camera looks
    straight through the head: the hole a player reads as a gap in the skin.
    Nothing about a person is meant to be transparent, so the material is
    told to be solid and the alpha channel goes with it.
    """
    n = 0
    for mt in g.get("materials", []):
        if mt.get("alphaMode", "OPAQUE") != "OPAQUE" or "alphaCutoff" in mt:
            mt["alphaMode"] = "OPAQUE"
            mt.pop("alphaCutoff", None)
            n += 1
        pbr = mt.get("pbrMetallicRoughness", {})
        bcf = pbr.get("baseColorFactor")
        if bcf and len(bcf) == 4 and bcf[3] < 1.0:
            bcf[3] = 1.0
            n += 1
    return n


def pad_glb(path: Path, check: bool = False, opaque: bool = False,
            normals: bool = False, shrink: bool = False) -> dict:
    from PIL import Image
    g, binb = _chunks(path.read_bytes())
    report = {"file": path.name, "images": []}
    changed = False
    roles = image_roles(g)
    if opaque:
        report["opaque"] = make_opaque(g)
        changed = changed or bool(report["opaque"])
    if normals and not check:
        # a character is organic: smooth everything. a prop may have edges.
        report["normals"] = renormal(g, binb, smooth_deg=180.0 if opaque else 40.0)
        changed = changed or bool(report["normals"])
    for ix, img in enumerate(g.get("images", [])):
        role = roles.get(ix, "color" if not roles else "unused")
        if "bufferView" not in img:
            continue
        if role != "color":
            bv = g["bufferViews"][img["bufferView"]]
            im = Image.open(io.BytesIO(bytes(binb[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])))
            report["images"].append({"size": im.size, "role": role, "used": None,
                                     "filled": 0, "specks": 0})
            continue
        bv = g["bufferViews"][img["bufferView"]]
        off, ln = bv.get("byteOffset", 0), bv["byteLength"]
        im = Image.open(io.BytesIO(bytes(binb[off:off + ln])))
        size = im.size
        padded, share, filled = pad_image(im)
        padded, specks = despeckle(padded)
        report["images"].append({"size": size, "role": role, "used": round(share, 3),
                                 "filled": filled, "specks": specks})
        if check or not (filled or specks or (opaque and im.mode in ("RGBA", "LA", "P"))):
            continue
        if opaque:
            padded = padded.convert("RGB")
        buf = io.BytesIO(); padded.save(buf, format="PNG", optimize=False)
        blob = buf.getvalue()
        bv["byteOffset"] = len(binb)
        bv["byteLength"] = len(blob)
        binb.extend(blob)
        binb.extend(b"\x00" * ((4 - len(binb) % 4) % 4))
        img["mimeType"] = "image/png"
        changed = True
    if shrink and not check:
        report["shrink"] = shrink_images(g, binb)
        changed = changed or bool(report["shrink"]["shrunk"])
    if changed and not check:
        binb = _compact(g, binb)
        path.write_bytes(_pack(g, binb))
        report["written"] = True
        report["bytes"] = len(binb)
    return report
