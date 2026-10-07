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
    elif isinstance(cur, str) and (BACKEND_ROOT / cur).exists():
        return                      # a ready optimized asset already wins
    # ...but an entry whose file is gone (retired as a bust, a car under a
    # person's name, or undressed) wins nothing: it silently blocked the
    # regenerated ranger from ever registering (2026-10-02)
    else:
        lib[k] = {"raw": rel}
    _save(lib)


# PROC MODULES (2026-08-30): sculpted code-only assets from the img2threejs
# lane. A proc: URI is not a file — the runtime imports runtime/proc/<n>.js
# and gets articulated pivots (steering, spinning wheels) no GLB carries.
_PROC_MODULES = {
    "roadster": "proc:roadster",
    "classic roadster": "proc:roadster",
    "classic car": "proc:roadster",
    "vintage car": "proc:roadster",
    "white roadster": "proc:roadster",
}


_MANIFEST: dict | None = None


def _manifest() -> dict:
    """assetmeta.py's measurements, by file name; empty when it has not run."""
    global _MANIFEST
    if _MANIFEST is None:
        _MANIFEST = {}
        try:
            import json as _json
            d = _json.loads((BACKEND_ROOT / "assets" / "library_manifest.json").read_text(encoding="utf-8"))
            for r in d.get("assets", []):
                if r.get("file"):
                    _MANIFEST[r["file"].lower()] = r
        except Exception:
            _MANIFEST = {}
    return _MANIFEST


def verdict(kind_or_path) -> str:
    """good, fair, poor, or unknown: what assetmeta.py made of the model."""
    p = kind_or_path if isinstance(kind_or_path, str) and kind_or_path.lower().endswith(".glb") else resolve(str(kind_or_path), any_quality=True)
    if not p:
        return "unknown"
    rec = _manifest().get(Path(p).name.lower())
    return (rec or {}).get("verdict", "unknown")


def resolve(kind: str, any_quality: bool = False) -> str | None:
    """THE QUALITY GATE (2026-09-23): a model assetmeta.py measured as poor
    (a mangled generation) is treated as missing, so the kin fallback or the
    parametric build takes its place; any_quality=True hands it out anyway."""
    p = _resolve(kind)
    if p and not any_quality:
        rec = _manifest().get(Path(p).name.lower())
        if rec and rec.get("verdict") == "poor":
            return None
    return p


def _resolve(kind: str) -> str | None:
    """Return an absolute path to a game-ready GLB for `kind`, or None.
    Raw (unoptimized) generated entries are decimated to game budget on first
    use via the CPU-Blender optimizer, then cached as ready."""
    k = (kind or "").strip().lower()
    if k in _PROC_MODULES:
        return _PROC_MODULES[k]
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
            from .generate import guess_pattern
            optimize_asset(raw, out, target_tris=(80000 if guess_pattern(key) in ('biped', 'quadruped') else 45000),
                           height_m=default_height(key), verbose=False)
            lib[key] = str(out.relative_to(BACKEND_ROOT)).replace("\\", "/")
            _save(lib)
            return str(out)
        except Exception:
            return str(raw)          # bridge down etc. — raw beats nothing
    return None


# Category stand-ins (2026-07-08): when a hero/prop can't be resolved AND can't
# be generated (e.g. a brand-new species on a GPU-less machine), we degrade to
# the CLOSEST asset of the SAME kind — a polar bear becomes a wolf, NEVER a
# man-with-a-sword. Ordered by visual similarity; the first that resolves wins.
_NEAREST = {
    "quadruped": ("wolf", "dog", "fox", "horse", "cat", "monkey", "penguin", "dragon"),
    "biped":     ("man", "knight", "samurai", "wizard"),
    "vehicle":   ("car", "truck"),
    "aquatic":   ("whale",),
    "flying":    ("dragon", "firefly"),
    "static":    ("man",),
}


def nearest(kind: str, pattern: str = "biped") -> str:
    """Closest available library asset of the SAME category as `kind`.

    Used as an honest stand-in when the real asset can't be built yet (a new
    species that needs a GPU to generate). Never crosses categories, so an
    animal hero never degrades to a human. Returns a kind name that `resolve`
    is guaranteed to satisfy (falls back to the first playable asset)."""
    if resolve(kind):
        return (kind or "").strip().lower()
    for cand in _NEAREST.get(pattern, _NEAREST["biped"]):
        if resolve(cand):
            return cand
    for cand in ("man", "fox", "car"):          # last resort: anything playable
        if resolve(cand):
            return cand
    return "man"


# TRUE SIZES (2026-10-04). A wolf, a bear, a gazelle and a cheetah all came
# out one metre tall because nothing in the old table named them, and a cat
# stood as tall as a dog. Heights here are the model's standing height as the
# runtime scales it (head included; a flyer's or swimmer's longest span, since
# those are normalised by their longest dimension). Whole words, so a cat
# burglar is a person; people are checked first for the same reason.
_TRUE_HEIGHT = (
    (("man", "woman", "person", "human", "knight", "wizard", "witch", "burglar", "thief", "girl", "boy",
      "hunter", "ranger", "explorer", "detective", "soldier", "guard", "farmer", "shepherd", "pirate",
      "astronaut", "scientist", "engineer", "keeper", "courier", "samurai", "ninja", "princess", "prince",
      "king", "queen", "villager", "zombie", "skeleton", "vampire", "elf", "orc", "goblin"), 1.75),
    (("child", "kid"), 1.2), (("dwarf",), 1.3), (("giant", "troll", "ogre"), 3.2),
    (("mouse", "rat", "hamster", "frog", "toad"), 0.12), (("squirrel", "weasel", "ferret", "chipmunk", "lizard"), 0.2),
    (("cat", "kitten", "rabbit", "bunny", "hare", "skunk"), 0.32), (("raccoon", "badger", "fox", "otter", "beaver"), 0.45),
    (("dog", "puppy", "coyote", "jackal"), 0.62), (("wolf", "hyena", "husky"), 0.85),
    (("sheep", "goat", "lamb", "boar", "pig"), 0.95), (("gazelle", "antelope", "impala"), 1.05),
    (("cheetah", "leopard", "panther", "cougar", "puma", "jaguar", "lynx"), 0.9),
    (("lion", "lioness", "tiger"), 1.2), (("bear", "panda"), 1.4), (("grizzly",), 1.5), (("gorilla",), 1.55),
    (("deer", "reindeer", "caribou", "zebra", "donkey"), 1.45), (("horse", "pony", "stallion", "mare", "cow", "bull", "ox", "bison", "buffalo"), 1.7),
    (("elk", "moose", "camel", "llama"), 2.2), (("rhino", "rhinoceros", "hippo", "hippopotamus"), 1.8),
    (("elephant", "mammoth"), 3.2), (("giraffe",), 5.0), (("kangaroo",), 1.5), (("monkey", "chimp", "chimpanzee", "ape", "lemur"), 0.8),
    (("crocodile", "alligator", "caiman"), 3.5), (("snake", "serpent", "cobra", "python", "viper"), 1.8),
    (("chicken", "hen", "rooster", "duck"), 0.45), (("goose", "swan", "turkey"), 0.8), (("penguin",), 0.8),
    (("firefly", "fireflie", "bee", "wasp", "fly", "moth"), 0.12), (("butterfly", "dragonfly"), 0.18),
    (("sparrow", "songbird", "swallow", "finch", "robin"), 0.3), (("bat", "parrot", "pigeon", "dove"), 0.5),
    (("crow", "raven", "owl", "gull", "seagull"), 1.0), (("eagle", "hawk", "falcon", "vulture", "condor"), 2.0),
    (("dragon", "wyvern", "griffin", "gryphon", "pegasus", "phoenix"), 3.2),
)


def _true_height(kind: str) -> float | None:
    # a noun phrase names its thing last: a pirate SHIP, a cat BURGLAR, an alpha WOLF
    import re as _re
    toks = _re.findall(r"[a-z]+", (kind or "").lower())
    if not toks:
        return None
    t = toks[-1]
    for cand in (t, t[:-1] if t.endswith("s") and len(t) > 3 and not t.endswith("ss") else t,
                 t[:-3] + "y" if t.endswith("ies") else t, t[:-3] + "f" if t.endswith("ves") else t):
        for words, h in _TRUE_HEIGHT:
            if cand in words:
                return h
    return None


def default_height(kind: str) -> float:
    k = (kind or "").lower()
    for _pre in ("toon ", "anime ", "clay "):     # a drawn gardener is as tall as a gardener
        if k.startswith(_pre):
            k = k[len(_pre):]
    th = _true_height(k)
    if th is not None:
        return th
    for words, h in ((("dog", "cat", "fox", "rabbit"), 0.6),
                     (("horse", "cow", "deer"), 1.7),
                     (("car", "truck", "vehicle"), 1.4),
                     (("dragon", "griffin", "pegasus"), 3.2),
                     (("bird", "eagle", "hawk", "owl", "bat"), 0.5),
                     (("plane", "jet", "helicopter", "spaceship"), 3.0),
                     (("whale", "orca"), 8.0),
                     (("shark", "dolphin"), 2.6),
                     (("fish", "turtle", "seal", "stingray"), 0.8),
                     (("boat", "ship", "submarine"), 6.0),
                     (("monkey", "ape", "chimp"), 0.9),
                     (("penguin",), 0.8),
                     (("bottle", "cup", "mug", "vase", "lantern"), 0.35),
                     (("crate", "barrel", "chest", "banana"), 0.6),
                     (("man", "woman", "person", "human", "knight", "wizard"), 1.75)):
        if any(w in k for w in words):
            return h
    return 1.0
