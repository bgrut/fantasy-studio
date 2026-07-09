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
_FLYING = ("dragon", "bird", "eagle", "hawk", "owl", "phoenix", "griffin",
           "pegasus", "bat", "butterfly", "bee", "plane", "airplane", "jet",
           "helicopter", "spaceship", "rocket", "drone", "ufo")
_AQUATIC = ("whale", "shark", "fish", "dolphin", "orca", "mermaid", "octopus",
            "squid", "turtle", "seal", "stingray", "eel", "submarine", "boat",
            "ship", "kayak")

_PATTERNS = ("biped", "quadruped", "flying", "aquatic", "vehicle", "static")
_PATTERN_CACHE = BACKEND_ROOT / "renders" / "_pattern_cache.json"


def _classify_with_ollama(kind: str) -> str | None:
    """SCALABLE classification for kinds no keyword list knows: one cached
    Ollama call — 'how does this thing move?'. Deterministic after first use
    (renders/_pattern_cache.json). Returns None when Ollama is unreachable."""
    try:
        cache = {}
        try:
            cache = json.loads(_PATTERN_CACHE.read_text(encoding="utf-8"))
        except Exception:
            pass
        if kind in cache:
            return cache[kind]
        from app.orchestrator.llm import OllamaClient
        msg = OllamaClient().chat(
            [{"role": "system", "content":
              "Classify how a creature or thing MOVES ITS BODY. Reply with "
              "exactly ONE word from: biped, quadruped, flying, aquatic, "
              "vehicle, static.\n"
              "biped = anything human or humanoid — ALL people, professions "
              "and roles (chef, pirate, knight, dancer), robots, apes.\n"
              "quadruped = four-legged animals. flying = birds/dragons/"
              "aircraft. aquatic = swimmers (whales, fish, boats). "
              "vehicle = wheeled/driven machines. static = ONLY inanimate "
              "objects that truly cannot move (a castle, a toaster)."},
             {"role": "user", "content": kind}],
            temperature=0.0)
        word = (msg or {}).get("content", "").strip().lower().split()[0].strip(".,")
        if word in _PATTERNS:
            cache[kind] = word
            _PATTERN_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _PATTERN_CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
            return word
    except Exception:
        pass
    return None


def guess_pattern(kind: str) -> str:
    k = (kind or "").lower()
    # flightless upright birds WADDLE on two legs — the quadruped guess gave
    # the 2026-07-08 penguin four legs in its SDXL reference (and its mesh)
    if any(w in k for w in ("penguin", "ostrich", "emu", "kiwi", "dodo")):
        return "biped"
    if any(w in k for w in _FLYING):
        return "flying"                   # fly mode; static mesh + hover (wing
        #                                   flap rig is the Phase 20 flying module)
    if any(w in k for w in _AQUATIC):
        return "aquatic"                  # swim mode
    if any(w in k for w in _QUADRUPED):
        return "quadruped"
    if any(w in k for w in _VEHICLE):
        return "vehicle"
    # keyword lists are the fast path; UNKNOWN kinds ask Ollama how the thing
    # moves (cached) — a whale must never be rigged like a person again
    if k and k not in ("man", "woman", "person", "human"):
        llm = _classify_with_ollama(k)
        if llm:
            return llm
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
    # THE VISION GATE, UNLOCKED (2026-07-05): generation used to hard-require
    # CUDA, so every new character fell back to "man". SDXL + TripoSR both run
    # on CPU — slowly (~30-60 min) but ONCE: the result registers in the
    # library and is instant for every later prompt. FS_CPU_CHARGEN=0 restores
    # the old library-only behavior.
    import os as _os
    cpu_gen = not gpu_available()
    if cpu_gen and _os.environ.get("FS_CPU_CHARGEN", "1") == "0":
        raise GPUUnavailable(
            f"'{kind}' is not in the asset library; CPU generation is disabled "
            f"(FS_CPU_CHARGEN=0) and no CUDA GPU is available")
    if cpu_gen and verbose:
        print(f"[game] no GPU — generating '{kind}' on CPU (first time only; "
              f"~30-60 min, then cached in the library)")

    from app.asset_gen import generate_reference, generate_mesh
    from app.asset_gen.reference import unload_reference_pipeline

    pattern = pattern or guess_pattern(kind)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(kind.lower().encode("utf-8")).hexdigest()[:12]
    raw_glb = CACHE_DIR / f"{key}.glb"

    if not raw_glb.exists():
        ref_png = CACHE_DIR / f"{key}_ref.png"
        if ref_png.exists():
            # reference-cache hit (mesh re-roll / orientation fix): skip the
            # 20-min SDXL repaint and go straight to image→3D
            if verbose:
                print(f"[game] reference cache hit for '{kind}' — meshing only")
        else:
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
        # engine order: CUDA gets the quality chain; CPU goes straight to
        # TripoSR (the only CPU-capable engine — TRELLIS.2/TripoSG need CUDA)
        _chain = ["triposr"] if cpu_gen else ["trellis2", "triposg", "triposr"]
        _last: Exception | None = None
        for _eng in _chain:
            try:
                generate_mesh(ref_png, output_path=raw_glb, engine=_eng,
                              tier="fast", base_pattern=pattern)
                _last = None
                break
            except Exception as ge:
                _last = ge
                if verbose:
                    print(f"[game] {_eng} failed ({type(ge).__name__}: {ge})")
        if _last is not None:
            raise _last
    elif verbose:
        print(f"[game] actor-cache hit for '{kind}'")

    # decimate to game budget + register (CPU Blender — works today).
    # ref_png: untextured gens (TripoSR CPU) get the reference photo PROJECTED
    # onto them so the library asset ships real colors, not ghost-white.
    out = LIB_DIR / f"{kind.lower().replace(' ', '_')}.glb"
    ref_png = CACHE_DIR / f"{key}_ref.png"
    try:
        optimize_asset(raw_glb, out, target_tris=target_tris,
                       height_m=library.default_height(kind), verbose=verbose,
                       ref_png=ref_png if ref_png.exists() else None,
                       despeckle=(pattern == "vehicle"),
                       pattern=pattern)
        _register(kind, str(out.relative_to(BACKEND_ROOT)).replace("\\", "/"))
        if verbose:
            print(f"[game] '{kind}' registered in library -> {out.name}")
        return str(out)
    except Exception as oe:
        # The MESH is already generated and cached (SDXL + TripoSR don't need
        # Blender) — only the final "optimize to game budget" step does, via the
        # Blender bridge. If that bridge is down/deadlocked, DON'T throw away a
        # good 30-min mesh and let the caller fall back to a stand-in: register
        # the RAW mesh so the CORRECT species plays now. It's stored as a raw
        # entry, so resolve() re-optimizes it automatically (orientation, texture
        # projection, decimation) the moment the bridge is healthy again.
        if verbose:
            print(f"[game] optimize step failed ({type(oe).__name__}: {oe}); "
                  f"registering RAW mesh so '{kind}' still plays — it auto-"
                  f"optimizes on next use once the Blender bridge is up")
        library.register(kind, raw_glb, ready=False)
        return str(raw_glb)
