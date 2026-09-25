"""Score every library character's reference picture for blotchiness.

    python backend/tools/refaudit.py           # every biped in the library
    python backend/tools/refaudit.py scientist # named kinds

The reference is what the mesh and its texture were made from: a coat with
paint splashes on it stays splashed through every bake and every rig, and no
amount of skinning work can take it off. The same CLIP judge generate_reference
now runs before meshing is applied here to what is already on the shelf, so a
regeneration list can be drawn up instead of guessed at.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
CACHE = BACKEND / "renders" / "_actor_cache"
LIB_JSON = BACKEND / "assets" / "library.json"
MANIFEST = BACKEND / "assets" / "library_manifest.json"


def main() -> int:
    from PIL import Image
    from app.asset_gen.reference import _blotchiness
    from app.game_export.generate import guess_pattern

    only = {a.lower() for a in sys.argv[1:] if not a.startswith("--")}
    lib = json.loads(LIB_JSON.read_text(encoding="utf-8"))
    rows = []
    for kind in sorted(lib):
        if only and kind not in only:
            continue
        if guess_pattern(kind) != "biped":
            continue
        ref = CACHE / (hashlib.md5(kind.encode()).hexdigest()[:12] + "_ref.png")
        src = "reference"
        if not ref.exists():
            # no cached reference (most of the roster predates the cache): ask
            # the same question of the model's own shaded render instead
            stem = "".join(ch if ch.isalnum() else "_" for ch in kind)
            ref = BACKEND / "tools" / "shotgate" / "renders" / f"{stem}_shaded.png"
            src = "render"
        if not ref.exists():
            continue
        try:
            b = _blotchiness(Image.open(ref).convert("RGB"))
        except Exception as e:  # noqa: BLE001
            print(f"  {kind:18} judge failed ({type(e).__name__})")
            continue
        rows.append((b, kind, src))
        # A RENDER IS NOT EVIDENCE (2026-09-29): asked of the finished model,
        # this judge cannot tell a soccer kit or a viking's furs, patterned by
        # design, from a coat SDXL splashed by accident; it scored all three
        # above 0.9. Only a REFERENCE answers the question it was built for,
        # so only a reference recommends a regeneration.
        flag = "   <- regenerate" if (b >= 0.45 and src == "reference") else ""
        print(f"  {kind:18} blotchiness {b:.2f}  ({src}){flag}", flush=True)
    rows.sort(reverse=True)
    bad = [k for b, k, sr in rows if b >= 0.45 and sr == "reference"]
    noted = [k for b, k, sr in rows if b >= 0.45 and sr == "render"]
    print(f"\n{len(rows)} judged; {len(bad)} blotchy by their reference: {' '.join(bad) if bad else 'none'}")
    if bad:
        print("\n  python tools/regen.py --attempts 2 " + " ".join(bad))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
