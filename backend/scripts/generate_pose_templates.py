"""
One-time bootstrap: generate pose templates (depth maps) per pattern.

For each pattern (quadruped/biped/vehicle/tree), this script:
  1. Renders a single canonical-pose reference image via plain SDXL with a
     strong pose prompt
  2. Runs DepthAnything-v2 on it to extract a depth map
  3. Saves the depth map to backend/app/asset_gen/pose_templates/{pattern}_depth.png

After running this once, every future render_from_prompt.py call will use
ControlNet-Depth conditioning so every "a dog" / "a cat" / "a fox" produces
the same canonical pose → TripoSR mesh orientation becomes pattern-stable.

Usage:
    .\venv\Scripts\Activate.ps1
    python scripts\generate_pose_templates.py

Optional: --pattern quadruped to regenerate just one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# Per-pattern canonical pose prompts. These are designed to be
# generic + pose-clamped — the depth map extracted should be the
# silhouette pose that EVERY subsequent prompt in this pattern locks to.
CANONICAL_PROMPTS = {
    "quadruped": {
        "prompt": (
            "studio photograph of a generic medium-sized four-legged animal, "
            "perfect side profile, standing still on all four legs, "
            "head facing left, full body centered in frame, "
            "vertical posture, feet flat on neutral studio floor, "
            "sharp focus, even lighting, plain background"
        ),
        "negative": (
            "running, jumping, leaping, mid-action, motion blur, dynamic pose, "
            "tilted, perspective distortion, cropped, multiple animals"
        ),
    },
    "biped": {
        "prompt": (
            "studio photograph of a generic humanoid figure in A-pose, "
            "standing upright facing camera, arms slightly out, feet flat on ground, "
            "full body centered in frame, neutral pose, plain background, "
            "sharp focus, even lighting"
        ),
        "negative": (
            "dynamic pose, motion blur, running, jumping, sitting, tilted, "
            "perspective distortion, cropped, multiple people"
        ),
    },
    "vehicle": {
        "prompt": (
            "studio photograph of a generic four-wheeled car, "
            "perfect side profile, parked stationary, all four wheels on ground, "
            "full body centered in frame, plain neutral background, "
            "sharp focus, even lighting"
        ),
        "negative": (
            "moving, motion blur, tilted, perspective distortion, cropped, "
            "front view, rear view, multiple cars"
        ),
    },
    "tree": {
        "prompt": (
            "studio photograph of a generic single tree, "
            "vertical trunk centered, full tree from base to top visible, "
            "upright, balanced canopy, plain neutral background, "
            "sharp focus, even lighting"
        ),
        "negative": (
            "tilted, leaning, multiple trees, forest, cropped top, cropped base"
        ),
    },
}


def _depth_estimator():
    """Lazy-load Intel DPT-Large for depth estimation.

    DepthAnything would be nicer but needs transformers >= 4.41 which would
    break TripoSR's image tokenizer state-dict loading. DPT has been in
    transformers since 4.27 and produces high-quality depth maps for our
    template-extraction use case.
    """
    print("  loading depth estimator (Intel DPT-Large)...")
    import torch
    from transformers import DPTForDepthEstimation, DPTImageProcessor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = DPTImageProcessor.from_pretrained("Intel/dpt-large")
    model = DPTForDepthEstimation.from_pretrained("Intel/dpt-large").to(device).eval()

    def _infer(pil_image):
        with torch.no_grad():
            inputs = processor(images=pil_image, return_tensors="pt").to(device)
            outputs = model(**inputs)
            depth = outputs.predicted_depth  # (1, H, W)
            # Resize back to source size
            depth = torch.nn.functional.interpolate(
                depth.unsqueeze(1),
                size=pil_image.size[::-1],  # (H, W)
                mode="bicubic",
                align_corners=False,
            ).squeeze().cpu().numpy()
        return {"predicted_depth": depth}

    return _infer


def _save_depth_as_png(depth_arr, out_path: Path):
    """Normalize depth → 8-bit grayscale → save as PNG."""
    import numpy as np
    from PIL import Image
    d = depth_arr.astype("float32")
    d = (d - d.min()) / (d.max() - d.min() + 1e-8)
    img = (d * 255.0).clip(0, 255).astype("uint8")
    Image.fromarray(img).save(out_path)


def generate_one(pattern: str, out_dir: Path, sdxl_pipe, depth_pipe, seed: int = 42):
    print(f"\n── pattern: {pattern} ─────────────────────")
    spec = CANONICAL_PROMPTS[pattern]
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    generator = torch.Generator(device=device).manual_seed(seed)

    print(f"  generating canonical reference (28 steps)...")
    img = sdxl_pipe(
        prompt=spec["prompt"],
        negative_prompt=spec["negative"],
        width=1024, height=1024,
        guidance_scale=7.5, num_inference_steps=28,
        generator=generator,
    ).images[0]

    ref_path = out_dir / f"{pattern}_reference.png"
    img.save(ref_path)
    print(f"  reference saved → {ref_path.name}")

    print(f"  extracting depth map...")
    depth_out = depth_pipe(img)
    depth_arr = depth_out["predicted_depth"]  # already a numpy ndarray

    depth_path = out_dir / f"{pattern}_depth.png"
    _save_depth_as_png(depth_arr, depth_path)
    print(f"  depth saved → {depth_path.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", choices=list(CANONICAL_PROMPTS.keys()),
                    help="generate just one pattern instead of all")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out_dir = BACKEND_ROOT / "app" / "asset_gen" / "pose_templates"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"output dir: {out_dir}")

    patterns = [args.pattern] if args.pattern else list(CANONICAL_PROMPTS.keys())

    from app.asset_gen.reference import _load_t2i_pipeline
    sdxl_pipe = _load_t2i_pipeline()
    depth_pipe = _depth_estimator()

    for p in patterns:
        generate_one(p, out_dir, sdxl_pipe, depth_pipe, seed=args.seed)

    print("\n✓ Done. Re-run a normal render and the [reference] log line will")
    print("  now say 'controlnet-depth(pattern=...)' instead of 'plain-sdxl'.")


if __name__ == "__main__":
    main()
