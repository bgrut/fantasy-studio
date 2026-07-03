"""
SDXL img2img refiner — turns a procedural Blender frame into a polished image.

The refiner is the heart of Phase 16. It bridges the gap between "blocky
metaball dog" and "photoreal dog" by passing the Blender render through
SDXL with low-to-medium strength + depth ControlNet for geometry lock.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Style presets (positive + negative prompts per style)
# ---------------------------------------------------------------------------

# Tightened to stay under CLIP's 77-token cap once subject + proportion +
# mood phrases get appended. Each base ~12 tokens, leaving ~60 for the
# dynamic parts.
STYLE_PRESETS: Dict[str, Dict[str, str]] = {
    "photoreal": {
        "positive": "photorealistic, sharp focus, natural lighting, high detail",
        "negative": "cartoon, drawing, blurry, deformed, plastic, low poly, toy",
    },
    "cartoon": {
        "positive": "pixar 3d style, vibrant, smooth shading, expressive",
        "negative": "photorealistic, gritty, blurry, deformed, scary",
    },
    "anime": {
        "positive": "anime cel-shaded, vibrant, ghibli inspired, clean lines",
        "negative": "photorealistic, 3d render, blurry, deformed",
    },
    "painting": {
        "positive": "oil painting, painterly brushstrokes, dramatic lighting",
        "negative": "photograph, 3d render, blurry, digital art",
    },
    "claymation": {
        "positive": "claymation, stop motion, soft clay, aardman style",
        "negative": "photorealistic, smooth digital, blurry, plastic",
    },
}


# ---------------------------------------------------------------------------
# Category-aware proportion prompts (Phase 16 user requirement)
# ---------------------------------------------------------------------------

# Per-pattern proportion conditioning. The user explicitly wants the diffusion
# layer to "understand proportions" for animals/cars/humans/characters — we
# inject these into the positive prompt so SDXL biases towards correct anatomy.
# Trimmed to ~8 tokens each so we stay under 77 with subject + style.
PATTERN_PROPORTION_PROMPTS: Dict[str, str] = {
    "quadruped":    "correct four-legged anatomy, defined snout ears legs",
    "biped":        "correct human anatomy, proportional limbs, natural pose",
    "vehicle":      "automotive proportions, four wheels, windshield, headlights",
    "tree":         "natural tree, trunk and canopy proportion",
    "celestial":    "spherical astronomical body, detailed surface",
    "primitive_geo": "",
}

# ~5-8 tokens each
SPECIES_ANATOMY: Dict[str, str] = {
    "cat":    "domestic cat, triangular ears, whiskers",
    "dog":    "dog, prominent snout, floppy ears",
    "fox":    "red fox, bushy tail, pointed muzzle",
    "rabbit": "rabbit, long ears, fluffy tail",
    "lion":   "lion with full mane, muscular",
    "horse":  "horse, long legs, flowing mane",
    "sheep":  "fluffy sheep, dense wool",
    "bear":   "bear, thick fur, rounded ears",
    "wolf":   "gray wolf, thick fur ruff",
    "human":  "human, realistic face features",
    "person": "person, natural skin, proportional body",
    "car":    "sleek modern car, glossy paint",
    "sports": "sports car, low aggressive styling",
}


# ---------------------------------------------------------------------------
# Lazy global pipeline cache
# ---------------------------------------------------------------------------

_PIPELINE = None
_PIPELINE_KIND: Optional[str] = None  # "controlnet" or "plain"


def is_available() -> bool:
    """Return True iff torch + diffusers import AND SDXL is downloaded."""
    try:
        import torch  # noqa: F401
        import diffusers  # noqa: F401
        from huggingface_hub import try_to_load_from_cache
        # Check at least one of the required SDXL config files is in cache
        path = try_to_load_from_cache(
            repo_id="stabilityai/stable-diffusion-xl-base-1.0",
            filename="model_index.json",
        )
        return path is not None
    except Exception:
        return False


def _load_pipeline(use_controlnet: bool = True):
    """Construct (or return cached) the SDXL img2img pipeline."""
    global _PIPELINE, _PIPELINE_KIND
    want_kind = "controlnet" if use_controlnet else "plain"
    if _PIPELINE is not None and _PIPELINE_KIND == want_kind:
        return _PIPELINE

    import torch
    from diffusers import (
        StableDiffusionXLImg2ImgPipeline,
        AutoencoderKL,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    # Stable VAE (fixes black-image bug on consumer GPUs in fp16)
    try:
        vae = AutoencoderKL.from_pretrained(
            "madebyollin/sdxl-vae-fp16-fix", torch_dtype=dtype,
        )
    except Exception:
        vae = None

    if use_controlnet:
        try:
            from diffusers import StableDiffusionXLControlNetImg2ImgPipeline, ControlNetModel
            controlnet = ControlNetModel.from_pretrained(
                "diffusers/controlnet-depth-sdxl-1.0", torch_dtype=dtype,
            )
            pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
                "stabilityai/stable-diffusion-xl-base-1.0",
                controlnet=controlnet,
                vae=vae,
                torch_dtype=dtype,
                variant="fp16" if device == "cuda" else None,
                use_safetensors=True,
            )
            _PIPELINE_KIND = "controlnet"
        except Exception as e:
            print(f"[refiner] ControlNet unavailable ({e}); falling back to plain img2img")
            use_controlnet = False

    if not use_controlnet:
        pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0",
            vae=vae,
            torch_dtype=dtype,
            variant="fp16" if device == "cuda" else None,
            use_safetensors=True,
        )
        _PIPELINE_KIND = "plain"

    pipe = pipe.to(device)

    # Memory savers. Modern PyTorch (2.2+) ships scaled_dot_product_attention
    # so xformers is redundant — only try to enable if available, silently skip.
    if device == "cuda":
        try:
            pipe.enable_vae_tiling()
        except Exception:
            pass
        # Only try xformers if it imports cleanly (avoids noisy warning on Blackwell)
        try:
            import xformers  # noqa: F401
            pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            pass  # PyTorch's native SDPA is already used by default in diffusers

    _PIPELINE = pipe
    return pipe


def unload():
    """Free the cached SDXL pipeline's GPU VRAM.

    Critical when interleaving with the Blender bridge: a resident SDXL pipeline
    holds ~6-8 GB, which starves the bridge's EEVEE renderer and yields BLACK
    frames. Call this once the img2img passes are done, before more EEVEE renders.
    """
    global _PIPELINE, _PIPELINE_KIND
    if _PIPELINE is None:
        return
    # Drop the reference outright (moving an fp16 pipe to CPU just warns); the
    # GPU allocation is freed by empty_cache once the Python ref is gone.
    _PIPELINE = None
    _PIPELINE_KIND = None
    try:
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass


def _controlnet_subprocess_paths():
    """Return (venv_triposg python, refine_subprocess.py) if both exist, else None.
    Reuses the isolated venv_triposg (diffusers 0.38, which HAS the SDXL ControlNet
    Img2Img class) so the depth-locked refiner never touches the main venv's
    pinned diffusers 0.20.2."""
    backend = Path(__file__).resolve().parents[2]
    py = backend / "venv_triposg" / "Scripts" / "python.exe"
    script = backend / "scripts" / "refine_subprocess.py"
    return (py, script) if (py.exists() and script.exists()) else None


def is_controlnet_available() -> bool:
    return _controlnet_subprocess_paths() is not None


def refine_frames_controlnet(
    jobs,
    slots: Dict[str, Any],
    style: str = "photoreal",
    strength: float = 0.72,
    steps: int = 28,
    seed: int = 42,
    controlnet_scale: float = 0.45,
    timeout: int = 600,
):
    """Depth-locked SDXL ControlNet img2img via the isolated venv_triposg
    subprocess. Sharper fur + features aligned to geometry (de-clay). BATCHED:
    one subprocess refines all jobs (loads the ~10 GB pipeline once).

    jobs: list of (input_image_path, output_path). Raises on failure so the
    caller can fall back to the in-process plain refiner.
    """
    import subprocess
    import json
    import tempfile
    paths = _controlnet_subprocess_paths()
    if paths is None:
        raise RuntimeError("controlnet subprocess unavailable (venv_triposg/script missing)")
    py, script = paths
    positive, negative = _build_prompts(slots, style)
    manifest = {
        "prompt": positive, "negative": negative, "strength": strength,
        "steps": steps, "seed": seed, "controlnet_scale": controlnet_scale,
        "jobs": [{"image": str(i), "output": str(o)} for i, o in jobs],
    }
    mf = Path(tempfile.gettempdir()) / "fs_refine_manifest.json"
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    proc = subprocess.run([str(py), str(script), "--manifest", str(mf)],
                          capture_output=True, text=True, timeout=timeout)
    missing = [o for _, o in jobs if not Path(o).exists()]
    if proc.returncode != 0 or missing:
        tail = (proc.stderr or proc.stdout or "")[-700:]
        raise RuntimeError(f"controlnet refine failed (exit {proc.returncode}, "
                           f"missing {len(missing)}):\n{tail}")
    return [Path(o) for _, o in jobs]


def _build_prompts(slots: Dict[str, Any], style: str) -> tuple[str, str]:
    """Compose positive + negative prompts from slot semantics + style."""
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["photoreal"])
    subj = (slots or {}).get("subject", {}) or {}
    scene = (slots or {}).get("scene", {}) or {}

    base_pattern = subj.get("base_pattern", "primitive_geo")
    library_query = (subj.get("library_query") or "").lower()
    name = (subj.get("name") or "").lower()
    color = subj.get("color_name") or ""
    material = subj.get("material") or ""
    mood = scene.get("mood") or ""

    # Subject phrase
    descriptor_bits: List[str] = []
    if color and color != "neutral":
        descriptor_bits.append(color)
    if material and material not in ("matte", "plastic"):
        descriptor_bits.append(material)
    if library_query:
        descriptor_bits.append(library_query)
    elif name:
        descriptor_bits.append(name)
    subject_phrase = " ".join(descriptor_bits) or "subject"

    # Proportion conditioning (the user's headline ask)
    proportion = PATTERN_PROPORTION_PROMPTS.get(base_pattern, "")
    species = ""
    for key, hint in SPECIES_ANATOMY.items():
        if key in library_query or key in name:
            species = hint
            break

    # Mood / lighting
    mood_phrase = ""
    if mood in ("sunset", "sunrise", "golden hour", "dusk"):
        mood_phrase = "warm golden hour lighting, soft shadows"
    elif mood in ("night", "moonlight", "moody"):
        mood_phrase = "moody night lighting, deep shadows, atmospheric"
    elif mood in ("noon", "daylight", "bright"):
        mood_phrase = "bright daylight, clear blue sky, vibrant"
    elif mood == "studio":
        mood_phrase = "studio lighting, clean white background, product photography"

    positive_parts = [
        preset["positive"],
        f"a {subject_phrase}",
        proportion,
        species,
        mood_phrase,
    ]
    positive = ", ".join(p for p in positive_parts if p)
    negative = preset["negative"]
    return positive, negative


_MIDAS = None

def _make_depth_map(pil_image):
    """Generate a depth map for ControlNet conditioning, sized to match input.

    SDXL ControlNet expects the control image at EXACTLY the same dimensions
    as the noise tensor (which derives from the input image). MidasDetector
    returns its own resolution by default → we resize + ensure multiples of 8.
    """
    from PIL import Image
    global _MIDAS
    try:
        if _MIDAS is None:
            from controlnet_aux import MidasDetector
            _MIDAS = MidasDetector.from_pretrained("lllyasviel/Annotators")
        depth = _MIDAS(pil_image)
    except Exception as e:
        print(f"[refiner] depth estimation failed ({e}); using grayscale fallback")
        depth = pil_image.convert("L").convert("RGB")
    # Always force depth → exact input dimensions, multiples of 8
    w, h = pil_image.size
    w8 = (w // 8) * 8
    h8 = (h // 8) * 8
    if (w, h) != (w8, h8):
        pil_image_resized = pil_image.resize((w8, h8), Image.LANCZOS)
    else:
        pil_image_resized = pil_image
    depth = depth.resize((w8, h8), Image.LANCZOS).convert("RGB")
    return depth, pil_image_resized


def refine_frame(
    image_path: str | Path,
    slots: Dict[str, Any],
    style: str = "photoreal",
    strength: float = 0.55,
    guidance_scale: float = 7.5,
    steps: int = 25,
    seed: Optional[int] = None,
    use_controlnet: bool = True,
    output_path: Optional[str | Path] = None,
) -> Path:
    """Refine one Blender PNG through SDXL img2img.

    Args:
        image_path: source PNG (e.g. from render_frame / render_animation)
        slots: extracted slot dict (used to build the prompt)
        style: photoreal | cartoon | anime | painting | claymation
        strength: 0.0 = no change, 1.0 = ignore source. 0.45-0.65 is the sweet
                  spot for refinement — keeps silhouette + lighting.
        guidance_scale: SDXL CFG. 7-9 is normal.
        steps: denoising steps. 20-30 is the cost/quality sweet spot.
        seed: reproducibility. None → random per call.
        use_controlnet: whether to use depth ControlNet (recommended).
        output_path: explicit destination; defaults to <stem>.refined.png

    Returns:
        Path to the refined PNG.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    from PIL import Image
    import torch

    src_img = Image.open(image_path).convert("RGB")
    pipe = _load_pipeline(use_controlnet=use_controlnet)
    positive, negative = _build_prompts(slots, style)

    generator = None
    if seed is not None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        generator = torch.Generator(device=device).manual_seed(int(seed))

    # If using ControlNet we must resize image + depth in lockstep to a
    # multiple of 8. _make_depth_map returns both, already aligned.
    if _PIPELINE_KIND == "controlnet":
        depth, src_img_aligned = _make_depth_map(src_img)
    else:
        depth = None
        # Still need to pad to multiples of 8 for plain SDXL
        from PIL import Image as _PILImage
        w, h = src_img.size
        w8 = (w // 8) * 8
        h8 = (h // 8) * 8
        src_img_aligned = src_img.resize((w8, h8), _PILImage.LANCZOS) if (w, h) != (w8, h8) else src_img

    kwargs = dict(
        prompt=positive,
        negative_prompt=negative,
        image=src_img_aligned,
        strength=float(strength),
        guidance_scale=float(guidance_scale),
        num_inference_steps=int(steps),
        generator=generator,
    )
    if depth is not None:
        kwargs["control_image"] = depth
        kwargs["controlnet_conditioning_scale"] = 0.5

    result = pipe(**kwargs).images[0]

    # Restore original dimensions on save so downstream encode_video stays consistent
    if result.size != src_img.size:
        from PIL import Image as _PILImage
        result = result.resize(src_img.size, _PILImage.LANCZOS)

    out = Path(output_path) if output_path else image_path.with_suffix(".refined.png")
    result.save(out)
    return out


def refine_animation(
    frame_dir: str | Path,
    slots: Dict[str, Any],
    style: str = "photoreal",
    strength: float = 0.55,
    pattern: str = "frame_*.png",
    seed: Optional[int] = 12345,  # fixed seed → frame-to-frame coherence
    **kwargs,
) -> int:
    """Refine every frame in a directory. Returns count refined.

    Frames are processed sequentially. A fixed seed across frames gives
    rough temporal coherence (full coherence needs a video diffusion model;
    that's out of scope for v1).
    """
    frame_dir = Path(frame_dir)
    frames = sorted(frame_dir.glob(pattern))
    if not frames:
        return 0

    t0 = time.time()
    print(f"[refiner] refining {len(frames)} frames, style={style}, strength={strength}")
    for i, f in enumerate(frames, 1):
        refine_frame(f, slots, style=style, strength=strength, seed=seed,
                     output_path=f, **kwargs)
        if i % 10 == 0 or i == len(frames):
            elapsed = time.time() - t0
            avg = elapsed / i
            eta = avg * (len(frames) - i)
            print(f"[refiner] frame {i}/{len(frames)} — {avg:.1f}s/frame, ETA {eta:.0f}s")
    return len(frames)
