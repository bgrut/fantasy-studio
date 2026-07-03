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
        "positive": "studio photograph, single subject centered, plain neutral background, sharp focus, even lighting, vibrant natural color, high detail, 8k",
        "negative": "multiple subjects, busy background, blurry, cropped, partial view, watermark, text, "
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
    "biped":     "standing upright, arms at sides, neutral pose, full body in frame, feet flat on ground, A-pose",
    "vehicle":   "parked stationary, three-quarter front view, all four wheels on ground, vertical orientation",
    "tree":      "vertical trunk centered, full tree from roots to top, upright",
    "celestial": "centered sphere, fills frame",
    "primitive_geo": "centered, full object visible",
}

# Negative-prompt additions per pattern — explicitly veto problematic poses
PATTERN_NEGATIVE: Dict[str, str] = {
    "quadruped": "running, jumping, leaping, mid-action, motion blur, dynamic pose, legs in the air, tilted, perspective distortion, wispy fur strands, flyaway hair, shaggy fuzzy silhouette, long unkempt fur",
    "biped":     "dynamic pose, motion blur, running, jumping, tilted, perspective distortion, cropped, anatomy figure, ecorche, flayed, skinless, exposed muscle, muscle suit, x-ray, medical illustration, red and blue veins, nude, naked",
    "vehicle":   "moving, motion blur, tilted, perspective distortion",
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


def _load_t2i_pipeline():
    """Construct or return cached SDXL text-to-image pipeline."""
    global _T2I_PIPELINE
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
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        _T2I_PIPELINE = None
        _T2I_CONTROLNET_PIPELINE = None


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
        "human":  "human person, neutral pose, realistic anatomy",
        "person": "person, natural anatomy",
        "car":    "modern car, clean paint job",
        "sports": "sports car, low aggressive styling",
    }
    species = ""
    vehicle_neg = ""
    for key, hint in species_hints.items():
        if key in library_query or key in name or key in identity:
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
            # generic humans need CLOTHES spelled out or SDXL renders a shirtless
            # anatomy/muscle-suit figure. Order: woman/person before "man" (which
            # is a substring of "woman") so the right one matches first.
            "woman":     "a woman wearing a casual t-shirt and jeans, fully clothed, everyday outfit",
            "girl":      "a girl wearing casual everyday clothes, fully clothed",
            "boy":       "a boy wearing casual everyday clothes, fully clothed",
            "person":    "a person wearing a casual t-shirt and jeans, fully clothed, everyday outfit",
            "human":     "a person wearing a casual t-shirt and jeans, fully clothed, everyday outfit",
            "man":       "a man wearing a casual t-shirt and jeans, fully clothed, everyday outfit",
            "guy":       "a man wearing casual everyday clothes, fully clothed",
        }
        cq = " ".join((identity, name, library_query))
        # skip if the user already described the outfit (robe/armor/etc. present)
        _has_costume = any(w in cq for w in ("robe", "armor", "armour", "staff", "hat", "cloak", "helmet", "suit", "uniform", "wings"))
        if not _has_costume:
            for key, hint in char_hints.items():
                if key in cq:
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

    positive_parts = [preset["positive"], f"a {subject_phrase}", species, framing]
    positive = ", ".join(p for p in positive_parts if p)

    # Append pattern-specific negative directives so SDXL avoids action poses
    pattern_neg = PATTERN_NEGATIVE.get(base_pattern, "")
    negative_parts = [preset["negative"], pattern_neg, vehicle_neg]
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
    if base_pattern == "vehicle" and _os.environ.get("FS_VEHICLE_DEPTH", "0") != "1":
        depth_image = None

    def _gen_once(s):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        gen = torch.Generator(device=device).manual_seed(int(s)) if s is not None else None
        if depth_image is not None:
            pipe = _load_t2i_controlnet_pipeline()
            img = pipe(
                prompt=positive, negative_prompt=negative, image=depth_image,
                width=int(width), height=int(height),
                guidance_scale=float(guidance_scale), num_inference_steps=int(steps),
                controlnet_conditioning_scale=_cscale,
                generator=gen,
            ).images[0]
            return img, f"controlnet-depth(pattern={base_pattern})"
        pipe = _load_t2i_pipeline()
        img = pipe(
            prompt=positive, negative_prompt=negative,
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
    elapsed = time.time() - t0
    img.save(output_path)
    print(f"[reference] saved → {output_path.name} ({width}×{height}, "
          f"{elapsed:.1f}s, {mode_tag})")
    return output_path
