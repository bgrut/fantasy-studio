"""
Image-to-3D mesh generation.

Two engines:

    TripoSR (default, "fast" + "standard" tier)
        - Single-view input, fast (3-5s on RTX 5070 Ti)
        - Lower mesh detail, fine for video-scale renders
        - Repo: stabilityai/TripoSR

    InstantMesh ("cinematic" tier)
        - Multi-view input (auto-generated from single view via Zero123++)
        - High mesh detail, ~15-25s per asset
        - Repo: TencentARC/InstantMesh

Both produce GLB output that Blender can import directly via the gltf addon.

The user-facing API is `generate_mesh(image_path, slots, output_path, engine, tier)` —
the orchestrator picks the engine based on render_tier; the user can override
through subj.mesh_engine if they want.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

MESH_ENGINES = ("trellis2", "triposg", "triposr", "instantmesh")

# ---------------------------------------------------------------------------
# Vendor path setup — TripoSR and InstantMesh aren't pip-installable packages,
# so we clone them to backend/vendor/ and add to sys.path on demand.
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_VENDOR_DIR = _BACKEND_ROOT / "vendor"


def _ensure_vendor_path(name: str) -> bool:
    """Add backend/vendor/<name> to sys.path if it exists. Idempotent.

    Also installs our torchmcubes shim so TripoSR's hard `from torchmcubes
    import` works without the CMake-built C++ extension. The shim wraps
    pymcubes (pure-Python marching cubes), which ships pre-built wheels.
    """
    # Always inject the torchmcubes shim before any vendor lib — it must
    # take precedence over a (failed) real torchmcubes import attempt.
    shim = _VENDOR_DIR / "_torchmcubes_shim"
    if shim.exists():
        s = str(shim)
        if s not in sys.path:
            sys.path.insert(0, s)

    p = _VENDOR_DIR / name
    if not p.exists():
        return False
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
    return True


# ---------------------------------------------------------------------------
# Tier → engine routing
# ---------------------------------------------------------------------------

def _engine_for_tier(tier: str) -> str:
    """Map render_tier → mesh engine.

    preview/fast: TripoSR (3-5s, lower detail) — keep iteration fast
    standard:     TripoSR (still cost-effective)
    cinematic:    InstantMesh (higher detail, worth the wait at this tier)
    """
    return "instantmesh" if tier == "cinematic" else "triposr"


def is_mesh_gen_available(engine: str = "triposr") -> bool:
    """Probe whether the chosen engine's model + dependencies are reachable."""
    try:
        import torch  # noqa: F401
    except Exception:
        return False
    if engine == "trellis2":
        return _is_trellis2_available()
    if engine == "triposg":
        return _is_triposg_available()
    if engine == "triposr":
        return _is_triposr_available()
    if engine == "instantmesh":
        return _is_instantmesh_available()
    return False


# ── TRELLIS.2 (isolated venv + subprocess) ──────────────────────────────────
# MIT-licensed (model + code; image encoder is Meta DINOv3 — commercial use
# permitted, gated download, attribution "Built with DINOv3"). Outputs a
# TEXTURED GLB (PBR baked from the reference) — much crisper hard-surface
# geometry than TripoSG and kills the clay look natively.
_TRELLIS2_DIR = _VENDOR_DIR / "TRELLIS.2"
_TRELLIS2_VENV_PY = _BACKEND_ROOT / "venv_trellis" / "Scripts" / "python.exe"
_TRELLIS2_SCRIPT = _BACKEND_ROOT / "scripts" / "inference_trellis2.py"


def _is_trellis2_available(verbose: bool = False) -> bool:
    ok = _TRELLIS2_DIR.exists() and _TRELLIS2_VENV_PY.exists() and _TRELLIS2_SCRIPT.exists()
    if not ok and verbose:
        print(f"[trellis2] not available — dir={_TRELLIS2_DIR.exists()} "
              f"venv={_TRELLIS2_VENV_PY.exists()} script={_TRELLIS2_SCRIPT.exists()}")
    return ok


def _gen_trellis2(pil_image, output_path: Path, seed: int = 42) -> Path:
    """Generate a TEXTURED mesh with TRELLIS.2 via its isolated venv subprocess."""
    import os as _os
    import subprocess
    import tempfile

    # The composer's quality re-roll gate retries flaky generations with a
    # different seed via this env var.
    seed = int(_os.environ.get("FS_TRELLIS_SEED", seed))

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_png = Path(tempfile.gettempdir()) / f"trellis2_in_{output_path.stem}.png"
    pil_image.convert("RGB").save(tmp_png)

    cmd = [str(_TRELLIS2_VENV_PY), str(_TRELLIS2_SCRIPT),
           "--image-input", str(tmp_png),
           "--output-path", str(output_path),
           "--seed", str(seed)]
    print(f"[trellis2] running subprocess (isolated venv)…")
    proc = subprocess.run(cmd, cwd=str(_BACKEND_ROOT), capture_output=True, text=True,
                          timeout=1800)
    if proc.returncode != 0 or not output_path.exists():
        tail = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(f"TRELLIS.2 failed (exit {proc.returncode}):\n{tail}")
    return output_path


# ── TripoSG (isolated venv + subprocess) ────────────────────────────────────
# MIT-licensed, higher-fidelity image-to-3D than TripoSR. Runs in its OWN venv
# (venv_triposg) to avoid the numpy/transformers/diffusers conflicts that would
# break SDXL + TripoSR in the main venv. We call it as a subprocess that takes
# an image and returns a GLB.
_TRIPOSG_DIR = _VENDOR_DIR / "TripoSG"
_TRIPOSG_VENV_PY = _BACKEND_ROOT / "venv_triposg" / "Scripts" / "python.exe"


def _is_triposg_available(verbose: bool = False) -> bool:
    ok = _TRIPOSG_DIR.exists() and _TRIPOSG_VENV_PY.exists() and \
        (_TRIPOSG_DIR / "scripts" / "inference_triposg.py").exists()
    if not ok and verbose:
        print(f"[triposg] not available — dir={_TRIPOSG_DIR.exists()} "
              f"venv={_TRIPOSG_VENV_PY.exists()}")
    return ok


def _gen_triposg(pil_image, output_path: Path, faces: int = 60000,
                 seed: int = 42) -> Path:
    """Generate a mesh with TripoSG via its isolated venv subprocess.

    Writes the input image to a temp PNG, runs TripoSG inference (which emits a
    GLB directly), then returns the path. TripoSG meshes are already smooth +
    high-detail, so we apply only a light color repair (no aggressive Taubin).
    """
    import subprocess
    import tempfile

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_png = Path(tempfile.gettempdir()) / f"triposg_in_{output_path.stem}.png"
    pil_image.convert("RGB").save(tmp_png)

    cmd = [
        str(_TRIPOSG_VENV_PY), "-m", "scripts.inference_triposg",
        "--image-input", str(tmp_png),
        "--output-path", str(output_path),
        "--seed", str(seed),
    ]
    if faces and faces > 0:
        cmd += ["--faces", str(faces)]

    print(f"[triposg] running subprocess (isolated venv)…")
    proc = subprocess.run(cmd, cwd=str(_TRIPOSG_DIR), capture_output=True, text=True,
                          timeout=600)
    if proc.returncode != 0 or not output_path.exists():
        tail = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(f"TripoSG failed (exit {proc.returncode}):\n{tail}")

    # Light cleanup: TripoSG has no vertex colors by default (geometry only), so
    # color-repair is a no-op; we keep the call for any future colored output.
    try:
        import trimesh
        mesh = trimesh.load(str(output_path), force="mesh")
        mesh = _cleanup_triposr_mesh(mesh)  # color-repair is conditional inside
        mesh.export(str(output_path), file_type="glb")
    except Exception as e:
        print(f"[triposg] post-load cleanup skipped ({type(e).__name__}: {e})")

    return output_path


def _is_triposr_available(verbose: bool = True) -> bool:
    """True iff TripoSR vendored repo importable AND weights present.

    Each sub-check prints why it failed when verbose=True. Useful for debugging
    the "asset_gen silently bails" class of issues.
    """
    if not _ensure_vendor_path("TripoSR"):
        if verbose:
            print(f"[triposr] vendor dir missing: {_VENDOR_DIR / 'TripoSR'}")
        return False
    try:
        from tsr.system import TSR  # noqa: F401
    except Exception as e:
        if verbose:
            print(f"[triposr] import failed: {type(e).__name__}: {e}")
        return False
    try:
        from huggingface_hub import try_to_load_from_cache
        path = try_to_load_from_cache(
            repo_id="stabilityai/TripoSR",
            filename="config.yaml",
        )
        if path is None:
            if verbose:
                print("[triposr] HF cache check: config.yaml not found in cache")
            return False
        return True
    except Exception as e:
        if verbose:
            print(f"[triposr] HF cache lookup raised: {type(e).__name__}: {e}")
        return False


def _is_instantmesh_available(verbose: bool = False) -> bool:
    """True iff InstantMesh vendored repo + Python deps + weights are all present.

    Tests all the hard dependencies:
      - vendor/InstantMesh dir (cloned)
      - src.utils.train_util importable (means deps installed: omegaconf, torch, etc.)
      - InstantMesh checkpoint downloaded
      - Optional: nvdiffrast importable (without it, mesh extraction may not work)
    """
    if not _ensure_vendor_path("InstantMesh"):
        if verbose:
            print(f"[instantmesh] vendor dir missing: {_VENDOR_DIR / 'InstantMesh'}")
        return False
    try:
        from src.utils.train_util import instantiate_from_config  # noqa: F401
    except Exception as e:
        if verbose:
            print(f"[instantmesh] import failed: {type(e).__name__}: {e}")
        return False
    try:
        from huggingface_hub import try_to_load_from_cache
        ckpt = try_to_load_from_cache(
            repo_id="TencentARC/InstantMesh",
            filename="instant_mesh_large.ckpt",
        )
        if ckpt is None:
            if verbose:
                print("[instantmesh] ckpt not in HF cache")
            return False
    except Exception as e:
        if verbose:
            print(f"[instantmesh] HF cache lookup failed: {e}")
        return False
    return True


# ---------------------------------------------------------------------------
# Pipeline caches
# ---------------------------------------------------------------------------

_TRIPOSR_MODEL = None
_INSTANTMESH_MODEL = None


def _remap_triposr_state_dict(state_dict: dict) -> dict:
    """Rewrite TripoSR checkpoint keys so they match the current model code.

    The checkpoint on HuggingFace was saved when TripoSR used HuggingFace's
    standard Dinov2Model (key format: ``encoder.layer.X.attention.attention.{query,key,value}``).
    Current TripoSR code uses its own custom DINOv2 implementation that
    expects ``layers.X.attention.{q_proj,k_proj,v_proj,o_proj}``.

    This function rewrites the keys in-place-style (returns a new dict)
    so the checkpoint loads cleanly into the new code. The tensor data
    itself is unchanged.
    """
    import re

    # Only image_tokenizer.model.* needs remapping
    new_state = {}
    pattern = re.compile(r"^image_tokenizer\.model\.encoder\.layer\.(\d+)\.(.+)$")

    # Per-key suffix remap table
    suffix_map = {
        "attention.attention.query.weight":      "attention.q_proj.weight",
        "attention.attention.query.bias":        "attention.q_proj.bias",
        "attention.attention.key.weight":        "attention.k_proj.weight",
        "attention.attention.key.bias":          "attention.k_proj.bias",
        "attention.attention.value.weight":      "attention.v_proj.weight",
        "attention.attention.value.bias":        "attention.v_proj.bias",
        "attention.output.dense.weight":         "attention.o_proj.weight",
        "attention.output.dense.bias":           "attention.o_proj.bias",
        "intermediate.dense.weight":             "mlp.fc1.weight",
        "intermediate.dense.bias":               "mlp.fc1.bias",
        "output.dense.weight":                   "mlp.fc2.weight",
        "output.dense.bias":                     "mlp.fc2.bias",
        "layernorm_before.weight":               "layernorm_before.weight",
        "layernorm_before.bias":                 "layernorm_before.bias",
        "layernorm_after.weight":                "layernorm_after.weight",
        "layernorm_after.bias":                  "layernorm_after.bias",
    }

    remapped_count = 0
    for k, v in state_dict.items():
        m = pattern.match(k)
        if m:
            layer_idx = m.group(1)
            suffix = m.group(2)
            new_suffix = suffix_map.get(suffix)
            if new_suffix is not None:
                new_key = f"image_tokenizer.model.layers.{layer_idx}.{new_suffix}"
                new_state[new_key] = v
                remapped_count += 1
                continue
        # Pass-through for anything we didn't explicitly remap
        new_state[k] = v

    print(f"[triposr] remapped {remapped_count} state_dict keys to match current model code")
    return new_state


def _load_triposr():
    global _TRIPOSR_MODEL
    if _TRIPOSR_MODEL is not None:
        return _TRIPOSR_MODEL

    import torch
    _ensure_vendor_path("TripoSR")
    try:
        from tsr.system import TSR
    except ImportError as e:
        raise RuntimeError(
            "TripoSR not installed. Run: .\\scripts\\install_mesh_engines.ps1"
        ) from e

    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Bypass TSR.from_pretrained's strict load — manually fetch config + weights
    # so we can remap state_dict keys before they hit the model.
    from huggingface_hub import hf_hub_download
    from omegaconf import OmegaConf

    config_path = hf_hub_download(repo_id="stabilityai/TripoSR", filename="config.yaml")
    weight_path = hf_hub_download(repo_id="stabilityai/TripoSR", filename="model.ckpt")

    cfg = OmegaConf.load(config_path)
    OmegaConf.resolve(cfg)  # resolve ${...} interpolations before model init
    model = TSR(cfg)

    raw_state_dict = torch.load(weight_path, map_location="cpu", weights_only=False)

    # The remap converts checkpoint's OLD HF Dinov2 keys (encoder.layer.X...) to
    # the NEW custom-DINOv2 keys (layers.X.q_proj...). But which format the model
    # ACTUALLY wants depends on the installed transformers version, since
    # `Dinov2Model.from_pretrained` builds its internals based on the lib version.
    # So: try BOTH the raw and remapped state dicts, keep whichever loads more
    # weights into the model. Whichever has fewer "missing keys" wins.
    model_keys = set(model.state_dict().keys())

    raw_overlap = len(model_keys & set(raw_state_dict.keys()))
    remapped = _remap_triposr_state_dict(raw_state_dict)
    remapped_overlap = len(model_keys & set(remapped.keys()))

    if raw_overlap >= remapped_overlap:
        print(f"[triposr] using RAW checkpoint keys "
              f"(raw={raw_overlap} vs remapped={remapped_overlap} match the model)")
        state_dict = raw_state_dict
    else:
        print(f"[triposr] using REMAPPED checkpoint keys "
              f"(remapped={remapped_overlap} vs raw={raw_overlap} match the model)")
        state_dict = remapped

    # strict=False because we only care that key NAMES line up; minor extra/missing
    # auxiliary keys (e.g. position_embeddings if HF added them) are fine.
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    if missing:
        print(f"[triposr] still missing {len(missing)} key(s) (first 3): {missing[:3]}")
    if unexpected:
        print(f"[triposr] {len(unexpected)} unexpected key(s) ignored (first 3): {unexpected[:3]}")

    model.renderer.set_chunk_size(8192)
    model.to(device)
    _TRIPOSR_MODEL = model
    return model


_ZERO123_PIPELINE = None  # Zero123++ multi-view diffusion (input → 6 views)


def _load_zero123_pipeline():
    """Load Zero123++ pipeline that generates 6 consistent views from 1 input image.

    This is InstantMesh's mandatory front-end: given a single image, Zero123++
    produces a grid of 6 views at fixed azimuth/elevation. The mesh reconstruction
    model needs these 6 views to triangulate the geometry.
    """
    global _ZERO123_PIPELINE
    if _ZERO123_PIPELINE is not None:
        return _ZERO123_PIPELINE

    import torch
    from diffusers import DiffusionPipeline, EulerAncestralDiscreteScheduler

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    # The diffusers community URL for zero123plus.py is dead (404) and the HF
    # model repo doesn't host pipeline.py at its root. InstantMesh's vendor ships
    # its own copy at vendor/InstantMesh/zero123plus/pipeline.py, so point
    # `custom_pipeline` at that local directory.
    from pathlib import Path as _Path
    _backend_root = _Path(__file__).resolve().parents[2]
    _zero123_local = _backend_root / "vendor" / "InstantMesh" / "zero123plus"
    if not (_zero123_local / "pipeline.py").exists():
        raise FileNotFoundError(
            f"Zero123++ pipeline.py not found at {_zero123_local}. "
            "Re-run scripts/install_mesh_engines.ps1 to refresh the InstantMesh vendor."
        )
    pipe = DiffusionPipeline.from_pretrained(
        "sudo-ai/zero123plus-v1.2",
        custom_pipeline=str(_zero123_local),
        torch_dtype=dtype,
    )
    pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing"
    )
    pipe = pipe.to(device)
    _ZERO123_PIPELINE = pipe
    return pipe


def _load_instantmesh():
    global _INSTANTMESH_MODEL
    if _INSTANTMESH_MODEL is not None:
        return _INSTANTMESH_MODEL

    import torch
    _ensure_vendor_path("InstantMesh")

    try:
        from src.utils.train_util import instantiate_from_config  # type: ignore
        from omegaconf import OmegaConf
    except ImportError as e:
        raise RuntimeError(
            "InstantMesh not installed or vendor path missing. "
            "Run: .\\scripts\\install_mesh_engines.ps1"
        ) from e

    device = "cuda" if torch.cuda.is_available() else "cpu"
    vendor_root = _VENDOR_DIR / "InstantMesh"
    cfg_path = vendor_root / "configs" / "instant-mesh-large.yaml"
    cfg = OmegaConf.load(str(cfg_path))
    model = instantiate_from_config(cfg.model_config)

    # Load the .ckpt downloaded by download_diffusion_models.py
    from huggingface_hub import hf_hub_download
    ckpt_path = hf_hub_download(
        repo_id="TencentARC/InstantMesh",
        filename="instant_mesh_large.ckpt",
    )
    state_dict = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    if "state_dict" in state_dict:
        state_dict = state_dict["state_dict"]
    # Strip the "lrm_generator." prefix the checkpoint adds
    state_dict = {k.replace("lrm_generator.", ""): v for k, v in state_dict.items()
                  if k.startswith("lrm_generator.")}
    model.load_state_dict(state_dict, strict=False)
    model = model.to(device).eval()

    # Initialize the model's flexicubes geometry head (does texture extraction)
    if hasattr(model, "init_flexicubes_geometry"):
        model.init_flexicubes_geometry(device, fovy=30.0)

    _INSTANTMESH_MODEL = model
    return model


# ---------------------------------------------------------------------------
# Background removal — both engines work better with a clean cutout
# ---------------------------------------------------------------------------

_REMBG_SESSION = None


def _remove_background(pil_image):
    """Strip background so the subject sits on alpha. Robust to no-rembg installs."""
    global _REMBG_SESSION
    try:
        from rembg import remove, new_session
        if _REMBG_SESSION is None:
            _REMBG_SESSION = new_session("u2net")
        return remove(pil_image, session=_REMBG_SESSION)
    except Exception as e:
        print(f"[mesh_gen] background removal unavailable ({e}); proceeding with original image")
        return pil_image.convert("RGBA")


# ---------------------------------------------------------------------------
# Pre-processing — square-pad + resize to model's native input size
# ---------------------------------------------------------------------------

def _prep_image(pil_image, size: int = 512, foreground_ratio: float = 0.85):
    """Prep image for TripoSR: remove bg, square-pad, alpha-blend to RGB.

    TripoSR's model expects a 3-channel RGB tensor where the background has
    been blended against the alpha mask using mid-gray. This matches the
    pre-processing in TripoSR's official run.py.
    """
    from PIL import Image
    import numpy as np

    # 1. Background removal — produces RGBA with subject on transparent bg
    img = _remove_background(pil_image)
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # 2. Crop to subject bbox so subject occupies foreground_ratio of canvas
    arr = np.array(img)
    alpha = arr[..., 3]
    mask = alpha > 0
    if mask.any():
        ys, xs = np.where(mask)
        y0, y1 = ys.min(), ys.max() + 1
        x0, x1 = xs.min(), xs.max() + 1
        cropped = img.crop((x0, y0, x1, y1))
    else:
        cropped = img

    # 3. Square-pad so subject is centered, leaves padding per foreground_ratio
    w, h = cropped.size
    long_side = max(w, h)
    canvas_side = int(long_side / foreground_ratio)
    bg = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
    paste_x = (canvas_side - w) // 2
    paste_y = (canvas_side - h) // 2
    bg.paste(cropped, (paste_x, paste_y))

    # 4. Resize to model's expected input size
    bg = bg.resize((size, size), Image.LANCZOS)

    # 5. Alpha-blend over mid-gray and convert to RGB (TripoSR convention)
    arr = np.array(bg).astype(np.float32) / 255.0
    rgb = arr[..., :3]
    a = arr[..., 3:4]
    blended = rgb * a + 0.5 * (1.0 - a)  # mid-gray bg
    rgb_img = Image.fromarray((blended * 255.0).clip(0, 255).astype(np.uint8), mode="RGB")
    return rgb_img


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_mesh(
    image_path: str | Path,
    output_path: str | Path,
    engine: Optional[str] = None,
    tier: str = "standard",
    foreground_ratio: float = 0.85,
    base_pattern: Optional[str] = None,
    force_flip_vertical: bool = False,
) -> Path:
    """Convert a reference image into a GLB mesh.

    Args:
        image_path: Path to the reference PNG (from asset_gen.reference)
        output_path: Where to save the .glb (parent dir created if needed)
        engine: "triposr" | "instantmesh" | None → auto-pick from tier
        tier: "preview"|"fast"|"standard"|"cinematic" → routes engine when engine=None
        foreground_ratio: how much of the input image the subject should occupy (TripoSR)

    Returns:
        Path to the saved GLB.
    """
    image_path = Path(image_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not image_path.exists():
        raise FileNotFoundError(image_path)

    chosen = engine or _engine_for_tier(tier)
    if chosen not in MESH_ENGINES:
        raise ValueError(f"unknown engine {chosen!r}; valid: {MESH_ENGINES}")

    # NEW BODY CLASSES (2026-07-06): flying/aquatic references use the SAME
    # side-profile framing as quadrupeds, so they take the same orientation
    # path. Without this the canonicalizer skipped them entirely and the
    # dragon shipped lying on its side.
    if base_pattern in ("flying", "aquatic"):
        base_pattern = "quadruped"

    from PIL import Image
    src = Image.open(image_path).convert("RGB")

    t0 = time.time()
    if chosen == "trellis2":
        # MIT-licensed, TEXTURED output, crispest hard-surface geometry.
        out = _gen_trellis2(src, output_path)
    elif chosen == "triposg":
        # MIT-licensed, higher-fidelity. Runs in its own venv via subprocess.
        out = _gen_triposg(src, output_path)
    elif chosen == "triposr":
        out = _gen_triposr(src, output_path, foreground_ratio=foreground_ratio,
                           base_pattern=base_pattern,
                           force_flip_vertical=force_flip_vertical)
    else:
        # InstantMesh outputs canonically-oriented meshes by model design.
        # No PCA, no silhouette matching, no orientation hacks needed.
        out = _gen_instantmesh(src, output_path)
    elapsed = time.time() - t0
    print(f"[mesh_gen] {chosen} → {out.name} ({elapsed:.1f}s)")
    return out


def _cleanup_triposr_mesh(mesh):
    """Phase 19 mesh-quality: de-blob the surface + fix dead-gray color patches.

    1. Taubin smoothing — melts marching-cubes lumps WITHOUT the shrinkage that
       plain Laplacian causes (preserves the silhouette).
    2. Gray-splotch repair — TripoSR leaves desaturated/gray patches where it
       couldn't infer color; blend those toward the subject's dominant color so
       there are no dead-gray blotches.
    """
    import numpy as np

    # 1. Taubin smoothing (in place; safe-guarded)
    try:
        import trimesh
        trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53, iterations=12)
    except Exception as e:
        print(f"[triposr] smoothing skipped ({type(e).__name__}: {e})")

    # 2. Gray-splotch color repair
    try:
        if hasattr(mesh.visual, "vertex_colors") and mesh.visual.vertex_colors is not None:
            vc = np.asarray(mesh.visual.vertex_colors).astype(np.float64)
            rgb = vc[:, :3]
            mx = rgb.max(axis=1)
            mn = rgb.min(axis=1)
            sat = np.where(mx > 1, (mx - mn) / np.maximum(mx, 1.0), 0.0)
            saturated = sat > 0.12          # vertices with real hue
            gray = ~saturated               # dead/gray patches
            if saturated.sum() > 200 and gray.sum() > 0:
                dominant = np.median(rgb[saturated], axis=0)
                # blend gray vertices 60% toward the dominant subject color
                rgb[gray] = 0.4 * rgb[gray] + 0.6 * dominant
                vc[:, :3] = np.clip(rgb, 0, 255)
                mesh.visual.vertex_colors = vc.astype(np.uint8)
                print(f"[triposr] color repair: blended {int(gray.sum())} gray verts "
                      f"toward dominant {tuple(int(c) for c in dominant)}")
    except Exception as e:
        print(f"[triposr] color repair skipped ({type(e).__name__}: {e})")

    return mesh


def _gen_triposr(pil_image, output_path: Path, foreground_ratio: float = 0.85,
                  base_pattern: Optional[str] = None,
                  force_flip_vertical: bool = False) -> Path:
    """TripoSR pipeline. Single-view → mesh in 3-5s on a 5070 Ti."""
    import torch
    model = _load_triposr()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    prepped = _prep_image(pil_image, size=512, foreground_ratio=foreground_ratio)
    scene_codes = model([prepped], device=device)
    # Phase 19 mesh-quality: bump marching-cubes resolution 256→320 for finer
    # geometry (less blobby). threshold 25 keeps the surface tight.
    meshes = model.extract_mesh(scene_codes, has_vertex_color=True, resolution=320, threshold=25.0)
    if not meshes:
        raise RuntimeError("TripoSR returned no meshes")
    mesh = meshes[0]

    # ── Phase 19 mesh-quality cleanup (before orientation/export) ───────────
    mesh = _cleanup_triposr_mesh(mesh)

    # Deterministic per-pattern orientation. TripoSR's output frame relative to
    # the input image is fixed (camera looks from +Z; image-up = mesh +Y), and
    # the glTF Y↔Z swap on Blender import is also fixed, so the rotation needed
    # to land the subject upright in Blender is constant per pattern type.
    # No PCA, no silhouette matching, no guessing.
    mesh = _apply_pattern_orientation(mesh, base_pattern, force_flip_vertical)

    mesh.export(str(output_path), file_type="glb")
    return output_path


# Rotation applied (in trimesh/glTF space, BEFORE Blender import) to land the
# subject upright. Tuned empirically against TripoSR + Blender's glTF import.
# Each entry is (axis, degrees). Set to None to skip rotation.
# TripoSR native frame: image-bottom pixels (subject's feet/base) land in
# mesh +Y. After glTF export + Blender import (+Y → Blender +Z, +Z → Blender
# -Y), that puts feet in Blender +Z = upside-down. The previous -90° X took
# us from upside-down to lying-on-side, which is the wrong direction.
#
# Correct fix: 180° around X in trimesh space, so feet land in trimesh -Y,
# which becomes Blender -Z (on the ground) after import. Same rotation works
# for every pattern because TripoSR's frame is deterministic.
# Phase 18 FINAL — deterministic orientation, calibrated via the 24-orientation
# contact sheet (scripts/orient_contact_sheet.py). Because the TripoSR mesh is
# byte-deterministic (CUDA determinism enabled in reference.py), the correct
# standing rotation is a CONSTANT per pattern. To (re)calibrate a pattern:
#   1. Generate one asset of that pattern.
#   2. Run: python scripts/orient_contact_sheet.py
#   3. Find the cell where the subject stands; read its rotation label.
#   4. Paste (axis, degrees) here.
# The trimesh→GLB export and Blender's glTF import conventions cancel, so the
# rotation that looks standing in the (Z-up) contact sheet is the same one that
# stands the mesh in Blender.
#
# DEPRECATED — orientation is now applied in BLENDER (composer), not here in
# trimesh. The trimesh↔glTF↔matplotlib frame conventions were the source of
# every failed calibration. Keeping this None so the mesh imports raw; the
# composer applies the calibrated per-pattern Blender Euler from
# composer._BLENDER_PATTERN_EULER (calibrated via scripts/orient_audit_blender.py).
_PATTERN_ORIENTATION = {
    "quadruped": None,
    "biped":     None,
    "vehicle":   None,
    "tree":      None,
    "celestial": None,
}


def _apply_pattern_orientation(mesh, base_pattern: str, force_flip_vertical: bool):
    """Rotate mesh so it stands upright in Blender after import.

    The rotation table is hardcoded per pattern because TripoSR's output
    coordinate frame is deterministic — there is nothing to compute.
    """
    import numpy as np
    import trimesh.transformations as tf

    rot_spec = _PATTERN_ORIENTATION.get(base_pattern)
    if rot_spec is None:
        print(f"[triposr] orientation: no rotation for pattern='{base_pattern}'")
    else:
        axis_name, degrees = rot_spec
        axis_vec = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[axis_name]
        rot = tf.rotation_matrix(np.deg2rad(degrees), axis_vec)
        mesh.apply_transform(rot)
        print(f"[triposr] orientation: rotated {degrees}° around {axis_name.upper()} "
              f"for pattern='{base_pattern}'")

    # Optional manual override: 180° around body axis if the user says the
    # head/tail came out swapped.
    if force_flip_vertical:
        rot = tf.rotation_matrix(np.pi, [0, 0, 1])
        mesh.apply_transform(rot)
        print(f"[triposr] orientation: force_flip_vertical applied (180° around Z)")

    return mesh


def _silhouette_match_orient(mesh, ref_pil_image, base_pattern: str):
    """Pick the orientation that matches the reference image's SIDE view.

    The SDXL reference shows the subject in side profile: body length
    horizontal, height vertical. We compare that to the mesh's SIDE
    silhouette (YZ plane in trimesh = looking from the +X direction)
    rather than the front/top view.

    For each candidate rotation (around the body axis = Z, plus optional
    head/foot flip via X-axis rotation), we compute the YZ-projection's
    aspect ratio (height-extent / body-length-extent) and pick the one
    closest to the reference's foreground bbox aspect ratio.

    Why this works: the reference shows the subject upright with the
    correct height/length ratio. The mesh, when oriented correctly,
    will have the same ratio in its side silhouette. Wrong rotations
    (lying on side, upside down, facing camera) produce different ratios.
    """
    import numpy as np
    import trimesh.transformations as tf

    # 1. Reference image foreground bbox aspect (height/width)
    ref_arr = np.array(ref_pil_image.convert("RGBA"))
    if ref_arr.shape[2] == 4:
        mask = ref_arr[..., 3] > 16
    else:
        mask = (ref_arr[..., :3].mean(axis=-1) < 245)
    if not mask.any():
        return mesh
    ys, xs = np.where(mask)
    ref_w = xs.max() - xs.min() + 1
    ref_h = ys.max() - ys.min() + 1
    ref_aspect = ref_h / max(ref_w, 1)
    print(f"[triposr] silhouette-match: reference aspect (h/w) = {ref_aspect:.3f}")

    # 2. Candidates — only rotations around the BODY axis (Z in trimesh)
    # and the "flip head/feet" (180° around the width axis X).
    # We do NOT rotate around the width axis because that would tip the
    # subject onto its side, which is the bug we're fixing.
    candidates = []
    for flip_xz in (False, True):  # 180° around X axis (head/feet flip)
        for rotz_deg in (0, 180):  # 180° around Z axis (left/right flip)
            candidates.append((rotz_deg, flip_xz))

    best_score = float("inf")
    best_transform = None
    best_dims = None
    for rotz_deg, flip_xz in candidates:
        T = np.eye(4)
        if flip_xz:
            T = tf.rotation_matrix(np.pi, [1, 0, 0]) @ T
        if rotz_deg:
            T = tf.rotation_matrix(np.radians(rotz_deg), [0, 0, 1]) @ T

        # Apply to vertex copies
        verts = np.asarray(mesh.vertices)
        verts_h = np.column_stack([verts, np.ones(len(verts))])
        verts_t = (T @ verts_h.T).T[:, :3]

        # SIDE view = project onto YZ plane (perpendicular to width axis X)
        # In trimesh canonical: Y=height, Z=body length. So aspect = Y / Z.
        z_extent = verts_t[:, 2].max() - verts_t[:, 2].min()
        y_extent = verts_t[:, 1].max() - verts_t[:, 1].min()
        cand_aspect = y_extent / max(z_extent, 1e-6)
        score = abs(cand_aspect - ref_aspect)
        if score < best_score:
            best_score = score
            best_transform = T
            best_dims = (y_extent, z_extent, cand_aspect)

    if best_transform is not None and not np.allclose(best_transform, np.eye(4)):
        mesh.apply_transform(best_transform)
        y_e, z_e, asp = best_dims
        print(f"[triposr] silhouette-match: applied transform "
              f"(side-view aspect {asp:.3f}, ref {ref_aspect:.3f}, score {best_score:.3f})")
    else:
        print(f"[triposr] silhouette-match: no rotation needed (already best, "
              f"score {best_score:.3f})")
    return mesh


def _canonical_orient(mesh, base_pattern: str):
    """Rotate mesh into a canonical Z-up orientation using PCA + pattern knowledge.

    Convention after this function:
        +Z = up (height)
        ±Y = body length (longest horizontal axis)
        ±X = side-to-side (width)

    Strategy:
        1. PCA on vertices → principal axes ordered by variance
        2. For ground-standing patterns (quadruped, biped), the SECOND-longest
           axis is height (animals stand tall but their nose-to-tail is longer
           than head-to-feet for most adult quadrupeds)
        3. For vehicles, the SHORTEST axis is height (cars are flat)
        4. Disambiguate "head up vs head down" by checking the heavier end of
           the height axis — gravity pulls weight to feet, so heavier end = bottom
        5. Build orthonormal basis (X, Y, Z) and rotate mesh into it

    This works on ANY input orientation TripoSR produces, no hardcoded
    per-engine rotation constants. It's the scalable solution.
    """
    import numpy as np

    # Centre on origin for clean PCA
    centroid = mesh.vertices.mean(axis=0)
    mesh.apply_translation(-centroid)

    # PCA via eigen-decomposition of the covariance matrix
    cov = np.cov(np.asarray(mesh.vertices).T)
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending order
    order = np.argsort(eigvals)[::-1]        # descending: longest first
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    longest_dir = eigvecs[:, 0]   # body length
    middle_dir  = eigvecs[:, 1]
    shortest_dir = eigvecs[:, 2]

    # Pattern-specific: which principal axis is "height"?
    if base_pattern == "vehicle":
        # Cars: low slung. Shortest principal axis = height.
        height_dir = shortest_dir
        width_dir = middle_dir
    else:
        # quadruped / biped: tall but body is longer. Middle axis = height.
        height_dir = middle_dir
        width_dir = shortest_dir
    body_dir = longest_dir

    # Disambiguate which END of the height axis is "up" (head).
    # Heuristic: for standing subjects the heavier/wider end is at the
    # BOTTOM (feet, wheels). Compare vertex density above vs below the
    # centroid along the height_dir.
    projected = np.asarray(mesh.vertices) @ height_dir
    if projected.mean() > 0:
        # Vertices skew toward +height_dir → "more stuff" up there → that's
        # actually the body. Flip so heavier end is at -Z (ground).
        height_dir = -height_dir

    # Build target orthonormal basis.
    #
    # IMPORTANT — Blender's glTF importer applies a Y-up → Z-up rotation
    # (effectively swaps the Y and Z axes) when loading. If we orient the
    # mesh with body on Y in trimesh, body lands on Z in Blender — standing
    # on tail. So we deliberately put body on Y in trimesh's *exported* GLB
    # convention which means body on +Z in trimesh's INTERNAL (Z-up) frame:
    #
    #   trimesh-internal axes → GLB-on-disk axes → Blender axes (Y-up swap)
    #   +Z (body)             → +Y               → +Y (correct)
    #   +Y (height)           → +Z (height up)  → +Z (correct)
    #   +X (width)            → +X               → +X (correct)
    #
    # So we map: body_dir → +Z, height_dir → +Y, width_dir → +X.
    new_y = height_dir / np.linalg.norm(height_dir)
    new_z = body_dir - np.dot(body_dir, new_y) * new_y
    new_z = new_z / np.linalg.norm(new_z)
    new_x = np.cross(new_y, new_z)

    # Empirical default flips per pattern, learned from observed TripoSR
    # behavior. Geometric heuristics are unreliable across subject types so
    # we use these as deterministic defaults. User can override with
    # subj.force_flip_vertical to flip 180° around body axis.
    #
    # Observed behavior (single-image TripoSR with side-profile inputs):
    #   quadruped → comes out head-down 100% of the time. Always flip.
    #   biped     → same as quadruped.
    #   vehicle   → comes out roof-down. Always flip.
    #   tree      → no flip needed.
    # Vehicles consistently come out roof-down (need flip). Animals are
    # random per-mesh — until silhouette matching is built, default to NO
    # flip and let user override with force_flip_vertical=True per prompt.
    PATTERN_DEFAULT_FLIP = {
        "quadruped": False,
        "biped":     False,
        "vehicle":   True,
        "tree":      False,
        "celestial": False,
        "primitive_geo": False,
    }
    needs_flip = PATTERN_DEFAULT_FLIP.get(base_pattern, False)
    if needs_flip:
        new_y = -new_y
        new_x = np.cross(new_y, new_z)
        print(f"[triposr] pattern-default flip APPLIED for {base_pattern}")
    else:
        print(f"[triposr] pattern-default flip skipped for {base_pattern}")

    # Rotation matrix sending old basis → new basis. R rows are the new
    # basis vectors expressed in old coords.
    R = np.column_stack([new_x, new_y, new_z]).T
    T = np.eye(4)
    T[:3, :3] = R
    mesh.apply_transform(T)

    # Re-center so the mesh sits at origin
    mesh.apply_translation(-mesh.bounds.mean(axis=0))

    dims = mesh.bounds[1] - mesh.bounds[0]
    print(f"[triposr] canonical-orient (pattern={base_pattern}) → "
          f"X={dims[0]:.3f} Y={dims[1]:.3f} Z={dims[2]:.3f} "
          f"(body on Z so after Blender import body lands on Y)")
    return mesh


def _gen_instantmesh(pil_image, output_path: Path) -> Path:
    """InstantMesh pipeline: Zero123++ generates 6 views → InstantMesh reconstructs mesh.

    Output is CANONICALLY ORIENTED — subjects come out upright, on their feet/wheels
    by construction of the model. No PCA, no silhouette matching, no guessing.

    Performance: ~15-25s on RTX 5070 Ti (12s Zero123++, 8s InstantMesh recon, 5s mesh export).
    """
    import numpy as np
    import torch
    from PIL import Image

    # Step 1: prep image (background removal, square crop, RGB blend)
    prepped = _prep_image(pil_image, size=320, foreground_ratio=0.85)

    # VRAM staging — 16GB GPU can't hold SDXL + Zero123++ + InstantMesh at once.
    # Free SDXL before Zero123++ loads; we won't need SDXL again this run.
    try:
        from .reference import unload_reference_pipeline
        unload_reference_pipeline()
        print(f"[instantmesh] freed SDXL VRAM before Zero123++ load")
    except Exception as e:
        print(f"[instantmesh] could not unload SDXL: {e}")

    # Step 2: Zero123++ generates 3x2 grid of 6 views around the subject
    zero123 = _load_zero123_pipeline()
    print(f"[instantmesh] generating 6 views via Zero123++")
    mv_image = zero123(prepped, num_inference_steps=75).images[0]
    # Zero123++ v1.2 output is a 640-wide × 960-tall grid arranged as
    # 3 ROWS × 2 COLUMNS of 320×320 views (matches InstantMesh run.py's
    # `rearrange(..., 'c (n h) (m w) -> (n m) c h w', n=3, m=2)`).
    mv_arr = np.array(mv_image).astype(np.float32) / 255.0
    H, W = mv_arr.shape[:2]
    tile_h = H // 3
    tile_w = W // 2
    views = []
    for row in range(3):
        for col in range(2):
            v = mv_arr[row*tile_h:(row+1)*tile_h, col*tile_w:(col+1)*tile_w]
            views.append(v)
    views = np.stack(views)  # (6, tile_h, tile_w, 3)
    views = torch.from_numpy(views).permute(0, 3, 1, 2).unsqueeze(0)  # (1, 6, 3, 320, 320)

    # Free Zero123++ before reconstruction — it's a ~5GB UNet we don't need anymore
    # this run. extract_mesh is what previously OOM'd allocating 15GB.
    global _ZERO123_PIPELINE
    try:
        del zero123
        _ZERO123_PIPELINE = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        print(f"[instantmesh] freed Zero123++ VRAM before reconstruction")
    except Exception as e:
        print(f"[instantmesh] could not unload Zero123++: {e}")

    # Step 3: feed views into InstantMesh
    model = _load_instantmesh()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = next(model.parameters()).dtype
    views = views.to(device=device, dtype=dtype)

    # Standard InstantMesh camera positions for the 6 input views
    _ensure_vendor_path("InstantMesh")
    from src.utils.camera_util import get_zero123plus_input_cameras  # type: ignore
    input_cameras = get_zero123plus_input_cameras(batch_size=1, radius=4.0).to(device)

    print(f"[instantmesh] reconstructing mesh from 6 views")
    with torch.no_grad():
        planes = model.forward_planes(views, input_cameras)
        # Extract mesh via flexicubes
        mesh_out = model.extract_mesh(
            planes,
            use_texture_map=False,  # vertex colors are enough for our purposes
            **{"texture_resolution": 1024},
        )

    # mesh_out is (vertices, faces, vertex_colors) tuple
    if isinstance(mesh_out, tuple) and len(mesh_out) >= 2:
        verts = mesh_out[0].cpu().numpy()
        faces = mesh_out[1].cpu().numpy()
        colors = mesh_out[2].cpu().numpy() if len(mesh_out) > 2 else None
    else:
        # Some versions return a trimesh directly
        verts = np.asarray(mesh_out.vertices)
        faces = np.asarray(mesh_out.faces)
        colors = None

    import trimesh
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    if colors is not None:
        # Convert vertex colors to 0-255 uint8 RGBA
        if colors.max() <= 1.0:
            colors = (colors * 255).astype(np.uint8)
        if colors.shape[1] == 3:
            colors = np.column_stack([colors, np.full(len(colors), 255, dtype=np.uint8)])
        mesh.visual.vertex_colors = colors

    mesh.export(str(output_path), file_type="glb")
    return output_path
