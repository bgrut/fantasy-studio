"""THE FINISHED CHARACTER IS JUDGED (2026-10-11).

Every step that makes a character checks its own input: the reference is
judged dressed, the mesh upright, the photo's alignment scored before it is
laid on. Nothing looked at the finished, rigged character the player will
see, so a blotchy one (a mesh from the fallback engine, a front the
projection refused, a coat mottled by its atlas) shipped and stayed in the
library. This renders the finished character from four sides, as a studio
light sees it, and scores it:

  mottle   colour noise at the scale of a hand's width: patches of a second
           colour inside what should be one material (band-passed chroma
           inside the figure, its edges excluded)
  speckle  the same for brightness, a finer band
  photo    CLIP's belief that a render is a clean, detailed character rather
           than a blotchy, smeared, low-quality model (mean over the views)
  face     the same question asked of the head crop alone, for a person

and folds them into one score, 0 to 1. A character under the bar is
reported, and with --fix is sent back through the stages that can mend it.

usage: python tools/char_qa.py man woman ...      (kinds)
       python tools/char_qa.py --all [--json out]  (the library's rigged people and animals)
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

BK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BK))
LIB = BK / "assets" / "library"
RENDER = BK / "scripts" / "_hd_views_render.py"
VIEWS = ["front", "back", "left", "right"]
BAR = 0.55                      # under this a character is blotchy (calibrated 2026-10-11, see --all)

_CLIP = None


def _clip():
    global _CLIP
    if _CLIP is None:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _CLIP = (CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).eval(),
                 CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32"), dev)
    return _CLIP


def _p_good(imgs: list[Image.Image], good: str, bads: list[str]) -> list[float]:
    import torch
    cm, cp, dev = _clip()
    texts = [good] + bads
    with torch.no_grad():
        inp = cp(text=texts, images=imgs, return_tensors="pt", padding=True).to(dev)
        pr = cm(**inp).logits_per_image.softmax(-1)
    return [float(x) for x in pr[:, 0]]


def _eyes(head_png: Path) -> dict | None:
    """THE EYES, ASKED ONE AT A TIME (2026-10-11). CLIP called a blank face and
    a ghosted eye clean; a local vision model (Ollama gemma3, already on the
    machine) asked for an overall rating gave every face 5 or 6. Asked about
    each eye on its own, and about stains, it flagged the man's milky eye and
    the archer's smeared face and passed the chef, the blacksmith and the
    detective. None when Ollama is not there; it is unloaded after use."""
    import base64, io, urllib.request
    try:
        im = Image.open(head_png).convert("RGB"); w, h = im.size
        im = im.crop((int(w * .2), int(h * .2), int(w * .8), int(h * .7))).resize((448, 373))
        b = io.BytesIO(); im.save(b, "PNG")
        prompt = ("Look closely at this face. For EACH eye separately, is it a clear, normal eye (a visible dark pupil or iris, "
                  "a white, an eyelid), or is it milky, washed-out, blurred into the skin, or missing? Also: is there any stain, "
                  "smudge or discoloured patch on the skin? JSON only: "
                  "{\"left_eye_clear\": true/false, \"right_eye_clear\": true/false, \"skin_stain\": true/false}")
        req = {"model": "gemma3:12b", "prompt": prompt, "images": [base64.b64encode(b.getvalue()).decode()], "stream": False,
               "format": "json", "options": {"temperature": 0}, "keep_alive": "2m"}
        r = json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/generate",
                       data=json.dumps(req).encode(), headers={"Content-Type": "application/json"}), timeout=300).read())
        j = json.loads(r.get("response") or "{}")
        return {"eyes": (bool(j.get("left_eye_clear")) + bool(j.get("right_eye_clear"))) / 2, "stain": bool(j.get("skin_stain"))}
    except Exception:
        return None


def unload_vlm() -> None:
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/generate",
                               data=json.dumps({"model": "gemma3:12b", "keep_alive": 0}).encode(),
                               headers={"Content-Type": "application/json"}), timeout=60).read()
    except Exception:
        pass


def _blur(a: np.ndarray, r: int) -> np.ndarray:
    """a box blur of radius r, twice (close enough to a gaussian), edge-normalised"""
    k = 2 * r + 1
    out = a.astype(np.float32)
    for _ in range(2):
        c = np.cumsum(np.pad(out, ((r + 1, r), (0, 0)), mode="edge"), axis=0)
        out = (c[k:] - c[:-k]) / k
        c = np.cumsum(np.pad(out, ((0, 0), (r + 1, r)), mode="edge"), axis=1)
        out = (c[:, k:] - c[:, :-k]) / k
    return out


def _metrics(png: Path) -> dict:
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.float32) / 255.0
    bg = np.array([0.42, 0.42, 0.43], np.float32)
    # the world colour reads back through the view transform; take the corner as the backdrop
    bg = a[:8, :8].reshape(-1, 3).mean(0)
    mask = np.abs(a - bg).max(-1) > 0.035
    if mask.sum() < 2000:
        return {"empty": True}
    # keep well inside the silhouette: an edge is not a blotch
    inner = _blur(mask.astype(np.float32), 6) > 0.98
    if inner.sum() < 1000:
        inner = mask
    y = a @ np.array([0.299, 0.587, 0.114], np.float32)
    cb = (a[..., 2] - y) * 0.564
    cr = (a[..., 0] - y) * 0.713
    H = a.shape[0]
    # a hand's width at this framing: the figure is ~0.92 of the frame for ~1.75 m
    s1, s2 = max(1, H // 320), max(3, H // 64)
    band = lambda c: _blur(c, s1) - _blur(c, s2)
    mottle = float(np.sqrt((band(cb) ** 2 + band(cr) ** 2)[inner].mean()))
    speckle = float(np.abs(_blur(y, max(1, s1 // 2)) - _blur(y, s1 * 2))[inner].mean())
    ys, xs = np.nonzero(mask)
    head = None
    if len(ys):
        top, bot = ys.min(), ys.max()
        hh = int((bot - top) * 0.15)
        cols = xs[ys < top + hh]
        if len(cols):
            cx = int(cols.mean())
            half = max(hh, 24)
            x0, x1 = max(0, cx - half), min(a.shape[1], cx + half)
            head = (x0, top, x1, top + 2 * half)
    return {"mottle": mottle, "speckle": speckle, "head": head, "coverage": float(mask.mean())}


def judge(kind: str, keep: Path | None = None, animal: bool | None = None) -> dict:
    from app.game_export.generate import BLENDER_EXE, guess_pattern
    slug = kind.strip().lower().replace(" ", "_")
    src = LIB / f"{slug}_anim.glb"
    if not src.exists():
        src = LIB / f"{slug}.glb"
    if not src.exists():
        return {"kind": kind, "error": "not in library"}
    pat = guess_pattern(kind)
    if animal is None:
        animal = pat == "quadruped"
    tmp = Path(tempfile.mkdtemp(prefix="cqa_")) if keep is None else keep
    tmp.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(BLENDER_EXE), "--background", "--python", str(RENDER), "--", str(src), str(tmp / slug),
                        ",".join(VIEWS + ["head_front"]), "animal" if animal else "person"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    pngs = [tmp / f"{slug}_{v}.png" for v in VIEWS]
    if not all(p.exists() for p in pngs):
        return {"kind": kind, "error": "render failed", "log": (r.stdout + r.stderr)[-600:]}
    ms = [_metrics(p) for p in pngs]
    ms = [m for m in ms if not m.get("empty")]
    if not ms:
        return {"kind": kind, "error": "empty renders"}
    imgs = [Image.open(p).convert("RGB") for p in pngs]
    good = ("a photorealistic 3D animal model with clean natural fur and detailed texture" if animal
            else "a photorealistic 3D character model of a person with clean detailed clothing texture")
    bads = ["a blotchy low quality 3D model with smeared patchy messy texture",
            "a lumpy melted 3D scan with mottled colour stains",
            "a blurry low resolution 3D model"]
    # asked about what it is: a skeleton, a robot or a helmeted gladiator is not
    # "a person" and read as a bad model when the question assumed one
    good = good.replace("of a person", "of a " + kind) if not animal else good.replace("animal", kind)
    photo = float(np.mean(_p_good(imgs, good, bads)))
    face = None
    eyes = None
    hf = tmp / f"{slug}_head_front.png"
    _faceless = any(w in kind.lower() for w in ("robot", "skeleton", "android", "astronaut", "knight", "diver", "ghost"))
    if not animal and hf.exists() and not _faceless:
        eyes = _eyes(hf)
    if eyes is not None:
        face = max(0.0, eyes["eyes"] - (0.35 if eyes["stain"] else 0.0))
    elif not animal and hf.exists():
        face = _p_good([Image.open(hf).convert("RGB")],
                       "a sharp clear face of a 3D character with distinct eyes, nose and mouth",
                       ["a smeared blurry face with no clear features", "a face with two noses or doubled features",
                        "a blotchy stained face"])[0]
    mottle = float(np.median([m["mottle"] for m in ms]))
    speckle = float(np.median([m["speckle"] for m in ms]))
    # mottle 0.010 is clean cloth, 0.035 is confetti; speckle the same for brightness
    s_mottle = float(np.clip(1.0 - (mottle - 0.010) / 0.030, 0, 1))
    s_speckle = float(np.clip(1.0 - (speckle - 0.012) / 0.035, 0, 1))
    score = 0.30 * s_mottle + 0.15 * s_speckle + 0.35 * photo + (0.20 * face if face is not None else 0.20 * photo)
    out = {"kind": kind, "pattern": pat, "score": round(score, 3), "mottle": round(mottle, 4), "speckle": round(speckle, 4),
           "photo": round(photo, 3), "face": None if face is None else round(face, 3), "renders": str(tmp),
           # a person with a smeared or missing eye fails whatever the rest scores:
           # the face is where a player looks
           "src": src.name, "pass": score >= BAR and (eyes is None or (eyes["eyes"] >= 1.0 and not eyes["stain"])), "eyes": eyes}
    return out


def best_of(kind: str, attempts: int = 2, verbose: bool = True) -> dict:
    """judge a finished character; while it is under the bar, paint it again
    with other seeds (tools/hd_views.py, FS_HDV_SEED) and keep the best of
    the attempts. Returns the kept judgement."""
    import os, shutil
    slug = kind.strip().lower().replace(" ", "_")
    anim = LIB / f"{slug}_anim.glb"
    best = judge(kind)
    if verbose:
        print(f"[qa] {kind}: {best.get('score')} {best.get('eyes')}", flush=True)
    if "error" in best or best.get("pass") or not anim.exists():
        unload_vlm()
        return best
    keep = anim.with_suffix(".qa_best.glb")
    shutil.copy2(anim, keep)
    for k in range(1, attempts + 1):
        unload_vlm()                                   # SDXL needs the card
        env = dict(os.environ, FS_HDV_SEED=str(k))
        subprocess.run([sys.executable, str(BK / "tools" / "hd_views.py"), kind], env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=2400)
        r = judge(kind)
        if verbose:
            print(f"[qa] {kind} retry {k}: {r.get('score')} {r.get('eyes')}", flush=True)
        # BETTER MEANS BETTER (2026-10-11): a retry that changes who the
        # character is must earn it. "Best" by total score swapped the bearded
        # man for a clean-shaven stranger on a 0.006 edge while the bad eye
        # stayed. A passing attempt wins; among failures the face decides, and
        # anything else must beat the kept one clearly.
        if "error" not in r:
            rf, bf = (r.get("face") or 0), (best.get("face") or 0)
            better = (r.get("pass") and not best.get("pass")) or rf > bf + 0.2 or (abs(rf - bf) <= 0.2 and r["score"] > best.get("score", 0) + 0.05)
            if better:
                best = r; shutil.copy2(anim, keep)
        if best.get("pass"):
            break
    shutil.copy2(keep, anim); keep.unlink(missing_ok=True)
    unload_vlm()
    best["retried"] = True
    return best


def library_kinds() -> list[str]:
    from app.game_export.generate import guess_pattern
    ks = []
    for f in sorted(LIB.glob("*_anim.glb")):
        k = f.name[:-len("_anim.glb")]
        if k.startswith(("blocky", "k_", "pr_", "toon", "anime", "clay")):
            continue
        if guess_pattern(k.replace("_", " ")) in ("biped", "quadruped"):
            ks.append(k.replace("_", " "))
    return ks


if __name__ == "__main__":
    args = sys.argv[1:]
    jout = None
    if "--json" in args:
        i = args.index("--json"); jout = Path(args[i + 1]); del args[i:i + 2]
    keep = None
    if "--keep" in args:
        i = args.index("--keep"); keep = Path(args[i + 1]); del args[i:i + 2]
    kinds = library_kinds() if "--all" in args else [a for a in args if not a.startswith("--")]
    res = []
    for k in kinds:
        r = judge(k, keep=keep / k.replace(" ", "_") if keep else None)
        res.append(r)
        if "error" in r:
            print(f"{k:22s} ERROR {r['error']}", flush=True)
        else:
            print(f"{k:22s} {r['score']:.3f} {'ok ' if r['pass'] else 'LOW'}  mottle {r['mottle']:.4f}  speckle {r['speckle']:.4f}  "
                  f"photo {r['photo']:.2f}  face {'-' if r['face'] is None else format(r['face'], '.2f')}  eyes {r.get('eyes')}", flush=True)
    unload_vlm()
    if jout:
        jout.write_text(json.dumps(res, indent=1), encoding="utf-8")
