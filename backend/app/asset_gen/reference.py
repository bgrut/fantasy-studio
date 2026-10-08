"""
Text-to-image reference generation using SDXL Base 1.0.

This is the *first* step of the asset-driven pipeline. We give SDXL a clean
prompt describing the subject in isolation (centered, neutral background,
front-facing) so the downstream image-to-3D model has the cleanest possible
input.

Why a separate module from refiner.py?
    - Different goal: generate a *training-quality* reference, not polish an existing render.
    - Different pipeline: text-to-image (no input image), so no ControlNet conditioning.
    - Different prompts: explicit "studio backdrop, single subject" framing for clean 3D extraction.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Style → prompt mapping (separate from refiner's STYLE_PRESETS so we can
# tune for reference quality, not output polish)
# ---------------------------------------------------------------------------

# ── Pose-lock strength (ControlNet-depth conditioning) ──────────────────────
# Lower = higher image quality + weaker pose consistency. Orientation is now
# handled by the fixed per-pattern Euler in composer._BLENDER_PATTERN_EULER, so
# we can afford to weaken this for quality.
#
# 5-LEGGED-DOG FIX (verified via scripts/leg_sweep.py): the quadruped depth
# template renders the near/far legs as offset columns; at scale 0.35 SDXL locks
# onto them and fills the ambiguity with a 5th leg (reproduced on seed 7). A
# scale of 0.22 gives a clean 4 legs on every tested seed while still keeping a
# standing side-profile pose, so orientation stays consistent. Don't raise above
# ~0.25 without re-running the sweep. (Deeper fix: regenerate the depth template
# as a TRUE orthographic side view where near/far legs overlap into 2 columns.)
import os as _os
# Pose-lock strength. With a CLEAN 4-leg depth template the control signal is no
# longer corrupt, so we can keep a moderate lock for pose/orientation consistency
# without inheriting an extra limb. (count_leg_columns below is kept only as a
# manual QA helper — NOT an automatic gate; it can't tell a tail from a 5th leg.)
CONTROLNET_CONDITIONING_SCALE = float(_os.environ.get("FS_CONTROLNET_SCALE", "0.35"))


REFERENCE_STYLES: Dict[str, Dict[str, str]] = {
    "photoreal": {
        "positive": "studio photograph, single subject centered, plain neutral background, sharp focus, even lighting, natural color, high detail",
        "negative": "multiple subjects, painting, illustration, drawing, artwork, shadow across the face, busy background, blurry, cropped, partial view, watermark, text, logo, emblem, insignia, trademark, "
                    # anti-anatomy-artifact (fixes the 5-legs / fused-limb issue from ControlNet)
                    "extra legs, extra limbs, too many legs, fused limbs, duplicate limbs, "
                    "missing legs, deformed, mutated, malformed anatomy, disfigured, "
                    # anti-vintage/desaturation (fixes the sepia/washed-out look)
                    "sepia, monochrome, grayscale, desaturated, faded, old photo, vintage",
    },
    "cartoon": {
        "positive": "pixar style 3d character, single subject centered, neutral background, clean turntable",
        "negative": "multiple subjects, busy scene, photorealistic, blurry, cropped",
    },
    "anime": {
        "positive": "anime character art, single subject centered, neutral background, clean line work",
        "negative": "multiple subjects, busy background, photorealistic, blurry, cropped",
    },
    "painting": {
        "positive": "painted character study, single subject centered, neutral background, classical pose",
        "negative": "multiple subjects, busy scene, photograph, blurry, cropped",
    },
    "claymation": {
        "positive": "claymation character, single subject centered, neutral studio backdrop, aardman style",
        "negative": "multiple subjects, photorealistic, blurry, cropped",
    },
}

# Per-pattern composition guidance — what the reference *should* look like
# for clean image-to-3D extraction.
PATTERN_REFERENCE_FRAMING: Dict[str, str] = {
    # Strong directives: NO action poses, NO motion blur, full body grounded.
    # These framings are what TripoSR/InstantMesh need for clean upright meshes.
    "quadruped": "perfect side profile, standing still on all four legs, motionless, full body in frame, vertical posture, feet flat on ground, short smooth well-groomed coat, clean silhouette",
    # 2026-08-07: THE PROMPT DOES NOT DECIDE THE POSE. Biped references are
    # generated through controlnet-depth against pose_templates/
    # biped_depth.png, and that template is a flat T-POSE — arms straight
    # out. Depth conditioning dominates the text, so asking for "arms
    # hanging down at sides" here changes nothing, and adding T-pose to the
    # negative prompt (below) changed nothing either: both were tried and
    # both produced arms-out references.
    #
    # That matters because the rigger builds its arm chain expecting a
    # TRELLIS A-pose (hands ~0.18H BELOW the shoulders, see
    # orchestrator/mocap_retarget.py). A T-posed mesh gets a skeleton that
    # disagrees with it, so the character keeps its arms out through every
    # clip — idle, walk and run alike. Fixing this means authoring an
    # arms-down biped_depth.png, NOT editing these strings.
    # THE FACE IS LIT (2026-10-08): a reference under dramatic studio light
    # threw a hat brim's shadow diagonally across the face, and that shadow
    # was projected onto the face of every hatted character. Soft frontal
    # light, early in the prompt where the encoder weighs it.
    "biped":     "a real person in loose everyday clothes, standing upright facing the camera, face evenly lit by soft frontal light, arms relaxed hanging straight down at sides, open empty hands, neutral A-pose, full body in frame, feet flat on ground, fully clothed",
    # seamless studio cyclorama (2026-07-22): SDXL loves posing trucks in
    # FORESTS — the busy background then projects onto the body as camo
    # blotch whenever the texture falls back to projection
    "vehicle":   "parked stationary, three-quarter front view, all four wheels on ground, on seamless white studio cyclorama, showroom floor, studio lighting",
    "tree":      "vertical trunk centered, full tree from roots to top, upright",
    "celestial": "centered sphere, fills frame",
    "primitive_geo": "centered, full object visible",
    # flying creatures/craft (dragons, birds, planes — 2026-07-05): without
    # this SDXL freestyles a coiled head-shot ILLUSTRATION that image-to-3D
    # turns to soup. Same recipe as quadruped: whole body, side-ish, isolated.
    "flying":    "perfect side profile, whole body visible in frame, wings spread wide and level, standing on the ground, motionless, plain background, single subject, clean silhouette, photorealistic",
    # aquatic (2026-07-06): without this SDXL painted a WALLPAPER PATTERN of
    # many small whales — image-to-3D extruded the pattern into a nonsense
    # slab. ONE animal, whole body, side-on, photoreal.
    "aquatic":   "exactly one single animal, perfect side profile, whole body visible in frame, horizontal swimming pose, centered, plain light background, clean silhouette, photorealistic, detailed skin texture",
}

# Negative-prompt additions per pattern — explicitly veto problematic poses
PATTERN_NEGATIVE: Dict[str, str] = {
    "quadruped": "running, jumping, leaping, mid-action, motion blur, dynamic pose, legs in the air, tilted, perspective distortion, wispy fur strands, flyaway hair, shaggy fuzzy silhouette, long unkempt fur",
    "biped":     "T-pose, t pose, arms outstretched, arms straight out, arms horizontal, arms spread wide, wingspan, jumping jack, holding weapon, holding object, aiming, raised arm, bent elbow, crossed arms, hands on hips, dynamic pose, motion blur, running, jumping, tilted, perspective distortion, cropped, anatomy figure, ecorche, flayed, skinless, exposed muscle, muscle suit, x-ray, medical illustration, red and blue veins, nude, naked, underwear, briefs, boxers, swimsuit, swim trunks, bare chest, shirtless, topless, bare legs, loincloth, undressed, partially clothed",
    "vehicle":   "moving, motion blur, tilted, perspective distortion, forest, trees, outdoor scene, road, landscape, buildings, sky",
    "flying":    "flying, mid-air, coiled, curled, head close-up, portrait, tattoo style, line art, illustration, logo, emblem, circular composition, cropped body, motion blur, dynamic pose",
    "aquatic":   "pattern, wallpaper, multiple animals, many, group, pod, school of fish, repeated, tiled, seamless pattern, illustration, cartoon, drawing, logo, fabric print, cropped body, top view, leaping, jumping out of the water, diagonal body, vertical body, arched body, splash",
    # ONE THING, WHOLE (2026-09-29): "a gem" came back as a wallpaper of forty
    # grey gem icons and meshed into a flat grey slab; "a diamond" as one stone
    # in a scatter of small ones. A prop's reference is a single object.
    "static":    "pattern, wallpaper, collage, grid of many items, many objects, multiple items, repeated icons, sticker sheet, scattered pieces, several copies, seamless pattern, tiled, background clutter",
    "primitive_geo": "pattern, wallpaper, collage, grid of many items, many objects, multiple items, repeated icons, sticker sheet, scattered pieces, several copies, seamless pattern, tiled, background clutter",
}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Pose templates — used by ControlNet to lock subject orientation across all
# prompts within a pattern. Without this, "a dog" and "a cat" produce SDXL
# images at different angles, which makes TripoSR's mesh orientation drift
# per-prompt and breaks our fixed per-pattern Euler correction.
#
# Templates are depth maps generated once via scripts/generate_pose_templates.py
# and committed under app/asset_gen/pose_templates/{pattern}_depth.png. If the
# template is missing, generate_reference() silently falls back to the plain
# SDXL pipeline (the previous behavior).
# ---------------------------------------------------------------------------

POSE_TEMPLATES_DIR = Path(__file__).resolve().parent / "pose_templates"


def get_pose_template_path(base_pattern: str) -> Optional[Path]:
    """Return path to the depth template for a pattern, or None if missing."""
    p = POSE_TEMPLATES_DIR / f"{base_pattern}_depth.png"
    return p if p.exists() else None


def count_leg_columns(pil_or_path, debug: bool = False) -> int:
    """Count distinct leg columns where the subject meets the ground.

    The reliable 5-legged-dog discriminator: in a leg-height band of the subject
    silhouette, count separated vertical limb columns. A real quadruped shows at
    most 4 (near+far front, near+far back); ≥5 means SDXL hallucinated a limb.
    Background-gradient-robust (segments by saturation + darkness, like the
    texture bbox detector). Returns the MAX column count across sampled rows.
    """
    try:
        from PIL import Image
        import numpy as np
        if hasattr(pil_or_path, "convert"):
            im = np.asarray(pil_or_path.convert("RGB"), dtype=np.float32)
        else:
            im = np.asarray(Image.open(pil_or_path).convert("RGB"), dtype=np.float32)
        h, w = im.shape[:2]
        f = 0.04
        ry0, ry1 = int(h * f), int(h * (1 - f))
        rx0, rx1 = int(w * f), int(w * (1 - f))
        mx = im.max(axis=2); mn = im.min(axis=2)
        sat = (mx - mn) / (mx + 1e-3)
        mask = (sat > 0.20) | (im.mean(axis=2) < 55.0)
        keep = np.zeros_like(mask); keep[ry0:ry1, rx0:rx1] = True
        mask &= keep
        cols = np.where(mask.any(axis=0))[0]
        rows = np.where(mask.any(axis=1))[0]
        if not (cols.size and rows.size):
            return 0
        x0, x1 = cols.min(), cols.max()
        y0, y1 = rows.min(), rows.max()
        sub_w = max(x1 - x0, 1)
        sub_h = max(y1 - y0, 1)
        min_w = max(3, int(sub_w * 0.02))     # ignore slivers
        min_gap = max(2, int(sub_w * 0.012))  # merge across tiny anti-alias gaps

        def seg_count(row_mask):
            idx = np.where(row_mask)[0]
            if idx.size == 0:
                return 0
            breaks = np.where(np.diff(idx) > 1)[0]
            runs = np.split(idx, breaks + 1)
            merged = []
            for r in runs:
                if merged and (r[0] - merged[-1][-1]) <= min_gap:
                    merged[-1] = np.concatenate([merged[-1], r])
                else:
                    merged.append(r)
            return sum(1 for r in merged if (r[-1] - r[0] + 1) >= min_w)

        # Sample the upper-leg / shin band. Stay ABOVE ~0.88 of subject height:
        # lower rows catch the hanging tail tip as a false extra column (a clean
        # 4-leg dog with a low tail then reads 5). These bands cleanly separate a
        # hallucinated mid-body 5th leg while excluding the tail. MAX across rows.
        counts = []
        for frac in (0.70, 0.76, 0.82, 0.88):
            ry = int(y0 + frac * sub_h)
            counts.append(seg_count(mask[ry, x0:x1 + 1]))
        result = max(counts) if counts else 0
        if debug:
            print(f"[reference] leg columns per-row {counts} → max {result}")
        return result
    except Exception as e:
        if debug:
            print(f"[reference] count_leg_columns failed ({type(e).__name__}: {e})")
        return 0  # fail-open: never block generation on a counting error


# ---------------------------------------------------------------------------
# Pipeline cache (shared instance)
# ---------------------------------------------------------------------------

_T2I_PIPELINE = None
_T2I_CONTROLNET_PIPELINE = None
_CONTROLNET_MODEL_ID = "diffusers/controlnet-depth-sdxl-1.0"


def is_t2i_available() -> bool:
    """True iff torch + diffusers + SDXL weights are present."""
    try:
        import torch  # noqa: F401
        import diffusers  # noqa: F401
        from huggingface_hub import try_to_load_from_cache
        path = try_to_load_from_cache(
            repo_id="stabilityai/stable-diffusion-xl-base-1.0",
            filename="model_index.json",
        )
        return path is not None
    except Exception:
        return False


def _evict_llms():
    """Unload every resident Ollama model from the GPU (2026-09-30).

    The director's 12B model (8 GB) was unloaded before generation began, and
    reloaded by the next planning call in the same build before SDXL ran; SDXL
    then sat at step 0 of 28 with the card oversubscribed. Called each time an
    SDXL pipeline is asked for, so whatever reloaded it in between goes."""
    try:
        import requests as _rq
        for _m in _rq.get("http://localhost:11434/api/ps", timeout=3).json().get("models", []):
            _rq.post("http://localhost:11434/api/generate",
                     json={"model": _m["name"], "keep_alive": 0}, timeout=5)
            print(f"[reference] unloaded '{_m['name']}' from VRAM for SDXL", flush=True)
    except Exception:
        pass


def _load_t2i_pipeline():
    """Construct or return cached SDXL text-to-image pipeline."""
    global _T2I_PIPELINE
    _evict_llms()
    if _T2I_PIPELINE is not None:
        return _T2I_PIPELINE

    import os
    import torch
    from diffusers import StableDiffusionXLPipeline, AutoencoderKL

    # CUDA determinism — without these, seed=42 still varies output across runs
    # because cuDNN picks different attention/conv kernel orderings each launch.
    # Locking them is what makes the SDXL → TripoSR → fixed-Euler pipeline
    # actually reproducible. cuBLAS workspace must be set BEFORE first CUDA op.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    try:
        vae = AutoencoderKL.from_pretrained(
            "madebyollin/sdxl-vae-fp16-fix", torch_dtype=dtype,
        )
    except Exception:
        vae = None

    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        vae=vae,
        torch_dtype=dtype,
        variant="fp16" if device == "cuda" else None,
        use_safetensors=True,
    )
    pipe = pipe.to(device)

    if device == "cuda":
        try:
            pipe.vae.enable_tiling()
        except Exception:
            pass

    _T2I_PIPELINE = pipe
    return pipe


def _load_t2i_controlnet_pipeline():
    """SDXL + ControlNet-Depth pipeline for pose-locked reference generation.

    Loads lazily on first use. Reuses determinism settings from the base
    pipeline loader (which must run first via _load_t2i_pipeline).
    """
    global _T2I_CONTROLNET_PIPELINE
    _evict_llms()
    if _T2I_CONTROLNET_PIPELINE is not None:
        return _T2I_CONTROLNET_PIPELINE

    import torch
    from diffusers import (
        StableDiffusionXLControlNetPipeline,
        ControlNetModel,
        AutoencoderKL,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    controlnet = ControlNetModel.from_pretrained(_CONTROLNET_MODEL_ID, torch_dtype=dtype)

    try:
        vae = AutoencoderKL.from_pretrained(
            "madebyollin/sdxl-vae-fp16-fix", torch_dtype=dtype,
        )
    except Exception:
        vae = None

    pipe = StableDiffusionXLControlNetPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        controlnet=controlnet,
        vae=vae,
        torch_dtype=dtype,
        variant="fp16" if device == "cuda" else None,
        use_safetensors=True,
    )
    pipe = pipe.to(device)

    if device == "cuda":
        try:
            pipe.vae.enable_tiling()
        except Exception:
            pass

    _T2I_CONTROLNET_PIPELINE = pipe
    return pipe


def unload_reference_pipeline():
    """Free SDXL pipeline VRAM. Call before launching mesh stage on tight GPUs."""
    global _T2I_PIPELINE, _T2I_CONTROLNET_PIPELINE
    try:
        import torch
        if _T2I_PIPELINE is not None:
            del _T2I_PIPELINE
            _T2I_PIPELINE = None
        if _T2I_CONTROLNET_PIPELINE is not None:
            del _T2I_CONTROLNET_PIPELINE
            _T2I_CONTROLNET_PIPELINE = None
        # (2026-09-30) the judge goes too, and the memory is actually handed
        # back: TRELLIS.2 loads its checkpoints in a subprocess right after
        # this, and on a machine whose paging file cannot grow it crashed
        # (0xC0000005) while SDXL and CLIP still held system memory here
        global _CLIP_JUDGE
        try:
            del _CLIP_JUDGE
        except NameError:
            pass
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        _T2I_PIPELINE = None
        _T2I_CONTROLNET_PIPELINE = None


_WARDROBE_KEYS = None


def has_wardrobe(kind: str) -> bool:
    """True when the reference generator has an outfit written for this role
    (2026-10-07): the planner used to keep its own list of roles it would
    generate, and a lumberjack or a ghost hunter with an outfit written here
    was still recast as the ranger. The outfits are read from this file's own
    table, so there is one list."""
    global _WARDROBE_KEYS
    if _WARDROBE_KEYS is None:
        import re as _rw
        src = Path(__file__).read_text(encoding="utf-8")
        i = src.find("char_hints = {")
        j = src.find("\n        }", i)
        _WARDROBE_KEYS = set(_rw.findall(r'^\s+"([a-z][a-z \-]*)":\s*"', src[i:j], _rw.M)) if i > 0 else set()
    return (kind or "").strip().lower() in _WARDROBE_KEYS


def _long_prompt_kwargs(pipe, positive: str, negative: str) -> Dict[str, Any]:
    """THE WHOLE PROMPT, NOT ITS FIRST 77 TOKENS (2026-10-08). SDXL's text
    encoders read 77 tokens and drop the rest, and a biped's negative prompt
    runs to 286: everything after "sepia" never applied. That included
    "monochrome, grayscale" (the farmer came out grey), the clothing guards
    ("futuristic bodysuit, skin-tight suit", "shirtless, nude"; the scientist
    came out in a white bodysuit) and "flayed, skinless". Both prompts are cut
    into 75-token chunks, each chunk encoded by both encoders, and the chunks
    joined along the sequence, which the UNet's cross-attention takes at any
    length; the pooled embedding comes from the first chunk, where the
    subject leads. Falls back to the plain strings on any failure."""
    try:
        import torch
        tk = pipe.tokenizer

        def chunks(t: str) -> list:
            ids = tk(t or "", add_special_tokens=False).input_ids
            return [tk.decode(ids[i:i + 75]) for i in range(0, len(ids), 75)] or [""]
        pc, nc = chunks(positive), chunks(negative)
        if len(pc) == 1 and len(nc) == 1:
            return {"prompt": positive, "negative_prompt": negative}
        n = max(len(pc), len(nc))
        pc += [""] * (n - len(pc)); nc += [""] * (n - len(nc))
        pe, ne, pool, npool = [], [], None, None
        dev = getattr(pipe, "_execution_device", None) or ("cuda" if torch.cuda.is_available() else "cpu")
        with torch.no_grad():
            for a, b in zip(pc, nc):
                e = pipe.encode_prompt(prompt=a, device=dev, num_images_per_prompt=1,
                                       do_classifier_free_guidance=True, negative_prompt=b)
                pe.append(e[0]); ne.append(e[1])
                if pool is None:
                    pool, npool = e[2], e[3]
        return {"prompt_embeds": torch.cat(pe, 1), "negative_prompt_embeds": torch.cat(ne, 1),
                "pooled_prompt_embeds": pool, "negative_pooled_prompt_embeds": npool}
    except Exception as _lp:  # noqa: BLE001
        print(f"[reference] long prompt fell back to 77 tokens ({type(_lp).__name__}: {_lp})")
        return {"prompt": positive, "negative_prompt": negative}


def _build_reference_prompt(slots: Dict[str, Any], style: str) -> tuple[str, str]:
    """Compose positive + negative prompts for a clean asset reference."""
    preset = REFERENCE_STYLES.get(style, REFERENCE_STYLES["photoreal"])
    subj = (slots or {}).get("subject", {}) or {}

    base_pattern = subj.get("base_pattern", "primitive_geo")
    library_query = (subj.get("library_query") or "").lower()
    name = (subj.get("name") or "").lower()
    identity = (subj.get("identity_phrase") or "").lower()
    color = subj.get("color_name") or ""
    material = subj.get("material") or ""

    # Build subject descriptor — keep tight, ≤25 tokens. PREFER the user's exact
    # identity phrase ("samurai warrior", "red ferrari") over the genericized
    # library_query/name so the reference depicts THE thing they asked for.
    descriptor_bits = []
    core = identity or library_query or name or "subject"
    if color and color not in ("neutral", "") and color not in core:
        descriptor_bits.append(color)
    if material and material not in ("matte", "plastic") and material not in core:
        descriptor_bits.append(material)
    descriptor_bits.append(core)
    subject_phrase = " ".join(descriptor_bits)

    framing = PATTERN_REFERENCE_FRAMING.get(base_pattern, "")

    # Late species hints — borrowed from refiner module to stay DRY-ish but
    # we DELIBERATELY don't import to keep modules independent.
    species_hints = {
        "cat":    "domestic cat, triangular ears, whiskers",
        "dog":    "domestic dog, prominent snout, floppy ears",
        "fox":    "red fox, bushy tail, pointed muzzle",
        "rabbit": "rabbit, long ears, fluffy tail",
        "lion":   "majestic lion with mane",
        "horse":  "horse, long elegant legs",
        "sheep":  "fluffy sheep, dense wool",
        "bear":   "bear, thick fur",
        "wolf":   "gray wolf, thick fur ruff",
        "human":  "human person, fully dressed in ordinary clothes, shirt and trousers and shoes",
        "person": "person, fully dressed, complete everyday outfit",
        "car":    "modern car, clean paint job",
        "sports": "sports car, low aggressive styling",
    }
    species = ""
    vehicle_neg = ""
    # WHOLE WORDS (2026-10-06): "car" in "carrot" added "modern car, clean paint
    # job" to a vegetable's prompt and SDXL drew an orange hatchback, twice;
    # lion/dandelion, fox/foxglove, cat/caterpillar were the same trap
    import re as _re_h
    _hq = " ".join((library_query or "", name or "", identity or "")).lower()
    _whole = lambda key, text: _re_h.search(r"\b" + _re_h.escape(key) + r"(?:s|es)?\b", text) is not None
    for key, hint in species_hints.items():
        if _whole(key, _hq):
            species = hint
            break

    # ── CHARACTER ARCHETYPE enrichment (bipeds). A bare identity like "wizard"
    # renders as a generic person under the photoreal/A-pose framing — SDXL needs
    # the COSTUME spelled out (the prior good wizards only worked because the user
    # typed "fantasy wizard with a staff"). Same idea as the animal/vehicle hints.
    # Only fires when the identity doesn't already describe the costume, so
    # "fantasy wizard with a staff" is left untouched.
    if base_pattern == "biped":
        char_hints = {
            "wizard":    "elderly wizard, long flowing robe, tall pointed hat, long white beard, holding a wooden staff, fantasy character",
            "sorcerer":  "sorcerer, ornate robe, arcane staff, fantasy character",
            "witch":     "witch, flowing dress, pointed hat, fantasy character",
            "mage":      "mage, hooded robe, glowing staff, fantasy character",
            "knight":    "knight in full plate armor, helmet, tabard, medieval",
            "viking":    "viking warrior, fur and leather armor, round shield, braided beard",
            "samurai":   "samurai warrior, layered lamellar armor, kabuto helmet, katana at the hip",
            "ninja":     "ninja, black hooded outfit, face mask, fantasy",
            "gladiator": "gladiator, roman segmented armor, helmet, shield",
            "barbarian": "barbarian warrior, fur clothing, leather straps, muscular",
            "pirate":    "pirate, tricorn hat, long coat, sash, fantasy",
            "king":      "king, royal robe with fur trim, golden crown",
            "queen":     "queen, elegant royal gown, crown",
            "monk":      "monk, simple hooded robe, rope belt",
            "soldier":   "soldier, military uniform, tactical gear",
            "robot":     "humanoid robot, sleek metallic armor plating, mechanical joints",
            "alien":     "humanoid alien, otherworldly features, sci-fi",
            "angel":     "angel, white robe, large feathered wings",
            "demon":     "demon, horns, dark menacing armor, fantasy",
            "astronaut": "astronaut, white space suit, helmet with visor",
            # THE ROSTER (2026-09-25): the studio's own hero roles were missing
            # here, so a "scientist" rendered as a woman in a futuristic sport
            # suit and became a flayed mesh. Each role gets the wardrobe a
            # reader expects, in the same voice as the entries above.
            "scientist": "scientist wearing a white lab coat over a collared shirt and dark trousers, safety glasses, id badge, plain shoes",
            "detective": "detective in a beige trench coat over a shirt and tie, fedora hat, dark trousers, leather shoes",
            "ranger":    "forest ranger in a green field jacket and khaki trousers, wide-brimmed hat, hiking boots",
            "engineer":  "engineer in an orange hi-vis work jacket, white hard hat, cargo trousers, work boots, tool belt",
            "explorer":  "explorer in a khaki safari shirt and trousers, wide-brimmed hat, leather boots, backpack straps",
            # (2026-10-07) an original Victorian investigator, nothing from any film
            "ghost hunter": "victorian ghost hunter in a long dark wool greatcoat over a buttoned waistcoat and high-collared white shirt, dark trousers, tall leather boots, leather gloves, a brass lantern on a belt hook, short tidy hair, determined face",
            "hunter":    "hunter in a camouflage jacket and trousers, baseball cap, boots",
            "courier":   "bicycle courier in a cycling jersey, cap, messenger bag strap across the chest, trainers",
            "thug":      "street thug in a dark hoodie and jeans, sneakers, tough expression",
            "driver":    "racing driver in a fireproof racing suit with sponsor patches, no helmet",
            "guard":     "security guard in a dark uniform shirt with a badge and epaulettes, dark trousers",
            "walker":    "pedestrian in casual street clothes, jacket, jeans, trainers",
            "lighthouse keeper": "lighthouse keeper in a thick wool sweater, oilskin coat, flat cap, sea boots, weathered face",
            "keeper":    "lighthouse keeper in a thick wool sweater, oilskin coat, flat cap, sea boots, weathered face",
            "sailor":    "sailor in a navy peacoat, knitted cap, canvas trousers, deck boots",
            "fisherman": "fisherman in a yellow oilskin jacket, waders, knitted cap",
            "farmer":    "farmer in a checked shirt, denim overalls, straw hat, work boots",
            "miner":     "miner in a helmet with a headlamp, dusty overalls, heavy boots",
            "pilot":     "pilot in a leather flight jacket, aviator cap, goggles on the forehead, trousers and boots",
            "chef":      "chef in a white double-breasted jacket, tall toque, checked trousers",
            "nurse":     "nurse in blue scrubs, comfortable shoes, a stethoscope",
            "mechanic":  "mechanic in stained grey coveralls, a rag in the pocket, work boots",
            # NEW KINDS OF GAME (2026-10-06): a superhero, a barista, a gardener
            # an ORIGINAL hero (commercially safe): no chest emblem, none of the
            # famous red-and-blue suits; the first try came out a known hero's
            # colours with another's bat on the chest
            "superhero": "original superhero in a sleek teal and silver armoured flight suit with glowing amber seams, a short charcoal cape, silver boots and gauntlets, plain chest with no symbol, fully clothed",
            "barista":   "barista in a dark brown apron over a white shirt with rolled sleeves, jeans, fully clothed",
            "waiter":    "waiter in a black waistcoat over a white shirt, a long black apron, dark trousers, fully clothed",
            "waitress":  "waitress in a black waistcoat over a white shirt, a long black apron, dark trousers, fully clothed",
            "bartender": "bartender in a dark waistcoat over a white shirt with rolled sleeves, dark trousers, fully clothed",
            "baker":     "baker in a white baker's jacket and a flour-dusted apron, a white cap, fully clothed",
            "sheriff":   "frontier sheriff in a brown leather vest over a cream shirt, a tan cowboy hat, denim trousers, a gun belt with a holster, cowboy boots, fully clothed",
            "marshal":   "frontier marshal in a long tan duster coat, a dark vest, a black cowboy hat, a gun belt, cowboy boots, fully clothed",
            "deputy":    "frontier deputy in a checked shirt and a leather vest, a brown cowboy hat, jeans, a gun belt, boots, fully clothed",
            "cowboy":    "cowboy in a checked shirt, a brown leather vest, leather chaps over jeans, a wide-brimmed cowboy hat, a neck bandana, cowboy boots, fully clothed",
            "cowgirl":   "cowgirl in a fringed suede jacket, a checked shirt, jeans, a cowboy hat, cowboy boots, fully clothed",
            "gunslinger": "gunslinger in a long dark duster coat, a black flat-brimmed hat, a gun belt, boots, fully clothed",
            "outlaw":    "outlaw in a long dusty brown duster coat, a red bandana over the lower face, a battered wide-brimmed hat, boots, fully clothed",
            "bandit":    "frontier bandit in a long dusty brown duster coat, a red bandana over the lower face, a battered wide-brimmed hat, boots, fully clothed",
            "child":     "a cheerful child in a bright striped t-shirt, colourful dungarees and sneakers, fully clothed",
            "kid":       "a cheerful child in a bright striped t-shirt, colourful dungarees and sneakers, fully clothed",
            "firefighter": "firefighter in a heavy tan turnout coat and trousers with reflective yellow stripes, a red helmet, thick gloves, black boots, fully clothed",
            "fireman":   "firefighter in a heavy tan turnout coat and trousers with reflective yellow stripes, a red helmet, thick gloves, black boots, fully clothed",
            "snowboarder": "snowboarder in a baggy bright winter jacket and snow pants, a knitted beanie, goggles pushed up, thick gloves, snow boots, fully clothed",
            "skier":     "skier in a fitted padded ski jacket and ski pants, a helmet and goggles, gloves, ski boots, fully clothed",
            "surfer":    "surfer in a full-length wetsuit, barefoot, fully covered",
            "skateboarder": "skateboarder in a loose t-shirt over a long-sleeved top, baggy jeans, a cap, skate shoes, fully clothed",
            "gardener":  "gardener in denim overalls over a checked shirt, a straw sun hat, gardening gloves, rubber boots, fully clothed",
            # (2026-10-07) the fourth wide test's people; original outfits, no logos or insignia
            "lumberjack": "lumberjack in a red and black checked flannel shirt, braces, sturdy brown work trousers, heavy leather boots, a knitted beanie, a full beard, fully clothed",
            "postman":   "postman in a plain navy blue uniform jacket and trousers, a peaked cap, a brown leather satchel strap across the chest, black shoes, no logos, fully clothed",
            "postwoman": "postwoman in a plain navy blue uniform jacket and trousers, a peaked cap, a brown leather satchel strap across the chest, black shoes, no logos, fully clothed",
            "mail carrier": "mail carrier in a plain navy blue uniform jacket and trousers, a peaked cap, a brown leather satchel strap across the chest, black shoes, no logos, fully clothed",
            "diver":     "scuba diver in a full black wetsuit with blue side panels, a dive mask pushed up on the forehead, an air tank on the back, dive boots, fully covered",
            "hiker":     "hiker in a red waterproof jacket, grey hiking trousers, walking boots, a small backpack, a knitted beanie, fully clothed",
            # (2026-10-07) the originality round's people: a beekeeper was played by the ranger
            "beekeeper": "beekeeper in a loose white full-body bee suit, a round mesh veil hat, long white gauntlet gloves, rubber boots, fully covered",
            "vintner":   "vintner in a rolled-sleeve linen shirt, a brown canvas apron, sturdy work trousers, leather boots, a straw hat, fully clothed",
            "winemaker": "winemaker in a rolled-sleeve linen shirt, a brown canvas apron, sturdy work trousers, leather boots, a straw hat, fully clothed",
            "photographer": "photographer in an olive field jacket with many pockets, dark trousers, hiking boots, a camera on a strap round the neck, a beanie, fully clothed",
            "storm chaser": "storm chaser in a dark blue rain jacket, cargo trousers, hiking boots, a baseball cap with no logo, fully clothed",
            "chaser":    "storm chaser in a dark blue rain jacket, cargo trousers, hiking boots, a baseball cap with no logo, fully clothed",
            "shepherd":  "shepherd in a heavy cream wool jumper under a waxed green jacket, a tweed flat cap, sturdy brown walking trousers, leather boots, fully clothed",
            "shepherdess": "shepherdess in a heavy cream wool jumper under a waxed green jacket, a knitted hat, sturdy brown walking trousers, leather boots, fully clothed",
            "buddhist monk": "man with a shaved head wearing a maroon long-sleeved tunic, loose maroon trousers, a saffron sash at the waist, a maroon shawl over both shoulders, simple sandals, fully clothed",
            "park ranger": "park ranger in a plain olive green uniform shirt and trousers, a wide-brimmed flat hat, hiking boots, no badges or logos, fully clothed",
            # (2026-10-07) an anime sentence's heroes; generic uniforms, no school crest or logo
            "schoolgirl": "a teenage schoolgirl in a navy blazer over a white shirt with a red ribbon tie, a pleated navy skirt, knee socks and black school shoes, holding nothing, fully clothed",
            "schoolboy": "a teenage schoolboy in a navy blazer over a white shirt and a dark tie, grey trousers and black school shoes, fully clothed",
            "student":   "a teenage student in a navy blazer over a white shirt, a pleated navy skirt, knee socks and black school shoes, fully clothed",
            "witch":     "a young witch in a long dark purple robe with a wide pointed hat, a belt with small pouches, boots, fully clothed",
            "mage":      "a young mage in a flowing blue and silver robe with a hood down, a sash belt, soft boots, fully clothed",
            "mountaineer": "mountaineer in a bright orange insulated down jacket, black climbing trousers, stiff mountaineering boots with gaiters, a climbing helmet, glacier glasses pushed up, a coil of rope over one shoulder, fully clothed",
            "climber":   "mountaineer in a bright orange insulated down jacket, black climbing trousers, stiff mountaineering boots with gaiters, a climbing helmet, glacier glasses pushed up, a coil of rope over one shoulder, fully clothed",
            # generic humans need CLOTHES spelled out or SDXL renders a shirtless
            # anatomy/muscle-suit figure. Order: woman/person before "man" (which
            # is a substring of "woman") so the right one matches first.
            "woman":     "a woman wearing a casual t-shirt and jeans, fully clothed, everyday outfit",
            "girl":      "a girl wearing casual everyday clothes, fully clothed",
            "boy":       "a boy wearing casual everyday clothes, fully clothed",
            "person":    "a person wearing a long-sleeved navy blue button-up shirt, dark jeans and brown boots, fully clothed",
            "human":     "a person wearing a long-sleeved navy blue button-up shirt, dark jeans and brown boots, fully clothed",
            "man":       "a man wearing a long-sleeved navy blue button-up shirt, dark jeans and brown boots, fully clothed",
            "guy":       "a man wearing casual everyday clothes, fully clothed",
        }
        cq = " ".join((identity, name, library_query))
        # skip if the user already described the outfit (robe/armor/etc. present)
        _has_costume = any(w in cq for w in ("robe", "armor", "armour", "staff", "hat", "cloak", "helmet", "suit", "uniform", "wings"))
        if not _has_costume:
            # the longest name that fits wins (2026-10-08): "monk" sat above "buddhist
            # monk" in the table and dressed the Himalayan monk as a hooded friar
            for key, hint in sorted(char_hints.items(), key=lambda kv: -len(kv[0])):
                if _re_h.search(r"\b" + _re_h.escape(key) + r"s?\b", cq.lower()):   # whole words: "king" is not in "viking"
                    species = hint
                    break

    # ── VEHICLE-TYPE shape descriptor — the silhouette must match the type the
    # user asked for (a sports car must NOT come out an SUV). These strong shape
    # phrases, combined with a LOWER depth-lock for vehicles, let SDXL render the
    # right body. Priority order: exotic > sports > suv > truck > van > sedan.
    if base_pattern == "vehicle":
        vq = (library_query + " " + name + " " + identity)
        _LOWNEG = "SUV, crossover, minivan, van, pickup truck, station wagon, tall body, high roofline, raised ride height, boxy"
        _VT = [
            (("ferrari", "lamborghini", "mclaren", "supercar", "exotic"),
             "exotic supercar, very low-slung sleek aerodynamic body, long hood, extremely low roofline, two-door", _LOWNEG),
            (("porsche", "corvette", "sports", "coupe", "convertible", "roadster", "racing"),
             "sleek low-slung two-door sports car, long hood, low roofline, short rear deck, aggressive aerodynamic styling, wide stance", _LOWNEG),
            (("suv", "jeep", "crossover", "wagon", "land rover", "range rover"),
             "tall boxy SUV, high ground clearance, upright blocky body, large greenhouse", "low sports car, sports coupe"),
            (("pickup", "truck"),
             "pickup truck, tall cabin, open cargo bed, high stance", "sports car, sedan"),
            (("van", "minivan", "bus"),
             "boxy van, tall slab-sided body", "sports car"),
            (("sedan", "saloon"),
             "four-door sedan, classic three-box silhouette", "SUV, van"),
        ]
        species = "modern car, clean glossy paint, polished bodywork"
        vehicle_neg = ""
        for keys, desc, neg in _VT:
            if any(k in vq for k in keys):
                species = desc; vehicle_neg = neg
                break

    # THE SUBJECT LEADS (2026-09-25). SDXL's text encoders read 77 tokens and
    # weigh the first ones most. With the studio boilerplate first, the
    # wardrobe sat at token forty and the pose framing fell off the end; the
    # scientist came out in a futuristic jumpsuit. Subject and costume first,
    # then the framing, then the studio, and the whole thing kept under 77.
    if species and core and species.lower().startswith(core):   # "a scientist, scientist wearing..." reads as two people
        positive_parts = [f"a {species}", framing, preset["positive"]]
    else:
        positive_parts = [f"a {subject_phrase}", species, framing, preset["positive"]]
    # A PHOTOGRAPH FIRST (2026-10-08): once the whole prompt was read, "studio
    # photograph" sat sixty tokens in, and a frontier sheriff came out a
    # Western cartoon. The medium leads.
    if style == "photoreal" and positive_parts:
        positive_parts[0] = "modern colour photograph of " + positive_parts[0]
    positive = ", ".join(p for p in positive_parts if p)

    # Append pattern-specific negative directives so SDXL avoids action poses
    pattern_neg = PATTERN_NEGATIVE.get(base_pattern, "")
    cloth_neg = ""
    if base_pattern == "biped":
        _cq = " ".join((identity, name, library_query))
        if not any(w in _cq for w in ("suit", "armor", "armour", "hero", "astronaut", "space", "racer", "diver", "robot", "cyborg", "pilot", "knight", "samurai", "viking")):
            cloth_neg = "robot, android, mannequin, cyborg, leggings, tights, futuristic bodysuit, skin-tight suit, spandex, spacesuit, superhero costume, sci-fi armor, racing suit, wetsuit, blotchy pattern, printed pattern, camouflage print, paint splashes"
    # NOBODY UNDRESSED (2026-10-02): the library's ranger was generated
    # shirtless in briefs and played that way in every game that cast him;
    # a person is always dressed for the part
    if base_pattern == "biped":
        cloth_neg = ", ".join(x for x in ("shirtless, bare chest, naked, nude, underwear, briefs, swimsuit, swimwear, bikini", cloth_neg) if x)
    negative_parts = [preset["negative"], pattern_neg, vehicle_neg, cloth_neg]
    negative = ", ".join(p for p in negative_parts if p)
    return positive, negative


def _not_one_thing(img, noun: str, pattern: str) -> float:
    """CLIP's belief that a reference is NOT one whole, level subject.

    The failures it catches are the ones that reached a game: a sheet of many
    small copies instead of one object (the gem), one object in a scatter of
    smaller ones (the diamond), and a swimmer leaping on a diagonal (the
    dolphin, which meshed standing on its tail). Same model as the blotch and
    asset judges."""
    import torch
    _blotchiness_model_ready()
    model, proc = _CLIP_JUDGE
    dev = next(model.parameters()).device
    n = (noun or "object").strip()
    pos = [f"a single {n} on a plain background", f"one {n}, whole, centered"]
    neg = [f"a pattern of many small {n}s", "a collage of many small objects", "a wallpaper of repeated icons",
           f"one {n} surrounded by many smaller ones"]
    if pattern in ("aquatic", "quadruped"):
        pos.append(f"a {n} seen from the side, body level")
        neg.append(f"a {n} leaping diagonally, body tilted up")
    with torch.no_grad():
        inputs = proc(text=pos + neg, images=img.convert("RGB"), return_tensors="pt", padding=True).to(dev)
        probs = torch.softmax(model(**inputs).logits_per_image[0].float(), dim=0)
    return float(probs[len(pos):].sum())


def _blotchiness_model_ready():
    """Load the shared CLIP judge once."""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    global _CLIP_JUDGE
    try:
        _CLIP_JUDGE
    except NameError:
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _CLIP_JUDGE = (CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).eval(),
                       CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32"))


def _blotchiness(img) -> float:
    """CLIP's belief that the figure's clothes are splashed or blotchy rather
    than plain; the same model the asset judge uses (openai/clip-vit-base-patch32, MIT)."""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    global _CLIP_JUDGE
    try:
        model, proc = _CLIP_JUDGE
    except NameError:
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).eval()
        proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        _CLIP_JUDGE = (model, proc)
    dev = next(model.parameters()).device
    pos = ["a person in plain clean clothes", "a person wearing a plain outfit with no pattern"]
    neg = ["a person with paint splashes on their clothes", "clothes covered in blotchy yellow stains",
           "a person in a loud printed pattern outfit"]
    with torch.no_grad():
        inputs = proc(text=pos + neg, images=img.convert("RGB"), return_tensors="pt", padding=True).to(dev)
        probs = torch.softmax(model(**inputs).logits_per_image[0].float(), dim=0)
    return float(probs[len(pos):].sum())


def generate_reference(
    slots: Dict[str, Any],
    output_path: str | Path,
    style: str = "photoreal",
    width: int = 1024,
    height: int = 1024,
    guidance_scale: float = 7.5,
    steps: int = 28,
    seed: Optional[int] = None,
) -> Path:
    """Generate a clean reference image of the subject.

    Args:
        slots: extracted slot dict (subject.base_pattern, .library_query, etc.)
        output_path: where to save the PNG
        style: photoreal / cartoon / anime / painting / claymation
        width, height: defaults to SDXL native 1024×1024 (best quality)
        guidance_scale: SDXL CFG. 7-9 works.
        steps: denoising steps. 25-30 is the sweet spot.
        seed: reproducibility. None = random.

    Returns:
        Path to the saved PNG.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import torch
    positive, negative = _build_reference_prompt(slots, style)

    # If a pose template exists for this pattern, use ControlNet-Depth to lock
    # subject composition. This is what makes "a dog" and "a cat" produce
    # the SAME pose (and therefore TripoSR produces the same mesh orientation).
    subj = (slots or {}).get("subject", {}) or {}
    base_pattern = subj.get("base_pattern", "primitive_geo")
    template_path = get_pose_template_path(base_pattern)

    depth_image = None
    if template_path is not None:
        from PIL import Image
        depth_image = Image.open(template_path).convert("RGB").resize(
            (int(width), int(height)), Image.BILINEAR
        )

    # Vehicles: the generic boxy vehicle_depth template forced an SUV/van
    # silhouette regardless of "sports car" — even at low conditioning. SKIP the
    # depth template for vehicles so the strong type descriptor + anti-SUV
    # negatives drive the body (orientation is handled later by the silhouette
    # gate). Set FS_VEHICLE_DEPTH=1 to restore depth-locked vehicle references.
    _cscale = CONTROLNET_CONDITIONING_SCALE
    # BIPED POSE IS UNSOLVED, AND THE LEVERS ARE MAPPED (2026-08-07).
    # Every generated biped is born T-posed while mocap_retarget binds its
    # arm chain expecting an A-pose (hands ~0.18H below the shoulders), so
    # each new character arrives with its arms splayed and gets corrected by
    # hand downstream. The cause is NOT the prompt: pose comes from
    # controlnet-depth against pose_templates/biped_depth.png.
    #
    # Measured, all on 'woman', so the next attempt does not repeat them:
    #   - negative prompt "T-pose, arms outstretched" +4 more : no effect
    #   - A-pose depth template at this 0.35 scale             : still T-pose
    #   - A-pose template at scale 0.75  : incoherent, and it reproduced the
    #     template's own hard mask edges as a rectangle across the chest —
    #     any future template edit must be feathered
    #   - A-pose template at scale 0.55  : T-pose gone, but SDXL omitted the
    #     arms below the shoulder entirely
    # The template rebuild itself is sound (rotate the arms about the
    # measured shoulder joints, inpaint the vacated region from background,
    # feather every edit) and is kept in git history at this commit.
    #
    # Left at the shared 0.35 deliberately: it is the only setting that
    # yields a coherent figure today, and shipping armless references would
    # be a worse asset pipeline than the T-posed one it replaced.
    if base_pattern == "vehicle":
        vq = (library_query + " " + name + " " + identity)
        _LOWNEG = "SUV, crossover, minivan, van, pickup truck, station wagon, tall body, high roofline, raised ride height, boxy"
        _VT = [
            (("ferrari", "lamborghini", "mclaren", "supercar", "exotic"),
             "exotic supercar, very low-slung sleek aerodynamic body, long hood, extremely low roofline, two-door", _LOWNEG),
            (("porsche", "corvette", "sports", "coupe", "convertible", "roadster", "racing"),
             "sleek low-slung two-door sports car, long hood, low roofline, short rear deck, aggressive aerodynamic styling, wide stance", _LOWNEG),
            (("suv", "jeep", "crossover", "wagon", "land rover", "range rover"),
             "tall boxy SUV, high ground clearance, upright blocky body, large greenhouse", "low sports car, sports coupe"),
            (("pickup", "truck"),
             "pickup truck, tall cabin, open cargo bed, high stance", "sports car, sedan"),
            (("van", "minivan", "bus"),
             "boxy van, tall slab-sided body", "sports car"),
            (("sedan", "saloon"),
             "four-door sedan, classic three-box silhouette", "SUV, van"),
        ]
        species = "modern car, clean glossy paint, polished bodywork"
        vehicle_neg = ""
        for keys, desc, neg in _VT:
            if any(k in vq for k in keys):
                species = desc; vehicle_neg = neg
                break

    # THE SUBJECT LEADS (2026-09-25). SDXL's text encoders read 77 tokens and
    # weigh the first ones most. With the studio boilerplate first, the
    # wardrobe sat at token forty and the pose framing fell off the end; the
    # scientist came out in a futuristic jumpsuit. Subject and costume first,
    # then the framing, then the studio, and the whole thing kept under 77.
    if species and core and species.lower().startswith(core):   # "a scientist, scientist wearing..." reads as two people
        positive_parts = [f"a {species}", framing, preset["positive"]]
    else:
        positive_parts = [f"a {subject_phrase}", species, framing, preset["positive"]]
    positive = ", ".join(p for p in positive_parts if p)

    # Append pattern-specific negative directives so SDXL avoids action poses
    pattern_neg = PATTERN_NEGATIVE.get(base_pattern, "")
    cloth_neg = ""
    if base_pattern == "biped":
        _cq = " ".join((identity, name, library_query))
        if not any(w in _cq for w in ("suit", "armor", "armour", "hero", "astronaut", "space", "racer", "diver", "robot", "cyborg", "pilot", "knight", "samurai", "viking")):
            cloth_neg = "robot, android, mannequin, cyborg, leggings, tights, futuristic bodysuit, skin-tight suit, spandex, spacesuit, superhero costume, sci-fi armor, racing suit, wetsuit, blotchy pattern, printed pattern, camouflage print, paint splashes"
    # NOBODY UNDRESSED (2026-10-02): the library's ranger was generated
    # shirtless in briefs and played that way in every game that cast him;
    # a person is always dressed for the part
    if base_pattern == "biped":
        cloth_neg = ", ".join(x for x in ("shirtless, bare chest, naked, nude, underwear, briefs, swimsuit, swimwear, bikini", cloth_neg) if x)
    negative_parts = [preset["negative"], pattern_neg, vehicle_neg, cloth_neg]
    negative = ", ".join(p for p in negative_parts if p)
    return positive, negative


def generate_reference(
    slots: Dict[str, Any],
    output_path: str | Path,
    style: str = "photoreal",
    width: int = 1024,
    height: int = 1024,
    guidance_scale: float = 7.5,
    steps: int = 28,
    seed: Optional[int] = None,
) -> Path:
    """Generate a clean reference image of the subject.

    Args:
        slots: extracted slot dict (subject.base_pattern, .library_query, etc.)
        output_path: where to save the PNG
        style: photoreal / cartoon / anime / painting / claymation
        width, height: defaults to SDXL native 1024×1024 (best quality)
        guidance_scale: SDXL CFG. 7-9 works.
        steps: denoising steps. 25-30 is the sweet spot.
        seed: reproducibility. None = random.

    Returns:
        Path to the saved PNG.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import torch
    positive, negative = _build_reference_prompt(slots, style)

    # If a pose template exists for this pattern, use ControlNet-Depth to lock
    # subject composition. This is what makes "a dog" and "a cat" produce
    # the SAME pose (and therefore TripoSR produces the same mesh orientation).
    subj = (slots or {}).get("subject", {}) or {}
    base_pattern = subj.get("base_pattern", "primitive_geo")
    template_path = get_pose_template_path(base_pattern)

    depth_image = None
    if template_path is not None:
        from PIL import Image
        depth_image = Image.open(template_path).convert("RGB").resize(
            (int(width), int(height)), Image.BILINEAR
        )

    # Vehicles: the generic boxy vehicle_depth template forced an SUV/van
    # silhouette regardless of "sports car" — even at low conditioning. SKIP the
    # depth template for vehicles so the strong type descriptor + anti-SUV
    # negatives drive the body (orientation is handled later by the silhouette
    # gate). Set FS_VEHICLE_DEPTH=1 to restore depth-locked vehicle references.
    _cscale = CONTROLNET_CONDITIONING_SCALE
    # BIPEDS NEED THE POSE TO ACTUALLY BIND (2026-08-07). At the shared 0.35
    # the depth map is a hint, and SDXL's own prior for "full body character
    # reference" is overwhelmingly a T-pose — so every biped came out
    # T-posed no matter what the template said. Proven the hard way: the
    # template was rebuilt into a clean A-pose and the output did not move
    # until this scale did. Bipeds are the one pattern where the pose is
    # load-bearing downstream (mocap_retarget binds its arm chain against an
    # A-pose), so they get a scale that makes the template govern.
    if base_pattern == "biped":
        _cscale = float(_os.environ.get("FS_CONTROLNET_SCALE_BIPED", "0.55"))
    if base_pattern == "vehicle" and _os.environ.get("FS_VEHICLE_DEPTH", "0") != "1":
        depth_image = None

    def _gen_once(s):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # HERO REROLL (Phase 108): FS_REF_SEED offsets the reference seed so
        # 'try a different hero' produces a genuinely different look
        _off = int(_os.environ.get("FS_REF_SEED", "0") or 0)
        if s is not None and _off:
            s = int(s) + _off
        gen = torch.Generator(device=device).manual_seed(int(s)) if s is not None else None
        if depth_image is not None:
            pipe = _load_t2i_controlnet_pipeline()
            img = pipe(
                **_long_prompt_kwargs(pipe, positive, negative), image=depth_image,
                width=int(width), height=int(height),
                guidance_scale=float(guidance_scale), num_inference_steps=int(steps),
                controlnet_conditioning_scale=_cscale,
                generator=gen,
            ).images[0]
            return img, f"controlnet-depth(pattern={base_pattern})"
        pipe = _load_t2i_pipeline()
        img = pipe(
            **_long_prompt_kwargs(pipe, positive, negative),
            width=int(width), height=int(height),
            guidance_scale=float(guidance_scale), num_inference_steps=int(steps),
            generator=gen,
        ).images[0]
        return img, "plain-sdxl"

    # Single-shot generation. The 5-legged-dog artifact is NOT a seed lottery —
    # it was a corrupt control signal (the quadruped depth template literally
    # depicted 5 legs), so ControlNet faithfully reproduced it. That is fixed at
    # the source (clean 4-leg depth template). A silhouette leg-counter can't
    # reliably distinguish "4 legs + hanging tail" from "5 legs", so we do NOT
    # gate on it — the clean template is the guarantee.
    t0 = time.time()
    img, mode_tag = _gen_once(seed)
    # THE REFERENCE IS JUDGED BEFORE THE MESH IS MADE (2026-09-28). A
    # scientist's coat came out splashed with paint, and every bake since
    # carried the splashes; the judge only ever saw the finished model. The
    # same CLIP scores the picture for paint splashes and blotchy prints on a
    # plainly dressed figure; a blotchy one is rolled again on a new seed,
    # twice at most, and the least blotchy of the tries is kept.
    if base_pattern == "biped":
        try:
            tries = [(img, mode_tag, _blotchiness(img))]
            for k in (1, 2):
                if tries[-1][2] < 0.45:
                    break
                s2 = (int(seed) if seed is not None else 1000) + 101 * k
                img2, tag2 = _gen_once(s2)
                tries.append((img2, tag2, _blotchiness(img2)))
            best = min(tries, key=lambda t: t[2])
            print(f"[reference] blotchiness " + ", ".join(f"{t[2]:.2f}" for t in tries) + f"; kept {best[2]:.2f}")
            img, mode_tag = best[0], best[1]
        except Exception as _je:  # noqa: BLE001
            print(f"[reference] blotch judge skipped ({type(_je).__name__})")
    # ONE WHOLE THING, LEVEL (2026-09-29): the same reroll for props, animals and
    # swimmers, judged for being a single subject instead of a sheet or a
    # scatter, and for lying level instead of leaping on a diagonal
    elif base_pattern != "vehicle":
        try:
            _noun = subj.get("name") or subj.get("identity_phrase") or ""
            tries = [(img, mode_tag, _not_one_thing(img, _noun, base_pattern))]
            for k in (1, 2):
                if tries[-1][2] < 0.5:
                    break
                s2 = (int(seed) if seed is not None else 1000) + 101 * k
                img2, tag2 = _gen_once(s2)
                tries.append((img2, tag2, _not_one_thing(img2, _noun, base_pattern)))
            best = min(tries, key=lambda t: t[2])
            print(f"[reference] not-one-thing " + ", ".join(f"{t[2]:.2f}" for t in tries) + f"; kept {best[2]:.2f}")
            img, mode_tag = best[0], best[1]
        except Exception as _oe:  # noqa: BLE001
            print(f"[reference] single-subject judge skipped ({type(_oe).__name__})")
    elapsed = time.time() - t0
    img.save(output_path)
    print(f"[reference] saved → {output_path.name} ({width}×{height}, "
          f"{elapsed:.1f}s, {mode_tag})")
    return output_path
