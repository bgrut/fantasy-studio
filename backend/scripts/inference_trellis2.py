"""TRELLIS.2 image-to-3D inference — runs inside venv_trellis as a subprocess.

Mirrors the TripoSG subprocess contract: --image-input PNG in, --output-path GLB
out. Unlike TripoSG, the GLB comes out TEXTURED (PBR baked from the image), which
is the whole point of the upgrade (kills the clay look natively).

Env knobs:
  ATTN_BACKEND=sdpa   (default here; flash-attn not required on Windows)
  FS_TRELLIS_TEXSIZE  texture bake size (default 2048; 4096 = slower, sharper)

Usage (from backend/, venv_trellis):
  venv_trellis/Scripts/python.exe scripts/inference_trellis2.py \
      --image-input ref.png --output-path out.glb [--seed 42]
"""
import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("ATTN_BACKEND", "sdpa")          # no flash-attn needed
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
# LOCAL FIRST (2026-09-30): once the weights are cached, they load from the
# cache and nothing is asked of the Hub. Hugging Face began answering file
# lookups with a redirect this venv's hub client does not follow, and every
# online lookup failed even for files already on disk. A first install, with
# nothing cached yet, still downloads.
if (Path.home() / ".cache" / "huggingface" / "hub" / "models--microsoft--TRELLIS.2-4B" / "snapshots").exists():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

BACKEND = Path(__file__).resolve().parent.parent
TRELLIS2_DIR = BACKEND / "vendor" / "TRELLIS.2"
if str(TRELLIS2_DIR) not in sys.path:
    sys.path.insert(0, str(TRELLIS2_DIR))

# ── LICENSE GUARD (2026-09-30): nvdiffrast is NVIDIA-licensed for
# non-commercial use only, and TRELLIS.2 bakes every texture with it. A
# PyTorch rasteriser with the same interface (scripts/_permissive_raster.py,
# matched against nvdiffrast on a real atlas: 99.8% of texels, the same
# triangle on 99.6%, positions within a millionth of the model) is registered
# under its name first, so NVIDIA's library is never imported.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _permissive_raster  # noqa: E402
_permissive_raster.install()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image-input", required=True)
    ap.add_argument("--output-path", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--texture-size", type=int,
                    default=int(os.environ.get("FS_TRELLIS_TEXSIZE", "2048")))   # 2026-09-25: the 4096 atlas ran the 30 GB machine out of RAM at export; the bake resamples anyway
    # THE RESOLUTION FITS THE CARD (2026-09-25): the 1024 cascade decoded a
    # mesh whose edge pass ran out of video memory on a 16 GB card sharing
    # the desktop, and every TRELLIS.2 run had been failing over to TripoSG,
    # untextured. 512 fits with room to spare; 1024_cascade when the card is
    # free (FS_TRELLIS_PIPE=1024_cascade).
    ap.add_argument("--pipeline-type", default=os.environ.get("FS_TRELLIS_PIPE", "512"),
                    choices=["512", "1024", "1024_cascade", "1536_cascade"])
    args = ap.parse_args()

    import torch  # noqa: E402
    from PIL import Image  # noqa: E402

    # ── LICENSE GUARD: TRELLIS.2's bundled background-remover is briaai/RMBG-2.0,
    # which is NON-COMMERCIAL for free users (violates our commercial-safe rule)
    # and gated. The pipeline skips it entirely when given an RGBA input with a
    # real alpha channel, so we (a) stub the BiRefNet wrapper so RMBG never
    # downloads/loads, and (b) cut out the subject ourselves with rembg (MIT,
    # u2net weights Apache-2.0) before calling the pipeline.
    from trellis2.pipelines import rembg as _t2_rembg  # noqa: E402

    class _NoRMBG:  # pragma: no cover - trivial stub
        def __init__(self, *a, **kw):
            pass
        def to(self, *a, **kw):
            return self
        def cpu(self):
            return self
        def __call__(self, img):
            raise RuntimeError("RMBG stubbed out (non-commercial license); "
                               "input must be RGBA so preprocess skips rembg")
    _t2_rembg.BiRefNet = _NoRMBG

    from trellis2.pipelines import Trellis2ImageTo3DPipeline  # noqa: E402
    import o_voxel  # noqa: E402

    # ONLY THE MODELS THIS PIPELINE RUNS (2026-09-30). Every checkpoint was
    # loaded whatever the pipeline, the 1024 flows included, and on a machine
    # with a nearly full disk the paging file could not grow for them: "The
    # paging file is too small" (os error 1455), and every generation fell
    # back to TripoSR. The 512 pipeline never touches the 1024 models.
    _need = {
        "512": {"shape_slat_flow_model_512", "tex_slat_flow_model_512"},
        "1024": {"shape_slat_flow_model_1024", "tex_slat_flow_model_1024"},
        "1024_cascade": {"shape_slat_flow_model_512", "shape_slat_flow_model_1024", "tex_slat_flow_model_1024"},
        "1536_cascade": {"shape_slat_flow_model_512", "shape_slat_flow_model_1024", "tex_slat_flow_model_1024"},
    }[args.pipeline_type]
    Trellis2ImageTo3DPipeline.model_names_to_load = [
        n for n in Trellis2ImageTo3DPipeline.model_names_to_load
        if "_512" not in n and "_1024" not in n or n in _need]

    t0 = time.time()
    print(f"[trellis2] loading pipeline (TRELLIS.2-4B)…", flush=True)
    pipeline = Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")
    pipeline.cuda()
    print(f"[trellis2] pipeline ready in {time.time()-t0:.1f}s", flush=True)

    import numpy as np  # noqa: E402
    image = Image.open(args.image_input)
    _needs_cutout = image.mode != "RGBA" or bool((np.array(image)[:, :, 3] == 255).all())
    if _needs_cutout:
        # Cut out the subject with MIT-licensed rembg so the pipeline's RGBA
        # fast-path engages (and the stubbed RMBG is never invoked).
        from rembg import remove as _rembg_remove  # noqa: E402
        image = _rembg_remove(image.convert("RGB"))
        print("[trellis2] background removed via rembg (MIT)", flush=True)
    t1 = time.time()
    # NOTE: run() calls torch.manual_seed(seed) internally with its OWN default,
    # so the seed MUST be passed here — seeding beforehand is silently ignored.
    print(f"[trellis2] pipeline type {args.pipeline_type}", flush=True)
    mesh = pipeline.run(image, seed=args.seed, pipeline_type=args.pipeline_type)[0]
    mesh.simplify(16777216)  # nvdiffrast limit
    print(f"[trellis2] mesh generated in {time.time()-t1:.1f}s", flush=True)

    t2 = time.time()
    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices, faces=mesh.faces,
        attr_volume=mesh.attrs, coords=mesh.coords,
        attr_layout=mesh.layout, voxel_size=mesh.voxel_size,
        aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=500000,            # plenty for our render scale
        texture_size=args.texture_size,
        remesh=True, remesh_band=1, remesh_project=0,
        verbose=True,
    )
    out = Path(args.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    glb.export(str(out), extension_webp=False)   # keep PNG textures (Blender-safe)
    print(f"[trellis2] GLB exported in {time.time()-t2:.1f}s -> {out} "
          f"({out.stat().st_size/1e6:.1f} MB, total {time.time()-t0:.1f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
