from __future__ import annotations

"""
asset_fetcher.py
================
Top-level fallback layer that fills in any assets the resolver could not
find in the local registry. Two providers are supported:

  - PolyHaven  (HDRIs + texture sets)
  - Sketchfab  (downloadable 3D models, CC0 / CC-BY only)

For each missing asset role, we ask the LLM (via
``asset_query_generator``) for a ranked list of concrete search queries
and try each in turn until one returns a usable hit. If everything
fails, the role is recorded in the ``skipped`` report and the pipeline
continues — the resolver will pick a sensible default from whatever
remains.
"""

from pathlib import Path
from typing import Any

from functools import partial

from .polyhaven_fetcher import fetch_hdri, fetch_texture_set
from .sketchfab_fetcher import fetch_model, is_available as sketchfab_available
from .asset_query_generator import generate_asset_queries, AssetQuerySet

# Round 4: Hybrid asset pipeline — Objaverse + AI generation fallback.
# Both imports are optional so the rest of the pipeline keeps working if
# the new modules or their deps (objaverse, gradio_client, requests+key)
# aren't installed.
try:
    from .objaverse_fetcher import (
        fetch_hero_from_objaverse,
        is_available as objaverse_available,
    )
    _HAS_OBJAVERSE = True
except Exception as _e:  # pragma: no cover
    print(f"[ASSET_FETCH] objaverse_fetcher unavailable: {_e}", flush=True)
    fetch_hero_from_objaverse = None  # type: ignore
    objaverse_available = lambda: False  # type: ignore
    _HAS_OBJAVERSE = False

try:
    from .ai_generator import generate_ai_model
    _HAS_AI_GEN = True
except Exception as _e:  # pragma: no cover
    print(f"[ASSET_FETCH] ai_generator unavailable: {_e}", flush=True)
    generate_ai_model = None  # type: ignore
    _HAS_AI_GEN = False


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SKETCHFAB_CACHE = _PROJECT_ROOT / "assets" / "cache" / "models" / "sketchfab"
_CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "curated_assets.json"


# ═══════════════════════════════════════════════════════════════════════════
# Curated asset registry — tested models bypass Objaverse search entirely
# ═══════════════════════════════════════════════════════════════════════════

_curated_cache: dict | None = None


def _load_curated() -> dict:
    """Load and cache the curated asset registry."""
    global _curated_cache
    if _curated_cache is not None:
        return _curated_cache
    import json
    if not _CURATED_PATH.exists():
        _curated_cache = {}
        return _curated_cache
    try:
        with open(_CURATED_PATH, encoding="utf-8") as f:
            _curated_cache = json.load(f)
    except Exception as e:
        print(f"[CURATED] failed to load {_CURATED_PATH}: {e}", flush=True)
        _curated_cache = {}
    return _curated_cache


def _check_curated_assets(subject: str) -> dict | None:
    """Check if we have a tested model for this subject.

    Returns a dict with 'type' (local/sketchfab/objaverse) and the
    corresponding key/uid, or None if no curated entry exists.
    """
    if not subject:
        return None
    curated = _load_curated()
    if not curated:
        return None

    subject_lower = subject.lower().strip()

    # Search actionable categories (skip _meta and needs_curation)
    for category in ("vehicles", "characters", "objects"):
        entries = curated.get(category, {})
        if not isinstance(entries, dict):
            continue
        if subject_lower in entries:
            entry = entries[subject_lower]
            if entry.get("use_local"):
                print(
                    f"[CURATED] matched {subject!r} -> local asset "
                    f"{entry['local_key']!r}",
                    flush=True,
                )
                return {"type": "local", "key": entry["local_key"]}
            elif entry.get("use_sketchfab"):
                print(
                    f"[CURATED] matched {subject!r} -> sketchfab "
                    f"{entry['sketchfab_uid']!r}",
                    flush=True,
                )
                return {"type": "sketchfab", "uid": entry["sketchfab_uid"]}
            elif entry.get("objaverse_uid"):
                print(
                    f"[CURATED] matched {subject!r} -> objaverse "
                    f"{entry['objaverse_uid']!r}",
                    flush=True,
                )
                return {"type": "objaverse", "uid": entry["objaverse_uid"]}

    # Check needs_curation (just logs, no override)
    needs = curated.get("needs_curation", {})
    if isinstance(needs, dict) and subject_lower in needs:
        notes = needs[subject_lower].get("notes", "")
        print(
            f"[CURATED] {subject!r} needs curation — using search fallback"
            + (f" ({notes})" if notes else ""),
            flush=True,
        )

    return None


def _fetch_curated_sketchfab(uid: str, subject: str) -> dict | None:
    """Download a specific Sketchfab model by UID (curated path).

    Reuses the Sketchfab fetcher's download infrastructure but skips
    the search step entirely — we already know exactly which model we want.
    """
    if not sketchfab_available():
        print("[CURATED] sketchfab unavailable, cannot fetch curated UID", flush=True)
        return None
    try:
        from .sketchfab_fetcher import (
            _download_url,
            _stream_to_file,
            _extract_archive,
            _cache_dir,
        )
    except ImportError as e:
        print(f"[CURATED] sketchfab internals not importable: {e}", flush=True)
        return None

    dl_info = _download_url(uid)
    if not dl_info:
        print(f"[CURATED] sketchfab download URL failed for uid={uid}", flush=True)
        return None

    gltf_block = dl_info.get("gltf") or {}
    src_block = dl_info.get("source") or {}
    archive_url = gltf_block.get("url") or src_block.get("url")
    if not archive_url:
        print(f"[CURATED] no download URL in response for uid={uid}", flush=True)
        return None

    cache_root = _cache_dir() / uid
    archive_path = cache_root / "model.zip"

    # Check if already cached
    from .sketchfab_fetcher import _find_3d_model
    existing = _find_3d_model(cache_root) if cache_root.exists() else None
    if existing and existing.stat().st_size > 500:
        abs_path = existing.resolve().as_posix()
        print(f"[CURATED] sketchfab cache hit: {abs_path}", flush=True)
    else:
        if not _stream_to_file(archive_url, archive_path):
            return None
        extracted = _extract_archive(archive_path, cache_root)
        if not extracted:
            return None
        abs_path = extracted.resolve().as_posix()
        # Clean up zip
        try:
            if archive_path.exists() and archive_path.resolve().as_posix() != abs_path:
                archive_path.unlink()
        except OSError:
            pass

    print(f"[CURATED] sketchfab fetched: uid={uid} -> {abs_path}", flush=True)
    return {
        "id":            f"sketchfab_{uid}",
        "type":          "character",
        "tags":          [subject],
        "path":          abs_path,
        "source":        "sketchfab",
        "source_uid":    uid,
        "license":       "unknown",
        "name":          subject,
        "face_count":    0,
        "query":         subject,
        "scale_class":   "medium",
        "has_animation": True,
        "is_rigged":     True,
        "species":       None,
    }


def _salvage_cached_model(query: str, role: str) -> dict | None:
    """
    Last-resort rescue: if a fetch raised a BOM/JSON error but the
    download actually finished and the 3D file is on disk, return a
    minimal record so the pipeline still gets its model.

    Scans ``assets/cache/models/sketchfab`` for the most recently
    modified .glb / .gltf / .fbx / .obj / .blend file and constructs a
    minimal asset record around it.
    """
    if not _SKETCHFAB_CACHE.exists():
        return None
    candidates: list[Path] = []
    for ext in (".glb", ".gltf", ".fbx", ".obj", ".blend"):
        candidates.extend(_SKETCHFAB_CACHE.rglob(f"*{ext}"))
    candidates = [p for p in candidates if p.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    best = candidates[0]
    print(
        f"[ASSET_FETCH] salvaging cached download for {role} q={query!r}: "
        f"{best}",
        flush=True,
    )
    q_lower = query.lower()
    return {
        "id":            f"sketchfab_cached_{best.parent.name}",
        "type":          "animal" if any(
            w in q_lower for w in ("dog", "cat", "horse", "bird", "fish", "bear")
        ) else "character",
        "tags":          [w for w in q_lower.split() if w],
        "path":          best.resolve().as_posix(),
        "source":        "sketchfab",
        "license":       "unknown",
        "name":          query,
        "face_count":    0,
        "query":         query,
        "scale_class":   "medium",
        "has_animation": True,
        "is_rigged":     True,
        "species":       None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Asset-role hints — determines whether we request animated models
# ═══════════════════════════════════════════════════════════════════════════

_ANIMATED_ROLES = {"character", "animal", "humanoid"}

# Vehicle-subject detection (Round 9 Pillar 1B). Vehicles on Sketchfab
# are almost never rigged/animated — if we insist on animated=True we
# immediately fall out of relevance and fetch stops returning cars at
# all. Detect vehicle subjects and bypass the animation requirement so
# the procedural vehicle animator can drive them instead.
_VEHICLE_SUBJECT_WORDS = (
    "car", "vehicle", "truck", "bus", "van", "motorcycle", "motorbike",
    "bike", "scooter", "suv", "coupe", "sedan", "hatchback", "pickup",
    "supercar", "sports car", "race car", "ferrari", "lamborghini",
    "porsche", "bmw", "audi", "mustang", "corvette", "tesla",
    "tank", "plane", "airplane", "helicopter", "boat", "ship", "train",
)


def _is_vehicle_subject(scene_plan: dict) -> bool:
    """True iff the scene's focal subject looks like a vehicle."""
    subject = str(
        scene_plan.get("focal_subject")
        or scene_plan.get("subject")
        or ""
    ).lower()
    family = str(scene_plan.get("scene_family") or "").lower()
    if family == "car_hero":
        return True
    return any(w in subject for w in _VEHICLE_SUBJECT_WORDS)


def _needs_animation(scene_plan: dict) -> bool:
    """Should we prefer animated models for this scene?"""
    # Vehicles override: never require animation — rigged Sketchfab
    # cars are vanishingly rare and procedural vehicle motion handles
    # driving forward + wheel spin just fine.
    if _is_vehicle_subject(scene_plan):
        return False

    subject = str(scene_plan.get("focal_subject", "")).lower()
    family = str(scene_plan.get("scene_family", "")).lower()
    action = str(scene_plan.get("animation_mode", "")).lower()

    # If the action suggests motion, prefer animated
    if action and action not in ("idle", "static", "still", "none"):
        return True
    # Character/animal families should try animated
    if family in ("character_stage", "street_scene", "ocean_scene"):
        return True
    # Check if subject itself is a living thing
    living_words = [
        "dog", "cat", "person", "human", "character", "animal", "fish",
        "whale", "shark", "dolphin", "bird", "robot", "dancer", "warrior",
    ]
    return any(w in subject for w in living_words)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _try_queries(fetch_fn, queries: list[str], role: str, report: dict) -> dict | None:
    """
    Try each query in order. The first one that produces a record wins.
    Records are returned as-is; failures are logged into ``report``.
    """
    for q in queries:
        if not q:
            continue
        try:
            record = fetch_fn(q)
        except Exception as e:
            print(f"[ASSET_FETCH] {role} fetch raised for q={q!r}: {e}", flush=True)
            record = None
            # BOM-aware salvage: if the failure was a JSON/BOM crash but
            # the 3D file is already sitting in the sketchfab cache,
            # reuse it rather than discarding the whole download.
            err_text = str(e).lower()
            if "bom" in err_text or "utf-8-sig" in err_text or "utf-8" in err_text:
                salvaged = _salvage_cached_model(q, role)
                if salvaged:
                    record = salvaged
        if record:
            report["fetched"].append({"role": role, "query": q, "id": record.get("id")})
            return record
    report["skipped"].append({"role": role, "tried": queries})
    return None


def _build_query_set(manifest: dict) -> AssetQuerySet:
    """
    Pull the scene plan + directorial manifest off the manifest dict and
    ask the query generator for concrete provider queries.
    """
    scene_plan = manifest.get("scene_plan") or {}
    directorial_manifest = manifest.get("directorial_manifest") or None
    return generate_asset_queries(scene_plan, directorial_manifest)


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

_GENERIC_SUBJECT_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "with", "at",
    "running", "walking", "flying", "swimming", "sitting", "standing",
    "park", "city", "street", "forest", "field", "beach", "ocean", "river",
    "scene", "video", "animation", "shot", "model",
}


# Broader-subject fallbacks keyed by specific subject → cascade of related
# queries. When the primary LLM-generated queries return nothing, we try
# these in order of specificity so a missing "bald eagle" asset falls
# through "eagle" → "bird of prey" → "hawk" → "bird" before giving up.
_BROADER_SUBJECT_FALLBACKS: dict[str, list[str]] = {
    "eagle":     ["eagle", "bald eagle", "eagle bird", "bird of prey", "hawk", "falcon", "bird"],
    "hawk":      ["hawk", "falcon", "bird of prey", "eagle", "bird"],
    "falcon":    ["falcon", "hawk", "bird of prey", "eagle", "bird"],
    "owl":       ["owl", "bird of prey", "bird"],
    "parrot":    ["parrot", "macaw", "tropical bird", "bird"],
    "raven":     ["raven", "crow", "black bird", "bird"],
    "crow":      ["crow", "raven", "black bird", "bird"],
    "bird":      ["bird", "sparrow", "pigeon", "dove"],
    "robot":     ["robot", "robot character", "humanoid robot", "mech", "android"],
    "android":   ["android", "robot", "humanoid robot", "mech"],
    "mech":      ["mech", "mecha", "robot", "humanoid robot"],
    "dragon":    ["dragon", "wyvern", "flying dragon", "serpent"],
    "dog":       ["dog", "puppy", "canine"],
    "cat":       ["cat", "feline", "kitten"],
    "horse":     ["horse", "stallion", "mare", "pony"],
    "wolf":      ["wolf", "grey wolf", "canine"],
    "fox":       ["fox", "red fox", "canine"],
    "bear":      ["bear", "grizzly bear", "brown bear"],
    "lion":      ["lion", "big cat", "feline"],
    "tiger":     ["tiger", "bengal tiger", "big cat", "feline"],
    "cheetah":   ["cheetah", "big cat", "feline", "cat"],
    "leopard":   ["leopard", "big cat", "feline", "cat"],
    "panther":   ["panther", "big cat", "feline", "cat"],
    "jaguar":    ["jaguar", "big cat", "feline", "cat"],
    "elephant":  ["elephant", "african elephant", "mammal"],
    "dolphin":   ["dolphin", "bottlenose dolphin", "marine mammal"],
    "whale":     ["whale", "humpback whale", "marine mammal"],
    "shark":     ["shark", "great white shark", "fish"],
    "dinosaur":  ["dinosaur", "t-rex", "tyrannosaurus", "raptor", "prehistoric"],
    "t-rex":     ["t-rex", "tyrannosaurus rex", "dinosaur", "prehistoric"],
    "raptor":    ["raptor", "velociraptor", "dinosaur", "prehistoric"],
    "triceratops": ["triceratops", "dinosaur", "prehistoric"],
    "gorilla":   ["gorilla", "ape", "primate"],
    "monkey":    ["monkey", "primate", "ape"],
    "deer":      ["deer", "stag", "elk", "buck"],
    "snake":     ["snake", "serpent", "cobra", "python reptile"],
    "crocodile": ["crocodile", "alligator", "reptile"],
    "frog":      ["frog", "toad", "amphibian"],
    "penguin":   ["penguin", "arctic bird", "bird"],
    "flamingo":  ["flamingo", "tropical bird", "bird"],
    "butterfly": ["butterfly", "moth", "insect"],
}


def _broader_hero_queries(subject: str, already_tried: list[str]) -> list[str]:
    """
    Build a cascade of broader fallback queries for a missing hero asset.
    Pulls from _BROADER_SUBJECT_FALLBACKS keyed on whichever word in the
    subject we recognise; skips queries already attempted.
    """
    subject = (subject or "").strip().lower()
    if not subject:
        return []
    tried_lower = {(q or "").strip().lower() for q in (already_tried or [])}
    candidates: list[str] = []

    # Match each recognised word in the subject (so "bald eagle" hits "eagle",
    # "robot dog" hits both "robot" and "dog" — robot first since it's the
    # primary noun in that phrase).
    for word in subject.split():
        word = word.strip(".,!?:;\"'`()").lower()
        if not word:
            continue
        if word in _BROADER_SUBJECT_FALLBACKS:
            candidates.extend(_BROADER_SUBJECT_FALLBACKS[word])

    # Also expose the raw subject itself — searching the full phrase
    # sometimes wins when the LLM query rewrite was too creative.
    candidates.append(subject)

    dedup: list[str] = []
    seen: set[str] = set()
    for q in candidates:
        key = (q or "").strip().lower()
        if not key or key in seen or key in tried_lower:
            continue
        seen.add(key)
        dedup.append(q)
    return dedup


def _existing_hero_matches_subject(existing_models: Any, subject: str) -> bool:
    """
    Decide whether the already-resolved models include something that
    actually matches the user's subject. We refuse to "count" a default
    template asset (cat, ferrari, whale, etc.) as a hero for an
    arbitrary prompt — otherwise ``has_hero_model`` short-circuits the
    Sketchfab search and the user never gets the robot they asked for.

    A model "matches" if the subject literally appears in its name/path,
    or any meaningful subject word (length > 2, not a stopword) appears
    in its name/path/tags.
    """
    if not subject:
        # No subject to compare against — fall back to the old behaviour
        # so we don't break tests/templates that intentionally pre-seed
        # the manifest with a specific asset.
        if isinstance(existing_models, dict):
            for bucket in ("characters", "vehicles", "cars", "products", "environments"):
                if existing_models.get(bucket):
                    return True
            return False
        return bool(existing_models)

    def _iter_models() -> list[dict]:
        if isinstance(existing_models, dict):
            out: list[dict] = []
            for bucket_list in existing_models.values():
                if isinstance(bucket_list, list):
                    out.extend(m for m in bucket_list if isinstance(m, dict))
            return out
        if isinstance(existing_models, list):
            return [m for m in existing_models if isinstance(m, dict)]
        return []

    subject_words = [
        w for w in subject.split()
        if len(w) > 2 and w not in _GENERIC_SUBJECT_WORDS
    ]
    # Fallback: if every word was generic (unlikely), still use the
    # raw subject string.
    if not subject_words:
        subject_words = [subject]

    for model in _iter_models():
        haystack = " ".join([
            str(model.get("name", "")),
            str(model.get("local_path", "")),
            str(model.get("path", "")),
            str(model.get("query", "")),
            " ".join(str(t) for t in (model.get("tags") or []) if isinstance(t, str)),
        ]).lower()
        if subject and subject in haystack:
            print(
                f"[ASSET_FETCH] existing hero matches subject "
                f"({subject!r} in {model.get('name') or model.get('path')!r})",
                flush=True,
            )
            return True
        for word in subject_words:
            if word in haystack:
                print(
                    f"[ASSET_FETCH] existing hero partial-matches subject "
                    f"(word {word!r} in {model.get('name') or model.get('path')!r})",
                    flush=True,
                )
                return True

    return False


_SEMANTIC_TYPES = {"animal", "character", "vehicle", "prop", "humanoid", "product"}


def _normalize_external_record(raw: dict, subject: str, query: str) -> dict:
    """Shape an Objaverse/AI record to look like the Sketchfab records
    downstream code already knows how to bucket and consume.

    If the raw record already carries a semantic `type` (animal, character,
    vehicle, prop), respect it — Objaverse's fetcher runs its own, richer
    classifier that factors in the Objaverse description. Only infer the
    type from the subject when the raw record didn't provide one or gave
    us a file-format string like 'glb'."""
    subject_l = (subject or "").lower()
    raw_type = str(raw.get("type") or "").lower().strip()

    if raw_type in _SEMANTIC_TYPES:
        rec_type = raw_type
    else:
        is_animal = any(
            w in subject_l for w in
            ("dog", "cat", "horse", "bird", "fish", "bear", "eagle",
             "pelican", "owl", "tiger", "lion", "wolf", "fox",
             "dolphin", "whale", "shark")
        )
        rec_type = "animal" if is_animal else "character"

    tags = [w for w in (query or subject_l).split() if w]
    src = raw.get("source") or "external"
    uid = raw.get("source_uid") or raw.get("uid")
    rec_id = f"{src}_{uid or _SANITIZE_ID(query or subject_l)}"
    # Preserve score so the post-filter's trusted-source bypass can
    # see that Objaverse already validated this match semantically.
    score = raw.get("score", 0)
    return {
        "id":            rec_id,
        "type":          rec_type,
        "tags":          tags,
        "path":          raw.get("path"),
        "source":        src,
        "source_uid":    uid,
        "uid":           uid,                # back-compat alias
        "score":         score,
        "license":       "unknown",
        "name":          raw.get("name") or subject or query,
        "description":   raw.get("description", ""),
        "face_count":    0,
        "query":         query or subject_l,
        "scale_class":   "medium",
        "has_animation": False,
        "is_rigged":     False,
        "species":       None,
        "file_format":   raw.get("file_format", "glb"),
    }


def _SANITIZE_ID(s: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_") or "asset"


def _try_objaverse_hero(subject: str, hero_queries: list[str], report: dict) -> dict | None:
    """Priority layer between curated and Sketchfab. Tries the subject
    first, then each hero query, until one produces a download."""
    if not _HAS_OBJAVERSE:
        print(
            "[ASSET_FETCH] objaverse skipped: _HAS_OBJAVERSE=False "
            "(module failed to import at boot — restart backend after "
            "`pip install objaverse`)",
            flush=True,
        )
        return None
    if not objaverse_available():
        print(
            "[ASSET_FETCH] objaverse skipped: objaverse_available()=False "
            "(objaverse package not importable in this process)",
            flush=True,
        )
        return None
    if fetch_hero_from_objaverse is None:
        print(
            "[ASSET_FETCH] objaverse skipped: fetch_hero_from_objaverse is None",
            flush=True,
        )
        return None

    candidates: list[str] = []
    if subject:
        candidates.append(subject)
    for q in hero_queries or []:
        if q and q.lower() not in {c.lower() for c in candidates}:
            candidates.append(q)

    for q in candidates:
        try:
            raw = fetch_hero_from_objaverse(q)
        except Exception as e:
            print(f"[ASSET_FETCH] objaverse raised for q={q!r}: {e}", flush=True)
            raw = None
        if raw and raw.get("path"):
            normalized = _normalize_external_record(raw, subject, q)
            # Carry Blender-side fallback candidates through to the manifest
            # so render_from_manifest can iterate if the primary fails
            # mesh validation (flat card, placeholder stub).
            if raw.get("hero_candidates"):
                normalized["hero_candidates"] = raw["hero_candidates"]
            report["fetched"].append({
                "role": "hero_model_objaverse",
                "query": q,
                "id": normalized.get("id"),
            })
            print(f"[ASSET_FETCH] objaverse HIT q={q!r} -> {normalized['path']}", flush=True)
            return normalized

    print(f"[ASSET_FETCH] objaverse MISS for subject={subject!r}", flush=True)
    return None


def _try_ai_generation(subject: str, report: dict) -> dict | None:
    """Last-resort AI generator. Only called after Sketchfab + broader
    cascade exhaust. Honors subject exactly (no query rewriting)."""
    if not _HAS_AI_GEN or generate_ai_model is None:
        return None
    if not subject:
        return None
    try:
        raw = generate_ai_model(subject)
    except Exception as e:
        print(f"[ASSET_FETCH] ai_generator raised: {e}", flush=True)
        raw = None
    if raw and raw.get("path"):
        normalized = _normalize_external_record(raw, subject, subject)
        report["fetched"].append({
            "role": "hero_model_ai_generated",
            "query": subject,
            "id": normalized.get("id"),
        })
        print(
            f"[ASSET_FETCH] AI-generated hero HIT subject={subject!r} "
            f"via {raw.get('source')} -> {normalized['path']}",
            flush=True,
        )
        return normalized
    print(f"[ASSET_FETCH] AI generation MISS for subject={subject!r}", flush=True)
    return None


def _append_model_record(resolved_assets: dict, record: dict) -> None:
    """Safely append a fetched model record regardless of models shape."""
    raw = resolved_assets.get("models")
    if isinstance(raw, dict):
        # Dict-shaped: flatten first, then append
        flat: list[dict] = []
        for bucket_list in raw.values():
            if isinstance(bucket_list, list):
                flat.extend(bucket_list)
        flat.append(record)
        resolved_assets["models"] = flat
    elif isinstance(raw, list):
        raw.append(record)
    else:
        resolved_assets["models"] = [record]


def fetch_missing_assets(template_name: str, resolved_assets: dict, manifest: dict) -> dict:
    """
    Fill any gaps in ``resolved_assets`` using the LLM-driven query
    generator + Sketchfab + PolyHaven. Always returns a complete report;
    never raises.
    """
    report: dict[str, list[Any]] = {"fetched": [], "skipped": []}
    template_name = (template_name or "").lower()

    # Prop fetching is globally disabled for now (signs / furniture were
    # cluttering scenes). Set manifest['_enable_prop_fetch']=True to turn
    # it back on once prop quality is solid.
    enable_prop_fetch = bool(manifest.get("_enable_prop_fetch"))

    query_set = _build_query_set(manifest)
    report["query_source"] = query_set.source
    if query_set.notes:
        report["query_notes"] = query_set.notes
    report["prop_fetch_enabled"] = enable_prop_fetch

    # ── Hero model: Sketchfab only (PolyHaven has no character models) ──
    scene_plan = manifest.get("scene_plan") or {}
    want_animated = _needs_animation(scene_plan)

    # Check if the resolver already picked a hero model that ACTUALLY
    # matches the requested subject. A bucket with items isn't enough —
    # a "robot" prompt used to see the template's default cat sitting
    # in `models.characters` and happily skip the Sketchfab search.
    # We now require the existing model's name/path/tags to contain at
    # least one meaningful word from the subject.
    existing_models = resolved_assets.get("models")
    scene_plan = manifest.get("scene_plan") or {}
    subject = str(
        scene_plan.get("focal_subject")
        or scene_plan.get("subject")
        or ""
    ).strip().lower()
    has_hero_model = _existing_hero_matches_subject(existing_models, subject)

    print(
        f"[ASSET_FETCH] hero check: has_hero_model={has_hero_model} "
        f"subject={subject!r} models_type={type(existing_models).__name__} "
        f"hero_queries={query_set.hero_model[:2] if query_set.hero_model else 'none'}",
        flush=True,
    )

    if not has_hero_model and query_set.hero_model:
        # ── Priority 0: Curated registry (tested, reliable models) ────
        curated_hit = _check_curated_assets(subject)
        if curated_hit:
            curated_record = None
            if curated_hit["type"] == "local":
                # Local asset — the resolver already has it in the manifest.
                # Signal to asset_agent that the local asset should be used
                # by NOT fetching anything external; the existing model in
                # resolved_assets.models.vehicles (etc.) will win.
                print(
                    f"[CURATED] local asset {curated_hit['key']!r} — "
                    f"skipping external fetch, resolver should already have it",
                    flush=True,
                )
                has_hero_model = True

                # Verify the local asset is actually still in resolved_assets.
                # The dedup layer may have already stripped it, leaving NO
                # vehicles → scenic_landscape fallback (the "Ferrari renders
                # mountain" bug). If missing, re-inject from asset registry.
                _curated_key = curated_hit["key"]
                _found_in_resolved = False
                if isinstance(existing_models, dict):
                    for _bkt in ("vehicles", "cars", "characters", "products", "props"):
                        for _item in (existing_models.get(_bkt) or []):
                            if not isinstance(_item, dict):
                                continue
                            _ip = str(_item.get("path") or _item.get("id") or "")
                            if _curated_key in _ip:
                                _found_in_resolved = True
                                break
                        if _found_in_resolved:
                            break

                if not _found_in_resolved:
                    print(
                        f"[CURATED] WARNING: {_curated_key!r} not found in "
                        f"resolved_assets — injecting from local disk",
                        flush=True,
                    )
                    try:
                        import os as _os_inj
                        from pathlib import Path as _Path_inj
                        _root = _Path_inj(__file__).resolve().parents[2]
                        # Search common local asset paths
                        _candidate_paths = [
                            _root / "assets" / "cache" / "models" / "vehicles" / f"{_curated_key}.blend",
                            _root / "assets" / "cache" / "models" / "vehicles" / f"{_curated_key}.glb",
                            _root / "assets" / "cache" / "models" / "characters" / f"{_curated_key}.blend",
                            _root / "assets" / "cache" / "models" / "characters" / f"{_curated_key}.glb",
                        ]
                        _found_path = None
                        for _cp in _candidate_paths:
                            if _cp.exists():
                                _found_path = str(_cp)
                                break

                        if _found_path and isinstance(existing_models, dict):
                            _local_entry = {
                                "id": _curated_key,
                                "name": _curated_key,
                                "path": _found_path,
                                "source": "local",
                                "type": "vehicle",
                            }
                            _target_bucket = "vehicles"
                            existing_models.setdefault(
                                _target_bucket, []
                            ).append(_local_entry)
                            print(
                                f"[CURATED] injected {_curated_key!r} into "
                                f"models.{_target_bucket} from {_found_path}",
                                flush=True,
                            )
                        elif not _found_path:
                            print(
                                f"[CURATED] cannot find {_curated_key!r} on disk",
                                flush=True,
                            )
                    except Exception as _inj_err:
                        print(
                            f"[CURATED] injection failed: {_inj_err}",
                            flush=True,
                        )
            elif curated_hit["type"] == "sketchfab":
                curated_record = _fetch_curated_sketchfab(
                    curated_hit["uid"], subject
                )
            elif curated_hit["type"] == "objaverse":
                # Direct Objaverse UID download (skip search)
                if _HAS_OBJAVERSE:
                    try:
                        from .objaverse_fetcher import download_objaverse_model
                        path = download_objaverse_model(curated_hit["uid"])
                        if path:
                            curated_record = _normalize_external_record(
                                {
                                    "path": str(path),
                                    "name": subject,
                                    "source": "objaverse",
                                    "source_uid": curated_hit["uid"],
                                    "uid": curated_hit["uid"],
                                    "type": "character",
                                    "file_format": "glb",
                                },
                                subject, subject,
                            )
                    except Exception as e:
                        print(f"[CURATED] objaverse UID fetch failed: {e}", flush=True)

            if curated_record and curated_record.get("path"):
                _append_model_record(resolved_assets, curated_record)
                report["fetched"].append({
                    "role": "hero_model_curated",
                    "query": subject,
                    "id": curated_record.get("id"),
                })
                has_hero_model = True
                print(
                    f"[CURATED] hero resolved: {curated_record['path']}",
                    flush=True,
                )

    if not has_hero_model and query_set.hero_model:
        # ── Priority 1: Objaverse (local-scored, free, 800K models) ──
        # Verbose per-render tracing so a silent skip (e.g. backend was
        # started before `pip install objaverse`) is immediately visible
        # in the logs instead of being swallowed at module-load time.
        print(
            f"[ASSET_FETCH] >>> About to try Objaverse for subject={subject!r} "
            f"(_HAS_OBJAVERSE={_HAS_OBJAVERSE})",
            flush=True,
        )
        try:
            # Re-import defensively — if the module-load import silently
            # failed, a fresh import attempt here will surface the real
            # reason via the exception handler below instead of hiding
            # behind the _HAS_OBJAVERSE=False fast-path.
            from app.services.objaverse_fetcher import (
                fetch_hero_from_objaverse as _fetch_hero_from_objaverse,
                is_available as _objaverse_available,
            )
            print(
                f"[ASSET_FETCH] Objaverse module imported OK "
                f"(available={_objaverse_available()})",
                flush=True,
            )

            objaverse_hit = _try_objaverse_hero(
                subject, query_set.hero_model, report
            )
            print(
                f"[ASSET_FETCH] Objaverse returned: "
                f"{'HIT' if objaverse_hit else 'None'}",
                flush=True,
            )
            if objaverse_hit:
                _append_model_record(resolved_assets, objaverse_hit)
                has_hero_model = True
            else:
                print(
                    "[ASSET_FETCH] Objaverse returned None, "
                    "falling through to Sketchfab",
                    flush=True,
                )
        except Exception as _obj_e:
            import traceback as _tb
            print(
                f"[ASSET_FETCH] Objaverse EXCEPTION: {_obj_e}",
                flush=True,
            )
            _tb.print_exc()

    if not has_hero_model and query_set.hero_model:
        if sketchfab_available():
            # Vehicle override: prepend vehicle-specific queries so the
            # first Sketchfab attempts always look explicitly vehicular,
            # even if the LLM's hero phrasing was vague ("red fast").
            hero_queries = list(query_set.hero_model)
            if _is_vehicle_subject(scene_plan) and subject:
                vehicle_queries = [
                    subject,
                    f"{subject} 3d model",
                    f"{subject} car",
                    f"{subject} vehicle",
                ]
                seen: set[str] = set()
                merged: list[str] = []
                for q in vehicle_queries + hero_queries:
                    k = q.strip().lower()
                    if k and k not in seen:
                        seen.add(k)
                        merged.append(q)
                hero_queries = merged
                print(
                    f"[ASSET_FETCH] vehicle override: hero_queries[:4]={hero_queries[:4]}",
                    flush=True,
                )

            fetch_fn = partial(
                fetch_model,
                animated=want_animated,
                asset_role="hero_model",
            )
            model = _try_queries(
                fetch_fn,
                hero_queries,
                role="hero_model",
                report=report,
            )
            # Broader-subject cascade: if none of the primary queries hit,
            # try progressively broader searches (e.g. eagle → bird of
            # prey → bird) before giving up. Keeps the scene from
            # rendering with no hero just because the LLM's first-round
            # query phrasing returned zero Sketchfab matches.
            if not model:
                broader = _broader_hero_queries(subject, hero_queries)
                if broader:
                    print(
                        f"[ASSET_FETCH] primary hero queries exhausted — "
                        f"broadening with {broader[:6]}",
                        flush=True,
                    )
                    model = _try_queries(
                        fetch_fn,
                        broader,
                        role="hero_model_broadened",
                        report=report,
                    )
            if model:
                _append_model_record(resolved_assets, model)
            else:
                # ── Priority 3 (last resort): AI 3D generation ──
                # Sketchfab primary + broadened cascade both failed. Try
                # generating a model from scratch (Meshy → HuggingFace).
                ai_hit = _try_ai_generation(subject, report)
                if ai_hit:
                    _append_model_record(resolved_assets, ai_hit)
                else:
                    print(
                        f"[ASSET_FETCH] HERO asset could NOT be resolved for "
                        f"subject={subject!r} — scene will render without hero",
                        flush=True,
                    )
                    report.setdefault("hero_missing", True)
        else:
            # Sketchfab unavailable — Objaverse already tried above; last
            # shot at getting a hero is the AI generator.
            ai_hit = _try_ai_generation(subject, report)
            if ai_hit:
                _append_model_record(resolved_assets, ai_hit)
            else:
                report["skipped"].append({
                    "role": "hero_model",
                    "reason": "sketchfab_unavailable",
                    "tried": query_set.hero_model,
                })

    # ── HDRI: PolyHaven ──
    if not resolved_assets.get("hdris") and query_set.environment:
        hdri = _try_queries(
            fetch_hdri,
            query_set.environment,
            role="environment_hdri",
            report=report,
        )
        if hdri:
            resolved_assets.setdefault("hdris", []).append(hdri)

    # ── Ground texture: PolyHaven ──
    if not resolved_assets.get("textures") and query_set.ground_texture:
        tex = _try_queries(
            fetch_texture_set,
            query_set.ground_texture,
            role="ground_texture",
            report=report,
        )
        if tex:
            resolved_assets.setdefault("textures", []).append(tex)

    # ── Optional props: DISABLED by default in Round 13 ──
    # Prop fetching was cluttering scenes with wrong-subject downloads
    # (neon signs, furniture, frisbees) that the template never asked for.
    # Re-enable by setting manifest['_enable_prop_fetch']=True.
    hero_resolved_now = has_hero_model or bool(
        any(r.get("role") == "hero_model" for r in report.get("fetched", []))
    )
    if not enable_prop_fetch:
        if query_set.props:
            report["skipped"].append({
                "role": "prop",
                "reason": "prop_fetch_disabled",
                "tried": list(query_set.props),
            })
            print(
                f"[ASSET_FETCH] prop fetch skipped ({len(query_set.props)} queries) — "
                f"set manifest['_enable_prop_fetch']=True to re-enable",
                flush=True,
            )
    elif hero_resolved_now and query_set.props and sketchfab_available():
        for prop_query in query_set.props[:2]:  # cap at 2 props per shot
            try:
                prop = fetch_model(prop_query, asset_role="prop")
            except Exception as e:
                print(f"[ASSET_FETCH] prop fetch raised for q={prop_query!r}: {e}", flush=True)
                prop = None
            if prop:
                _append_model_record(resolved_assets, prop)
                report["fetched"].append({
                    "role": "prop",
                    "query": prop_query,
                    "id": prop.get("id"),
                })
            else:
                report["skipped"].append({"role": "prop", "tried": [prop_query]})

    # Ensure models is always a flat list for the agent to bucket later.
    # resolve_scene_assets returns models as dict; we flatten for consistency.
    raw_models = resolved_assets.get("models")
    if isinstance(raw_models, dict):
        flat = []
        for bucket_list in raw_models.values():
            if isinstance(bucket_list, list):
                flat.extend(bucket_list)
        resolved_assets["models"] = flat

    return {
        "ok": True,
        "resolved_assets": resolved_assets,
        "report": report,
    }
