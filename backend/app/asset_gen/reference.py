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

REFERENCE_STYLES: Dict[str, Dict[str, str]] = {
    "photoreal": {
        "positive": "studio photograph, single subject centered, plain neutral background, sharp focus, even lighting",
        "negative": "multiple subjects, busy background, blurry, cropped, partial view, watermark, text",
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
    "quadruped": "perfect side profile, standing still on all four legs, motionless, full body in frame, vertical posture, feet flat on ground",
    "biped":     "standing upright, arms at sides, neutral pose, full body in frame, feet flat on ground, A-pose",
    "vehicle":   "parked stationary, three-quarter front view, all four wheels on ground, vertical orientation",
    "tree":      "vertical trunk centered, full tree from roots to top, upright",
    "celestial": "centered sphere, fills frame",
    "primitive_geo": "centered, full object visible",
}

# Negative-prompt additions per pattern — explicitly veto problematic poses
PATTERN_NEGATIVE: Dict[str, str] = {
    "quadruped": "running, jumping, leaping, mid-action, motion blur, dynamic pose, legs in the air, tilted, perspective distortion",
    "biped":     "dynamic pose, motion blur, running, jumping, tilted, perspective distortion, cropped",
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
    color = subj.get("color_name") or ""
    material = subj.get("material") or ""

    # Build subject descriptor — keep tight, ≤25 tokens
    descriptor_bits = []
    if color and color not in ("neutral", ""):
        descriptor_bits.append(color)
    if material and material not in ("matte", "plastic"):
        descriptor_bits.append(material)
    descriptor_bits.append(library_query or name or "subject")
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
    for key, hint in species_hints.items():
        if key in library_query or key in name:
            species = hint
            break

    positive_parts = [preset["positive"], f"a {subject_phrase}", species, framing]
    positive = ", ".join(p for p in positive_parts if p)

    # Append pattern-specific negative directives so SDXL avoids action poses
    pattern_neg = PATTERN_NEGATIVE.get(base_pattern, "")
    negative_parts = [preset["negative"], pattern_neg]
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

    generator = None
    if seed is not None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        generator = torch.Generator(device=device).manual_seed(int(seed))

    t0 = time.time()
    if template_path is not None:
        from PIL import Image
        depth_image = Image.open(template_path).convert("RGB").resize(
            (int(width), int(height)), Image.BILINEAR
        )
        pipe = _load_t2i_controlnet_pipeline()
        result = pipe(
            prompt=positive,
            negative_prompt=negative,
            image=depth_image,
            width=int(width),
            height=int(height),
            guidance_scale=float(guidance_scale),
            num_inference_steps=int(steps),
            # 0.65 dictated proportions too rigidly (cat came out greyhound-shaped).
            # 0.5 keeps pose/composition locked while letting subject identity
            # (cat proportions, dog snout etc.) come through.
            controlnet_conditioning_scale=0.5,
            generator=generator,
        ).images[0]
        mode_tag = f"controlnet-depth(pattern={base_pattern})"
    else:
        pipe = _load_t2i_pipeline()
        result = pipe(
            prompt=positive,
            negative_prompt=negative,
            width=int(width),
            height=int(height),
            guidance_scale=float(guidance_scale),
            num_inference_steps=int(steps),
            generator=generator,
        ).images[0]
        mode_tag = "plain-sdxl"
    elapsed = time.time() - t0

    result.save(output_path)
    print(f"[reference] saved → {output_path.name} ({width}×{height}, {elapsed:.1f}s, {mode_tag})")
    return output_path
