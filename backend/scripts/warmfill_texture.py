"""Texture warm-fill experiment (pre-demo, on COPIES): the side-projection
bake leaves off-axis texels as desaturated gray smears. Recolor those texels
toward the asset's real fur palette (hue+sat transfer, keep luminance) so
haunches/backs read as soft fur instead of gray plastic. Skins/animations are
untouched — only the embedded baseColor image bytes are swapped.
"""
import io
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from pygltflib import GLTF2

SRC = Path(sys.argv[1])
DST = Path(sys.argv[2])

g = GLTF2().load_binary(str(SRC))
blob = bytearray(g.binary_blob())

def bv_bytes(bv):
    off = bv.byteOffset or 0
    return bytes(blob[off:off + bv.byteLength])

changed = 0
new_chunks = []
for img_idx, img in enumerate(g.images):
    if img.bufferView is None:
        continue
    bv = g.bufferViews[img.bufferView]
    im = Image.open(io.BytesIO(bv_bytes(bv))).convert("RGB")
    a = np.asarray(im).astype(np.float32) / 255.0
    r, gg, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    sat = np.where(mx > 1e-5, (mx - mn) / np.maximum(mx, 1e-5), 0)
    val = mx
    # fur palette = well-saturated, mid-bright texels
    fur = (sat > 0.25) & (val > 0.15) & (val < 0.95)
    if fur.mean() < 0.05:
        continue                     # not a photo-textured asset — skip
    fur_rgb = a[fur]
    fur_mean = fur_rgb.mean(0)       # the asset's average fur tone
    # smear texels: desaturated, mid-value (excludes true white paws >0.93
    # and dark features <0.25)
    smear = (sat < 0.13) & (val > 0.25) & (val < 0.93)
    if smear.mean() < 0.02:
        continue
    # keep each texel's luminance, take the fur's chroma
    lum = 0.299 * r + 0.587 * gg + 0.114 * b
    fur_lum = 0.299 * fur_mean[0] + 0.587 * fur_mean[1] + 0.114 * fur_mean[2]
    tinted = np.clip(fur_mean[None, None, :] * (lum / max(fur_lum, 1e-4))[..., None], 0, 1)
    w = smear.astype(np.float32) * 0.85          # blend, don't replace
    out = a * (1 - w[..., None]) + tinted * w[..., None]
    out_im = Image.fromarray((out * 255).astype(np.uint8))
    buf = io.BytesIO()
    out_im.save(buf, format="PNG")
    new_chunks.append((img_idx, buf.getvalue()))
    changed += 1
    print(f"image {img_idx}: {im.size}, smear {smear.mean()*100:.1f}% of texels warmed "
          f"toward fur tone {tuple(round(float(c), 2) for c in fur_mean)}")

# append new image bytes to the blob, repoint bufferViews (4-byte aligned)
from pygltflib import BufferView
for img_idx, data in new_chunks:
    while len(blob) % 4:
        blob += b"\x00"
    off = len(blob)
    blob += data
    g.bufferViews.append(BufferView(buffer=0, byteOffset=off, byteLength=len(data)))
    g.images[img_idx].bufferView = len(g.bufferViews) - 1
    g.images[img_idx].mimeType = "image/png"

g.buffers[0].byteLength = len(blob)
g.set_binary_blob(bytes(blob))
g.save_binary(str(DST))
print(f"wrote {DST} ({DST.stat().st_size/1e6:.1f} MB, {changed} textures warmed)")
