"""Warm a character's skin where the generator painted it magenta (2026-10-17).

The ranger's reference photo baked into a face of pink-magenta cheeks and
blue-grey shadows; under a game's cool grade the hero walked about with a
purple face. This finds the texels the head uses (vertices in the top band of
the body, their UVs dilated over the island), and inside them turns any
magenta-to-crimson skin tone round to a warm skin hue, keeping its value and
most of its saturation. Hats, hair and collars are other hues and are left.

The GLB is edited in place: only the base colour image's bytes change, and
the buffer views after it are shifted to fit.

    python backend/tools/skin_warm.py [--dry] [--band 0.14] files...
"""
from __future__ import annotations

import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def _read(path: Path):
    b = path.read_bytes()
    n = struct.unpack('<I', b[12:16])[0]
    j = json.loads(b[20:20 + n])
    off = 20 + n
    bn = struct.unpack('<I', b[off:off + 4])[0]
    return j, bytearray(b[off + 8:off + 8 + bn])


def _write(path: Path, j, bin_: bytes):
    js = json.dumps(j, separators=(',', ':')).encode()
    js += b' ' * ((4 - len(js) % 4) % 4)
    bin_ = bytes(bin_) + b'\0' * ((4 - len(bin_) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    out = struct.pack('<III', 0x46546C67, 2, total) + struct.pack('<II', len(js), 0x4E4F534A) + js \
        + struct.pack('<II', len(bin_), 0x004E4942) + bin_
    path.write_bytes(out)


def _acc(j, bin_, i):
    a = j['accessors'][i]
    bv = j['bufferViews'][a['bufferView']]
    comp = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}[a['componentType']]
    k = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
    st = bv.get('byteStride')
    o = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    if st and st != k * np.dtype(comp).itemsize:
        raw = np.frombuffer(bytes(bin_[o:o + st * a['count']]), np.uint8).reshape(a['count'], st)
        return raw[:, :k * np.dtype(comp).itemsize].copy().view(comp).reshape(a['count'], k)
    return np.frombuffer(bytes(bin_[o:o + a['count'] * k * np.dtype(comp).itemsize]), comp).reshape(a['count'], k)


def fix(path: Path, band: float = 0.14, dry: bool = False) -> str:
    j, bin_ = _read(path)
    mat = j['materials'][0]
    t = mat.get('pbrMetallicRoughness', {}).get('baseColorTexture')
    if t is None:
        return f'{path.name}: no base colour texture'
    img_i = j['textures'][t['index']]['source']
    im_meta = j['images'][img_i]
    bv_i = im_meta['bufferView']
    bv = j['bufferViews'][bv_i]
    o, ln = bv.get('byteOffset', 0), bv['byteLength']
    img = Image.open(io.BytesIO(bytes(bin_[o:o + ln]))).convert('RGB')
    W, H = img.size
    # the head: vertices in the top band of the body, their UVs
    mask = np.zeros((H, W), np.uint8)
    for m in j['meshes']:
        for p in m['primitives']:
            if 'TEXCOORD_0' not in p['attributes']:
                continue
            V = _acc(j, bin_, p['attributes']['POSITION'])
            UV = _acc(j, bin_, p['attributes']['TEXCOORD_0'])
            y = V[:, 1]
            h = y > y.max() - band * (y.max() - y.min())
            # and the hands: the far ends of the arms in the bind pose
            x = V[:, 0] - np.median(V[:, 0])
            h |= np.abs(x) > 0.8 * np.abs(x).max()
            u = (UV[h, 0] % 1.0) * (W - 1)
            v = (UV[h, 1] % 1.0) * (H - 1)
            mask[v.astype(int).clip(0, H - 1), u.astype(int).clip(0, W - 1)] = 255
    mask = np.asarray(Image.fromarray(mask).filter(ImageFilter.MaxFilter(17))) > 0
    hsv = np.asarray(img.convert('HSV')).astype(np.float32) / 255.0
    hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    skin = mask & ((hh > 0.83) | (hh < 0.035)) & (ss > 0.12) & (vv > 0.12)
    n = int(skin.sum())
    if not n:
        return f'{path.name}: no magenta skin under the head'
    # round to a warm skin hue, a little less saturated; a soft edge so a
    # cheek does not end in a seam
    soft = np.asarray(Image.fromarray((skin * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))).astype(np.float32) / 255.0
    nh = np.where(skin | (soft > 0), 0.055, hh)
    hsv2 = hsv.copy()
    hsv2[..., 0] = hh * (1 - soft) + nh * soft
    hsv2[..., 1] = ss * (1 - soft) + np.minimum(ss * 0.85, 0.55) * soft
    out = Image.fromarray((hsv2 * 255).clip(0, 255).astype(np.uint8), 'HSV').convert('RGB')
    if dry:
        return f'{path.name}: would warm {n} texels ({n / (W * H):.2%})'
    buf = io.BytesIO()
    mime = im_meta.get('mimeType', 'image/png')
    out.save(buf, 'JPEG' if 'jpeg' in mime else 'PNG', quality=94)
    new = buf.getvalue()
    # re-pack the buffer views with the new image, keeping 4-byte alignment
    views = j['bufferViews']
    order = sorted(range(len(views)), key=lambda k: views[k].get('byteOffset', 0))
    packed = bytearray()
    for k in order:
        vw = views[k]
        data = new if k == bv_i else bytes(bin_[vw.get('byteOffset', 0):vw.get('byteOffset', 0) + vw['byteLength']])
        packed += b'\0' * ((4 - len(packed) % 4) % 4)
        vw['byteOffset'] = len(packed)
        vw['byteLength'] = len(data)
        packed += data
    j['buffers'][0]['byteLength'] = len(packed)
    _write(path, j, packed)
    return f'{path.name}: warmed {n} texels ({n / (W * H):.2%})'


def main(argv) -> int:
    dry = '--dry' in argv
    band = 0.14
    if '--band' in argv:
        band = float(argv[argv.index('--band') + 1])
    files = [a for a in argv if a.endswith('.glb')]
    for f in files:
        print(fix(Path(f), band, dry))
    # THE RIG STAYS NEWER THAN ITS STATIC (2026-10-17): ensure_playable re-rigs
    # a kind whose static mesh is newer than its _anim.glb, and the re-rig
    # rebuilds the texture from the photo, magenta and all. Warming the static
    # after the rig undid the rig at the next build
    if not dry:
        import os, time
        now = time.time()
        for f in files:
            p = Path(f)
            if p.name.endswith('_anim.glb') or not p.exists():
                continue
            anim = p.with_name(p.stem + '_anim.glb')
            if anim.exists() and anim.stat().st_mtime <= p.stat().st_mtime:
                os.utime(anim, (now + 1, now + 1))
                print(f'{anim.name}: touched, so it stays newer than {p.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
