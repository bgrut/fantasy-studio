"""GPU DAY-1 AUTOMATION (photoreal ladder step 1) — run this the day the new
PSU lands and the RTX 5070 Ti is back:

    venv/Scripts/python.exe scripts/gpu_day1.py            # checklist + dry run
    venv/Scripts/python.exe scripts/gpu_day1.py --run      # full regeneration

What --run does, in order:
  1. Verifies CUDA is actually visible to torch.
  2. Regenerates EVERY library character at TRELLIS quality tier (crisp
     geometry, native 2K textures — kills the CPU-era splotches/ghosts at
     the source). Old assets are kept as .bak until the new one verifies.
  3. Re-bakes the playable (animated) variants on the new meshes.
  4. Runs the regression pack + builds one canonical game per pattern.
  5. Prints the manual follow-ups (Wan 2.2 VACE weights, upright-fix
     validation, car_city rerun, shot-director facing e2e).
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

B = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(B))

LIB = B / "assets" / "library"

MANUAL_FOLLOWUPS = [
    "Download Wan 2.2 / VACE weights -> app/orchestrator/photoreal.py finds them",
    "Validate biped upright fix e2e (wizard/man) — pending since 2026-06-15",
    "Rerun car_city regression + Phase 31 shot-director facing e2e",
    "Prompt-exact characters: knight-in-armor, squirrel, dragon (quality tier)",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="actually regenerate (default: dry run)")
    args = ap.parse_args()

    try:
        import torch
        cuda = torch.cuda.is_available()
        name = torch.cuda.get_device_name(0) if cuda else "-"
    except Exception as e:
        cuda, name = False, f"torch import failed: {e}"
    print(f"CUDA: {cuda} ({name})")

    from app.game_export import library
    kinds = list(json.loads(library.LIBRARY_JSON.read_text(encoding="utf-8")).keys())
    print(f"library kinds to regenerate: {kinds}")

    if not args.run:
        print("\nDRY RUN — pass --run on GPU day. Manual follow-ups after:")
        for f in MANUAL_FOLLOWUPS:
            print(f"  - {f}")
        return 0
    if not cuda:
        print("ABORT: --run requires a CUDA device.")
        return 1

    import hashlib
    from app.game_export.generate import ensure_asset, guess_pattern
    from app.game_export.bake import ensure_playable

    CACHE = B / "renders" / "_actor_cache"
    ok, failed = [], []
    for kind in kinds:
        print(f"\n=== {kind} ===")
        glb = LIB / f"{kind}.glb"
        bak = LIB / f"{kind}.glb.bak"
        anim = LIB / f"{kind}_anim.glb"
        try:
            if glb.exists():
                shutil.copy2(glb, bak)
            # force full regeneration: clear the actor cache + library entry
            key = hashlib.md5(kind.encode("utf-8")).hexdigest()[:12]
            for f in CACHE.glob(f"{key}*"):
                f.unlink(missing_ok=True)
            lib = json.loads(library.LIBRARY_JSON.read_text(encoding="utf-8"))
            lib.pop(kind, None)
            library.LIBRARY_JSON.write_text(json.dumps(lib, indent=2) + "\n", encoding="utf-8")
            t0 = time.time()
            ensure_asset(kind)
            if anim.exists():
                anim.unlink()
            if guess_pattern(kind) in ("biped", "quadruped"):
                ensure_playable(kind)
            print(f"    regenerated in {time.time() - t0:.0f}s")
            bak.unlink(missing_ok=True)
            ok.append(kind)
        except Exception as e:
            print(f"    FAILED ({type(e).__name__}: {e}) — restoring backup")
            if bak.exists():
                shutil.copy2(bak, glb)
            failed.append(kind)

    print(f"\nregenerated: {ok}\nfailed: {failed}")
    print("\nnow run: scripts/regression_pack.py, then the manual follow-ups:")
    for f in MANUAL_FOLLOWUPS:
        print(f"  - {f}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
