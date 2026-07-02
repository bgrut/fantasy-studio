"""One-time (re-runnable) backfill: harvest every good GENERATED asset already
on disk into the shared library. The user's own creations become the catalog;
curated packs are fallback. Newest GLB per kind wins; each is decimated to
game budget (CPU Blender) and registered ready.

Usage: python scripts/backfill_library.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.game_export import library  # noqa: E402

# ordered: specific identities before generic ones (samurai before man)
KIND_WORDS = [
    "samurai", "wizard", "knight", "viking", "gladiator", "astronaut", "robot",
    "pickup_truck", "truck", "sports_car", "car",
    "dog", "cat", "horse", "wolf", "fox", "bear", "lion", "tiger", "deer",
    "cow", "rabbit", "elephant",
    "woman", "man", "person",
]


def detect_kind(slug: str) -> str | None:
    s = slug.lower()
    for w in KIND_WORDS:
        if w.replace("_", " ") in s.replace("_", " "):
            return w.split("_")[-1] if w in ("pickup_truck", "sports_car") else w
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--target-tris", type=int, default=45000)
    args = ap.parse_args()

    # newest first, so the first GLB seen per kind is the freshest generation
    runs = sorted((d for d in (BACKEND_ROOT / "renders").iterdir()
                   if d.is_dir() and re.match(r"(anim|video)_\d{8}_", d.name)),
                  key=lambda d: d.name.split("_", 1)[1], reverse=True)
    picked: dict[str, Path] = {}
    for d in runs:
        kind = detect_kind(d.name)
        if not kind or kind in picked:
            continue
        glbs = sorted(d.glob("asset_*.glb"))
        if glbs:
            picked[kind] = glbs[0]

    if not picked:
        print("nothing to backfill")
        return
    print(f"backfilling {len(picked)} kinds: {', '.join(sorted(picked))}")
    if args.dry_run:
        for k, p in sorted(picked.items()):
            print(f"  {k:12s} <- {p.relative_to(BACKEND_ROOT)}")
        return

    from app.game_export.bake import optimize_asset
    out_dir = BACKEND_ROOT / "assets" / "library"
    ok, failed = 0, []
    for kind, raw in sorted(picked.items()):
        # a ready library entry already present? keep it (don't churn the man)
        existing = library._load().get(kind)
        if isinstance(existing, str) and (BACKEND_ROOT / existing).exists():
            print(f"  {kind:12s} already ready — kept")
            continue
        out = out_dir / f"{kind}.glb"
        try:
            optimize_asset(raw, out, target_tris=args.target_tris,
                           height_m=library.default_height(kind), verbose=False)
            library.register(kind, out, ready=True)
            mb = out.stat().st_size / 1e6
            print(f"  {kind:12s} OK ({mb:.0f} MB) <- {raw.parent.name}")
            ok += 1
        except Exception as e:
            failed.append(kind)
            print(f"  {kind:12s} FAILED ({type(e).__name__}: {e})")
    print(f"done: {ok} registered, {len(failed)} failed {failed or ''}")


if __name__ == "__main__":
    main()
