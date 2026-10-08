"""An animal's coat in its reference photo's colours (2026-10-08).

The image-to-3D step re-colours a body now and then: the elephant was made
from a grey studio photo and came out a brown that read as a boulder in the
grass. An animal's photo is a side view the body cannot be laid over exactly
(scripts/_hd_front.py --side could not align it), but its colours do not need
aligning: the coat's colour statistics are moved onto the photo figure's, per
channel in a perceptual space (mean and spread), so a brown hide turns the
photo's grey while its own light and dark patterning stays where it is.

Usage: blender --background --python _coat_recolor.py -- coated.glb ref.png out.glb [--k 0.85]
Prints RECOLOR <before rgb> <after rgb> on success.
"""
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
src, refpng, dst = argv[0], argv[1], argv[2]
K = float(argv[argv.index("--k") + 1]) if "--k" in argv else 0.85      # how far toward the photo

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.data.color_attributes]
if not meshes:
    print("RECOLORFAIL no vertex colour"); sys.exit(2)

to_s = lambda x: np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(np.clip(x, 0, None), 1 / 2.4) - 0.055)
to_l = lambda x: np.where(x <= 0.04045, x / 12.92, np.power((np.clip(x, 0, None) + 0.055) / 1.055, 2.4))

# the photo's figure: each row's backdrop from its own margins, a threshold from the backdrop's grain
img = bpy.data.images.load(refpng)
W, H = img.size
R = np.empty(W * H * 4, np.float32); img.pixels.foreach_get(R); R = R.reshape(H, W, 4)[::-1, :, :3]
E = max(24, W // 16)
bg = np.median(np.concatenate([R[:, :E], R[:, -E:]], axis=1), axis=1)
d = np.linalg.norm(R - bg[:, None, :], axis=2)
m = d > max(0.08, float(np.median(np.abs(d[:, :E])) + 3 * np.std(d[:, :E])))
m[int(H * 0.92):] = False                  # the floor shadow under the feet is not the hide
fig = R[m]
if len(fig) < 500:
    print("RECOLORFAIL no figure"); sys.exit(3)

cols = []
for o in meshes:
    ca = o.data.color_attributes.active_color or o.data.color_attributes[0]
    a = np.empty(len(ca.data) * 4, np.float32); ca.data.foreach_get("color", a)
    cols.append((o, ca, a.reshape(-1, 4)))
allc = np.concatenate([to_s(c[2][:, :3]) for c in cols])        # coat colours are linear floats; compare in sRGB
mu_c, sd_c = allc.mean(0), allc.std(0) + 1e-4
mu_p, sd_p = fig.mean(0), fig.std(0) + 1e-4
for o, ca, a in cols:
    s = to_s(a[:, :3])
    t = (s - mu_c) / sd_c * (sd_c + (sd_p - sd_c) * K) + (mu_c + (mu_p - mu_c) * K)
    a[:, :3] = to_l(np.clip(t, 0, 1))
    ca.data.foreach_set("color", a.ravel())
bpy.ops.export_scene.gltf(filepath=dst, export_yup=True, export_vertex_color="ACTIVE", export_attributes=True)
print("RECOLOR %s %s" % (np.round(mu_c, 2).tolist(), np.round(mu_c + (mu_p - mu_c) * K, 2).tolist()))
