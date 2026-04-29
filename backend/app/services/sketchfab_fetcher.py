from __future__ import annotations

"""
sketchfab_fetcher.py
====================
Thin client around the Sketchfab v3 API for the asset agent.

Responsibilities
----------------
- Search downloadable models matching a free-form query.
- Score and pick the best match for a given subject/style.
- Download the chosen .glb (or .gltf zip) into the local asset cache.
- Register the downloaded model in the asset registry so the resolver
  can pick it up on the next pass without re-downloading.

Design rules
------------
- Requires the env var ``SKETCHFAB_API_TOKEN``. Without it, every call
  returns ``None`` and prints a single warning. The pipeline must keep
  working in offline / unauthenticated mode.
- Network failures and 4xx/5xx are caught — they NEVER raise into the
  caller. The caller is responsible for falling back to PolyHaven /
  hardcoded assets.
- Only downloadable, license-compatible (CC-BY / CC0) models are
  considered. We never download models flagged as ``downloadable: false``.
- Every download is logged with timing.
"""

import json
import os
import re
import time
import zipfile
from pathlib import Path
from typing import Any

try:
    import requests  # type: ignore
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from .registry_io import upsert_asset


def _json_from_response(response) -> Any:
    """
    Parse a requests.Response body as JSON, tolerating a UTF-8 BOM.
    Sketchfab occasionally returns responses prefixed with a BOM which
    the default ``response.json()`` (strict utf-8 decoder) chokes on.
    """
    raw = response.content or b""
    if not raw:
        return None
    # utf-8-sig silently strips the BOM if present, otherwise behaves as utf-8.
    text = raw.decode("utf-8-sig", errors="replace")
    if not text:
        return None
    return json.loads(text)


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

API_BASE = "https://api.sketchfab.com/v3"
DEFAULT_TIMEOUT = float(os.environ.get("SKETCHFAB_TIMEOUT", "30"))
DEFAULT_DOWNLOAD_TIMEOUT = float(os.environ.get("SKETCHFAB_DOWNLOAD_TIMEOUT", "300"))

# Compatible licenses (slugs returned by the Sketchfab API).
# These are the only ones we will download from.
ALLOWED_LICENSES = {
    "cc0",
    "cc-by",
    "cc-by-sa",
    "by",
    "by-sa",
}


def _api_token() -> str | None:
    token = os.environ.get("SKETCHFAB_API_TOKEN", "").strip()
    return token or None


def _headers() -> dict[str, str]:
    token = _api_token()
    if not token:
        return {}
    return {"Authorization": f"Token {token}"}


def is_available() -> bool:
    """Quick gate the asset agent can use before calling search/download."""
    return bool(_HAS_REQUESTS and _api_token())


# ═══════════════════════════════════════════════════════════════════════════
# Search
# ═══════════════════════════════════════════════════════════════════════════

def _slug_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


# Models whose names match these keywords are almost never what a user
# asking for a "dog" or "robot" actually wants. Heavy penalty, not a
# hard reject — a "halloween dog costume" would still win if the word
# "dog" carried its own name bonus first.
_IRRELEVANT_NAME_KEYWORDS = (
    "halloween", "christmas", "easter", "holiday", "valentine", "party",
    "ui", "icon", "logo", "badge", "sticker",
    "2d", "sprite", "pixel",
    "diorama", "photobash",
)

# Keywords that suggest an environment/scene model rather than a hero
# character. Heavy penalty when we're searching for a hero.
_ENVIRONMENT_NAME_KEYWORDS = (
    "scene", "room", "house", "building", "environment", "landscape",
    "level", "map", "terrain", "dungeon",
)


def _score_model(query: str, model: dict, *, want_animated: bool = False) -> int:
    """
    Relevance score 0-100. Higher = better match for the query.

    Scoring philosophy (overhauled in Round 8)
    ------------------------------------------
    Direct name match is the dominant signal. A model whose name does
    not contain the query at all gets at most a small tag/description
    bonus — it should rarely beat a model with the query literally in
    its name. Irrelevant novelty models ("Halloween 🎃", emoji-heavy
    names, environment dioramas) are heavily penalised so they don't
    win by racking up bonus points on license/popularity alone.

    Breakdown
        Name relevance          : up to 40 pts  (40 for exact query in name)
        Negative name keywords  : -15 each      (halloween, scene, ui, etc.)
        Emoji in name           : -10 each
        License                 : up to 15 pts  (CC0=15)
        Animation               : up to 15 pts  (animated hero)
        Geometry sweet spot     : up to 15 pts  (5k-100k faces)
        Texture present         : up to 5 pts
        Popularity              : up to 5 pts
        Downloadable            : hard zero if false
    """
    raw_name = str(model.get("name", ""))
    name = raw_name.lower()
    query_lower = query.lower().strip()
    query_words = [w for w in query_lower.split() if w]

    tag_names: list[str] = []
    for tag in model.get("tags", []) or []:
        if isinstance(tag, dict):
            tag_names.append(str(tag.get("name", "")).lower())
        else:
            tag_names.append(str(tag).lower())
    description = str(model.get("description", "") or "").lower()

    score = 0

    # === NAME RELEVANCE (up to 40 points) ===
    if query_lower and query_lower in name:
        score += 40
    elif query_words:
        matched_words = sum(1 for w in query_words if w in name)
        if matched_words > 0:
            score += int(25 * (matched_words / len(query_words)))
        else:
            # No name match — weak tag/description fallback only.
            tag_blob = " ".join(tag_names)
            if query_lower and any(query_lower in t for t in tag_names):
                score += 20
            elif any(w in tag_blob for w in query_words):
                score += 12
            elif query_lower and query_lower in description:
                score += 10
            # else: zero — this model probably isn't what we want

    # === NEGATIVE NAME KEYWORDS ===
    # These are almost always NOT what the user asked for.
    for kw in _IRRELEVANT_NAME_KEYWORDS:
        if kw in name:
            score -= 15
    for kw in _ENVIRONMENT_NAME_KEYWORDS:
        if kw in name:
            score -= 15

    # === EMOJI PENALTY ===
    # Emoji-heavy names ("Halloween 🎃 👻") correlate with novelty/meme models.
    emoji_count = sum(1 for c in raw_name if ord(c) > 0x1F000)
    if emoji_count > 0:
        score -= 10 * emoji_count

    # === LICENSE (up to 15 points) ===
    lic_slug = _license_slug(model)
    license_scores = {
        "cc0":      15,
        "cc-by":    12,
        "by":       12,
        "cc-by-sa": 10,
        "by-sa":    10,
        "cc-by-nd": 8,
        "cc-by-nc": 5,
    }
    score += license_scores.get(lic_slug, 2)

    # === ANIMATION (up to 15 points) ===
    anim_count = int(model.get("animationCount") or 0)
    if anim_count > 0:
        score += 15
    elif want_animated:
        score -= 10  # we explicitly wanted motion

    # === GEOMETRY SWEET SPOT (up to 15 points) ===
    face_count = int(model.get("faceCount") or 0)
    if 5_000 <= face_count <= 100_000:
        score += 15
    elif 1_000 <= face_count < 5_000 or 100_000 < face_count <= 200_000:
        score += 10
    elif face_count > 200_000:
        score += 3   # too heavy
    else:
        score += 5   # too simple

    # === TEXTURES (up to 5 points) ===
    if int(model.get("textureCount") or 0) > 0:
        score += 5
    elif model.get("archives") or model.get("thumbnails"):
        score += 2  # conservative — textures not reliably signalled in search

    # === POPULARITY (up to 5 points) ===
    likes = int(model.get("likeCount") or 0)
    if likes >= 100:
        score += 5
    elif likes >= 20:
        score += 3
    elif likes >= 5:
        score += 1

    # === DOWNLOADABLE HARD GATE ===
    if not model.get("isDownloadable"):
        return 0
    if model.get("isAgeRestricted"):
        score -= 20

    return max(0, score)


# Minimum score a hero candidate must earn before we accept it. A
# Halloween-themed novelty model usually scores in the 20s (license +
# popularity - penalties); a real "dog" hit comfortably clears 40.
MINIMUM_HERO_SCORE = 35

# Minimum Sketchfab relevance score for a PROP to be accepted.
# Prop queries (seaweed, coral reef, campfire, etc.) have historically
# returned weakly-related hits like "Round goby" at score=47 for a
# "seaweed" query because both share the "ocean" tag.  A prop that
# doesn't clearly match the query is worse than no prop at all — it
# pollutes the scene and steals framing from the hero.  Set to 60 so
# only confident matches inject.  Tune if the false-rejection rate
# turns out too high.
MINIMUM_PROP_SCORE = 60


# ═══════════════════════════════════════════════════════════════════════════
# Subject-relevance hard gate (Round 9 Pillar 1A)
# ═══════════════════════════════════════════════════════════════════════════
#
# The scoring overhaul in Round 8 made irrelevant picks rare, but we still
# saw "a car racing" return a neon cyberpunk sign because the model was
# high-quality enough for its bonuses to dominate. The relevance gate is a
# hard boolean filter: if the subject (or a known synonym) doesn't appear
# anywhere in name/tags/categories, the result is dropped BEFORE scoring.

_SUBJECT_SYNONYMS: dict[str, list[str]] = {
    "car":     ["car", "vehicle", "automobile", "sedan", "coupe", "supercar",
                "sports car", "race car", "hatchback", "pickup", "truck",
                "ferrari", "lamborghini", "porsche", "bmw", "audi",
                "mustang", "corvette", "tesla"],
    "vehicle": ["car", "vehicle", "truck", "bus", "van", "motorcycle",
                "motorbike", "bike", "scooter", "suv", "coupe", "sedan"],
    "truck":   ["truck", "pickup", "lorry", "semi", "vehicle"],
    "motorcycle": ["motorcycle", "motorbike", "bike", "chopper", "scooter"],
    "dog":     ["dog", "puppy", "canine", "retriever", "shepherd", "labrador",
                "poodle", "bulldog", "husky", "corgi", "shiba", "terrier",
                "hound", "beagle", "dachshund", "doggo"],
    "cat":     ["cat", "kitten", "feline", "tabby", "persian", "siamese",
                "calico", "kitty"],
    "robot":   ["robot", "mech", "mecha", "droid", "android", "cyborg",
                "automaton", "mechanical", "bot"],
    "lizard":  ["lizard", "reptile", "gecko", "chameleon", "iguana",
                "salamander", "dragon", "dinosaur", "godzilla", "newt"],
    "horse":   ["horse", "stallion", "mare", "pony", "equine"],
    "bird":    ["bird", "eagle", "hawk", "parrot", "owl", "sparrow", "crow",
                "raven", "pigeon", "falcon"],
    "fish":    ["fish", "shark", "whale", "dolphin", "salmon", "tuna",
                "trout", "koi", "carp"],
    "person":  ["person", "human", "man", "woman", "character", "figure",
                "warrior", "soldier", "dancer", "humanoid"],
    "tree":    ["tree", "oak", "pine", "palm", "forest", "plant", "vegetation",
                "shrub", "bush"],
    "house":   ["house", "home", "cottage", "cabin", "building", "residence"],
}


def _subject_from_query(query: str) -> str:
    """
    Extract the primary subject word from a free-form Sketchfab query.
    The first word that appears in the synonym table wins. If none
    match, fall back to the first non-stopword in the query.
    """
    stopwords = {
        "a", "an", "the", "and", "or", "of", "in", "on", "with", "at",
        "3d", "model", "rigged", "animated", "free", "low", "high", "poly",
    }
    words = [w.lower() for w in query.split() if w.strip()]
    for w in words:
        if w in _SUBJECT_SYNONYMS:
            return w
    for w in words:
        if w not in stopwords:
            return w
    return query.strip().lower()


def _result_text_blob(result: dict) -> str:
    name = str(result.get("name", "")).lower()
    tag_names: list[str] = []
    for t in result.get("tags", []) or []:
        if isinstance(t, dict):
            tag_names.append(str(t.get("name", "")).lower())
        else:
            tag_names.append(str(t).lower())
    cat_names: list[str] = []
    for c in result.get("categories", []) or []:
        if isinstance(c, dict):
            cat_names.append(str(c.get("name", "")).lower())
        else:
            cat_names.append(str(c).lower())
    return " ".join([name, " ".join(tag_names), " ".join(cat_names)])


def is_relevant_to_subject(result: dict, subject: str) -> bool:
    """
    Hard relevance gate: does this Sketchfab hit actually represent the
    requested subject? Checks the subject word and its synonym family
    against name/tags/categories. Returns False if nothing matches so
    the caller can drop the result before it ever reaches scoring.
    """
    subject_lower = (subject or "").strip().lower()
    if not subject_lower:
        return True  # no subject to filter by, accept everything

    text = _result_text_blob(result)

    check_words = _SUBJECT_SYNONYMS.get(subject_lower)
    if not check_words:
        # Also try individual subject words — e.g. "sports car" → try "car"
        for part in subject_lower.split():
            if part in _SUBJECT_SYNONYMS:
                check_words = _SUBJECT_SYNONYMS[part]
                break
    if not check_words:
        check_words = [subject_lower]

    return any(w in text for w in check_words)


def _license_slug(model: dict) -> str:
    lic = model.get("license") or {}
    if isinstance(lic, dict):
        return str(lic.get("slug") or "").lower()
    return str(lic or "").lower()


def search_models(
    query: str,
    *,
    limit: int = 12,
    min_face_count: int = 0,
    max_face_count: int | None = None,
    categories: list[str] | None = None,
    animated: bool | None = None,
) -> list[dict]:
    """
    Search Sketchfab for downloadable, license-compatible models.

    Returns a ranked list of dicts with keys:
        ``uid``, ``name``, ``score``, ``license``, ``thumbnail``,
        ``face_count``, ``animation_count``, ``raw``.
    Returns an empty list on any failure.
    """
    if not is_available():
        return []

    params: dict[str, Any] = {
        "type": "models",
        "q": query,
        "downloadable": "true",
        "archives_flavours": "false",
        "count": min(48, max(limit * 3, 12)),
        "sort_by": "-likeCount",
    }
    if min_face_count:
        params["min_face_count"] = min_face_count
    if max_face_count:
        params["max_face_count"] = max_face_count
    if categories:
        params["categories"] = ",".join(categories)
    if animated is True:
        params["animated"] = "true"

    started = time.time()
    try:
        r = requests.get(
            f"{API_BASE}/search",
            params=params,
            headers=_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        body = _json_from_response(r) or {}
    except Exception as e:
        print(f"[SKETCHFAB] search failed for q={query!r}: {e}", flush=True)
        return []

    raw_results = body.get("results") or []
    want_animated = animated is True

    # Subject-relevance hard gate (Round 9 Pillar 1A): drop hits that
    # don't mention the subject (or a known synonym) anywhere in
    # name/tags/categories BEFORE we waste time scoring them. If the
    # gate eats everything, fall back to the unfiltered list rather
    # than returning empty — better a weak match than none.
    subject = _subject_from_query(query)
    relevant_results = [r for r in raw_results if is_relevant_to_subject(r, subject)]
    if raw_results and not relevant_results:
        print(
            f"[SKETCHFAB] WARNING: no subject-relevant results for "
            f"subject={subject!r} q={query!r} out of {len(raw_results)} hits "
            f"— falling back to unfiltered list",
            flush=True,
        )
        relevant_results = raw_results
    elif raw_results:
        dropped = len(raw_results) - len(relevant_results)
        if dropped:
            print(
                f"[SKETCHFAB] subject gate ({subject!r}) dropped "
                f"{dropped}/{len(raw_results)} irrelevant hits",
                flush=True,
            )

    scored: list[dict] = []
    for model in relevant_results:
        if not model.get("isDownloadable"):
            continue
        lic_slug = _license_slug(model)
        if lic_slug and lic_slug not in ALLOWED_LICENSES:
            continue
        scored.append({
            "uid": model.get("uid"),
            "name": model.get("name"),
            "score": _score_model(query, model, want_animated=want_animated),
            "license": lic_slug or "unknown",
            "thumbnail": (model.get("thumbnails", {}).get("images") or [{}])[0].get("url"),
            "face_count": int(model.get("faceCount") or 0),
            "animation_count": int(model.get("animationCount") or 0),
            "raw": model,
        })

    scored.sort(key=lambda m: m["score"], reverse=True)
    elapsed = time.time() - started
    print(
        f"[SKETCHFAB] search q={query!r} -> {len(scored)} hits "
        f"(of {len(raw_results)}) in {elapsed:.2f}s",
        flush=True,
    )
    # Per-hit dump of the top 3 candidates for diagnosing misses.
    # When a cascade has to broaden ("eagle" → "bird of prey" → "bird"),
    # these lines make it obvious which stage each hit came from and why
    # the pick got ranked where it did.
    for candidate in scored[:3]:
        try:
            print(
                f"[SKETCHFAB]   - {candidate.get('name')!r} "
                f"score={candidate.get('score')} "
                f"faces={candidate.get('face_count')} "
                f"anims={candidate.get('animation_count')} "
                f"license={candidate.get('license')}",
                flush=True,
            )
        except Exception:
            pass
    if not scored and raw_results:
        print(
            f"[SKETCHFAB]   (all {len(raw_results)} raw hits were filtered by "
            f"downloadable/license/subject gates)",
            flush=True,
        )
    return scored[:limit]


def search_with_fallback_queries(
    subject: str,
    query_variations: list[str] | None = None,
    *,
    top_n: int = 5,
    animated: bool | None = None,
) -> list[dict]:
    """Run multiple Sketchfab queries and merge results (deduplicated by uid).

    Used by the subject-accuracy gate when the primary hero doesn't match
    the requested subject.  Running 3-5 query variations ("porsche 911",
    "porsche", "911 car", "sports car porsche") massively improves the
    chance of finding a real subject-matching model when one exists.

    Returns candidates sorted by score across all queries, capped at
    ``top_n``.  Preserves per-query telemetry via [SKETCHFAB] log lines
    from the underlying ``search_models`` calls.
    """
    subject_lower = (subject or "").strip().lower()
    queries: list[str] = []
    if subject_lower:
        queries.append(subject_lower)
    for q in query_variations or []:
        if not q:
            continue
        ql = str(q).strip().lower()
        if ql and ql not in queries:
            queries.append(ql)

    if not queries:
        return []

    merged: dict[str, dict] = {}
    for q in queries:
        try:
            print(f"[SKETCHFAB_MULTI] q={q!r}", flush=True)
            hits = search_models(q, limit=top_n, animated=animated)
            for h in hits:
                uid = h.get("uid")
                if not uid:
                    continue
                if uid in merged:
                    # keep the higher-scoring record
                    if h.get("score", 0) > merged[uid].get("score", 0):
                        merged[uid] = h
                else:
                    merged[uid] = h
            print(
                f"[SKETCHFAB_MULTI] q={q!r} -> {len(hits)} hits "
                f"(merged total={len(merged)})",
                flush=True,
            )
        except Exception as e:
            print(f"[SKETCHFAB_MULTI] q={q!r} failed (non-fatal): {e}", flush=True)

    ranked = sorted(merged.values(), key=lambda h: h.get("score", 0), reverse=True)
    return ranked[:top_n]


# ═══════════════════════════════════════════════════════════════════════════
# Download
# ═══════════════════════════════════════════════════════════════════════════

def _project_root() -> Path:
    """Backend project root (blender-studio-backend/)."""
    return Path(__file__).resolve().parents[2]


def _cache_dir() -> Path:
    """
    Local cache directory for downloaded Sketchfab assets, anchored to
    the backend project root so the path is valid regardless of the
    FastAPI worker's CWD.
    """
    return _project_root() / "assets" / "cache" / "models" / "sketchfab"


def _download_url(uid: str) -> dict | None:
    """
    Hit /models/{uid}/download to get a short-lived signed URL for the
    glTF (or other) archive. Returns the JSON body or None on failure.
    """
    if not is_available():
        return None
    try:
        r = requests.get(
            f"{API_BASE}/models/{uid}/download",
            headers=_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        return _json_from_response(r) or None
    except Exception as e:
        print(f"[SKETCHFAB] download URL fetch failed for {uid}: {e}", flush=True)
        return None


def _stream_to_file(url: str, dest: Path) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, stream=True, timeout=DEFAULT_DOWNLOAD_TIMEOUT) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        f.write(chunk)
        size = dest.stat().st_size if dest.exists() else 0
        print(
            f"[SKETCHFAB] downloaded {dest.name} ({size:,} bytes)",
            flush=True,
        )
        return dest
    except Exception as e:
        print(f"[SKETCHFAB] file download failed {url} -> {dest}: {e}", flush=True)
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None


def _find_3d_model(directory: Path) -> Path | None:
    """
    Search a directory recursively for a usable 3D model file.
    Priority: .glb > .gltf > .fbx > .obj > .blend. On ties, prefer the
    largest file (usually the main mesh rather than a proxy).
    """
    for ext in (".glb", ".gltf", ".fbx", ".obj", ".blend"):
        matches = list(directory.rglob(f"*{ext}"))
        if matches:
            matches.sort(key=lambda p: p.stat().st_size, reverse=True)
            return matches[0]
    return None


def _extract_archive(archive_path: Path, target_dir: Path) -> Path | None:
    """
    Extract a downloaded glTF archive. Returns the absolute path to the
    .glb / .gltf (or other) 3D file, or None if extraction failed AND
    the archive wasn't actually a naked model file in disguise.

    Defensive cases handled:
      - Archive is a valid ZIP → extractall, then find the 3D file.
      - "Archive" is actually a naked .glb (some Sketchfab direct links) →
        detect magic bytes, rename to .glb in place.
      - Archive is HTML / empty / truncated → log and return None.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    # Sanity check before we try to unzip — zero-byte or HTML bodies are
    # a common Sketchfab failure mode that zipfile will choke on with a
    # noisier, less actionable error.
    try:
        size = archive_path.stat().st_size
    except OSError as e:
        print(f"[SKETCHFAB] archive missing: {archive_path} :: {e}", flush=True)
        return None
    if size == 0:
        print(f"[SKETCHFAB] archive is empty: {archive_path}", flush=True)
        return None

    try:
        with open(archive_path, "rb") as f:
            head = f.read(8)
    except OSError as e:
        print(f"[SKETCHFAB] cannot read archive header: {archive_path} :: {e}", flush=True)
        return None

    # Case A: naked GLB/GLTF that came through with a .zip filename.
    if head[:4] == b"glTF":
        renamed = archive_path.with_suffix(".glb")
        try:
            archive_path.replace(renamed)
            print(
                f"[SKETCHFAB] archive was actually a naked GLB — renamed to {renamed.name}",
                flush=True,
            )
            return renamed
        except OSError as e:
            print(f"[SKETCHFAB] could not rename naked GLB {archive_path}: {e}", flush=True)
            return None

    # Case B: HTML error page masquerading as an archive.
    if head[:1] == b"<":
        print(
            f"[SKETCHFAB] archive is HTML (likely an auth/quota error), not a model: "
            f"{archive_path}",
            flush=True,
        )
        return None

    # Case C: real ZIP — extract and find the 3D file.
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            names = zf.namelist()
            zf.extractall(target_dir)
    except (zipfile.BadZipFile, OSError) as e:
        print(f"[SKETCHFAB] archive extract failed {archive_path}: {e}", flush=True)
        return None

    print(
        f"[SKETCHFAB] extracted {len(names)} file(s) into {target_dir.name}: "
        f"{names[:5]}{'...' if len(names) > 5 else ''}",
        flush=True,
    )

    found = _find_3d_model(target_dir)
    if found is None:
        all_files = [p.name for p in target_dir.rglob("*") if p.is_file()][:20]
        print(
            f"[SKETCHFAB] no .glb/.gltf/.fbx/.obj/.blend found after extract. "
            f"Extracted files: {all_files}",
            flush=True,
        )
    return found


_ASSET_TYPE_KEYWORDS: dict[str, list[str]] = {
    "vehicle": ["car", "vehicle", "truck", "bus", "motorcycle", "bike", "sedan",
                "suv", "sports car", "race car", "van", "ambulance", "taxi"],
    "character": ["character", "human", "person", "man", "woman", "boy", "girl",
                  "warrior", "knight", "soldier", "robot", "humanoid", "anime"],
    "animal": ["dog", "cat", "horse", "bird", "fish", "whale", "shark", "dolphin",
               "lion", "tiger", "bear", "wolf", "fox", "deer", "rabbit", "elephant",
               "dragon", "dinosaur", "snake", "turtle", "frog", "monkey", "gorilla"],
    "building": ["building", "house", "skyscraper", "tower", "castle", "church",
                 "temple", "bridge", "architecture"],
    "prop": ["sword", "weapon", "furniture", "chair", "table", "lamp", "tool",
             "book", "bottle", "cup", "phone", "guitar"],
    "product": ["watch", "shoe", "bag", "jewelry", "ring", "headphone", "camera",
                "perfume", "sunglasses", "sneaker"],
    "environment": ["landscape", "terrain", "mountain", "forest", "city", "scene",
                    "island", "cave", "dungeon"],
}


def _classify_asset_type(query: str, tags: list[str], raw_meta: dict) -> str:
    """
    Classify a downloaded Sketchfab model into a type bucket that the
    asset resolver can route to the correct template slot.
    """
    search_text = " ".join([
        query,
        " ".join(tags),
        raw_meta.get("name", ""),
        raw_meta.get("description", "") or "",
    ]).lower()

    best_type = "prop"
    best_score = 0

    for asset_type, keywords in _ASSET_TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in search_text)
        if score > best_score:
            best_score = score
            best_type = asset_type

    return best_type


def _infer_scale_class(asset_type: str) -> str:
    """Map classified type to a reasonable default scale_class."""
    return {
        "vehicle": "large",
        "character": "medium",
        "animal": "medium",
        "building": "xlarge",
        "prop": "small",
        "product": "tiny",
        "environment": "xlarge",
    }.get(asset_type, "medium")


_SEARCH_CASCADE_EXPANSIONS: dict[str, list[str]] = {
    "eagle":     ["bald eagle", "eagle bird", "hawk", "bird of prey", "falcon", "bird animated"],
    "chef":      ["chef character", "cook character", "cooking person", "kitchen worker"],
    "tiger":     ["tiger animated", "bengal tiger", "big cat animated"],
    "lion":      ["lion animated", "african lion", "big cat"],
    "bear":      ["bear animated", "grizzly bear", "brown bear"],
    "fish":      ["fish animated", "tropical fish", "goldfish", "koi fish"],
    "snake":     ["snake animated", "cobra", "python snake"],
    "dragon":    ["dragon animated", "dragon creature", "wyvern"],
    "dinosaur":  ["dinosaur animated", "t-rex", "raptor"],
    "penguin":   ["penguin animated", "emperor penguin"],
    "frog":      ["frog animated", "tree frog", "toad"],
    "owl":       ["owl animated", "barn owl", "snowy owl"],
    "deer":      ["deer animated", "stag", "elk"],
    "wolf":      ["wolf animated", "grey wolf"],
    "fox":       ["fox animated", "red fox", "arctic fox"],
    "parrot":    ["parrot animated", "macaw", "cockatoo"],
    "octopus":   ["octopus animated", "squid", "octopus sea"],
    "crab":      ["crab animated", "lobster"],
    "butterfly": ["butterfly animated", "monarch butterfly", "moth"],
    "spider":    ["spider animated", "tarantula"],
    "alien":     ["alien character", "alien creature", "extraterrestrial"],
    "zombie":    ["zombie animated", "zombie character", "undead"],
    "pirate":    ["pirate character", "pirate captain"],
    "wizard":    ["wizard character", "mage", "wizard animated"],
    "princess":  ["princess character", "princess animated", "queen"],
    "knight":    ["knight animated", "medieval knight", "armor warrior"],
    "samurai":   ["samurai animated", "samurai warrior"],
    "ninja":     ["ninja animated", "ninja character", "shinobi"],
}

# Animals that should get a generic last-resort query
_ANIMAL_SUBJECTS = {
    "dog", "cat", "horse", "eagle", "fish", "bird", "tiger", "lion",
    "bear", "wolf", "deer", "fox", "frog", "snake", "dolphin", "whale",
    "monkey", "rabbit", "penguin", "owl", "parrot", "butterfly",
    "spider", "octopus", "crab", "cow", "pig", "chicken", "bee", "ant",
    "shark", "turtle", "gorilla", "elephant", "zebra", "giraffe",
}


def _build_search_cascade(query: str) -> list[str]:
    """Build a broadening search cascade for any subject."""
    q = query.lower().strip()
    queries = [q]

    # Standard variations
    queries.append(f"{q} 3d model")
    queries.append(f"{q} animated")

    # Subject-specific broadening
    extra = _SEARCH_CASCADE_EXPANSIONS.get(q, [])
    queries.extend(extra)

    # Also try individual words against expansions
    if not extra:
        for word in q.split():
            word_extra = _SEARCH_CASCADE_EXPANSIONS.get(word, [])
            if word_extra:
                queries.extend(word_extra)
                break

    # Generic animal fallback
    if q in _ANIMAL_SUBJECTS:
        queries.append(f"{q} animal 3d")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for cand in queries:
        if cand not in seen:
            seen.add(cand)
            unique.append(cand)

    return unique[:10]  # Max 10 queries


def fetch_model(
    query: str,
    *,
    max_face_count: int | None = 250_000,
    animated: bool | None = None,
    asset_role: str = "hero_model",
) -> dict | None:
    """
    Search Sketchfab, pick the best downloadable hit, download it, register
    it, and return an asset record. Returns None on any failure.

    The asset record has the same shape as PolyHaven records so the
    resolver / runtime can treat them interchangeably:
        {id, type, tags, path, source, license, ...}

    When the primary query fails, an aggressive broadening cascade tries
    up to 10 query variations so rare subjects (eagle, chef, etc.) have
    the best possible chance of finding a match.
    """
    if not is_available():
        print("[SKETCHFAB] skipped (no SKETCHFAB_API_TOKEN)", flush=True)
        return None

    print(
        f"[SKETCHFAB] searching for {asset_role}: {query!r} "
        f"(animated={animated}, max_faces={max_face_count})",
        flush=True,
    )

    # Build the full cascade upfront; we'll try each query until one works.
    cascade = _build_search_cascade(query)

    best = None
    best_query = query

    for i, q in enumerate(cascade):
        print(f"[SKETCHFAB] cascade {i + 1}/{len(cascade)}: {q!r}", flush=True)

        hits = search_models(
            q, limit=8, max_face_count=max_face_count, animated=animated,
        )
        if not hits and animated:
            hits = search_models(q, limit=8, max_face_count=max_face_count)

        if not hits:
            continue

        candidate = hits[0]

        # Relevance gate for hero picks
        if asset_role == "hero_model" and candidate["score"] < MINIMUM_HERO_SCORE:
            print(
                f"[SKETCHFAB]   score {candidate['score']} < {MINIMUM_HERO_SCORE} "
                f"for {candidate['name']!r} — trying next query",
                flush=True,
            )
            continue

        # Relevance gate for prop picks — prevents "seaweed query → Round
        # goby" style misfires that inject wrong-subject geometry into
        # the scene.  A prop without a confident subject match is worse
        # than no prop at all.
        if asset_role == "prop" and candidate["score"] < MINIMUM_PROP_SCORE:
            print(
                f"[SKETCHFAB]   skipping {candidate['name']!r} "
                f"(score={candidate['score']} < {MINIMUM_PROP_SCORE}) — "
                f"no confident match for prop query {q!r}",
                flush=True,
            )
            continue

        best = candidate
        best_query = q
        break

    if not best:
        print(
            f"[SKETCHFAB] ❌ all {len(cascade)} cascade queries exhausted for {query!r}",
            flush=True,
        )
        return None

    uid = best["uid"]
    started = time.time()

    print(
        f"[SKETCHFAB] best match: {best['name']!r} score={best['score']} "
        f"license={best['license']} faces={best['face_count']} "
        f"anims={best.get('animation_count', 0)} (from query={best_query!r})",
        flush=True,
    )

    dl_info = _download_url(uid)
    if not dl_info:
        return None

    # Sketchfab returns several flavours; prefer gltf (most portable),
    # fall back to source if needed.
    gltf_block = dl_info.get("gltf") or {}
    src_block = dl_info.get("source") or {}
    archive_url = gltf_block.get("url") or src_block.get("url")
    if not archive_url:
        print(f"[SKETCHFAB] no glTF/source URL in download response for {uid}", flush=True)
        return None

    cache_root = _cache_dir() / uid
    archive_path = cache_root / "model.zip"
    if not _stream_to_file(archive_url, archive_path):
        return None

    extracted = _extract_archive(archive_path, cache_root)
    if not extracted:
        return None

    # Post-extract sanity: confirm the 3D file is on disk and non-trivial.
    try:
        ext_size = extracted.stat().st_size
    except OSError:
        ext_size = 0
    if ext_size < 500:
        print(
            f"[SKETCHFAB] extracted file is suspiciously small "
            f"({ext_size} bytes): {extracted}",
            flush=True,
        )
        return None

    # Try to clean up the zip — keep only the extracted glTF tree.
    # (Only delete the zip if it still exists — _extract_archive may
    # have renamed it in place when it turned out to be a naked GLB.)
    try:
        if archive_path.exists() and archive_path.resolve() != extracted.resolve():
            archive_path.unlink()
    except OSError:
        pass

    # Store an absolute POSIX path so Blender (any CWD) can find it.
    abs_path = extracted.resolve()
    rel_path = abs_path.as_posix()
    print(
        f"[SKETCHFAB] final model path: {rel_path} ({ext_size:,} bytes)",
        flush=True,
    )
    raw_meta = best["raw"] or {}
    tags = []
    for tag in raw_meta.get("tags", []) or []:
        if isinstance(tag, dict) and tag.get("name"):
            tags.append(str(tag["name"]))
        elif isinstance(tag, str):
            tags.append(tag)
    for cat in raw_meta.get("categories", []) or []:
        if isinstance(cat, dict) and cat.get("name"):
            tags.append(str(cat["name"]))

    # Classify what kind of 3D asset this is so the resolver can route it
    classified_type = _classify_asset_type(query, tags, raw_meta)
    scale_class = _infer_scale_class(classified_type)
    has_animations = int(best.get("animation_count", 0)) > 0

    record = {
        "id":            f"sketchfab_{uid}",
        "type":          classified_type,
        "tags":          tags,
        "path":          rel_path,
        "source":        "sketchfab",
        "license":       best["license"],
        "name":          best["name"],
        "face_count":    best["face_count"],
        "query":         query,
        "scale_class":   scale_class,
        "has_animation": has_animations,
        "is_rigged":     has_animations,  # animation implies rig for most models
        "species":       _infer_species(query, tags),
    }
    # Registry write is best-effort — a corrupt registry file (BOM,
    # stray bytes, etc.) must NEVER throw away a fully downloaded model
    # that's already sitting on disk. We log and keep going so the
    # caller still receives the record.
    try:
        upsert_asset("models", record)
    except Exception as reg_err:
        print(
            f"[SKETCHFAB] WARNING: registry upsert failed "
            f"({type(reg_err).__name__}: {reg_err}) — keeping downloaded "
            f"record: {rel_path}",
            flush=True,
        )

    elapsed = time.time() - started
    print(
        f"[SKETCHFAB] fetched uid={uid} | name={best['name']!r} | "
        f"type={classified_type} | scale={scale_class} | "
        f"animated={has_animations} | license={best['license']} | {elapsed:.2f}s",
        flush=True,
    )
    return record


def _infer_species(query: str, tags: list[str]) -> str | None:
    """Try to detect the species from query and tags for character routing."""
    text = f"{query} {' '.join(tags)}".lower()
    species_list = [
        "cat", "dog", "horse", "bird", "fish", "whale", "shark", "dolphin",
        "lion", "tiger", "bear", "wolf", "fox", "deer", "rabbit", "elephant",
        "dragon", "dinosaur", "monkey", "gorilla", "turtle", "frog", "snake",
    ]
    for sp in species_list:
        if sp in text:
            return sp
    # Check for generic human/character
    human_words = ["human", "person", "man", "woman", "boy", "girl", "character"]
    for hw in human_words:
        if hw in text:
            return "human"
    return None
