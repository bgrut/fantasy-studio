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


def depth_face(depth_png: Path, dst: Path, prompt: str, neg: str, colour_ref=None, seed: int = 42, skin_wanted: bool = True, style: str = "photo",
               cn_scale: float = 0.7, hair_rgb=None):
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
    # a depth map alone pulled the engineer and the dog into line drawings: the
    # medium leads, the negative opens against drawing, and both prompts are
    # read whole (reference._long_prompt_kwargs), not cut at 77 tokens
    from app.asset_gen.reference import _long_prompt_kwargs
    c = cn_pipe()
    if style == "anime":
        # a drawn hero keeps its drawing: the face is drawn, onto its own geometry
        neg2 = ("photo, photograph, photorealistic, realistic skin, 3d render, black and white, monochrome, "
                "text, letters, logo, " + neg)
        kw = _long_prompt_kwargs(c, prompt, neg2)
    else:
        neg2 = ("black and white, monochrome, grayscale, sepia, desaturated, "
                "illustration, drawing, line art, sketch, cartoon, anime, painting, vector art, flat colours, 3d render, cgi, "
                "low poly, polygonal, faceted, geometric shapes, triangles, wireframe, stained glass, mosaic, outlines, "
                "construction lines, guide lines, concentric lines, contour lines, signature, watermark, "
                "text, letters, lettering, words, logo, badge text, "
                "doll, mannequin, " + neg)
        kw = _long_prompt_kwargs(c, "RAW colour photo, " + prompt + ", photorealistic, real skin, natural colour", neg2)
    mm = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((1024, 1024))) > 127

    def _skin_share(arr):
        hp_ = arr[mm]
        r_, g_, b_ = hp_[:, 0], hp_[:, 1], hp_[:, 2]
        return float(((r_ > g_) & (g_ >= b_ * 0.9) & (r_ - b_ > 12) & (r_ - b_ < 120) & (r_ > 50)).mean())
    # A COLOUR FACE (2026-10-09): a scientist in a white coat with greying hair came
    # out a black-and-white photograph, and colour matching cannot add colour that
    # is not there. Up to three draws; the one with the most real skin is kept.
    # FUR, NOT FACETS (2026-10-09): a grizzly's head came out low-poly art, flat
    # panels edged in lines, and was painted on as it was. Pixel statistics
    # could not tell it from fur; CLIP can. Where no skin is wanted each draw
    # is asked whether it is a photograph or drawn, faceted art.
    def _fine(arr):
        from transformers import CLIPModel, CLIPProcessor
        global _CLIPF
        if "_CLIPF" not in globals():
            _CLIPF = (CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to("cuda").eval(),
                      CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32"))
        cm, cp = _CLIPF
        texts = ["a close-up photograph of a real animal's head with fur",
                 "low poly geometric polygon art", "an illustration or drawing with outlines"]
        with torch.no_grad():
            inp = cp(text=texts, images=[Image.fromarray(arr.astype(np.uint8))], return_tensors="pt", padding=True).to("cuda")
            return float(cm(**inp).logits_per_image.softmax(-1)[0, 0])
    best_a, best_s = None, -1.0
    # HER OWN HAIR (2026-10-10): a drawn head given "black hair" still came back
    # silver; with the hair's colour known, the draw whose crown is nearest it wins
    def _hair_score(arr):
        c = _crown_rgb(arr)
        return 0.0 if c is None else float(max(0.0, 1.0 - np.linalg.norm(c - np.asarray(hair_rgb)) / 160.0))
    for _t in range(3 if (colour_ref is not None or skin_wanted or hair_rgb is not None) else 1):
        g = torch.Generator("cuda").manual_seed(seed + 977 * _t)
        out = c(**kw, image=dimg, controlnet_conditioning_scale=cn_scale,
                guidance_scale=6.0, num_inference_steps=34, generator=g, width=1024, height=1024).images[0]
        _a = np.asarray(out, dtype=np.float32)
        _s = (_skin_share(_a) if skin_wanted else (_fine(_a) if style != "anime" else
              (_hair_score(_a) if hair_rgb is not None else 1.0)))
        print("DEPTHFACE draw %d score %.3f" % (_t, _s), flush=True)
        if _s > best_s:
            best_a, best_s = _a, _s
        if _s >= (0.35 if skin_wanted else 0.8):
            break
    a = best_a
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


def _np_load(png: Path):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(png).convert("RGB"), dtype=np.float32)


def _crown_rgb(a):
    """Median colour of the crown (the top fifth of the head, above the face) of
    an RGB array (0-255) on a studio backdrop, or None."""
    import numpy as np
    m, _ = _figure_mask(a / 255.0)                    # the backdrop is vignetted, not one grey
    ys = np.nonzero(m.any(1))[0]
    if len(ys) < 20:
        return None
    y0 = _figure_top(m)
    y0 = int(ys[0]) if y0 is None else int(y0)
    y1 = y0 + int(0.18 * (ys[-1] - y0))
    px = a[y0:y1][m[y0:y1]]
    return np.median(px, axis=0) if len(px) >= 200 else None


def _hair_name(head_png: Path) -> str:
    """A name for the hair colour at the top of a head render (the crown, above
    the face), for a prompt: black, dark brown, brown, auburn, blonde, grey..."""
    import colorsys
    import numpy as np
    from PIL import Image
    c = _crown_rgb(np.asarray(Image.open(head_png).convert("RGB"), dtype=np.float32))
    if c is None:
        return ""
    r, g, b = c / 255.0
    h, sat, val = colorsys.rgb_to_hsv(r, g, b)
    h *= 360
    if val < 0.22:
        return "black"
    if sat < 0.18:
        return "white" if val > 0.8 else ("silver grey" if val > 0.55 else "dark grey")
    if h < 45 or h > 330:
        if val < 0.42:
            return "dark brown"
        return "auburn" if (sat > 0.55 and h < 25) else ("blonde" if val > 0.7 and h > 30 else "brown")
    if h < 70:
        return "blonde"
    return {True: "green"}.get(h < 170, "blue" if h < 260 else "purple")


def photo_head_colour(ref: Path):
    """Mean and spread of the reference photo's head (top of the figure), for depth_face."""
    import numpy as np
    from PIL import Image
    im = Image.open(ref).convert("RGB"); R = np.asarray(im, dtype=np.float32) / 255.0
    fig, _ = _figure_mask(R)
    ys = np.where(fig.any(1))[0]
    if len(ys) < 50:
        return None
    top, bot = int(ys[0]), int(ys[-1])
    _t = _figure_top(fig)
    if _t is not None:
        top = _t
    Hf = bot - top
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


def _figure_mask(R):
    """The figure against a studio backdrop that is lit brighter in the middle
    than at its edges (2026-10-09): each row's level from its margins plus a
    horizontal profile from the empty strip along the top of the frame."""
    import numpy as np
    H, W = R.shape[:2]; E = max(24, W // 16)
    row = np.median(np.concatenate([R[:, :E], R[:, -E:]], axis=1), axis=1)          # (H, 3)
    t = max(8, H // 40)
    prof = np.median(R[:t], axis=0) - row[:t].mean(0)                                 # (W, 3)
    B = row[:, None, :] + prof[None, :, :]
    fig = np.linalg.norm(R - B, axis=2) > 0.11
    fig &= (fig.sum(1, keepdims=True) > 3) & (fig.sum(0, keepdims=True) > 3)
    return fig, B


def _figure_top(fig):
    """The crown of the figure: the first row whose central strip holds figure,
    followed by a run of rows that also do. A vignetted backdrop marked the
    wall's top rows as figure, and a scientist's hair was read off the wall
    (2026-10-09)."""
    import numpy as np
    H, W = fig.shape
    strip = fig[:, int(W * 0.35):int(W * 0.65)].mean(1)
    for y in range(H - 25):
        if strip[y] > 0.04 and (strip[y:y + 25] > 0.02).all():
            return y
    return None


def photo_hair(ref: Path) -> str:
    """The hair's tone from the top of the photo's figure, for the face prompt:
    a freely painted face gave a woman with a black bun a pale hairline (2026-10-08)."""
    import numpy as np
    from PIL import Image
    try:
        im = Image.open(ref).convert("RGB"); R = np.asarray(im, dtype=np.float32) / 255.0
        W, H = im.size; E = max(24, W // 16)
        fig, Bg = _figure_mask(R)
        ys = np.where(fig.any(1))[0]
        top, bot = int(ys[0]), int(ys[-1])
        _t = _figure_top(fig)
        if _t is not None:
            top = _t
        Hf = bot - top
        # inside the hair: a band a little below the crown, the middle of the head's
        # width, and nothing near the backdrop's own colour (the anti-aliased rim
        # of a brown-haired scientist against a pale wall read as grey hair)
        y0, y1 = top + max(2, int(0.012 * Hf)), top + max(6, int(0.05 * Hf))
        sub, msk = R[y0:y1], fig[y0:y1]
        xs = np.where(msk.any(0))[0]
        if len(xs) < 4:
            return ""
        cx_, hw_ = (xs.min() + xs.max()) / 2, (xs.max() - xs.min()) / 2
        cols = np.abs(np.arange(sub.shape[1]) - cx_) < 0.45 * hw_
        far = np.linalg.norm(sub - Bg[y0:y1], axis=2) > 0.18
        band = sub[msk & cols[None, :] & far]
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
    # a drawn hero stays drawn: the repaint asks for a photograph. AN ANIME HERO
    # STILL HAS A FACE (2026-10-09): the anime schoolgirl and explorer shipped
    # with blank faces. Their heads are drawn onto their own geometry in the
    # anime style, and their bodies repainted as anime too (below).
    anime = kind.split()[0] == "anime"
    if kind.split()[0] in ("toon", "clay", "blocky"):
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
        if anime:
            neg_head = ("photo, photograph, photorealistic, realistic skin, 3d render, text, letters, logo, blurry, "
                        "deformed face, asymmetric eyes, extra eyes, two noses, double face, blank face")
        # 1. the body: the photo on the front (a person's), repaints on every side,
        #    and nothing of the photo on the head, which is painted next
        if not render(coated, "v", list(VIEWS)):
            return "render failed"
        extras = []
        # AN ANIME BODY IS DRAWN SHARP (2026-10-10): left as it was made, the
        # schoolgirl's sailor tie was a pink glow on a blurred blouse. The body
        # is repainted too, as an anime illustration, lighter, so the design holds.
        for v, phrase in VIEWS.items():
            if anime:
                prompt = (f"anime style full body character illustration of {outfit}, {phrase}, standing with arms out, "
                          f"clean cel shading, crisp line art, sharp clothing details, high quality anime illustration, plain grey backdrop")
                repaint(tmp / f"v_{v}.png", tmp / f"r_{v}.png", prompt, min(strength, 0.45),
                        neg="photo, photograph, photorealistic, realistic skin, 3d render, text, letters, logo, blurry, smudge, "
                            "smeared, glow, watercolour, extra limbs, extra arms, nude")
                extras += ["--extra", f"{tmp / f'r_{v}.png'}|{tmp / 'v.json'}|{v}"]
                continue
            if animal:
                prompt = (f"raw photograph, DSLR, of a {outfit}, {ANIMAL_VIEWS.get(v, phrase)}, whole animal standing, "
                          f"natural light, plain grey backdrop, sharp focus, detailed fur, natural colouring")
            else:
                prompt = (f"raw photograph, DSLR, of a real {outfit}, {phrase}, full body, standing with arms out, "
                          f"soft studio light, plain grey backdrop, sharp focus, detailed fabric texture, seams and folds")
            repaint(tmp / f"v_{v}.png", tmp / f"r_{v}.png", prompt, strength, neg=NEG_ANIMAL if animal else NEG)
            extras += ["--extra", f"{tmp / f'r_{v}.png'}|{tmp / 'v.json'}|{v}"]
        stage = tmp / "s0.glb"
        line = project(coated, stage, extras + (["--nophoto"] if (animal or noref or anime) else ["--nohead"])
                       + (["--bodyreplace"] if anime else []))
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
                    _m, _ = _figure_mask(_a / 255.0)       # the backdrop is vignetted, not one grey
                    cref = (_a[_m].mean(0), _a[_m].std(0)) if _m.sum() > 1000 else None
                else:
                    hair = "" if (noref or anime) else photo_hair(ref)
                    prompt = (f"close-up portrait photograph of a real {outfit}, {hair + ', ' if hair else ''}facing the camera, natural skin texture, pores, "
                              f"clear detailed eyes, sharp focus, 85mm, soft even studio light, plain grey backdrop")
                    if anime:
                        # HER OWN HAIR (2026-10-10): matched to skin, a dark-haired
                        # schoolgirl's head came back grey-haired with magenta streaks.
                        # The hair colour is read off her own head and asked for; the
                        # drawing keeps its own palette, unmatched.
                        _hat = any(w in outfit.lower() for w in ("hat", "cap", "helmet", "hood", "turban", "bandana", "beanie"))
                        hc = "" if _hat else _hair_name(tmp / f"{pre}_{v}.png")      # a hat's crown is not hair
                        hair_rgb = None if _hat else _crown_rgb(_np_load(tmp / f"{pre}_{v}.png"))
                        if hc in ("black", "dark brown", "brown", "dark grey", "auburn"):
                            neg_head = neg_head + ", white hair, silver hair, grey hair, light hair, purple tint, pink tint"
                        prompt = (f"anime style character portrait of {outfit}, {hc + ' hair, ' if hc else ''}facing the camera, "
                                  f"big expressive detailed eyes, small nose, clean cel shading, crisp line art, "
                                  f"high quality anime illustration, plain grey backdrop")
                    if anime:
                        cref = None
                    elif noref:
                        import numpy as _np
                        from PIL import Image as _I
                        _a = _np.asarray(_I.open(tmp / f"{pre}_{v}.png").convert("RGB"), dtype=_np.float32).reshape(-1, 3)
                        r_, g_, b_ = _a[:, 0], _a[:, 1], _a[:, 2]
                        _sk = (r_ > g_) & (g_ >= b_ * 0.9) & (r_ - b_ > 12) & (r_ - b_ < 120) & (r_ > 50) & ((r_ - g_) < 70)
                        cref = (_a[_sk].mean(0), _a[_sk].std(0)) if _sk.sum() > 800 else None
                    else:
                        cref = photo_head_colour(ref)
                if depth_face(tmp / f"{pre}_{v}_depth.png", tmp / f"r_{v}.png", prompt, neg_head, cref,
                              skin_wanted=not (animal or anime), style="anime" if anime else "photo",
                              # an animal's round, flat-faced head read as a drawing's guide
                              # circles at 0.7 (a grizzly, 2026-10-09); at 0.5 it is fur
                              cn_scale=0.5 if animal else 0.7,
                              hair_rgb=hair_rgb if anime else None):
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
                elif anime:
                    prompt = (f"anime style character portrait of {outfit}, {phrase}, expressive detailed eyes, clean cel shading, "
                              f"crisp line art, high quality anime illustration, plain grey backdrop")
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
