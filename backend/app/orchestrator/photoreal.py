"""Photoreal ladder step 2 (SCAFFOLD, code-ahead like Phase 27 was):
Wan 2.2 / VACE video-to-video polish — our 3D render supplies exact identity,
motion, camera and depth control; the diffusion pass re-skins frames
photoreal. Apache-2.0, runs local, commercial-safe (see
docs/realism_plan.md R3.1).

Ships DISABLED-BY-ABSENCE: everything no-ops with a clear message until the
model weights exist under models/wan22. On GPU day: download weights, then
render any video with render_tier="photoreal".
"""
from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
WAN_DIR = BACKEND_ROOT / "models" / "wan22"


def is_available(verbose: bool = False) -> bool:
    """True when the Wan 2.2/VACE weights are installed AND CUDA is up."""
    if not WAN_DIR.exists() or not any(WAN_DIR.glob("*.safetensors")):
        if verbose:
            print(f"[photoreal] weights not found under {WAN_DIR} — tier inactive")
        return False
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def apply_photoreal_pass(video_path: str | Path, work_dir: str | Path,
                         prompt: str = "", verbose: bool = True) -> Path:
    """Re-skin `video_path` photoreal. Returns the output mp4 path.

    GPU-day implementation plan (kept here so the wiring is decided before
    the hardware arrives):
      1. Extract frames + estimate depth per frame (or reuse the composer's
         Z-pass — preferred: render a depth EXR sequence alongside beauty).
      2. Run Wan 2.2 VACE conditioned on depth + first-frame identity with
         the scene prompt; chunk into ~49-frame windows with overlap blend.
      3. Encode to <name>_photoreal.mp4 next to the input; caller swaps the
         artifact. The 3D render stays the source of truth for motion.
    """
    if not is_available(verbose=verbose):
        raise RuntimeError(
            "photoreal tier is not active: install Wan 2.2/VACE weights under "
            f"{WAN_DIR} and run on a CUDA machine (GPU day-1 item)")
    raise NotImplementedError(
        "photoreal pass lands with the GPU — wiring reserved (see docstring)")
