"""Phase 27 — on-demand asset generation for games (CODE-AHEAD: written while
the dGPU is down; the no-GPU paths are tested now, the generation path gets
its first live run when the new PSU lands).

ensure_asset(kind): library hit → done. Miss → SDXL reference + TRELLIS.2
mesh (same recipe as the composer's extra-actor path, incl. the
renders/_actor_cache md5 cache and the triposg fallback) → decimate to game
budget → register in assets/library.json. After this, "a knight riding
through a forest" needs zero pre-existing assets.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from . import library
from .bake import optimize_asset

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = BACKEND_ROOT / "renders" / "_actor_cache"
LIB_DIR = BACKEND_ROOT / "assets" / "library"


class GPUUnavailable(RuntimeError):
    """Raised when generation is requested but no CUDA device is up."""


_QUADRUPED = ("dog", "cat", "horse", "cow", "wolf", "fox", "deer", "lion",
              "tiger", "bear", "pig", "sheep", "goat", "rabbit")
_VEHICLE = ("car", "truck", "bus", "van", "jeep", "tank", "motorcycle")


def guess_pattern(kind: str) -> str:
    k = (kind or "").lower()
    if any(w in k for w in _QUADRUPED):
        return "quadruped"
    if any(w in k for w in _VEHICLE):
        return "vehicle"
    return "biped"


def gpu_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _minimal_slots(kind: str, pattern: str) -> dict:
    """The slot skeleton generate_reference() expects — mirrors the composer's
    extra-actor slots2 construction."""
    return {
        "subject": {
            "name": kind, "base_pattern": pattern, "shape": None,
            "library_query": None, "identity_phrase": kind, "pose": "standing",
            "color_name": "neutral", "material": "matte", "emissive": False,
            "scale": 1.0, "location": [0, 0, 0],
        },
        "scene": {"mood": "daylight", "setting": None, "ground": True},
        "style": "photoreal",
    }


def _register(kind: str, rel_path: str) -> None:
    lib = {}
    try:
        lib = json.loads(library.LIBRARY_JSON.read_text(encoding="utf-8"))
    except Exception:
        pass
    lib[kind.lower()] = rel_path
    library.LIBRARY_JSON.write_text(json.dumps(lib, indent=2) + "\n", encoding="utf-8")


def ensure_asset(kind: str, pattern: str | None = None, target_tris: int = 45000,
                 verbose: bool = True) -> str:
    """Return a game-ready GLB path for `kind`, generating it if the library
    misses. Raises GPUUnavailable (clean gate) when generation would be needed
    but no CUDA device is present."""
    hit = library.resolve(kind)
    if hit:
        return hit
    if not gpu_available():
        raise GPUUnavailable(
            f"'{kind}' is not in the asset library and no CUDA GPU is available "
            f"to generate it (Phase 27 path — retry once the GPU is back)")

    from app.asset_gen import generate_reference, generate_mesh
    from app.asset_gen.reference import unload_reference_pipeline

    pattern = pattern or guess_pattern(kind)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(kind.lower().encode("utf-8")).hexdigest()[:12]
    raw_glb = CACHE_DIR / f"{key}.glb"

    if not raw_glb.exists():
        ref_png = CACHE_DIR / f"{key}_ref.png"
        if verbose:
            print(f"[game] generating '{kind}' ({pattern}) via SDXL + TRELLIS.2 ...")
        generate_reference(copy.deepcopy(_minimal_slots(kind, pattern)),
                           output_path=ref_png, style="photoreal", seed=42)
        try:
            unload_reference_pipeline()
            import torch as _t
            if _t.cuda.is_available():
                _t.cuda.empty_cache()
        except Exception:
            pass
        try:
            generate_mesh(ref_png, output_path=raw_glb, engine="trellis2",
                          tier="fast", base_pattern=pattern)
        except Exception as ge:
            if verbose:
                print(f"[game] trellis2 failed ({type(ge).__name__}) -> triposg")
            generate_mesh(ref_png, output_path=raw_glb, engine="triposg",
                          tier="fast", base_pattern=pattern)
    elif verbose:
        print(f"[game] actor-cache hit for '{kind}'")

    # decimate to game budget + register (CPU Blender — works today)
    out = LIB_DIR / f"{kind.lower().replace(' ', '_')}.glb"
    optimize_asset(raw_glb, out, target_tris=target_tris,
                   height_m=library.default_height(kind), verbose=verbose)
    _register(kind, str(out.relative_to(BACKEND_ROOT)).replace("\\", "/"))
    if verbose:
        print(f"[game] '{kind}' registered in library -> {out.name}")
    return str(out)
