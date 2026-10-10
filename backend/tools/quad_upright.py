"""Is this animal standing? (2026-10-09)

The generation's orientation gate matches the silhouette to the reference
photo, and its feet-down rule only knows "belly-up". A regenerated sheep came
out standing on its hind end, an elephant lying on its side and a T-rex tipped
over, and all three passed (IoU 0.40-0.45) and were rigged that way.

This renders the model from both sides at six candidate rotations (as is,
rolled 90 either way about each horizontal axis, and upside down) and asks
CLIP which shows "a <kind> standing upright on its legs". With --fix the
static GLB is rotated in place (Blender, texture kept) when another
rotation wins clearly.

    python backend/tools/quad_upright.py [--fix] sheep elephant ...
    python backend/tools/quad_upright.py --biped [--fix] firefighter ...
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

ROTS = {"as_is": (0, 0, 0), "x+90": (90, 0, 0), "x-90": (-90, 0, 0), "y+90": (0, 90, 0), "y-90": (0, -90, 0), "x180": (180, 0, 0)}
# A person only ever comes out on its head (a firefighter, 2026-10-09: gear and
# boots at the top, rigged and coated that way). Turning it over about Y keeps
# the face where it was, toward +Y.
BIPED_ROTS = {"as_is": (0, 0, 0), "y180": (0, 180, 0)}

_RENDER = r'''
import bpy, sys, math, json
from mathutils import Vector, Euler
argv = sys.argv[sys.argv.index("--") + 1:]
src, out, rots = argv[0], argv[1], json.loads(argv[2])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in bpy.data.objects:
    if o.type == "ARMATURE": o.data.pose_position = "REST"
roots = [o for o in bpy.data.objects if o.parent is None]
piv = bpy.data.objects.new("piv", None); bpy.context.scene.collection.objects.link(piv)
for o in roots: o.parent = piv
scn = bpy.context.scene
scn.render.engine = "BLENDER_WORKBENCH"; scn.display.shading.light = "STUDIO"
ms = [o for o in bpy.data.objects if o.type == "MESH"]
scn.display.shading.color_type = "VERTEX" if any(m.data.color_attributes for m in ms) else "TEXTURE"
w = bpy.data.worlds.new("w"); w.color = (0.75, 0.75, 0.76); scn.world = w
scn.render.resolution_x = scn.render.resolution_y = 384
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scn.collection.objects.link(cam); scn.camera = cam
cam.data.type = "ORTHO"
for name, e in rots.items():
    piv.rotation_euler = Euler([math.radians(a) for a in e])
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ v.co for o in ms for v in o.data.vertices]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (mn + mx) / 2; size = max(mx - mn) * 1.15
    cam.data.ortho_scale = size
    for side, d in (("a", Vector((1, 0, 0))), ("b", Vector((0, 1, 0)))):
        cam.location = c + d * 10; cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        scn.render.filepath = f"{out}_{name}_{side}.png"; bpy.ops.render.render(write_still=True)
'''

_ROTATE = r'''
import bpy, sys, math, json
from mathutils import Euler
argv = sys.argv[sys.argv.index("--") + 1:]
src, dst, e = argv[0], argv[1], json.loads(argv[2])
biped = len(argv) > 3 and argv[3] == "biped"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ms = [o for o in bpy.data.objects if o.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for o in ms:
    o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
R = Euler([math.radians(a) for a in e]).to_matrix().to_4x4()
for o in ms:                                   # glTF imports in quaternion mode: rotate the matrix, not the Euler
    o.matrix_world = R @ o.matrix_world
bpy.context.view_layer.update()
bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
# and turned the way every animal here faces: body along Y, head at -Y
# (glTF +Z, where the quadruped rigs and the runtime expect the front)
import numpy as np
P = np.array([list(o.matrix_world @ v.co) for o in ms for v in o.data.vertices])
ext = P.max(0) - P.min(0)
if ext[0] > ext[1] and not biped:
    Rz = Euler((0, 0, math.radians(90))).to_matrix().to_4x4()
    for o in ms:
        o.matrix_world = Rz @ o.matrix_world
    bpy.context.view_layer.update(); bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    P = np.array([list(o.matrix_world @ v.co) for o in ms for v in o.data.vertices])
L = np.ptp(P[:, 1]); c = (P[:, 1].max() + P[:, 1].min()) / 2
neg = P[P[:, 1] < c - 0.3 * L, 2]; pos = P[P[:, 1] > c + 0.3 * L, 2]
if not biped and len(neg) and len(pos) and pos.max() > neg.max():         # the head (the higher end) belongs at -Y
    Rz = Euler((0, 0, math.radians(180))).to_matrix().to_4x4()
    for o in ms:
        o.matrix_world = Rz @ o.matrix_world
    bpy.context.view_layer.update(); bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
zs = [(o.matrix_world @ v.co).z for o in ms for v in o.data.vertices]
for o in ms:
    o.location.z -= min(zs)
bpy.ops.export_scene.gltf(filepath=dst, export_yup=True)
print("ROTATED", e)
'''

_CLIP = None


def clip():
    global _CLIP
    if _CLIP is None:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _CLIP = (CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).eval(),
                 CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32"), dev)
    return _CLIP


def judge(glb: Path, kind: str, biped: bool = False) -> dict:
    from app.game_export.generate import BLENDER_EXE
    import torch
    from PIL import Image
    tmp = Path(tempfile.mkdtemp(prefix="upr_"))
    rs = tmp / "r.py"; rs.write_text(_RENDER, encoding="utf-8")
    subprocess.run([str(BLENDER_EXE), "--background", "--python", str(rs), "--", str(glb), str(tmp / "v"), json.dumps(BIPED_ROTS if biped else ROTS)],
                   capture_output=True, timeout=600)
    model, proc, dev = clip()
    texts = [f"a photo of a {kind} standing upright on its legs", f"a photo of a {kind} lying on its side",
             f"a photo of a {kind} upside down", f"a photo of a {kind} standing on its hind legs"]
    if biped:
        texts = [f"a photo of a {kind} standing upright, head at the top and feet on the ground",
                 f"a photo of a {kind} upside down, standing on their head"]
    scores = {}
    for name in (BIPED_ROTS if biped else ROTS):
        ims = [Image.open(tmp / f"v_{name}_{s}.png").convert("RGB") for s in ("a", "b") if (tmp / f"v_{name}_{s}.png").exists()]
        if not ims:
            continue
        with torch.no_grad():
            inp = proc(text=texts, images=ims, return_tensors="pt", padding=True).to(dev)
            p = model(**inp).logits_per_image.softmax(-1).mean(0)
        scores[name] = round(float(p[0]), 3)
    return {"scores": scores, "tmp": str(tmp)}


def fix(glb: Path, kind: str, margin: float = 0.15, apply: bool = False, biped: bool = False) -> str:
    j = judge(glb, kind, biped)
    sc = j["scores"]
    if not sc:
        return "render failed"
    best = max(sc, key=sc.get)
    msg = "%s %s" % (best, " ".join("%s:%.2f" % (k, v) for k, v in sorted(sc.items(), key=lambda t: -t[1])))
    if biped:
        margin = max(margin, 0.30)                                   # a person turned over is plain to CLIP
    if os.environ.get("QU_FORCE_FACE") == "1" and apply and best == "as_is" and not biped:
        best = "as_is"; sc[best] = 9.0                               # face-only pass on an upright model
    if (best != "as_is" and sc[best] - sc.get("as_is", 0) > margin) or (os.environ.get("QU_FORCE_FACE") == "1" and apply and not biped):
        if apply:
            from app.game_export.generate import BLENDER_EXE
            rs = Path(j["tmp"]) / "rot.py"; rs.write_text(_ROTATE, encoding="utf-8")
            out = glb.with_name(glb.stem + "_uprtmp.glb")
            r = subprocess.run([str(BLENDER_EXE), "--background", "--python", str(rs), "--", str(glb), str(out),
                                json.dumps((BIPED_ROTS if biped else ROTS)[best])] + (["biped"] if biped else []), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            if out.exists() and "ROTATED" in (r.stdout or ""):
                out.replace(glb)
                return "ROTATED " + msg
            return "rotate failed " + msg
        return "WOULD ROTATE " + msg
    return "upright " + msg


def main() -> int:
    apply = "--fix" in sys.argv
    biped = "--biped" in sys.argv
    for k in [a for a in sys.argv[1:] if not a.startswith("--")]:
        glb = BACKEND / "assets" / "library" / (k.replace(" ", "_") + ".glb")
        print(k, ":", fix(glb, k.replace("_", " "), apply=apply, biped=biped) if glb.exists() else "missing", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
