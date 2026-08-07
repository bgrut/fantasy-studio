"""CANDIDATE builder for an A-pose biped depth template (2026-08-07).

NOT WIRED UP. The live template is still the T-pose one, because no
conditioning scale tested so far turns this candidate into a usable
reference — see the measured ladder in app/asset_gen/reference.py.
Run from backend/:  python scripts/_make_apose_template.py

Rotate the biped depth template's arms down into a real A-pose.

The template is the ControlNet conditioning every biped reference is
generated from, and it was a flat T-pose. mocap_retarget builds its arm
chain expecting hands ~0.18H BELOW the shoulders; a T-posed mesh gets a
skeleton that disagrees with it and the character keeps its arms out
through every clip. Rotating the existing arms preserves the anatomy and
depth gradient that make this template work at all — redrawing it would
throw both away.
"""
from PIL import Image, ImageFilter
import numpy as np
from scipy import ndimage

SRC = 'app/asset_gen/pose_templates/biped_depth.png'
# writes a CANDIDATE, never the live template — see the header
OUT = 'app/asset_gen/pose_templates/biped_depth_apose_candidate.png'
PREVIEW = (r'C:\Users\bgrut\AppData\Local\Temp\claude'
           r'\C--Users-bgrut-Desktop-FantasyAI-fantasy-studio'
           r'\bf22f1cd-89a7-4f51-80d2-04dba58eb91a\scratchpad\apose_preview.png')

img = Image.open(SRC).convert('L')
a = np.asarray(img, dtype=np.float32)
H, W = a.shape

# Geometry measured off this template: head crown y=89, feet ~y=800,
# shoulder line y~285, torso spans x~[391,630] at the shoulders.
SH_Y = 288
SH_LX, SH_RX = 404, 622          # shoulder joints
ARM_TOP, ARM_BOT = 250, 470      # the band the outstretched arms occupy
DEG = 42.0                       # hands land ~0.25H below the shoulders

body = a > 60
# arm pixels: outside the shoulder joints, within the arm band
cols = np.arange(W)[None, :].repeat(HH := H, axis=0) if False else np.tile(np.arange(W), (H, 1))
rows = np.tile(np.arange(H)[:, None], (1, W))
band = (rows >= ARM_TOP) & (rows <= ARM_BOT)
arm_L = body & band & (cols < SH_LX)
arm_R = body & band & (cols > SH_RX)


def rotate_about(src, mask, cx, cy, deg):
    """Rotate the masked pixels about (cx, cy). affine_transform samples the
    INPUT at matrix @ out + offset, so the matrix is the inverse rotation."""
    th = np.deg2rad(deg)
    # image y runs down, so this is a screen-space rotation of -th
    R = np.array([[np.cos(-th), -np.sin(-th)],
                  [np.sin(-th),  np.cos(-th)]], dtype=np.float64)
    c = np.array([cy, cx], dtype=np.float64)          # (row, col) order
    Rrc = np.array([[R[1, 1], R[1, 0]], [R[0, 1], R[0, 0]]])
    layer = np.where(mask, src, 0.0)
    out = ndimage.affine_transform(layer, Rrc, offset=c - Rrc @ c,
                                   order=1, mode='constant', cval=0.0)
    return out


# left arm swings down-left, right arm down-right
rot_L = rotate_about(a, arm_L, SH_LX, SH_Y, -DEG)
rot_R = rotate_about(a, arm_R, SH_RX, SH_Y, +DEG)

# EVERY EDIT MUST BE FEATHERED. At a conditioning scale high enough for the
# pose to actually bind, ControlNet reproduces the TEMPLATE's own artifacts —
# a hard-edged mask rectangle came back as a literal translucent rectangle
# across the model's chest. So the arm removal blends with a soft alpha and
# there are no rectangular repair zones anywhere.
holes = ndimage.binary_dilation(arm_L | arm_R, iterations=14)
holes &= band
holes &= (cols < SH_LX) | (cols > SH_RX)

bg_src = (~(a > 25)) & (~holes)
idx = ndimage.distance_transform_edt(~bg_src, return_distances=False,
                                     return_indices=True)
bgfield = ndimage.gaussian_filter(a[tuple(idx)], 9.0)

alpha = ndimage.gaussian_filter(holes.astype(np.float32), 9.0)
alpha = np.clip(alpha * 1.6, 0.0, 1.0)
torso = a * (1.0 - alpha) + bgfield * alpha
merged = np.maximum(np.maximum(torso, rot_L), rot_R)

# close the shoulder notch across the WHOLE image, then blend that repair in
# by a soft mask grown from the shoulder joints — no rectangle
m = Image.fromarray(np.clip(merged, 0, 255).astype(np.uint8))
closed = np.asarray(
    m.filter(ImageFilter.MaxFilter(21)).filter(ImageFilter.MinFilter(15)),
    dtype=np.float32)
sh = np.zeros_like(a, dtype=np.float32)
for px in (SH_LX, SH_RX):
    d2 = (rows - SH_Y) ** 2 + (cols - px) ** 2
    sh = np.maximum(sh, np.exp(-d2 / (2.0 * 95.0 ** 2)))
final = np.clip(merged * (1 - sh) + np.maximum(merged, closed) * sh,
                0, 255).astype(np.uint8)

Image.fromarray(final).save(OUT)

# side-by-side so the change can be judged by eye
prev = Image.new('L', (W // 2 * 2 + 12, H // 2), 0)
prev.paste(img.resize((W // 2, H // 2)), (0, 0))
prev.paste(Image.fromarray(final).resize((W // 2, H // 2)), (W // 2 + 12, 0))
prev.save(PREVIEW)

# report where the hands ended up, in the units the rigger cares about
fb = final > 60
fr, fc = np.nonzero(fb)
top = fr.min()
feet = max(y for y in range(H) if (fb[y].sum() and fb[y].sum() < 900))
BH = feet - top
hand_y = max(y for y in range(ARM_TOP, H) if fb[y][:SH_LX - 40].any())
print(f'body height {BH}px  shoulders y={SH_Y}  lowest left-arm pixel y={hand_y}')
print(f'hands sit {(hand_y - SH_Y) / BH:.3f}H below the shoulders '
      f'(rigger treats >0.18H as a usable A-pose)')
