"""
Objaverse asset fetcher.

Objaverse is a HuggingFace dataset with 800K+ 3D models, each annotated
with GPT-4 descriptions. This fetcher searches the annotations locally and
downloads individual GLB files on demand.

Public API:
    search_objaverse(query, max_results=20) -> list[dict]
    download_objaverse_model(uid) -> Path | None
    fetch_hero_from_objaverse(subject) -> dict | None
    is_available() -> bool

All operations are wrapped in try/except and return None/empty on failure
so callers can fall through to other fetchers (Sketchfab, curated, AI).

First invocation loads ~800MB of annotations and may take 30-60 seconds.
Subsequent calls in the same process hit the in-memory cache immediately.
Downloaded models are cached to disk under assets/cache/models/objaverse/.
"""

from __future__ import annotations

import json
import re
import shutil
import struct
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# Vehicle quality gate — reject blocky proxies before import
# ═══════════════════════════════════════════════════════════════════════════

VEHICLE_MIN_MESH_COUNT = 20
VEHICLE_MIN_VERTEX_COUNT = 5000

_VEHICLE_SUBJECT_RE = re.compile(
    r"\b(car|sportscar|sports\s*car|racecar|race\s*car|supercar|vehicle|"
    r"sedan|coupe|truck|van|motorcycle|bike|hypercar|ferrari|bmw|porsche|"
    r"lamborghini|audi|tesla|mustang|corvette)\b",
    re.IGNORECASE,
)


def _is_vehicle_subject(subject: str) -> bool:
    return bool(_VEHICLE_SUBJECT_RE.search(subject or ""))


def _passes_vehicle_quality_gate(glb_path: str) -> tuple[bool, str]:
    """Inspect a GLB without importing it.

    A real car has hundreds of meshes and tens of thousands of vertices.
    A "blocky proxy" that ranked high on name-exact match (the Objaverse
    'racecar' that's just 9 cubes) fails here and gets rejected before
    we waste an import cycle on it.

    GLB layout: header(12) + JSON chunk header(8) + JSON payload.
    We only need to parse the JSON to count meshes and sum POSITION
    accessor vertex counts.  On any parse failure we let it through
    (empty non-vehicle fallback paths shouldn't break on malformed files).
    """
    try:
        with open(glb_path, "rb") as f:
            magic = f.read(4)
            if magic != b"glTF":
                return True, f"not a GLB (magic={magic!r}) — allowing through"
            f.read(8)  # version + total length
            json_chunk_len = struct.unpack("<I", f.read(4))[0]
            f.read(4)  # chunk type
            payload = f.read(json_chunk_len)
            data = json.loads(payload.decode("utf-8", errors="replace"))

        meshes = data.get("meshes", []) or []
        accessors = data.get("accessors", []) or []
        mesh_count = len(meshes)

        total_verts = 0
        for m in meshes:
            for prim in m.get("primitives", []) or []:
                attrs = prim.get("attributes", {}) or {}
                pos_idx = attrs.get("POSITION")
                if pos_idx is not None and 0 <= pos_idx < len(accessors):
                    total_verts += int(accessors[pos_idx].get("count", 0) or 0)

        if mesh_count < VEHICLE_MIN_MESH_COUNT:
            return False, (
                f"only {mesh_count} meshes "
                f"(need >= {VEHICLE_MIN_MESH_COUNT} for vehicle)"
            )
        if total_verts < VEHICLE_MIN_VERTEX_COUNT:
            return False, (
                f"only {total_verts} vertices "
                f"(need >= {VEHICLE_MIN_VERTEX_COUNT} for vehicle)"
            )
        return True, f"mesh_count={mesh_count} total_verts={total_verts} OK"
    except Exception as e:
        return True, f"inspection_failed ({e}) — allowing through"

# Project root resolves to the backend directory (this file lives at
# app/services/objaverse_fetcher.py, so go up three levels).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "assets" / "cache" / "models" / "objaverse"

_ANNOTATIONS_CACHE: dict[str, Any] | None = None
_OBJAVERSE_MODULE = None
_IMPORT_FAILED = False


def _lazy_import():
    """Import the objaverse package lazily so the server can start even
    when the optional dependency is missing. Returns the module or None."""
    global _OBJAVERSE_MODULE, _IMPORT_FAILED
    if _OBJAVERSE_MODULE is not None:
        return _OBJAVERSE_MODULE
    if _IMPORT_FAILED:
        return None
    try:
        import objaverse  # type: ignore
        _OBJAVERSE_MODULE = objaverse
        return objaverse
    except Exception as e:
        print(f"[OBJAVERSE] package not available: {e}", flush=True)
        _IMPORT_FAILED = True
        return None


def is_available() -> bool:
    """Quick check: can we use Objaverse at all?"""
    return _lazy_import() is not None


def _load_annotations() -> dict[str, Any]:
    """Load (and cache) the full annotation dict. First call is slow
    (30-60s + ~800MB download on very first run of the dev machine).
    Subsequent calls return the cached dict immediately."""
    global _ANNOTATIONS_CACHE
    if _ANNOTATIONS_CACHE is not None:
        return _ANNOTATIONS_CACHE

    ov = _lazy_import()
    if ov is None:
        return {}

    try:
        print("[OBJAVERSE] loading annotations (first run: 30-60s)...", flush=True)
        _ANNOTATIONS_CACHE = ov.load_annotations()
        print(f"[OBJAVERSE] loaded {len(_ANNOTATIONS_CACHE)} annotations", flush=True)
        return _ANNOTATIONS_CACHE
    except Exception as e:
        print(f"[OBJAVERSE] failed to load annotations: {e}", flush=True)
        _ANNOTATIONS_CACHE = {}
        return _ANNOTATIONS_CACHE


_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


# Scoring hygiene — keep the realistic/literal interpretation ahead of
# the cartoon/mascot/voxel/etc. versions. The numbers are tuned so that
# a single penalty usually isn't enough to flip the ranking by itself,
# but a mascot that hits 2-3 of these (anamorphic + mascot + cute) will
# sink below a plain "Pelican" with no penalties.
_STYLIZED_PENALTIES: tuple[tuple[str, int], ...] = (
    # Stylization (anthropomorphic / mascot / toy / voxel / ...):
    ("anamorphic",      -40),   # this is the word that tripped us up
    ("anthropomorphic", -40),
    ("mascot",          -30),
    ("cartoon",         -25),
    ("stylized",        -20),
    ("stylised",        -20),
    ("toy",             -20),
    ("low-poly",        -15),
    ("low poly",        -15),
    ("lowpoly",         -15),
    ("voxel",           -25),
    ("minecraft",       -30),
    ("pixel",           -25),
    ("lego",            -30),
    ("chibi",           -30),
    ("cute",            -10),

    # Product / container nouns — a "Pelican Case" scored 86 for the
    # prompt 'pelican' because it's a well-photographed plastic storage
    # box that happens to be Pelican-brand. Same pattern for suitcase /
    # luggage etc.
    ("case",            -30),
    ("box",             -20),
    ("container",       -20),
    ("packaging",       -20),
    ("crate",           -20),
    ("suitcase",        -25),
    ("luggage",         -25),
    ("bag",             -15),

    # Named locations / buildings — "Prospect Of Whitby And Pelican
    # Stairs" is a London pub, not a bird.
    ("stairs",          -25),
    ("pub",             -25),
    ("building",        -20),
    ("house",           -15),
    ("street",          -15),

    # Anatomical fragments — a skull / skeleton / bones record is NOT
    # the whole animal. The user wants a pelican, not a pelican skull.
    ("skull",           -25),
    ("skeleton",        -25),
    ("bones",           -20),
    ("fossil",          -20),
)

_REALISM_BONUSES: tuple[tuple[str, int], ...] = (
    ("photorealistic",  20),
    ("photogrammetry",  20),
    ("scanned",         15),
    ("realistic",       15),
    ("high-poly",       10),
    ("high poly",       10),
    ("detailed",         8),
    ("real",             5),
)

# Object-type penalties for non-subject records. Covers things the query
# might partially match (trophy of a horse, horseshoe, eagle sculpture,
# pelican stairs) and things Objaverse is overrun with (photogrammetry
# scans of streets / caves / interiors that surface on broad queries).
#
# Keywords that already appear in _STYLIZED_PENALTIES are intentionally
# NOT repeated here — keeping a single source of truth prevents
# double-penalizing the same record.
_OBJECT_TYPE_PENALTIES: tuple[tuple[str, int], ...] = (
    # Static depictions ----------------------------------------------------
    ("sculpture",  -25),
    ("statue",     -25),
    ("bust",       -20),
    ("trophy",     -20),
    ("figurine",   -15),
    ("ornament",   -15),
    ("miniature",  -15),
    ("model kit",  -15),
    ("diorama",    -15),
    ("scan",       -10),   # scans are often partial / damaged
    # Compound-word traps --------------------------------------------------
    ("horseshoe",   -50),  # 'horse' → horseshoe had been #1
    ("sawhorse",    -50),  # 'horse' → sawhorse (woodworking bench)
    ("seahorse",    -30),  # 'horse' → seahorse (wrong animal)
    ("shoe",        -30),
    ("cauliflower", -40),  # 'flower' → cauliflower
    ("sunflower",   -10),  # 'flower' → sunflower (still flower-ish)
    ("eaglet",       -5),  # 'eagle' → juvenile bird, mild penalty
    ("pelican case", -50), # 'pelican' → plastic storage box
    # 2D / carvings --------------------------------------------------------
    ("painting",   -30),
    ("drawing",    -25),
    ("mural",      -25),
    ("carving",    -25),
    ("engraving",  -20),
    # Locations / landmarks ------------------------------------------------
    ("passage",    -30),
    ("marker",     -30),
    ("boundary",   -30),
    ("parish",     -30),
    ("bridge",     -25),
    ("cave",       -20),
    # Anatomy fragments ---------------------------------------------------
    ("bone",       -25),
    # Game / toy franchises -----------------------------------------------
    ("playmobil",  -25),
    ("roblox",     -25),
    ("halo",       -20),
)

# Living-thing bonus — applied only when the query is in the animal or
# character keyword set. Favours records that clearly depict a living
# specimen over static scans / carvings / anatomy models.
_LIVING_BONUSES: tuple[tuple[str, int], ...] = (
    ("animated",   20),
    ("rigged",     15),
    ("lifelike",   10),
    ("walking",    10),
    ("running",    10),
    ("flying",     10),
    ("swimming",   10),
    ("alive",      10),
    ("animal",     10),
    ("wildlife",   10),
    ("standing",    5),
    ("sitting",     5),
    ("creature",    5),
    ("nature",      5),
    ("natural",     5),
)

# Multi-part "worn item" signals: co-occurring with each other strongly
# implies the record is a dressed-up anthropomorphic character (a
# pelican mascot in a jacket and shirt), not the realistic subject.
_MASCOT_PARTS: tuple[str, ...] = (
    "shirt", "jacket", "hat", "mascot", "costume", "clothing",
    "trousers", "pants", "tie", "scarf", "glove", "gloves",
)


def _word_boundary(needle: str, haystack: str) -> bool:
    """True when ``needle`` appears in ``haystack`` as a whole word.
    Distinguishes 'horse' in 'horse running' (True) from 'horse' in
    'horseshoe' (False) — the core test that keeps compound words from
    masquerading as subject hits."""
    if not needle or not haystack:
        return False
    return re.search(r"\b" + re.escape(needle) + r"\b", haystack) is not None


def _score_annotation(
    ann: dict, query: str, query_tokens: list[str]
) -> tuple[int, list[tuple[str, int]]]:
    """Heuristic score with a HARD subject-relevance gate.

    Step 1 — compute subject_score from name/description/tags/categories.
             A model with zero subject_score is returned as 0 and will be
             skipped by the caller. Without this gate, realism bonuses
             like "+20 photogrammetry / +15 realistic / +8 detailed" would
             pile onto completely irrelevant records — e.g. "Stone (8K
             Textures)" scored 93 for a 'pelican' query because it has
             realism keywords in its description but nothing pelican-like.
    Step 2 — apply realism bonuses ONLY to records that already passed
             the gate.
    Step 3 — apply stylization / object-type / mascot penalties.
    Step 4 — apply living-thing bonuses when the query is an animal or
             character (so 'Pelican (Animated, Rigged)' outranks
             'Pelican Sculpture').

    Returns ``(score, reasons)`` where ``reasons`` is a list of
    ``(label, delta)`` tuples — used by the top-N log so unexpected
    rankings can be diagnosed from a single line of output.
    """
    name = str(ann.get("name") or "").lower()
    description = str(ann.get("description") or "").lower()

    tags_field = ann.get("tags") or []
    tags_text = " ".join(
        str(t.get("name") if isinstance(t, dict) else t).lower()
        for t in tags_field
    )

    cats_field = ann.get("categories") or []
    cats_text = " ".join(
        str(c.get("name") if isinstance(c, dict) else c).lower()
        for c in cats_field
    )

    reasons: list[tuple[str, int]] = []

    # ── Step 1: subject relevance (gate) ───────────────────────────────
    # Name-level tiers are mutually exclusive to avoid double-counting:
    #   * exact name match     → +150  (very strong: 'Pelican' for 'pelican')
    #   * whole-word match     → +80   (strong:      'Pelican Statue' for 'pelican')
    #   * substring only       → +5    (very weak:   'Horseshoe' for 'horse')
    # The substring tier is deliberately tiny — it should never outrank
    # a real subject on its own; its main job is to keep borderline
    # compound-words in the scoring pool long enough for the object-type
    # penalty list to flush them.
    subject_score = 0
    name_stripped = name.strip()
    name_matched = False

    if query and name_stripped == query:
        subject_score += 150
        reasons.append(("name_exact", 150))
        name_matched = True
    elif query and _word_boundary(query, name):
        subject_score += 80
        reasons.append(("word_match", 80))
        name_matched = True
    elif query and query in name:
        # Substring only — almost certainly a compound word like
        # 'horseshoe', 'sawhorse', 'pelicancase'.
        subject_score += 5
        reasons.append(("substring", 5))
        name_matched = True

    # Multi-word fallback: only fire per-token matching against the name
    # when the *full* query didn't hit. Stops double-counting 'pelican'
    # in 'Pelican' as both name_exact=+150 AND tok_pelican_name=+10.
    # Useful for multi-word queries like 'horse running' → 'Running Horse',
    # where the full query as a contiguous phrase doesn't appear.
    if not name_matched:
        for tok in query_tokens:
            if not tok:
                continue
            if _word_boundary(tok, name):
                subject_score += 10
                reasons.append((f"tok_{tok}_name", 10))
            elif tok in name:
                subject_score += 2
                reasons.append((f"tok_{tok}_sub", 2))

    # Token-level signals from description / tags / categories always
    # apply — they're orthogonal to the name tier and rarely double-count
    # (they score different fields).
    for tok in query_tokens:
        if not tok:
            continue
        if tok in description:
            subject_score += 3
            reasons.append((f"tok_{tok}_desc", 3))
        if tok in tags_text:
            subject_score += 5
            reasons.append((f"tok_{tok}_tag", 5))
        if tok in cats_text:
            subject_score += 5
            reasons.append((f"tok_{tok}_cat", 5))

    # HARD GATE — a model with no subject hit is irrelevant. Realism
    # bonuses must NOT be able to lift it into the results.
    if subject_score <= 0:
        return 0, reasons

    score = subject_score
    all_text = f"{name} {description} {tags_text} {cats_text}"

    # ── Step 2: realism bonuses (only for gated-in models) ─────────────
    for keyword, bonus in _REALISM_BONUSES:
        if keyword in all_text:
            score += bonus
            reasons.append((keyword, bonus))

    # ── Step 3a: stylization penalties ─────────────────────────────────
    for keyword, penalty in _STYLIZED_PENALTIES:
        if keyword in all_text:
            score += penalty
            reasons.append((keyword, penalty))

    # ── Step 3b: object-type penalties (sculpture, trophy, horseshoe...) ─
    for keyword, penalty in _OBJECT_TYPE_PENALTIES:
        if keyword in all_text:
            score += penalty
            reasons.append((keyword, penalty))

    # ── Step 4: living-thing bonus when query is animal/character ─────
    is_living_query = any(
        tok in _ANIMAL_KEYWORDS or tok in _CHARACTER_KEYWORDS
        for tok in query_tokens
    )
    if is_living_query:
        for keyword, bonus in _LIVING_BONUSES:
            if keyword in all_text:
                score += bonus
                reasons.append((keyword, bonus))

    # Clothed-mascot detector: multiple "worn item" words co-occurring
    # inside a single record strongly implies an anthropomorphic
    # character rather than a realistic animal/object.
    mascot_hits = sum(
        1 for part in _MASCOT_PARTS if part in all_text
    )
    if mascot_hits >= 2:
        score -= 30
        reasons.append(("mascot_parts", -30))

    # ── Step 5: asset quality filters ─────────────────────────────────
    # Photogrammetry / 3D-scan captures are environment chunks, not
    # isolated subjects. "Eagle" scores well by name but the model is
    # a 1 km² terrain scan with an eagle somewhere in the texture.
    _SCAN_KEYWORDS = (
        "photogrammetry", "photoscan", "reality capture", "point cloud",
        "lidar", "3d scan", "stereo mesh", "reconstructed",
        "captured with", "terrain scan", "environment scan",
    )
    if any(kw in all_text for kw in _SCAN_KEYWORDS):
        score -= 40
        reasons.append(("scan_model", -40))

    # Bonus for clean, game-ready models — intentionally authored (not
    # scanned) and far more likely to be a usable isolated subject.
    _CLEAN_KEYWORDS = (
        "game ready", "game-ready", "optimized", "clean topology",
        "quad", "low poly", "pbr",
    )
    if any(kw in all_text for kw in _CLEAN_KEYWORDS):
        score += 10
        reasons.append(("game_ready", 10))

    # High face count is a strong signal for raw scans / unoptimised
    # photogrammetry captures. Check the annotation's faceCount field.
    _face_count = ann.get("faceCount") or ann.get("face_count") or 0
    try:
        _face_count = int(_face_count)
    except (TypeError, ValueError):
        _face_count = 0
    if _face_count > 150_000:
        score -= 20
        reasons.append(("high_poly", -20))
    elif _face_count > 80_000:
        score -= 10
        reasons.append(("med_poly", -10))

    # ── Step 6: pose quality ──────────────────────────────────────────
    # For living subjects, a standing/T-pose model is far more useful
    # than one lying down or dead. The horse query kept returning a
    # lying-down horse (0.52m wide for a 2.26m body).
    if is_living_query:
        _GOOD_POSE = ("standing", "t-pose", "a-pose", "idle", "upright")
        _BAD_POSE = ("lying", "sleeping", "resting", "dead",
                      "fallen", "collapsed", "prone", "recumbent")
        for kw in _GOOD_POSE:
            if kw in all_text:
                score += 10
                reasons.append((f"pose_{kw}", 10))
        for kw in _BAD_POSE:
            if kw in all_text:
                score -= 20
                reasons.append((f"pose_{kw}", -20))

    return score, reasons


_ANIMAL_KEYWORDS = (
    "dog", "cat", "horse", "bird", "eagle", "pelican", "owl", "parrot",
    "fish", "dolphin", "whale", "shark", "tiger", "lion", "bear",
    "wolf", "fox", "deer", "rabbit", "frog", "snake", "lizard",
    "monkey", "chimpanzee", "ape", "cow", "pig", "sheep", "chicken",
    "duck", "penguin", "butterfly", "spider", "octopus", "crab",
    "dragon", "dinosaur", "animal", "creature", "beast",
)
_CHARACTER_KEYWORDS = (
    "robot", "mech", "droid", "android", "person", "man", "woman",
    "character", "warrior", "knight", "soldier", "astronaut",
    "chef", "cook", "dancer", "ninja", "wizard", "superhero",
    "zombie", "pirate", "samurai", "human",
)
_VEHICLE_KEYWORDS = (
    "car", "truck", "motorcycle", "vehicle", "ferrari", "lamborghini",
    "airplane", "plane", "helicopter", "boat", "ship", "bicycle",
    "tank", "bus", "train",
)


def _classify_asset_type(subject: str, description: str = "") -> str:
    """Map a subject (plus optional Objaverse description) to the pipeline's
    asset-type buckets: animal / character / vehicle / prop.

    Used to ensure a downloaded Objaverse 'pelican' record lands in the
    characters bucket (as an animal) instead of being routed as a prop
    because its raw `type` field was the file format ('glb')."""
    text = f"{subject or ''} {description or ''}".lower()
    for kw in _ANIMAL_KEYWORDS:
        if kw in text:
            return "animal"
    for kw in _CHARACTER_KEYWORDS:
        if kw in text:
            return "character"
    for kw in _VEHICLE_KEYWORDS:
        if kw in text:
            return "vehicle"
    return "prop"


def _format_reasons(reasons: list[tuple[str, int]], limit: int = 6) -> str:
    """Render a short '(name_exact=+150, animated=+20, horseshoe=-50)' line
    for a logged top-N entry. Prefers the highest-magnitude items when
    the reason list is longer than ``limit`` so the most load-bearing
    signals always appear first."""
    if not reasons:
        return ""
    ordered = sorted(reasons, key=lambda kv: abs(kv[1]), reverse=True)[:limit]
    return ", ".join(f"{k}={v:+d}" for k, v in ordered)


def search_objaverse(query: str, max_results: int = 20) -> list[dict]:
    """Score every annotation against `query` and return the top N.
    Each result dict includes: uid, name, description, score."""
    query = (query or "").strip().lower()
    if not query:
        return []

    annotations = _load_annotations()
    if not annotations:
        return []

    tokens = _tokenize(query)
    scored: list[tuple[int, str, dict, list[tuple[str, int]]]] = []
    for uid, ann in annotations.items():
        if not isinstance(ann, dict):
            continue
        s, reasons = _score_annotation(ann, query, tokens)
        if s > 0:
            scored.append((s, uid, ann, reasons))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_results]

    results: list[dict] = [{
        "uid":         uid,
        "name":        ann.get("name", ""),
        "description": ann.get("description", ""),
        "score":       s,
    } for s, uid, ann, _reasons in top]

    # Observability: log the top 5 with the scoring breakdown so that
    # unexpected rankings can be diagnosed from a single log chunk.
    # Example:
    #   [OBJAVERSE] Top 5 for 'horse':
    #   [OBJAVERSE]   #1: 'Horse' score=230 (name_exact=+150, animated=+20, rigged=+15)
    #   [OBJAVERSE]   #2: 'Running Horse' score=175 (word_match=+80, animated=+20, running=+10)
    #   [OBJAVERSE]   #3: 'Horseshoe' score=-45 (horseshoe=-50, substring=+5)  # filtered
    if top:
        print(f"[OBJAVERSE] Top {min(5, len(top))} for {query!r}:", flush=True)
        for i, (s, _uid, ann, reasons) in enumerate(top[:5]):
            name = ann.get("name", "") or "<unnamed>"
            print(
                f"[OBJAVERSE]   #{i+1}: {name!r} score={s} "
                f"({_format_reasons(reasons)})",
                flush=True,
            )
    else:
        print(f"[OBJAVERSE] no results for {query!r}", flush=True)

    return results


def download_objaverse_model(uid: str) -> Path | None:
    """Download the GLB for `uid` if it isn't cached already. Returns the
    cached path, or None on any failure."""
    if not uid:
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{uid}.glb"
    if cached.exists():
        _sz = cached.stat().st_size
        if _sz > 0:
            # Reject suspiciously small cached files — likely a placeholder
            # or a failed partial download. Delete and re-download.
            if _sz < 50_000:
                print(
                    f"[OBJAVERSE] cached file too small ({_sz} bytes), "
                    f"deleting and re-downloading: {cached.name}",
                    flush=True,
                )
                cached.unlink(missing_ok=True)
            else:
                return cached

    ov = _lazy_import()
    if ov is None:
        return None

    try:
        print(f"[OBJAVERSE] downloading {uid}...", flush=True)
        paths = ov.load_objects(uids=[uid])
        src = paths.get(uid) if isinstance(paths, dict) else None
        if not src:
            print(f"[OBJAVERSE] load_objects returned nothing for {uid}", flush=True)
            return None
        src_path = Path(src)
        if not src_path.exists():
            print(f"[OBJAVERSE] downloaded path missing: {src_path}", flush=True)
            return None
        shutil.copy2(src_path, cached)
        print(f"[OBJAVERSE] cached -> {cached.name} ({cached.stat().st_size} bytes)", flush=True)
        return cached
    except Exception as e:
        print(f"[OBJAVERSE] download failed for {uid}: {e}", flush=True)
        return None


def fetch_hero_from_objaverse(subject: str) -> dict | None:
    """Full hero-fetch pipeline: search, then try downloading the top 3
    candidates. Returns a dict shaped like the other fetchers:
        {"path": str, "name": str, "source": "objaverse",
         "type": "glb", "uid": str, "score": int}
    or None if nothing works."""
    if not subject:
        return None
    if not is_available():
        return None

    try:
        candidates = search_objaverse(subject, max_results=20)
    except Exception as e:
        print(f"[OBJAVERSE] search error: {e}", flush=True)
        return None

    if not candidates:
        print(f"[OBJAVERSE] no matches for '{subject}'", flush=True)
        return None

    # ── Variety: shuffle top-N when scores are close ──────────────────
    # Without this, "cat" always returns the same sleeping cat because
    # the top-scored annotation is deterministic.  We shuffle among
    # candidates whose score is within 20% of the top score, so "cat"
    # can return a different model each render while still staying on
    # the high-quality end of the ranking.
    import random as _random
    if len(candidates) > 1:
        _top_score = candidates[0].get("score", 0)
        _threshold = max(1, int(_top_score * 0.8))
        _close_candidates = [
            c for c in candidates[:10]
            if c.get("score", 0) >= _threshold
        ]
        if len(_close_candidates) > 1:
            _random.shuffle(_close_candidates)
            # Preserve the tail (lower-scored fallbacks) after the shuffled head
            _remainder = [c for c in candidates if c not in _close_candidates]
            candidates = _close_candidates + _remainder
            print(
                f"[OBJAVERSE] variety: shuffled {len(_close_candidates)} "
                f"candidates within 80% of top score ({_top_score}); "
                f"new leader={candidates[0].get('name', '?')!r}",
                flush=True,
            )

    # ── Subject-name match filter with synonyms ──────────────────────
    # Build an allowed-word set: subject tokens + known synonyms.  A
    # candidate whose name contains NONE of these words is rejected,
    # unless all candidates fail (then we keep the top-scored as a
    # best-effort fallback).  This is what prevents "cheetah" from
    # returning a robot and "pelican" from returning a starfighter.
    _SUBJECT_SYNONYMS = {
        "cheetah":  ["cheetah", "leopard", "jaguar", "feline", "big cat"],
        "pelican":  ["pelican", "bird", "seabird"],
        "dinosaur": ["dinosaur", "dino", "rex", "raptor", "sauropod",
                     "trex", "t-rex"],
        "dolphin":  ["dolphin", "porpoise"],
        "polar":    ["polar", "bear"],
        "eagle":    ["eagle", "bird", "raptor", "hawk"],
        "horse":    ["horse", "stallion", "mare", "pony", "equine"],
        "cat":      ["cat", "kitten", "feline"],
        "dog":      ["dog", "puppy", "canine", "hound"],
        "bear":     ["bear", "polar", "grizzly"],
        "robot":    ["robot", "mech", "droid", "android", "cyborg"],
    }

    _subject_tokens: set = set()
    for _tok in (subject or "").lower().split():
        if len(_tok) > 2:
            _subject_tokens.add(_tok)
    # Expand with synonyms
    _allowed_words: set = set(_subject_tokens)
    for _tok in list(_subject_tokens):
        for _syn in _SUBJECT_SYNONYMS.get(_tok, []):
            _allowed_words.add(_syn.lower())

    def _name_matches_subject(cand_obj) -> bool:
        if not _allowed_words:
            return True
        _hay = (
            str(cand_obj.get("name", "")).lower() + " "
            + str(cand_obj.get("description", "")).lower()
        )
        return any(w in _hay for w in _allowed_words)

    _matching = [c for c in candidates if _name_matches_subject(c)]
    _non_matching = [c for c in candidates if not _name_matches_subject(c)]

    if _matching:
        # Only candidates with matching names survive — non-matching are
        # dropped completely (not just demoted) for the top-5 window.
        # Non-matching are appended at the end as last-resort fallback.
        candidates = _matching + _non_matching
        print(
            f"[OBJAVERSE] subject-name filter: kept "
            f"{len(_matching)} match / dropped {len(_non_matching)} "
            f"non-match to tail; allowed={sorted(_allowed_words)!r}; "
            f"new leader={candidates[0].get('name', '?')!r}",
            flush=True,
        )
    elif _subject_tokens and _non_matching:
        # No candidate matched — warn loudly and fall back to original order
        print(
            f"[OBJAVERSE] WARNING: no candidate name contains any of "
            f"{sorted(_allowed_words)!r} — using top-scored fallback "
            f"{candidates[0].get('name', '?')!r}",
            flush=True,
        )

    # ── Sleeping/static pose penalty for action prompts ───────────────
    # The "sleeping cat" keeps winning for "cat running" prompts.  When
    # the user's prompt implies motion, push sleeping/sitting models to
    # the tail of the list so an animated pose wins.
    _ACTION_WORDS = (
        "running", "walking", "jumping", "playing", "dancing",
        "chasing", "galloping", "flying", "swimming", "fighting",
        "driving", "racing", "riding", "climbing", "leaping",
    )
    _prompt_text = (subject or "").lower()
    _is_action_prompt = any(w in _prompt_text for w in _ACTION_WORDS)
    if _is_action_prompt and candidates:
        _STATIC_POSE_WORDS = (
            "sleeping", "lying", "sitting", "resting",
            "laying", "napping", "dead",
        )
        def _is_static_pose(cand_obj) -> bool:
            _hay = (
                str(cand_obj.get("name", "")).lower() + " "
                + str(cand_obj.get("description", "")).lower()
            )
            return any(p in _hay for p in _STATIC_POSE_WORDS)
        _active = [c for c in candidates if not _is_static_pose(c)]
        _static = [c for c in candidates if _is_static_pose(c)]
        if _active and _static:
            candidates = _active + _static
            print(
                f"[OBJAVERSE] action-prompt filter: demoted "
                f"{len(_static)} static-pose candidate(s); "
                f"new leader={candidates[0].get('name', '?')!r}",
                flush=True,
            )

    # Collect all viable candidate paths so Blender-side can iterate
    # if the first one fails mesh validation (flat card, placeholder).
    viable_paths: list[dict] = []

    # For vehicle subjects we widen the candidate window to 10 (from 5)
    # because the quality gate may reject many low-poly proxies before
    # finding a real car.
    _is_vehicle_subj = _is_vehicle_subject(subject)
    _candidate_window = 10 if _is_vehicle_subj else 5

    # ── Variant pool: register candidates + apply recency-aware re-rank ─
    # Same subject across renders → rotate through variants instead of
    # always picking the same top-scored result.  Non-fatal: pool errors
    # fall through to original ranking.
    try:
        from .variant_pool import register_variants, pick_variant
        _pool_candidates = [
            {
                "id":     c.get("uid", ""),
                "uid":    c.get("uid", ""),
                "name":   c.get("name", ""),
                "score":  c.get("score", 0),
                "source": "objaverse",
            }
            for c in candidates[:10]
        ]
        register_variants(subject, _pool_candidates)
        _winner = pick_variant(subject, _pool_candidates)
        if _winner is not None:
            _winner_uid = _winner.get("uid")
            if _winner_uid and candidates:
                # Re-order candidates so the pool-selected winner is first
                _reordered = [
                    c for c in candidates if c.get("uid") == _winner_uid
                ] + [
                    c for c in candidates if c.get("uid") != _winner_uid
                ]
                if _reordered and _reordered[0].get("uid") == _winner_uid:
                    candidates = _reordered
                    print(
                        f"[VARIANT_POOL] promoted {_winner.get('name', '?')!r} "
                        f"to candidate #1 for subject={subject!r}",
                        flush=True,
                    )
    except Exception as _vp_err:
        print(f"[VARIANT_POOL] non-fatal error: {_vp_err}", flush=True)

    for cand in candidates[:_candidate_window]:
        # Blacklist check — skip assets previously marked as bad
        try:
            from .asset_logger import is_blacklisted
            if is_blacklisted("objaverse", cand["uid"]):
                print(
                    f"[OBJAVERSE] skipping blacklisted model: "
                    f"{cand['name']!r} ({cand['uid']})",
                    flush=True,
                )
                continue
        except Exception:
            pass  # logger not available — skip check

        path = download_objaverse_model(cand["uid"])
        if path is None:
            continue

        # ── File-size quality gate ────────────────────────────────────
        # Reject placeholders (<50 KB) and raw photogrammetry (>50 MB).
        try:
            _fsize = Path(path).stat().st_size
        except Exception:
            _fsize = 0
        if _fsize < 50_000:
            print(
                f"[OBJAVERSE] rejected {cand['name']!r} ({cand['uid']}): "
                f"file too small ({_fsize} bytes), trying next",
                flush=True,
            )
            continue
        if _fsize > 50_000_000:
            print(
                f"[OBJAVERSE] rejected {cand['name']!r} ({cand['uid']}): "
                f"file too large ({_fsize/1e6:.1f} MB, likely scan), "
                f"trying next",
                flush=True,
            )
            continue

        # ── Vehicle quality gate ──────────────────────────────────────
        # Reject blocky proxies for vehicle subjects by inspecting the
        # GLB's mesh/vertex counts WITHOUT importing it.  The 9-cube
        # "Racecar" that name-exact-matches at score=150 fails here.
        if _is_vehicle_subj:
            _qa_ok, _qa_msg = _passes_vehicle_quality_gate(str(path))
            print(
                f"[OBJAVERSE_QA] candidate {cand['name']!r} "
                f"(score={cand.get('score', 0)}): {_qa_msg}",
                flush=True,
            )
            if not _qa_ok:
                print(
                    f"[OBJAVERSE_QA] REJECTED — trying next candidate",
                    flush=True,
                )
                continue

        asset_type = _classify_asset_type(subject, cand.get("description", ""))
        viable_paths.append({
            "path":  str(path),
            "name":  cand["name"] or subject,
            "uid":   cand["uid"],
            "score": cand["score"],
            "type":  asset_type,
        })

        # Cap at 3 viable candidates for Blender-side iteration
        if len(viable_paths) >= 3:
            break

    if not viable_paths:
        if _is_vehicle_subj:
            print(
                f"[OBJAVERSE_QA] all {_candidate_window} candidates failed "
                f"vehicle QA — downstream should fall back to curated vehicle",
                flush=True,
            )
        print(f"[OBJAVERSE] all top candidates failed quality gate for '{subject}'", flush=True)
        return None

    best = viable_paths[0]
    print(
        f"[OBJAVERSE] accepted {best['name']!r} score={best['score']} "
        f"type={best['type']} (+{len(viable_paths)-1} backup candidates)",
        flush=True,
    )

    # Mark the accepted variant as used in the rotation pool
    try:
        from .variant_pool import mark_used
        mark_used(subject, best["uid"])
    except Exception:
        pass

    # Log to asset library for future curation
    try:
        from .asset_logger import log_asset
        log_asset(
            subject=subject,
            source="objaverse",
            uid=best["uid"],
            name=best["name"],
            file_path=best["path"],
        )
    except Exception:
        pass  # logger not available — non-fatal

    # Build extra candidate paths for Blender-side fallback iteration
    hero_candidates = [v["path"] for v in viable_paths[1:]]

    return {
        "path":             best["path"],
        "name":             best["name"],
        "description":      cand.get("description", ""),
        "source":           "objaverse",
        "source_uid":       best["uid"],
        "uid":              best["uid"],
        "score":            best["score"],
        "type":             best["type"],
        "file_format":      "glb",
        "hero_candidates":  hero_candidates,
    }
