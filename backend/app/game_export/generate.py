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
# Human roles/professions are ALWAYS biped — never ask the LLM. Ollama once
# classified 'hunter' as a quadruped (cached!), so the player got a
# four-legged rig and shipped looking like a dog (2026-07-15).
_BIPED = ("hunter", "archer", "soldier", "warrior", "ranger", "ninja",
          "pirate", "king", "queen", "prince", "princess", "farmer",
          "cowboy", "cowgirl", "hero", "heroine", "elf", "dwarf", "orc",
          "goblin", "zombie", "skeleton", "vampire", "witch", "astronaut",
          "pilot", "doctor", "police", "officer", "firefighter", "explorer",
          "adventurer", "assassin", "thief", "rogue", "monk", "paladin",
          "barbarian", "gladiator", "spy", "detective", "scientist", "miner",
          "lumberjack", "fisherman", "shepherd", "guard", "sniper", "medic",
          # PEOPLE THE MODEL MISREAD (2026-10-02): the cached answers had a
          # castaway as a statue, a nomad and a guide as cars, a hermit and a
          # wanderer on four legs, an informant and a ghost as objects; the
          # castaway's hero was then never rigged and the build failed
          "castaway", "nomad", "hermit", "survivor", "wanderer", "traveller", "traveler",
          "drifter", "exile", "outlaw", "bandit", "trader", "merchant", "scout", "climber",
          "camper", "informant", "guide", "villager", "sailor", "captain", "courier",
          "keeper", "engineer", "bender", "mage", "wizard", "sorcerer", "knight", "samurai",
          "viking", "chef", "baker", "priest", "nun", "striker", "goalkeeper", "player",
          "ghost", "spirit", "child", "kid", "boy", "girl", "man", "woman", "person",
          "stranger", "pilgrim", "hiker", "tourist", "student", "teacher", "nurse",
          "mechanic", "smith", "blacksmith", "hunter", "huntress", "princess", "rider",
          "warden", "jailer", "prisoner", "thug", "burglar", "heir", "noble", "peasant")
_VEHICLE = ("car", "truck", "bus", "van", "jeep", "tank", "motorcycle")
_FLYING = ("dragon", "bird", "eagle", "hawk", "owl", "phoenix", "griffin",
           "pegasus", "bat", "butterfly", "bee", "plane", "airplane", "jet",
           "helicopter", "spaceship", "rocket", "drone", "ufo")
# THE THING IS THE LAST WORD (2026-09-27). "pirate ship" was cast as a biped
# because "pirate" is a human role and that list is read first; in a noun
# phrase the modifiers come first and the head comes last, and a pirate ship
# is a ship. A head noun that names a vessel decides before anything else.
_VESSELS = ("ship", "boat", "sailboat", "galleon", "schooner", "yacht", "raft",
            "canoe", "kayak", "frigate", "dinghy", "ferry", "longboat", "junk",
            "gondola", "trawler", "warship", "submarine", "catamaran", "clipper")
# the same for aircraft: "space fighter" and "starfighter" were asked of the
# model and came back "vehicle", a car on the ground; a fighter alone is a
# person, a fighter with space, star or jet in front of it flies
_CRAFT = ("jet", "plane", "airplane", "spaceship", "starship", "spacecraft",
          "starfighter", "x-wing", "helicopter", "glider", "rocket", "gunship",
          "biplane", "airship", "ufo", "shuttle", "drone", "zeppelin")
_AQUATIC = ("whale", "shark", "fish", "dolphin", "orca", "mermaid", "octopus",
            "squid", "turtle", "seal", "stingray", "eel", "submarine", "boat",
            "ship", "kayak")

# headless Blender for the vehicle orientation normalize (5.1 preferred;
# config default may point at an older install)
from app.config import BLENDER_EXE as _CFG_BEXE
from pathlib import Path as _P
BLENDER_EXE = (_CFG_BEXE if _P(_CFG_BEXE).exists()
               else r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")

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


import re as _re_kw


def guess_pattern(kind: str) -> str:
    k = (kind or "").lower()
    _wk = k.split()
    if _wk and _wk[-1] in _VESSELS and not (len(_wk) > 1 and _wk[-2] in ("space", "star", "air")):
        return "aquatic"
    if _wk and (_wk[-1] in _CRAFT or (_wk[-1] in ("fighter", "ship") and len(_wk) > 1
                                      and _wk[-2] in ("space", "star", "jet", "tie", "air"))):
        return "flying"
    # flightless upright birds WADDLE on two legs — the quadruped guess gave
    # the 2026-07-08 penguin four legs in its SDXL reference (and its mesh)
    if any(w in k for w in ("penguin", "ostrich", "emu", "kiwi", "dodo")):
        return "biped"
    # exact-word match for human roles (substring would hit 'king' in
    # 'viking'; split on spaces so 'zombie pirate' still works)
    # (2026-10-02) the HEAD noun decides here too: a hermit crab is a crab
    # and a king cobra a snake, while a zombie pirate is still a pirate
    if _wk and _wk[-1] in _BIPED:
        return "biped"
    # A KEYWORD ENDS A WORD (2026-10-06): substring matching made a carrot a
    # vehicle ("car"), a bush a bus, a scarecrow a car, and its reference image
    # was an orange hatchback that the gardener collected ten of. A keyword
    # now has to end a word (bulldog is still a dog, carrot is not a car);
    # anything no list knows goes to the classifier below, as before.
    _ends = lambda w: _re_kw.search(r"\b" + _re_kw.escape(w) + r"(?:s|es)?\b", k) is not None   # whole words: a dandelion is not a lion
    if any(_ends(w) for w in _FLYING):
        return "flying"                   # fly mode; static mesh + hover (wing
        #                                   flap rig is the Phase 20 flying module)
    if any(_ends(w) for w in _AQUATIC):
        return "aquatic"                  # swim mode
    if any(_ends(w) for w in _QUADRUPED):
        return "quadruped"
    if any(_ends(w) for w in _VEHICLE):
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



def _dress_reference(kind: str, pattern: str, ref_png, verbose: bool = True) -> None:
    """DRESSED, CHECKED (2026-10-03): the prompt and its negative were not
    enough; six library people came out in briefs or bare-chested. A person's
    reference is judged (CLIP, the reference judge's own model) and made again
    with another seed while it reads undressed. Every reference a person is
    made from passes here, the two-faced retry's too (the thug's retry was
    shirtless when only the first roll was checked)."""
    if pattern != "biped":
        return
    try:
        from app.asset_gen.dressed import undressed_belief
        from app.asset_gen.reference import generate_reference as _gr
        for _seed in (43, 44, 45, 46):
            _ub = undressed_belief(ref_png)
            # bare chests scored 0.48-0.79, every clothed figure under 0.06
            if _ub is None or _ub <= 0.25:
                return
            if verbose:
                print(f"[game] reference for '{kind}' reads undressed ({_ub:.2f}); making it again (seed {_seed})")
            _gr(copy.deepcopy(_minimal_slots(kind, pattern)), output_path=ref_png, style="photoreal", seed=_seed)
    except Exception as _de:  # noqa: BLE001
        if verbose:
            print(f"[game] dressed check skipped ({type(_de).__name__}: {_de})")

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


def ensure_asset(kind: str, pattern: str | None = None, target_tris: int | None = None,
                 verbose: bool = True) -> str:
    """Return a game-ready GLB path for `kind`, generating it if the library
    misses. Raises GPUUnavailable (clean gate) when generation would be needed
    but no CUDA device is present.

    (2026-09-30) Whatever happens, SDXL and the judge are let go when it ends:
    the server kept them resident after generating, 15.6 GB of a 30 GB machine,
    and the next build's planner and TRELLIS.2 could not load beside them."""
    hit = library.resolve(kind)
    if hit:
        return hit
    try:
        return _ensure_asset_generate(kind, pattern, target_tris, verbose)
    finally:
        try:
            from app.asset_gen.reference import unload_reference_pipeline
            unload_reference_pipeline()
        except Exception:
            pass


def _ensure_asset_generate(kind: str, pattern: str | None, target_tris: int | None,
                           verbose: bool) -> str:
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

    # THE LLM LEAVES BEFORE THE PICTURE (2026-09-30): the director's 12B model
    # stays resident after planning, and SDXL starved beside it (a horse sat
    # at step 0 of 28 for minutes with the card full). It was only unloaded
    # before the 3D stage; it goes before the reference image too.
    if not cpu_gen:
        try:
            import requests as _rq0
            for _m in _rq0.get("http://localhost:11434/api/ps", timeout=3).json().get("models", []):
                _rq0.post("http://localhost:11434/api/generate",
                          json={"model": _m["name"], "keep_alive": 0}, timeout=5)
                if verbose:
                    print(f"[game] evicted '{_m['name']}' from VRAM for the reference image", flush=True)
        except Exception:
            pass

    pattern = pattern or guess_pattern(kind)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(kind.lower().encode("utf-8")).hexdigest()[:12]
    raw_glb = CACHE_DIR / f"{key}.glb"

    def _two_faced(glb_path) -> bool:
        """TWO-FACED GATE (Phase 110): TRELLIS sometimes mirrors the FRONT
        texture onto a biped's back — a phantom face on the back of the head
        that reads as 'walking backwards' from the chase camera (the ranger).
        Render front+back and compare: near-identical = mirrored artifact."""
        import subprocess as _sp
        import tempfile as _tf
        # ONLY A STANDING MESH CAN BE TWO-FACED (2026-09-25). TRELLIS.2 rests
        # a figure in its own frame, and the bake stands it up later; judged
        # raw, a figure lying flat is seen from above and below, two views
        # that match at 0.78 whatever the texture, and a good mesh was thrown
        # away for it. A raw mesh whose tallest axis is not Y is left to the
        # bake's orientation gate, and the comparison itself now asks the head
        # band as well: a white coat is alike front and back, a face is not.
        try:
            import sys as _sys2
            _tp = str(BACKEND_ROOT / "tools")
            if _tp not in _sys2.path:
                _sys2.path.insert(0, _tp)
            from assetmeta import measure as _measure
            _dm = (_measure(Path(glb_path)).get("dims_m") or {})
            if _dm and _dm.get("y", 0) < max(_dm.get("x", 0), _dm.get("z", 0)):
                if verbose:
                    print("[game] two-faced gate skipped: the raw mesh is not standing in its own frame; the bake orients it")
                return False
        except Exception as _me:  # noqa: BLE001
            if verbose:
                print(f"[game] two-faced gate: could not measure the raw mesh ({type(_me).__name__}); judging anyway")
        try:
            import numpy as _np
            from PIL import Image as _Im
            exe = r"C:\Program Files\Blender Foundation\Blender 5.1\\blender.exe"
            try:
                from app.main import get_setting
                exe = get_setting("blender_executable_path") or exe
            except Exception:
                pass
            with _tf.TemporaryDirectory() as td:
                r = _sp.run([exe, "--background", "--python",
                             str(BACKEND_ROOT / "scripts" / "_facing_refmatch.py"),
                             "--", str(glb_path), td],
                            capture_output=True, timeout=420)
                if b"REFMATCH-RENDERED back" not in r.stdout:
                    return False
                def _norm(fp):
                    v = _np.asarray(_Im.open(fp).convert("RGB").resize((48, 48)),
                                    dtype=float)
                    return (v - v.mean()) / (v.std() + 1e-6)
                from pathlib import Path as _P
                f = _norm(_P(td) / "front.png")
                b = _norm(_P(td) / "back.png")
                sim = float((f * b).mean())
                _hb = max(4, int(f.shape[0] * 0.25))            # the head band: a mirrored face shows here
                _fh, _bh = f[:_hb], b[:_hb]
                sim_head = float(((_fh - _fh.mean()) * (_bh - _bh.mean())).mean() / (_fh.std() * _bh.std() + 1e-6))
                if verbose:
                    print(f"[game] two-faced gate: front/back similarity {sim:.2f}, head {sim_head:.2f}")
                return sim > 0.55 and sim_head > 0.5
        except Exception:
            return False

    if not raw_glb.exists():
        ref_png = CACHE_DIR / f"{key}_ref.png"
        if ref_png.exists():
            # reference-cache hit (mesh re-roll / orientation fix): skip the
            # 20-min SDXL repaint and go straight to image→3D
            if verbose:
                print(f"[game] reference cache hit for '{kind}' — meshing only")
            _dress_reference(kind, pattern, ref_png, verbose)
        else:
            if verbose:
                print(f"[game] generating '{kind}' ({pattern}) via SDXL + TRELLIS.2 ...")
            generate_reference(copy.deepcopy(_minimal_slots(kind, pattern)),
                               output_path=ref_png, style="photoreal", seed=42)
            _dress_reference(kind, pattern, ref_png, verbose)
            try:
                unload_reference_pipeline()
                import torch as _t
                if _t.cuda.is_available():
                    _t.cuda.empty_cache()
            except Exception:
                pass
        # OLLAMA EVICTION (Phase 124): the extraction LLM stays resident on
        # the GPU (~5GB) after every prompt parse — TRELLIS then starts
        # starved on a 16GB card and THRASHES (the 20-30 min 'slow gen'
        # class). keep_alive:0 unloads it; it reloads in ~2s next prompt.
        try:
            import requests as _rq
            for _m in _rq.get("http://localhost:11434/api/ps", timeout=3).json().get("models", []):
                _rq.post("http://localhost:11434/api/generate",
                         json={"model": _m["name"], "keep_alive": 0}, timeout=5)
                print(f"[game] evicted '{_m['name']}' from VRAM for the mesh engine", flush=True)
        except Exception:
            pass
        # engine order: CUDA gets the quality chain; CPU goes straight to
        # TripoSR (the only CPU-capable engine — TRELLIS.2/TripoSG need CUDA)
        # (2026-09-30) TripoSG left the chain: its script downloads and runs
        # RMBG-1.4 ("non-commercial use") and its decoder imports diso (CC
        # BY-NC 4.0), so an asset it made could not go into a game that is
        # sold. TRELLIS.2 falls back to TripoSR (MIT) instead.
        _chain = ["triposr"] if cpu_gen else ["trellis2", "triposr"]
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
        # one seed-varied retry when the fresh biped mesh is two-faced
        if pattern == "biped" and _two_faced(raw_glb):
            if verbose:
                print(f"[game] '{kind}' is TWO-FACED (mirrored back) — one seed-varied retry")
            import os as _os2
            import random as _rd2
            raw_glb.unlink(missing_ok=True)
            ref_png.unlink(missing_ok=True)
            _os2.environ["FS_REF_SEED"] = str(_rd2.randint(1000, 999999))
            try:
                generate_reference(copy.deepcopy(_minimal_slots(kind, pattern)),
                                   output_path=ref_png, style="photoreal", seed=42)
                _dress_reference(kind, pattern, ref_png, verbose)
                try:
                    unload_reference_pipeline()
                    import torch as _t2
                    if _t2.cuda.is_available():
                        _t2.cuda.empty_cache()
                except Exception:
                    pass
                # THE SAME CHAIN AS THE FIRST ROLL (2026-09-25): this retry
                # called TRELLIS.2 alone, so when it was down every retry died
                # after TripoSG had already made a perfectly good mesh
                _last2 = None
                for _eng2 in _chain:
                    try:
                        generate_mesh(ref_png, output_path=raw_glb, engine=_eng2,
                                      tier="fast", base_pattern=pattern)
                        _last2 = None
                        break
                    except Exception as ge2:
                        _last2 = ge2
                        if verbose:
                            print(f"[game] retry: {_eng2} failed ({type(ge2).__name__}: {str(ge2)[:100]})")
                if _last2 is not None:
                    raise _last2
            finally:
                _os2.environ.pop("FS_REF_SEED", None)
    elif verbose:
        print(f"[game] actor-cache hit for '{kind}'")

    # decimate to game budget + register (CPU Blender — works today).
    # ref_png: untextured gens (TripoSR CPU) get the reference photo PROJECTED
    # onto them so the library asset ships real colors, not ghost-white.
    out = LIB_DIR / f"{kind.lower().replace(' ', '_')}.glb"
    ref_png = CACHE_DIR / f"{key}_ref.png"
    # THE BUDGET FITS THE BODY (2026-09-26): a character is skinned and
    # seen up close, and at 45 k triangles its sleeves tore at the elbow
    # under the walk; 80 k keeps the folds. Props and vehicles keep 45 k.
    if target_tris is None:
        target_tris = 80000 if pattern in ("biped", "quadruped") else 45000
    try:
        # ONE MORE TRY ON A FRESH BRIDGE (2026-09-30): the bridge is often
        # still relaunching when TRELLIS.2 hands its mesh over, the first
        # call times out, and the raw 485 k-face mesh was rigged instead: the
        # heat weights came out empty and the monkey and the horse each lost
        # a ten-minute attempt. A dropped bridge is brought back and asked
        # again before the raw mesh is settled for.
        for _opt_try in (1, 2):
            try:
                optimize_asset(raw_glb, out, target_tris=target_tris,
                               height_m=library.default_height(kind), verbose=verbose,
                               ref_png=ref_png if ref_png.exists() else None,
                               # vehicles grow "strings"; bipeds grow rod hallucinations
                               # (a 2m spike off a huntress fooled the orientation gate
                               # on 2026-07-15) — both are the same de-spike class
                               despeckle=(pattern in ("vehicle", "biped")),
                               pattern=pattern)
                break
            except Exception as _be:
                if _opt_try == 2 or "Bridge" not in type(_be).__name__:
                    raise
                if verbose:
                    print(f"[game] optimize: bridge dropped ({type(_be).__name__}); relaunching and trying again")
                from .bake import ensure_bridge
                ensure_bridge(verbose=verbose)
                # the relaunch returns before Blender listens: the woman's
                # first attempt asked again into a bridge still starting
                # (2026-10-01), so wait until it answers, up to a minute
                import time as _t
                from app.mcp import bridge as _br
                for _w in range(20):
                    try:
                        _br.connect(timeout=3)
                        break
                    except Exception:  # noqa: BLE001
                        _t.sleep(3)
        # BIPED DEFAULT FLIP (2026-07-24): every recent TRELLIS biped came out
        # facing -Y (soldier, knight, ranger — 3/3); photo-correlation sign
        # detection failed calibration (would flip the correct hunter), so
        # the default IS the evidence. Exceptions land in library_heading.json
        # and the reroll button re-runs this path.
        if pattern == "biped":
            import subprocess as _sp3
            _sp3.run([BLENDER_EXE, "--background", "--python",
                      str(BACKEND_ROOT / "scripts" / "_apply_euler.py"), "--",
                      str(out), str(out), "0", "0", "180"],
                     capture_output=True, timeout=300)
            if verbose:
                print(f"[game] biped default flip applied to '{kind}' (TRELLIS faces -Y)")
        # A SWIMMER LIES LEVEL (2026-09-29): a dolphin's reference leapt on a
        # diagonal and the player swam a dolphin standing on its tail. Its
        # long axis is rotated into the horizontal plane, heading kept.
        if pattern == "aquatic":
            try:
                import subprocess
                _lv = subprocess.run(
                    [str(BLENDER_EXE), "--background", "--python",
                     str(BACKEND_ROOT / "scripts" / "_level_swimmer.py"), "--",
                     str(out), str(out)],
                    capture_output=True, text=True, timeout=180, check=True)
                if verbose:
                    _m = [l for l in (_lv.stdout or "").splitlines() if l.startswith("LEVEL")]
                    print(f"[game] swimmer levelled: {(_m or ['LEVEL ?'])[-1][6:]} degrees")
            except Exception as _le:
                if verbose:
                    print(f"[game] swimmer level skip: {type(_le).__name__}")
        # VEHICLE ORIENTATION (2026-07-22): vehicles never pass through the
        # rig bake, so the bake-time orientation gate never sees them — the
        # regenerated car shipped lying on its side, the corvette nose-down.
        # TRELLIS.2 rests vehicles in ONE consistent frame (verified on
        # car + corvette contact sheets): euler (0, 90, 180) puts them
        # wheels-down with the nose at +X (the runtime's alignLongAxis
        # convention). Applied headless; failure leaves the mesh as-was.
        if pattern == "vehicle":
            try:
                import subprocess
                subprocess.run(
                    [str(BLENDER_EXE), "--background", "--python",
                     str(BACKEND_ROOT / "scripts" / "_orient_vehicle.py"), "--",
                     str(out), str(out)],
                    capture_output=True, timeout=180, check=True)
                if verbose:
                    print(f"[game] vehicle orientation solved (wheels-down)")
            except Exception as _ve:
                if verbose:
                    print(f"[game] vehicle orient skip: {type(_ve).__name__}")
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
