"""Asset library resolver: entity/prop NAME → best .glb on this machine.

assets/library.json maps kinds to backend-relative GLB paths (a manifest, not
binaries — generated assets stay out of git). Until Phase 27 generates assets
on demand, this is how "a dog in the park" finds a dog. Synonyms fold common
phrasings onto library kinds.
"""
from __future__ import annotations

import json
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_JSON = BACKEND_ROOT / "assets" / "library.json"

_SYNONYMS = {
    "puppy": "dog", "hound": "dog", "doggo": "dog",
    "kitten": "cat", "kitty": "cat",
    "pony": "horse",
    "automobile": "car", "sportscar": "car", "sports car": "car",
}


def _load() -> dict:
    try:
        return json.loads(LIBRARY_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(lib: dict) -> None:
    import json as _json
    LIBRARY_JSON.write_text(_json.dumps(lib, indent=2) + "\n", encoding="utf-8")


def register(kind: str, glb_path: str | Path, ready: bool = False) -> None:
    """Record a GENERATED asset in the library — the user's own creations ARE
    the marketplace; curated packs demote to fallback. `ready=False` stores it
    as a raw entry that gets decimated to game budget lazily on first use."""
    k = (kind or "").strip().lower()
    if not k:
        return
    p = Path(glb_path)
    try:
        rel = str(p.relative_to(BACKEND_ROOT)).replace("\\", "/")
    except ValueError:
        rel = str(p).replace("\\", "/")
    lib = _load()
    cur = lib.get(k)
    if ready:
        lib[k] = rel
    elif isinstance(cur, str):
        return                      # a ready optimized asset already wins
    else:
        lib[k] = {"raw": rel}
    _save(lib)


def resolve(kind: str) -> str | None:
    """Return an absolute path to a game-ready GLB for `kind`, or None.
    Raw (unoptimized) generated entries are decimated to game budget on first
    use via the CPU-Blender optimizer, then cached as ready."""
    k = (kind or "").strip().lower()
    lib = _load()
    for key in (k, _SYNONYMS.get(k, ""), *(w for w in k.split() if w in lib)):
        entry = lib.get(key)
        if not entry:
            continue
        if isinstance(entry, str):
            p = BACKEND_ROOT / entry
            if p.exists():
                return str(p)
            continue
        raw = BACKEND_ROOT / entry.get("raw", "")
        if not raw.exists():
            continue
        out = BACKEND_ROOT / "assets" / "library" / f"{key.replace(' ', '_')}.glb"
        try:
            from .bake import optimize_asset
            optimize_asset(raw, out, target_tris=45000,
                           height_m=default_height(key), verbose=False)
            lib[key] = str(out.relative_to(BACKEND_ROOT)).replace("\\", "/")
            _save(lib)
            return str(out)
        except Exception:
            return str(raw)          # bridge down etc. — raw beats nothing
    return None


def default_height(kind: str) -> float:
    k = (kind or "").lower()
    for words, h in ((("dog", "cat", "fox", "rabbit"), 0.6),
                     (("horse", "cow", "deer"), 1.7),
                     (("car", "truck", "vehicle"), 1.4),
                     (("dragon", "griffin", "pegasus"), 3.2),
                     (("bird", "eagle", "hawk", "owl", "bat"), 0.5),
                     (("plane", "jet", "helicopter", "spaceship"), 3.0),
                     (("man", "woman", "person", "human", "knight", "wizard"), 1.75)):
        if any(w in k for w in words):
            return h
    return 1.0
