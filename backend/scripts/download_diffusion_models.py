"""
Download the diffusion models Fantasy Studio uses for img2img refinement.

Models are cached via the HuggingFace hub default cache. To put them on a
specific drive, set HF_HOME or HUGGINGFACE_HUB_CACHE before running.

Usage:
    python scripts/download_diffusion_models.py
    python scripts/download_diffusion_models.py --skip-controlnet   # SDXL only
    HF_HOME=D:\\hf-cache python scripts/download_diffusion_models.py
"""

import argparse
import sys
from pathlib import Path


# Default patterns suit diffusers checkpoints (safetensors-based). Mesh
# engines ship .ckpt files which we'd otherwise filter out — override per-model.
_DIFFUSERS_ALLOW = ["*.json", "*.txt", "*.safetensors", "*.bin",
                    "tokenizer/*", "scheduler/*", "*.fp16.safetensors"]
_DIFFUSERS_IGNORE = ["*.ckpt", "*.msgpack", "*.h5", "flax_model.*"]

MODELS = {
    "sdxl_base": {
        "repo_id": "stabilityai/stable-diffusion-xl-base-1.0",
        "size_gb": 6.6,
        "purpose": "Reference image generation (Phase 17) + optional img2img refinement",
        "allow": _DIFFUSERS_ALLOW,
        "ignore": _DIFFUSERS_IGNORE,
    },
    "sdxl_vae_fix": {
        "repo_id": "madebyollin/sdxl-vae-fp16-fix",
        "size_gb": 0.3,
        "purpose": "Stable VAE in fp16 (fixes black images on consumer GPUs)",
        "allow": _DIFFUSERS_ALLOW,
        "ignore": _DIFFUSERS_IGNORE,
    },
    "controlnet_depth": {
        "repo_id": "diffusers/controlnet-depth-sdxl-1.0",
        "size_gb": 2.5,
        "purpose": "Depth-guided refinement (only used when user opts in to img2img)",
        "allow": _DIFFUSERS_ALLOW,
        "ignore": _DIFFUSERS_IGNORE,
    },
    "triposr": {
        "repo_id": "stabilityai/TripoSR",
        "size_gb": 1.5,
        "purpose": "Phase 17 image-to-3D — fast default (3-5s/asset)",
        # TripoSR ships its weights as model.ckpt + config.yaml — need to allow .ckpt
        "allow": ["*.ckpt", "*.yaml", "*.json", "*.txt", "*.md"],
        "ignore": ["*.msgpack", "*.h5"],
    },
    "instantmesh": {
        "repo_id": "TencentARC/InstantMesh",
        "size_gb": 6.8,
        "purpose": "Phase 17 image-to-3D — cinematic tier (15-25s/asset, higher detail)",
        # InstantMesh ships .ckpt checkpoints across several files
        "allow": ["*.ckpt", "*.safetensors", "*.bin", "*.yaml", "*.json", "*.txt"],
        "ignore": ["*.msgpack", "*.h5"],
    },
}


def _human_gb(n_bytes: int) -> str:
    return f"{n_bytes / 1024**3:.2f} GB"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Fantasy Studio diffusion models")
    parser.add_argument("--skip-controlnet", action="store_true",
                        help="Skip ControlNet-depth (only needed if you opt in to img2img refinement)")
    parser.add_argument("--skip-vae", action="store_true",
                        help="Skip the SDXL VAE fp16 fix (only do this if you know you don't need it)")
    parser.add_argument("--skip-instantmesh", action="store_true",
                        help="Skip InstantMesh (~6.8GB). Only TripoSR will be available for cinematic tier.")
    parser.add_argument("--skip-triposr", action="store_true",
                        help="Skip TripoSR (only do this if you'll only use InstantMesh)")
    parser.add_argument("--only", default=None,
                        help="Comma-separated keys to download (sdxl_base, triposr, instantmesh, etc)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be downloaded without doing it")
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download, HfApi
    except ImportError:
        print("✗ huggingface_hub not installed. Run:\n"
              "   pip install -r requirements-diffusion.txt", file=sys.stderr)
        return 2

    skip = set()
    if args.skip_controlnet:  skip.add("controlnet_depth")
    if args.skip_vae:         skip.add("sdxl_vae_fix")
    if args.skip_instantmesh: skip.add("instantmesh")
    if args.skip_triposr:     skip.add("triposr")
    if args.only:
        keep = {k.strip() for k in args.only.split(",")}
        skip = set(MODELS) - keep

    plan = [(k, v) for k, v in MODELS.items() if k not in skip]
    total_gb = sum(v["size_gb"] for _, v in plan)

    print("╔══════════════════════════════════════════════════════════════")
    print(f"║ Downloading {len(plan)} model(s) — approx {total_gb:.1f} GB total")
    print("╠══════════════════════════════════════════════════════════════")
    for key, info in plan:
        print(f"║  • {key:<22} ~{info['size_gb']:>4.1f} GB  {info['repo_id']}")
        print(f"║    {info['purpose']}")
    print("╚══════════════════════════════════════════════════════════════\n")

    if args.dry_run:
        print("(dry-run mode — no download)")
        return 0

    failed = []
    for key, info in plan:
        repo_id = info["repo_id"]
        print(f"\n── {key} ────────────────────────────────────────")
        print(f"   {repo_id}")
        try:
            path = snapshot_download(
                repo_id=repo_id,
                allow_patterns=info.get("allow", _DIFFUSERS_ALLOW),
                ignore_patterns=info.get("ignore", _DIFFUSERS_IGNORE),
            )
            print(f"   ✓ cached at {path}")
        except Exception as e:
            print(f"   ✗ FAILED: {type(e).__name__}: {e}")
            failed.append((key, str(e)))

    if failed:
        print("\n╔══════════════════════════════════════════════════════════════")
        print(f"║ {len(failed)} model(s) failed to download:")
        for k, err in failed:
            print(f"║   • {k}: {err[:60]}")
        print("╚══════════════════════════════════════════════════════════════")
        return 1

    print("\n✓ All models downloaded. Refinement is ready.")
    print("  Run a test:  python scripts/render_from_prompt.py 'a brown dog at noon'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
