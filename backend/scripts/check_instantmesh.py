"""
Diagnostic: check whether InstantMesh's dependency chain is installable + working.

Prints a per-step PASS/FAIL so you can see exactly what's blocking. Run this
BEFORE attempting a full render — it'll save you 30 seconds of compile time.

Usage:
    python scripts/check_instantmesh.py
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def check(name, fn):
    try:
        result = fn()
        if result is True or result is None:
            print(f"  ✓ {name}")
            return True
        print(f"  ✗ {name}: {result}")
        return False
    except Exception as e:
        print(f"  ✗ {name}: {type(e).__name__}: {e}")
        return False


def main():
    print("\n── Dependency chain ──────────────────────────────")

    ok = True
    ok &= check("torch installed",
                lambda: __import__("torch") and None)
    ok &= check("torch CUDA available",
                lambda: __import__("torch").cuda.is_available()
                    or "no GPU detected (CPU mode would be unusable for InstantMesh)")
    ok &= check("diffusers installed",
                lambda: __import__("diffusers") and None)
    ok &= check("omegaconf installed",
                lambda: __import__("omegaconf") and None)
    ok &= check("einops installed",
                lambda: __import__("einops") and None)
    ok &= check("trimesh installed",
                lambda: __import__("trimesh") and None)
    ok &= check("rembg installed",
                lambda: __import__("rembg") and None)

    print("\n── Compiled C++/CUDA extensions ────────────────────")
    ok &= check("nvdiffrast importable (needs VS Build Tools + CUDA)",
                lambda: __import__("nvdiffrast") and None)
    ok &= check("xatlas importable",
                lambda: __import__("xatlas") and None)

    print("\n── InstantMesh vendor + weights ────────────────────")
    vendor_path = BACKEND_ROOT / "vendor" / "InstantMesh"
    ok &= check(f"vendor dir exists ({vendor_path})",
                lambda: vendor_path.exists()
                    or "run scripts/install_mesh_engines.ps1")
    sys.path.insert(0, str(vendor_path))
    ok &= check("src.utils.train_util importable",
                lambda: __import__("src.utils.train_util") and None)
    ok &= check("src.utils.camera_util importable",
                lambda: __import__("src.utils.camera_util") and None)
    ok &= check("InstantMesh ckpt in HF cache",
                lambda: _check_hf_cache())

    print("\n── Zero123++ (multi-view diffusion front-end) ──────")
    ok &= check("Zero123++ pipeline downloadable",
                lambda: _check_zero123_cache())

    print("\n══════════════════════════════════════════════════")
    if ok:
        print("✓ READY — InstantMesh should work")
        print("  Run: python scripts/render_from_prompt.py 'a brown dog sitting on grass' --no-render")
        return 0
    else:
        print("✗ NOT READY — see failures above")
        print("\nMost common fixes:")
        print("  - install VS Build Tools: scripts/install_vs_buildtools.ps1")
        print("  - install Python deps:    scripts/install_instantmesh_deps.ps1")
        print("  - clone vendor:           scripts/install_mesh_engines.ps1")
        print("  - download weights:       python scripts/download_diffusion_models.py --only instantmesh")
        return 1


def _check_hf_cache():
    from huggingface_hub import try_to_load_from_cache
    p = try_to_load_from_cache(repo_id="TencentARC/InstantMesh",
                               filename="instant_mesh_large.ckpt")
    if p is None:
        return "not cached — run: python scripts/download_diffusion_models.py --only instantmesh"
    return True


def _check_zero123_cache():
    from huggingface_hub import try_to_load_from_cache
    p = try_to_load_from_cache(repo_id="sudo-ai/zero123plus-v1.2",
                               filename="model_index.json")
    if p is None:
        return ("not cached — will download on first run (~3 GB). "
                "If you'd rather pre-download, set HF_HUB_OFFLINE=0 before first run.")
    return True


if __name__ == "__main__":
    sys.exit(main())
