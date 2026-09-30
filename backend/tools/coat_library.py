"""Give every animated character in the library one clean coat (2026-09-29).

    python backend/tools/coat_library.py                 # every *_anim, *_hero and walker*
    python backend/tools/coat_library.py fox_anim man_hero

The coat itself is app/game_export/coat.py (scripts/_clean_coat.py in
Blender); new characters get it as they are baked. This runs it over what the
library already holds. A result is kept only when it is sound (same clips,
still skinned, carrying COLOR_0); anything else keeps its original and is
reported. Originals are copied to renders/_coat_backup/ first.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.game_export.coat import coat  # noqa: E402

LIB = BACKEND / "assets" / "library"


def main() -> int:
    redo = "--redo" in sys.argv                # coat again from the pre-coat originals
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = ([LIB / (n if n.endswith(".glb") else n + ".glb") for n in names] if names else
             sorted(p for p in LIB.glob("*.glb")
                    if p.name.endswith("_anim.glb") or p.name.endswith("_hero.glb") or p.name.startswith("walker")))
    backup = BACKEND / "renders" / "_coat_backup"
    if redo:
        import shutil
        for p in files:
            if (backup / p.name).exists():
                shutil.copy2(backup / p.name, p)
    bad = 0
    for p in files:
        ok, msg = coat(p, backup)
        bad += not ok
        print(("ok   " if ok else "KEPT ") + p.name.ljust(28) + msg, flush=True)
    print(f"{len(files) - bad} of {len(files)} coated; originals in {backup.relative_to(BACKEND)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
