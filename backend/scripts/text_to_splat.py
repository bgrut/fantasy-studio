"""Image-to-Gaussian-splat inference — runs inside venv_trellis as a subprocess.

Tier 3 of Gaussian-splat worlds: turn an SDXL reference image into a 3D
Gaussian-splat .ply.

ENGINE NOTE: the studio's working mesh engine is TRELLIS.2
(backend/vendor/TRELLIS.2, see scripts/inference_trellis2.py) — but TRELLIS.2
outputs o-voxel MESHES ONLY and has no gaussian decoder. Gaussian splats come
from ORIGINAL Microsoft TRELLIS (backend/vendor/TRELLIS, MIT), whose pipeline
supports formats=["gaussian"] and Gaussian.save_ply(). This script therefore
targets vendor/TRELLIS, mirroring the env/venv contract of the TRELLIS.2
script.

DEPENDENCIES (2026-07-27): spconv-cu126 is installed in venv_trellis for the
sparse conv backend. Sparse ATTENTION runs on our vendored 'sdpa' patch
(PyTorch-native) — do NOT install xformers into this venv: it has no kernels
for Blackwell (sm_120) AND DINOv2 auto-detects + uses it, which breaks BOTH
this script and the TRELLIS.2 character pipeline sharing the venv.

Licensing: all code paths MIT/Apache. Original TRELLIS is MIT; its background
removal uses rembg (MIT) with u2net weights (Apache-2.0) — NOT the
non-commercial RMBG model that TRELLIS.2 bundles, so no stub is needed here.
DINOv2 image encoder (torch.hub, facebookresearch/dinov2) is Apache-2.0.

Env knobs:
  ATTN_BACKEND=sdpa      dense attention backend (default here; no flash-attn)
  SPARSE_ATTN_BACKEND    sparse attention backend — auto-set below to whichever
                         of xformers / flash_attn is importable
  SPCONV_ALGO=native     avoids spconv benchmarking on one-shot runs

Usage (from backend/, venv_trellis):
  venv_trellis/Scripts/python.exe scripts/text_to_splat.py ref.png out.ply [--seed 42]
"""
import argparse
import importlib.util
import os
import sys
import time
import types
from pathlib import Path

# ── env setup: mirror inference_trellis2.py, plus original-TRELLIS knobs ────
os.environ.setdefault("ATTN_BACKEND", "sdpa")          # dense attn: no flash-attn
os.environ.setdefault("SPCONV_ALGO", "native")         # one-shot run: skip benchmark
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

BACKEND = Path(__file__).resolve().parent.parent
TRELLIS_DIR = BACKEND / "vendor" / "TRELLIS"
if str(TRELLIS_DIR) not in sys.path:
    sys.path.insert(0, str(TRELLIS_DIR))

MODEL_ID = "microsoft/TRELLIS-image-large"


def _die(msg: str) -> "SystemExit":
    return SystemExit(f"[text_to_splat] FATAL: {msg}")


def _preflight() -> None:
    """Fail fast with actionable messages instead of deep vendored tracebacks."""
    if not (TRELLIS_DIR / "trellis" / "pipelines").is_dir():
        raise _die(f"vendored original TRELLIS not found at {TRELLIS_DIR}")

    missing = []

    # Sparse conv backend: original TRELLIS's SLat flow model uses
    # sp.SparseConv3d, which needs spconv (or torchsparse). Not stub-able.
    if importlib.util.find_spec("spconv") is None:
        if importlib.util.find_spec("torchsparse") is not None:
            os.environ["SPARSE_BACKEND"] = "torchsparse"
        else:
            missing.append(
                "sparse conv backend: pip install spconv-cu126 "
                "(match the venv's CUDA; torchsparse also accepted)")

    # xformers must NOT be present: DINOv2 auto-detects and uses it, and its
    # kernels don't cover Blackwell (sm_120). Belt-and-suspenders disable.
    os.environ.setdefault("XFORMERS_DISABLED", "1")

    # Sparse attention backend: default to our vendored 'sdpa' patch —
    # PyTorch-native attention works on EVERY CUDA GPU including Blackwell
    # (sm_120), where xformers/flash-attn ship no kernels (verified broken
    # on the RTX 5070 Ti, 2026-07-27). Export SPARSE_ATTN_BACKEND=xformers
    # to opt back into fused kernels on older GPUs.
    os.environ.setdefault("SPARSE_ATTN_BACKEND", "sdpa")

    if missing:
        raise _die(
            "original TRELLIS (the only vendored engine with gaussian-splat "
            "output) is missing runtime deps in venv_trellis:\n  - "
            + "\n  - ".join(missing)
            + "\nInstall into backend/venv_trellis, then re-run.")

    # trellis/pipelines/__init__.py also imports the TEXT pipeline, which
    # imports open3d at module level. We never use the text pipeline, so stub
    # open3d if absent rather than dragging in a heavyweight dependency.
    if importlib.util.find_spec("open3d") is None:
        stub = types.ModuleType("open3d")
        stub.__doc__ = "stub injected by text_to_splat.py (text pipeline unused)"
        # the text pipeline's method annotations reference o3d.geometry.* at
        # class-definition time, so the stub needs a geometry submodule too
        geom = types.ModuleType("open3d.geometry")
        geom.TriangleMesh = type("TriangleMesh", (), {})
        stub.geometry = geom
        sys.modules["open3d"] = stub
        sys.modules["open3d.geometry"] = geom

    # FlexiCubes (mesh extraction) is an UN-VENDORED git submodule — and must
    # stay that way: it is NVIDIA Source Code License NON-COMMERCIAL. Gaussian
    # output never touches it, but trellis/__init__ imports the mesh
    # representation unconditionally, so pre-seed a stub that only fails if
    # something actually tries to extract a mesh.
    class _FlexiCubesStub:
        def __init__(self, *a, **k):
            pass

        def __call__(self, *a, **k):
            raise RuntimeError(
                "FlexiCubes (non-commercial license) is not vendored — "
                "mesh extraction is unavailable in text_to_splat; use "
                "formats=['gaussian'] only")

        def __getattr__(self, name):
            return self.__call__

    fc_pkg = types.ModuleType("trellis.representations.mesh.flexicubes")
    fc_mod = types.ModuleType("trellis.representations.mesh.flexicubes.flexicubes")
    fc_mod.FlexiCubes = _FlexiCubesStub
    fc_pkg.flexicubes = fc_mod
    sys.modules["trellis.representations.mesh.flexicubes"] = fc_pkg
    sys.modules["trellis.representations.mesh.flexicubes.flexicubes"] = fc_mod


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reference image -> 3D Gaussian splat .ply (original TRELLIS)")
    ap.add_argument("image_input", help="reference image (PNG; RGBA alpha used if present)")
    ap.add_argument("output_path", help="output .ply path (3D Gaussian splat)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    in_path = Path(args.image_input)
    if not in_path.is_file():
        raise _die(f"input image not found: {in_path}")

    _preflight()

    import torch  # noqa: E402
    from PIL import Image  # noqa: E402

    if not torch.cuda.is_available():
        raise _die("CUDA is not available — original TRELLIS requires a CUDA GPU "
                   "(no CPU fallback for gaussian-splat generation)")

    from trellis.pipelines import TrellisImageTo3DPipeline  # noqa: E402

    t0 = time.time()
    print(f"[text_to_splat] loading pipeline ({MODEL_ID})…", flush=True)
    try:
        pipeline = TrellisImageTo3DPipeline.from_pretrained(MODEL_ID)
    except Exception as e:  # weights missing / download failed / cache broken
        raise _die(
            f"could not load {MODEL_ID} weights: {e}\n"
            "First run downloads ~4.5 GB from Hugging Face (plus DINOv2 via "
            "torch.hub and rembg u2net). Check network/HF cache and retry.")
    pipeline.cuda()
    print(f"[text_to_splat] pipeline ready in {time.time()-t0:.1f}s", flush=True)

    # RGBA fast-path mirrors the TRELLIS.2 script: if the input already has a
    # real alpha channel, preprocess_image() uses it directly; otherwise the
    # pipeline cuts the subject out itself with rembg u2net (MIT/Apache — the
    # commercially-safe remover, unlike TRELLIS.2's bundled RMBG).
    image = Image.open(in_path)

    t1 = time.time()
    # NOTE (same gotcha as inference_trellis2.py): run() calls
    # torch.manual_seed(seed) internally — the seed MUST be passed here;
    # seeding beforehand is silently ignored.
    outputs = pipeline.run(image, seed=args.seed, formats=["gaussian"])
    print(f"[text_to_splat] gaussians generated in {time.time()-t1:.1f}s", flush=True)

    out = Path(args.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    outputs["gaussian"][0].save_ply(str(out))
    print(f"[text_to_splat] splat saved -> {out} "
          f"({out.stat().st_size/1e6:.1f} MB, total {time.time()-t0:.1f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
