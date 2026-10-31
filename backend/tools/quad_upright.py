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
import re
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

ROTS = {"as_is": (0, 0, 0), "x+90": (90, 0, 0), "x-90": (-90, 0, 0), "y+90": (0, 90, 0), "y-90": (0, -90, 0), "x180": (180, 0, 0)}
# A person comes out on its head (a firefighter, 2026-10-09: gear and boots at
# the top, rigged and coated that way) or on its side (a samurai). Turning
# about Y keeps the face where it was, toward +Y.
BIPED_ROTS = {"as_is": (0, 0, 0), "y180": (0, 180, 0), "y+90": (0, 90, 0), "y-90": (0, -90, 0)}

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
DIMS = {}
for name, e in rots.items():
    piv.rotation_euler = Euler([math.radians(a) for a in e])
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ v.co for o in ms for v in o.data.vertices]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (mn + mx) / 2; size = max(mx - mn) * 1.15
    # the spread of the mesh along each axis (standard deviation): splayed legs and
    # antennae widen a bounding box without moving the body's own long axis
    _n = max(len(pts), 1); _m = sum(pts, Vector((0, 0, 0))) / _n
    DIMS[name] = [math.sqrt(sum((p.x - _m.x) ** 2 for p in pts) / _n), math.sqrt(sum((p.y - _m.y) ** 2 for p in pts) / _n), math.sqrt(sum((p.z - _m.z) ** 2 for p in pts) / _n),
                  (_m.z - mn.z) / max(mx.z - mn.z, 1e-6)]          # where the mass sits: high over the feet when standing on legs
    cam.data.ortho_scale = size
    for side, d in (("a", Vector((1, 0, 0))), ("b", Vector((0, 1, 0)))):
        cam.location = c + d * 10; cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        scn.render.filepath = f"{out}_{name}_{side}.png"; bpy.ops.render.render(write_still=True)
open(f"{out}_dims.json", "w").write(json.dumps(DIMS))
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


def judge(glb: Path, kind: str, biped: bool = False, stand: bool = False) -> dict:
    from app.game_export.generate import BLENDER_EXE
    import torch
    from PIL import Image
    tmp = Path(tempfile.mkdtemp(prefix="upr_"))
    _TMPS.append(str(tmp))
    rs = tmp / "r.py"; rs.write_text(_RENDER, encoding="utf-8")
    subprocess.run([str(BLENDER_EXE), "--background", "--python", str(rs), "--", str(glb), str(tmp / "v"), json.dumps(BIPED_ROTS if biped else ROTS)],
                   capture_output=True, timeout=600)
    model, proc, dev = clip()
    texts = [f"a photo of a {kind} standing upright on its legs", f"a photo of a {kind} lying on its side",
             f"a photo of a {kind} upside down", f"a photo of a {kind} standing on its hind legs"]
    if biped or stand:
        texts = [f"a photo of a {kind} standing upright, head at the top and feet on the ground",
                 f"a photo of a {kind} upside down, standing on their head",
                 f"a photo of a {kind} lying down on their side"]
    scores = {}
    for name in (BIPED_ROTS if biped else ROTS):
        ims = [Image.open(tmp / f"v_{name}_{s}.png").convert("RGB") for s in ("a", "b") if (tmp / f"v_{name}_{s}.png").exists()]
        if not ims:
            continue
        with torch.no_grad():
            inp = proc(text=texts, images=ims, return_tensors="pt", padding=True).to(dev)
            p = model(**inp).logits_per_image.softmax(-1).mean(0)
        scores[name] = round(float(p[0]), 3)
    # AN ANIMAL ON ITS LEGS IS LONGER THAN IT IS TALL (2026-10-22): CLIP judged a
    # generated ant standing on its tail "upright", and it was rigged and played that
    # way. Where the shape says a pose stands far taller than it is long, its score is
    # cut (the long-necked and the ones that do stand up are exempt)
    try:
        dims = json.loads((tmp / "v_dims.json").read_text())
    except Exception:
        dims = {}
    if stand:                                          # a person laid flat: which turns stand them up
        return {"scores": scores, "tmp": str(tmp), "tall": {n: d[2] > max(d[0], d[1]) for n, d in dims.items()}}
    # A thing with six or eight legs is flat: its least spread is its height, and on its
    # legs its body rides above the leg tips (the mass high in the box). CLIP could not
    # tell an ant on its tail from an ant on its legs at all.
    _flat = bool(re.search(r"\b(ants?|beetles?|ladybugs?|ladybirds?|spiders?|tarantulas?|scorpions?|cockroach\w*|roach\w*|crabs?|lobsters?|crickets?|grasshoppers?|locusts?|mantis\w*|termites?|pillbugs?|woodlouse|woodlice|ticks?|mites?|centipedes?|millipedes?|weevils?|bugs?|insects?)\b", kind.lower()))
    # (the body's long axis lies level, and on its legs the mass rides high over the
    # leg tips: of the level poses, the one with the highest-riding mass stands; a pose
    # on its side has its legs out level and its mass in the middle of the box)
    if not biped and dims and _flat and all(len(d) >= 4 for d in dims.values()):
        ok = {n: d[2] < max(d[0], d[1]) for n, d in dims.items()}
        for name in scores:
            d = dims.get(name)
            if d:
                scores[name] = round(d[3] * (1.0 if ok[name] else 0.3) + 0.01 * scores[name], 3)
        return {"scores": scores, "tmp": str(tmp), "tall": {n: not v for n, v in ok.items()}}
    if not biped and dims and not re.search(r"\b(giraffes?|kangaroos?|meerkats?|penguins?|seahorses?|bears? standing|ostrich\w*|emus?|flamingos?|t-?rex|dinosaurs?|raptors?|owls?|parrots?)\b", kind.lower()):
        for name, d in dims.items():
            dx, dy, dz = d[:3]
            if name in scores and dz > 1.2 * max(dx, dy):
                scores[name] = round(scores[name] * 0.3, 3)
        j_tall = {n: d[2] > 1.2 * max(d[0], d[1]) for n, d in dims.items()}
        return {"scores": scores, "tmp": str(tmp), "tall": j_tall}
    return {"scores": scores, "tmp": str(tmp)}


_TMPS: list[str] = []


def fix(glb: Path, kind: str, margin: float = 0.15, apply: bool = False, biped: bool = False, stand: bool = False) -> str:
    """The upright check, and its renders cleared after (2026-10-10: every
    bake left a folder of them in %TEMP%, 195 by the end of a day)."""
    import shutil
    try:
        return _fix(glb, kind, margin, apply, biped, stand)
    finally:
        while _TMPS:
            shutil.rmtree(_TMPS.pop(), ignore_errors=True)


def _heading(glb: Path, kind: str, base) -> list:
    """Which quarter turn about the vertical, after the turn that stands a person up,
    shows their face to a camera at +Y (Blender; glTF -Z, the way every rig faces).
    Standing a body up leaves its heading wherever the lying pose had it."""
    from app.game_export.generate import BLENDER_EXE
    import torch
    from PIL import Image
    tmp = Path(tempfile.mkdtemp(prefix="upr_"))
    _TMPS.append(str(tmp))
    rs = tmp / "r.py"; rs.write_text(_RENDER, encoding="utf-8")
    rots = {f"h{z}": [base[0], base[1], z] for z in (0, 90, 180, 270)}
    subprocess.run([str(BLENDER_EXE), "--background", "--python", str(rs), "--", str(glb), str(tmp / "v"), json.dumps(rots)],
                   capture_output=True, timeout=600)
    model, proc, dev = clip()
    texts = [f"a photo of the front of a {kind}, face toward the camera", f"a photo of the back of a {kind}",
             f"a photo of a {kind} seen from the side, in profile"]
    best, bs = [base[0], base[1], 0], -1.0
    for name, r in rots.items():
        f = tmp / f"v_{name}_b.png"                     # side b: the camera at +Y
        if not f.exists():
            continue
        with torch.no_grad():
            inp = proc(text=texts, images=[Image.open(f).convert("RGB")], return_tensors="pt", padding=True).to(dev)
            p = float(model(**inp).logits_per_image.softmax(-1)[0][0])
        if p > bs:
            best, bs = r, p
    return best


def _fix(glb: Path, kind: str, margin: float = 0.15, apply: bool = False, biped: bool = False, stand: bool = False) -> str:
    j = judge(glb, kind, biped, stand)
    sc = j["scores"]
    if not sc:
        return "render failed"
    best = max(sc, key=sc.get)
    msg = "%s %s" % (best, " ".join("%s:%.2f" % (k, v) for k, v in sorted(sc.items(), key=lambda t: -t[1])))
    # A PERSON LAID FLAT IS STOOD UP (2026-10-30): a witch's flared cloak led the
    # silhouette orienter to lay her along Z three times, and the animal-mode check
    # kept her flat (lying long is right for an animal) until she was retired as a
    # bust. Only the turns that leave the body taller than wide are weighed, by the
    # person wording, and the best of them is applied whatever the margin.
    if stand:
        _up = [n for n in sc if (j.get("tall") or {}).get(n)]
        if not _up:
            return "no turn stands it " + msg
        best = max(_up, key=sc.get)
        msg = "stood %s %s" % (best, msg)
        if best == "as_is":
            return msg
        margin = -1.0                   # applied whatever the margin, rotated as a person
        _stood = _heading(glb, kind, ROTS[best])          # and turned to face +Y (glTF -Z), like every rig
        msg += " facing z%+d" % _stood[2]
    if biped and not stand:
        margin = max(margin, 0.30)                                   # a person turned over is plain to CLIP
    if os.environ.get("QU_FORCE_FACE") == "1" and apply and best == "as_is" and not biped:
        best = "as_is"; sc[best] = 9.0                               # face-only pass on an upright model
    # stood on its tail as it is, and some turn lays it out on its legs: that turn wins
    # whatever CLIP's margin (the shape is surer than the picture here)
    _tall = j.get("tall") or {}
    if _tall.get("as_is") and not biped and not stand:
        _flat = [n for n in sc if not _tall.get(n)]
        if _flat:
            best = max(_flat, key=sc.get); margin = -1.0
            msg += " (as-is stands taller than long: laid on its legs)"
    if (best != "as_is" and sc[best] - sc.get("as_is", 0) > margin) or (os.environ.get("QU_FORCE_FACE") == "1" and apply and not biped):
        if apply:
            from app.game_export.generate import BLENDER_EXE
            rs = Path(j["tmp"]) / "rot.py"; rs.write_text(_ROTATE, encoding="utf-8")
            out = glb.with_name(glb.stem + "_uprtmp.glb")
            r = subprocess.run([str(BLENDER_EXE), "--background", "--python", str(rs), "--", str(glb), str(out),
                                json.dumps(_stood if stand else (BIPED_ROTS if biped else ROTS)[best])] + (["biped"] if (biped or stand) else []), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
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
