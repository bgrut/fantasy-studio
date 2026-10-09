"""Sharp backs and flanks for the library's people (2026-10-08).

scripts/_hd_front.py lays a character's reference photo on its front. The
chase camera mostly sees a hero from behind, and the back and the flanks were
still the coat: smooth, a vertex a few centimetres across. For each person:

1. scripts/_hd_views_render.py renders the coated rest pose straight-on from
   the back and both flanks, orthographic, the camera written to JSON;
2. each render is repainted photographically by SDXL img2img (strength
   ~0.62: real fabric, seams and folds, the silhouette kept), prompted with
   the person's own wardrobe and the side being seen;
3. _hd_front.py projects the reference photo on the front and the repaints on
   the rest (--extra), each through its known camera.

The coated original is kept in renders/_coat_backup_hdfront/.

    python tools/hd_views.py [name ...] [--strength 0.62]
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BK))
LIB = BK / "assets" / "library"
CACHE = BK / "renders" / "_actor_cache"
BACKUP = BK / "renders" / "_coat_backup_hdfront"
RENDER = BK / "scripts" / "_hd_views_render.py"
FRONT = BK / "scripts" / "_hd_front.py"
VIEWS = {"front": "facing the camera, front view",
         "back": "seen from behind, back view, the back of the head",
         "left": "seen from the side, side view, profile",
         "right": "seen from the side, side view, profile"}
HEAD_VIEWS = {"head_front": "facing the camera, front view",
              "head_left34": "three-quarter view, turned slightly to the side",
              "head_right34": "three-quarter view, turned slightly to the side",
              "head_left": "side profile view",
              "head_right": "side profile view"}
HEAD_STRENGTH = float(os.environ.get("FS_HDHEAD_STRENGTH", "0.45"))
ANIMAL_VIEWS = {"front": "photographed straight on", "back": "photographed straight on", "left": "photographed straight on", "right": "photographed straight on",
                "head_front": "head seen from the front", "head_left34": "head in three-quarter view", "head_right34": "head in three-quarter view",
                "head_left": "head in side profile", "head_right": "head in side profile"}
NEG_ANIMAL = ("cartoon, illustration, painting, 3d render, cgi, plastic, toy, blurry, low detail, deformed, extra legs, extra eyes, "
              "two heads, text, logo, watermark, person, human")
# NO MARKS (2026-10-09): a soccer jersey came back with a sports brand's swoosh
# and a crest, a firefighter's helmet with made-up letters; nothing that ships
# may carry a mark, so the marks lead the negative, where SDXL weighs it most
NEG = ("text, lettering, letters, words, logo, brand logo, swoosh, crest, emblem, badge, trademark, sponsor, "
       "cartoon, illustration, painting, 3d render, cgi, plastic, smooth, blurry, low detail, deformed, extra limbs, "
       "extra arms, face on the back of the head, text, logo, watermark, nude, bare skin, underwear")


def wardrobe(kind: str) -> str:
    """The person's outfit from the reference generator's own table, longest name first."""
    src = (BK / "app" / "asset_gen" / "reference.py").read_text(encoding="utf-8")
    i = src.find("char_hints = {"); j = src.find("\n        }", i)
    table = dict(re.findall(r'^\s+"([a-z][a-z \-]*)":\s*"([^"]+)"', src[i:j], re.M))
    for key in sorted(table, key=len, reverse=True):
        if re.search(r"\b" + re.escape(key) + r"s?\b", kind.lower()):
            return table[key]
    return f"{kind}, fully clothed"


_PIPE = None


_CN = None


def cn_pipe():
    """SDXL with the depth ControlNet: a face painted onto its own geometry."""
    global _CN
    if _CN is None:
        from app.asset_gen.reference import _load_t2i_controlnet_pipeline
        _CN = _load_t2i_controlnet_pipeline()
    return _CN


def pipe():
    global _PIPE
    if _PIPE is None and os.environ.get("FS_HDV_SHARED", "1") == "1":
        # one set of SDXL weights for both: the img2img shares the ControlNet
        # pipeline's (two copies did not fit the card beside TRELLIS's leftovers)
        from diffusers import StableDiffusionXLImg2ImgPipeline
        c = cn_pipe()
        _PIPE = StableDiffusionXLImg2ImgPipeline(vae=c.vae, text_encoder=c.text_encoder, text_encoder_2=c.text_encoder_2,
                                                 tokenizer=c.tokenizer, tokenizer_2=c.tokenizer_2, unet=c.unet, scheduler=c.scheduler)
    if _PIPE is None:
        import torch
        from app.asset_gen.reference import _evict_llms
        _evict_llms()
        from diffusers import StableDiffusionXLImg2ImgPipeline, AutoencoderKL
        vae = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=torch.float16)
        _PIPE = StableDiffusionXLImg2ImgPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0", vae=vae, torch_dtype=torch.float16, variant="fp16",
            use_safetensors=True).to("cuda")
    return _PIPE


def repaint(src: Path, dst: Path, prompt: str, strength: float, seed: int = 42, neg: str = None):
    import torch
    from PIL import Image
    img = Image.open(src).convert("RGB").resize((1024, 1024))
    g = torch.Generator("cuda").manual_seed(seed)
    from app.asset_gen.reference import _long_prompt_kwargs       # the whole negative, not its first 77 tokens
    _p = pipe()
    out = _p(**_long_prompt_kwargs(_p, prompt, neg or NEG), image=img, strength=strength, guidance_scale=6.5,
                 num_inference_steps=36, generator=g).images[0]
    out.save(dst)


def head_hr(ref: Path, outfit: str, dst: Path, strength: float = 0.5):
    """THE FACE AT ITS OWN SIZE (2026-10-08, the user: close-ups of the
    characters were blurry). In a full-length reference the head is forty or
    fifty pixels across, so the front's projection had nothing finer to give
    the face than that. The head is found at the top of the photo's figure,
    cropped square, enlarged to 1024 and repainted at half strength as a
    close-up portrait: the same face, pose and colouring, with skin, eyes and
    hair at the size a close-up needs. Its colour is matched back to the crop's
    so it lands at the photo's tone. Returns the box in reference pixels."""
    import numpy as np
    from PIL import Image
    im = Image.open(ref).convert("RGB"); W, H = im.size
    R = np.asarray(im, dtype=np.float32) / 255.0
    E = max(24, W // 16)
    bg = np.median(np.concatenate([R[:, :E], R[:, -E:]], axis=1), axis=1)
    fig = np.linalg.norm(R - bg[:, None, :], axis=2) > 0.11
    fig &= (fig.sum(1, keepdims=True) > 3) & (fig.sum(0, keepdims=True) > 3)
    ys = np.where(fig.any(1))[0]
    if len(ys) < 50:
        return None
    top, bot = int(ys[0]), int(ys[-1]); Hf = bot - top
    band = fig[top:top + int(0.12 * Hf)]
    bx = np.where(band)[1]
    if len(bx) < 50 or Hf < 200:
        return None
    cx = float(np.median(bx)); cy = top + 0.075 * Hf; s = 0.17 * Hf
    box = (int(round(cx - s / 2)), int(round(cy - s / 2)), int(round(cx + s / 2)), int(round(cy + s / 2)))
    if box[0] < 0 or box[1] < 0 or box[2] > W or box[3] > H:
        return None
    crop = im.crop(box).resize((1024, 1024), Image.LANCZOS)
    import torch
    g = torch.Generator("cuda").manual_seed(7)
    prompt = (f"close-up portrait photograph of the face of a {outfit}, looking at the camera, natural skin texture, "
              f"detailed eyes, sharp focus, DSLR, 85mm, soft studio light, plain grey backdrop")
    out = pipe()(prompt=prompt, negative_prompt="painting, illustration, drawing, " + NEG, image=crop, strength=strength,
                 guidance_scale=6.0, num_inference_steps=40, generator=g).images[0]
    a = np.asarray(out, dtype=np.float32); b = np.asarray(crop, dtype=np.float32)
    a = (a - a.mean((0, 1))) / (a.std((0, 1)) + 1e-3) * b.std((0, 1)) + b.mean((0, 1))
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(dst)
    return box


def depth_face(depth_png: Path, dst: Path, prompt: str, neg: str, colour_ref=None, seed: int = 42):
    """THE FACE ON ITS OWN GEOMETRY (2026-10-08). The front of the head is
    painted by SDXL against the head's depth: every feature lands where the
    geometry has it (eyes in the sockets, nose on the nose), sharp, whatever
    the coat or the photo got wrong. The depth is stretched over its own
    silhouette so the face's relief reads; the result is matched in colour to
    colour_ref (the photo's head, or the coat's) inside the silhouette."""
    import numpy as np
    import torch
    from PIL import Image
    d = np.asarray(Image.open(depth_png).convert("L"), dtype=np.float32) / 255.0
    m = d > 0.02
    if m.sum() < 1000:
        return False
    lo, hi = np.percentile(d[m], 2), np.percentile(d[m], 99.5)
    d2 = np.where(m, 0.25 + 0.75 * np.clip((d - lo) / max(hi - lo, 1e-3), 0, 1) ** 0.9, 0.0)
    dimg = Image.fromarray((d2 * 255).astype(np.uint8)).convert("RGB").resize((1024, 1024))
    g = torch.Generator("cuda").manual_seed(seed)
    # a depth map alone pulled the engineer and the dog into line drawings: the
    # medium leads, the negative opens against drawing, and both prompts are
    # read whole (reference._long_prompt_kwargs), not cut at 77 tokens
    from app.asset_gen.reference import _long_prompt_kwargs
    c = cn_pipe()
    neg2 = ("illustration, drawing, line art, sketch, cartoon, anime, painting, vector art, flat colours, 3d render, cgi, "
            "text, letters, lettering, words, logo, badge text, "
            "doll, mannequin, " + neg)
    kw = _long_prompt_kwargs(c, "RAW photo, " + prompt + ", photorealistic, real skin, natural colour", neg2)
    out = c(**kw, image=dimg, controlnet_conditioning_scale=0.7,
            guidance_scale=6.0, num_inference_steps=34, generator=g, width=1024, height=1024).images[0]
    a = np.asarray(out, dtype=np.float32)
    mm = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((1024, 1024))) > 127
    if colour_ref is not None and mm.sum() > 1000:
        ref_mu, ref_sd = colour_ref
        hp = a[mm]
        # measured on the generated face's own skin (the reference is skin only),
        # applied to the whole head
        r_, g_, b_ = hp[:, 0], hp[:, 1], hp[:, 2]
        sk = (r_ > g_) & (g_ >= b_ * 0.9) & (r_ - b_ > 12) & (r_ - b_ < 120) & (r_ > 50) & ((r_ - g_) < 70)
        src = hp[sk] if sk.sum() > 500 else hp
        mu, sd = src.mean(0), src.std(0) + 1e-3
        k = 0.8                                           # most of the way to the reference's colouring
        a[mm] = (a[mm] - mu) / sd * (sd + (ref_sd - sd) * k) + (mu + (ref_mu - mu) * k)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(dst)
    return True


def photo_head_colour(ref: Path):
    """Mean and spread of the reference photo's head (top of the figure), for depth_face."""
    import numpy as np
    from PIL import Image
    im = Image.open(ref).convert("RGB"); R = np.asarray(im, dtype=np.float32) / 255.0
    W, H = im.size; E = max(24, W // 16)
    bg = np.median(np.concatenate([R[:, :E], R[:, -E:]], axis=1), axis=1)
    fig = np.linalg.norm(R - bg[:, None, :], axis=2) > 0.11
    ys = np.where(fig.any(1))[0]
    if len(ys) < 50:
        return None
    top, bot = int(ys[0]), int(ys[-1]); Hf = bot - top
    band = fig[top:top + int(0.13 * Hf)]
    px = (R[top:top + int(0.13 * Hf)][band] * 255.0)
    # SKIN ONLY (2026-10-09): the head's band holds the hat too, and a red
    # helmet turned a firefighter's face red. Skin is warm (red over green over
    # blue) and not grey; matched on that, or not matched at all.
    r_, g_, b_ = px[:, 0], px[:, 1], px[:, 2]
    skin = (r_ > g_) & (g_ >= b_ * 0.9) & (r_ - b_ > 12) & (r_ - b_ < 120) & (r_ > 50) & ((r_ - g_) < 70)
    px = px[skin]
    if len(px) < 200:
        return None
    return px.mean(0), px.std(0)


def photo_hair(ref: Path) -> str:
    """The hair's tone from the top of the photo's figure, for the face prompt:
    a freely painted face gave a woman with a black bun a pale hairline (2026-10-08)."""
    import numpy as np
    from PIL import Image
    try:
        im = Image.open(ref).convert("RGB"); R = np.asarray(im, dtype=np.float32) / 255.0
        W, H = im.size; E = max(24, W // 16)
        bg = np.median(np.concatenate([R[:, :E], R[:, -E:]], axis=1), axis=1)
        fig = np.linalg.norm(R - bg[:, None, :], axis=2) > 0.11
        ys = np.where(fig.any(1))[0]
        top, bot = int(ys[0]), int(ys[-1]); Hf = bot - top
        band = R[top:top + max(4, int(0.035 * Hf))][fig[top:top + max(4, int(0.035 * Hf))]]
        if len(band) < 50:
            return ""
        l = float((band @ np.array([0.299, 0.587, 0.114])).mean())
        sat = float((band.max(1) - band.min(1)).mean())
        if l < 0.22:
            return "black hair"
        if l < 0.36:
            return "dark brown hair"
        if l > 0.62 and sat < 0.25:
            return "blonde hair" if band[:, 0].mean() > band[:, 2].mean() + 0.03 else "grey hair"
        return "brown hair"
    except Exception:
        return ""


def upgrade(anim: Path, strength=0.62, verbose=True) -> str:
    from app.game_export.generate import BLENDER_EXE
    kind = anim.stem[:-len("_anim")].replace("_", " ")
    ref = CACHE / (hashlib.md5(kind.lower().encode("utf-8")).hexdigest()[:12] + "_ref.png")
    from app.game_export.generate import guess_pattern as _gp
    noref = not ref.exists()
    if noref:
        # NO PHOTO, STILL A FACE (2026-10-09): an older person made before the
        # references were kept (a knight, a viking, a wizard) is painted like an
        # animal, from its own views and its own depth, its colour from its coat
        ref = Path(__file__).resolve().parents[1] / "scripts" / "_hd_noref.png"
        if not ref.exists():
            from PIL import Image as _I
            _I.new("RGB", (64, 64), (110, 110, 112)).save(ref)
    # a drawn hero stays drawn: the repaint asks for a photograph
    if kind.split()[0] in ("toon", "anime", "clay", "blocky"):
        return "stylised, left as it is"
    from app.game_export.generate import guess_pattern
    animal = guess_pattern(kind) == "quadruped"
    # the coated original, unless the character was made again since (a stale backup is another body)
    static = LIB / (anim.stem[:-len("_anim")] + ".glb")
    bk = BACKUP / anim.name
    fresh = bk.exists() and not (static.exists() and static.stat().st_mtime > bk.stat().st_mtime)
    coated = bk if fresh else anim
    if not fresh and bk.exists():
        bk.unlink()
    tmp = Path(tempfile.mkdtemp(prefix="hdv_"))
    try:
        def render(src, prefix, views, flat=False):
            subprocess.run([str(BLENDER_EXE), "--background", "--python", str(RENDER), "--", str(src), str(tmp / prefix),
                            ",".join(views)] + (["flat"] if flat else []) + (["animal"] if animal else ["person"]),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
            return (tmp / (prefix + ".json")).exists()

        plated = any(w in kind for w in ("robot", "knight", "astronaut", "android", "cyborg", "armor", "armour", "mech"))

        def project(src, dst, extras):
            extras = extras + ([] if (animal or plated) else ["--matte"])
            r = subprocess.run([str(BLENDER_EXE), "--background", "--python", str(FRONT), "--", str(src), str(ref), str(dst)] + extras,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
            line = next((l for l in (r.stdout or "").splitlines() if l.startswith(("HDF ", "HDFAIL"))), "HDFAIL no result")
            return line if (line.startswith("HDF ") and dst.exists()) else (line if not line.startswith("HDF ") else "HDFAIL no output")

        outfit = wardrobe(kind) if not animal else f"real {kind}"
        neg_head = (NEG_ANIMAL if animal else NEG) + ", deformed face, asymmetric eyes, extra eyes, two noses, double face"
        # 1. the body: the photo on the front (a person's), repaints on every side,
        #    and nothing of the photo on the head, which is painted next
        if not render(coated, "v", list(VIEWS)):
            return "render failed"
        extras = []
        for v, phrase in VIEWS.items():
            if animal:
                prompt = (f"raw photograph, DSLR, of a {outfit}, {ANIMAL_VIEWS.get(v, phrase)}, whole animal standing, "
                          f"natural light, plain grey backdrop, sharp focus, detailed fur, natural colouring")
            else:
                prompt = (f"raw photograph, DSLR, of a real {outfit}, {phrase}, full body, standing with arms out, "
                          f"soft studio light, plain grey backdrop, sharp focus, detailed fabric texture, seams and folds")
            repaint(tmp / f"v_{v}.png", tmp / f"r_{v}.png", prompt, strength, neg=NEG_ANIMAL if animal else NEG)
            extras += ["--extra", f"{tmp / f'r_{v}.png'}|{tmp / 'v.json'}|{v}"]
        stage = tmp / "s0.glb"
        line = project(coated, stage, extras + (["--nophoto"] if (animal or noref) else ["--nohead"]))
        if not line.startswith("HDF "):
            return line
        # 2. THE HEAD IN STEPS, EACH FROM THE LAST (2026-10-08). Repainted
        #    independently, the five head views came back as five slightly
        #    different people (a cap in one, another skin in the next), and
        #    blended they were mush. The front is painted first; the three-
        #    quarters are rendered from the front's result, so they already
        #    show this face and only their cheeks are new; the profiles last.
        #    Rendered flat, so no light is painted in once per step.
        steps = [(["head_front"], HEAD_STRENGTH), (["head_left34", "head_right34"], 0.36), (["head_left", "head_right"], 0.36)]
        for si, (views, st) in enumerate(steps):
            pre = f"h{si}"
            if not render(stage, pre, views + ([v + "_depth" for v in views] if si == 0 else []), flat=(si > 0)):
                break
            ex = []
            if si == 0 and os.environ.get("FS_HDV_DEPTHFACE", "1") == "1":
                v = views[0]
                if animal:
                    prompt = (f"close-up photograph of the head of a {outfit}, head seen from the front, detailed fur, "
                              f"clear bright eyes, sharp focus, natural light, plain grey backdrop")
                    import numpy as _np
                    from PIL import Image as _I
                    _a = _np.asarray(_I.open(tmp / f"{pre}_{v}.png").convert("RGB"), dtype=_np.float32)
                    _m = _np.abs(_a - _np.array([107.0, 107.0, 110.0])).sum(2) > 18
                    cref = (_a[_m].mean(0), _a[_m].std(0)) if _m.sum() > 1000 else None
                else:
                    hair = "" if noref else photo_hair(ref)
                    prompt = (f"close-up portrait photograph of a real {outfit}, {hair + ', ' if hair else ''}facing the camera, natural skin texture, pores, "
                              f"clear detailed eyes, sharp focus, 85mm, soft even studio light, plain grey backdrop")
                    if noref:
                        import numpy as _np
                        from PIL import Image as _I
                        _a = _np.asarray(_I.open(tmp / f"{pre}_{v}.png").convert("RGB"), dtype=_np.float32).reshape(-1, 3)
                        r_, g_, b_ = _a[:, 0], _a[:, 1], _a[:, 2]
                        _sk = (r_ > g_) & (g_ >= b_ * 0.9) & (r_ - b_ > 12) & (r_ - b_ < 120) & (r_ > 50) & ((r_ - g_) < 70)
                        cref = (_a[_sk].mean(0), _a[_sk].std(0)) if _sk.sum() > 800 else None
                    else:
                        cref = photo_head_colour(ref)
                if depth_face(tmp / f"{pre}_{v}_depth.png", tmp / f"r_{v}.png", prompt, neg_head, cref):
                    ex += ["--extra", f"{tmp / f'r_{v}.png'}|{tmp / (pre + '.json')}|{v}"]
                nxt = tmp / f"s{si + 1}.glb"
                if ex and project(stage, nxt, ex + ["--keepuv", "--nophoto"]).startswith("HDF "):
                    stage = nxt
                continue
            for v in views:
                phrase = HEAD_VIEWS[v]
                if animal:
                    prompt = (f"close-up photograph of the head of a {outfit}, {ANIMAL_VIEWS.get(v, phrase)}, detailed fur, "
                              f"clear bright eyes, sharp focus, natural light, plain grey backdrop")
                else:
                    prompt = (f"close-up portrait photograph of a real {outfit}, {phrase}, natural skin texture, pores, "
                              f"clear detailed eyes, sharp focus, 85mm, soft even studio light, plain grey backdrop")
                repaint(tmp / f"{pre}_{v}.png", tmp / f"r_{v}.png", prompt, st, neg=neg_head)
                ex += ["--extra", f"{tmp / f'r_{v}.png'}|{tmp / (pre + '.json')}|{v}"]
            nxt = tmp / f"s{si + 1}.glb"
            fd = []
            try:
                fdir = json.loads((tmp / "h0.json").read_text())["views"]["head_front"]["dir"]
                fd = ["--frontdir", ",".join("%.6f" % x for x in fdir)]
            except Exception:
                pass
            if project(stage, nxt, ex + ["--keepuv", "--nophoto"] + fd).startswith("HDF "):
                stage = nxt
        out = anim.with_name(anim.stem + "_hdvtmp.glb")
        shutil.copy2(str(stage), str(out))
        BACKUP.mkdir(parents=True, exist_ok=True)
        if not (BACKUP / anim.name).exists():
            shutil.copy2(anim, BACKUP / anim.name)
        shutil.move(str(out), str(anim))
        keep = BK / "renders" / "_hd_views" / anim.stem
        keep.mkdir(parents=True, exist_ok=True)
        for f in tmp.glob("r_*.png"):
            shutil.copy2(f, keep / f.name)
        return line + " +views"
    finally:
        if os.environ.get("FS_HDV_KEEP") == "1":
            print("HDV kept", tmp, flush=True)
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    st = float(sys.argv[sys.argv.index("--strength") + 1]) if "--strength" in sys.argv else 0.62
    if "--strength" in sys.argv:
        args = [a for a in args if a != sys.argv[sys.argv.index("--strength") + 1]]
    files = [LIB / f"{a.replace(' ', '_')}_anim.glb" for a in args] if args else sorted(
        f for f in LIB.glob("*_anim.glb") if (BACKUP / f.name).exists())
    for f in files:
        if not f.exists():
            print(f"{f.name}: missing", flush=True); continue
        try:
            print(f"{f.name}: {upgrade(f, st)}", flush=True)
        except Exception as e:
            print(f"{f.name}: error {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    main()
