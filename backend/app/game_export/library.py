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


def resolve(kind: str) -> str | None:
    """Return an absolute path to a GLB for `kind`, or None."""
    k = (kind or "").strip().lower()
    lib = _load()
    for key in (k, _SYNONYMS.get(k, ""), *(w for w in k.split() if w in lib)):
        rel = lib.get(key)
        if rel:
            p = BACKEND_ROOT / rel
            if p.exists():
                return str(p)
    return None


def default_height(kind: str) -> float:
    k = (kind or "").lower()
    for words, h in ((("dog", "cat", "fox", "rabbit"), 0.6),
                     (("horse", "cow", "deer"), 1.7),
                     (("car", "truck", "vehicle"), 1.4),
                     (("man", "woman", "person", "human", "knight", "wizard"), 1.75)):
        if any(w in k for w in words):
            return h
    return 1.0
