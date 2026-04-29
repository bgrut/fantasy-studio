from __future__ import annotations

"""
curated_resolver.py
===================
Round 11 strategic pivot: curated asset library is Priority 1.

The old flow trusted Sketchfab search to return a good model for every
prompt. In practice that was a lottery — "dog" could return a Halloween
costume, "tiger" could return a weapon. The curated library is a small
(30-50 asset) hand-picked set stored locally with rich metadata. When a
prompt's subject matches a curated asset we use it directly; only when
nothing matches do we fall back to Sketchfab.

Public API
----------
- ``load_catalog()``                    -> dict with ``assets`` list
- ``search_curated_library(subject, asset_type=None, min_score=10)``
                                        -> best-match asset dict or None
- ``find_closest_curated_asset(subject, asset_type=None)``
                                        -> best-effort fallback (lower bar)
- ``resolve_hero_from_catalog(manifest)`` -> (asset_record, score) or (None, 0)
- ``asset_to_resolver_record(asset)``   -> shape used by resolve_scene_assets

All functions are side-effect free apart from a single
``print(...)`` for observability. A missing or malformed catalog file
is treated as "no curated assets available" — the caller then falls
back to the existing Sketchfab + registry pipeline unchanged.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_PATH = _PROJECT_ROOT / "assets" / "curated" / "catalog.json"


# ═══════════════════════════════════════════════════════════════════════════
# Catalog I/O
# ═══════════════════════════════════════════════════════════════════════════

def _catalog_path() -> Path:
    return _CATALOG_PATH


def load_catalog() -> dict:
    """
    Load and return the curated catalog. Tolerant of a missing file
    (returns an empty catalog) and a UTF-8 BOM (utf-8-sig).
    Never raises — errors surface as an empty catalog.
    """
    path = _catalog_path()
    if not path.exists():
        return {"version": 1, "assets": []}
    try:
        raw = path.read_text(encoding="utf-8-sig")
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"[CURATED] catalog load failed ({path}): {e}", flush=True)
        return {"version": 1, "assets": []}
    if not isinstance(data, dict):
        return {"version": 1, "assets": []}
    if not isinstance(data.get("assets"), list):
        data["assets"] = []
    return data


@lru_cache(maxsize=1)
def _cached_catalog() -> dict:
    """
    Per-process cache for the catalog. The catalog is small and rarely
    changes during a render session. Call ``invalidate_catalog_cache()``
    after a curation run to pick up new entries.
    """
    return load_catalog()


def invalidate_catalog_cache() -> None:
    _cached_catalog.cache_clear()


# ═══════════════════════════════════════════════════════════════════════════
# Category inference
# ═══════════════════════════════════════════════════════════════════════════
#
# We map the ``asset_type`` hint (from resolver / manifest) onto the
# coarser category buckets used in the curated library. The library uses
# five top-level categories: animal, vehicle, character, environment,
# prop. The resolver passes through a few synonyms.

_ASSET_TYPE_TO_CATEGORY: dict[str, str] = {
    "animal":      "animal",
    "character":   "character",
    "humanoid":    "character",
    "person":      "character",
    "vehicle":     "vehicle",
    "car":         "vehicle",
    "product":     "prop",
    "prop":        "prop",
    "building":    "environment",
    "environment": "environment",
}


def _normalize_category(asset_type: str | None) -> str | None:
    if not asset_type:
        return None
    return _ASSET_TYPE_TO_CATEGORY.get(asset_type.strip().lower())


# ═══════════════════════════════════════════════════════════════════════════
# Scoring
# ═══════════════════════════════════════════════════════════════════════════

_GENERIC_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "with", "at",
    "3d", "model", "rigged", "animated", "free", "low", "high", "poly",
    "scene", "video", "animation", "shot", "clip",
}


def _subject_tokens(subject: str) -> list[str]:
    toks = [w.strip().lower() for w in (subject or "").split()]
    return [w for w in toks if w and w not in _GENERIC_WORDS]


def _score_asset(asset: dict, subject: str, category: str | None) -> int:
    """
    Score a curated asset against the prompt's subject. Higher = better.

    The weighting matches the plan from the Round 11 spec:
      • keyword match       : 10 per match
      • subcategory in subj  : 15
      • category match       : 5
    """
    if not isinstance(asset, dict):
        return 0

    subj_lower = (subject or "").lower()
    subj_tokens = _subject_tokens(subj_lower)
    if not subj_tokens and not subj_lower:
        return 0

    score = 0
    keywords = [str(k).lower() for k in asset.get("keywords") or []]
    for kw in keywords:
        if not kw:
            continue
        if kw in subj_lower:
            score += 10
        elif any(kw in tok or tok in kw for tok in subj_tokens):
            score += 6

    subcat = str(asset.get("subcategory") or "").lower()
    if subcat and subcat in subj_lower:
        score += 15

    asset_cat = str(asset.get("category") or "").lower()
    if category and asset_cat == category:
        score += 5

    # Small tiebreakers so all-else-equal prefers animated + tested assets.
    if asset.get("tested"):
        score += 2
    if asset.get("animations"):
        score += 2

    return score


# ═══════════════════════════════════════════════════════════════════════════
# Public search API
# ═══════════════════════════════════════════════════════════════════════════

def search_curated_library(
    subject: str,
    asset_type: str | None = None,
    min_score: int = 10,
) -> dict | None:
    """
    Return the highest-scoring curated asset for ``subject``. Returns
    None when nothing clears ``min_score`` — callers should fall through
    to Sketchfab in that case.

    ``asset_type`` is an optional hint from the manifest
    (``animal`` / ``vehicle`` / ``character`` / ...). It boosts scores
    within the matching category but does not hard-filter.
    """
    catalog = _cached_catalog()
    assets = catalog.get("assets") or []
    if not assets:
        return None

    category = _normalize_category(asset_type)

    best = None
    best_score = 0
    for asset in assets:
        score = _score_asset(asset, subject, category)
        if score > best_score:
            best_score = score
            best = asset

    if best and best_score >= min_score:
        print(
            f"[CURATED] match for subject={subject!r} "
            f"type={asset_type!r} -> {best.get('id')!r} (score={best_score})",
            flush=True,
        )
        return best
    return None


def find_closest_curated_asset(
    subject: str,
    asset_type: str | None = None,
) -> dict | None:
    """
    Soft fallback: return the highest-scoring curated asset even when
    it doesn't clear the strict match threshold. Used when Sketchfab has
    also failed — better to render a curated cat for "tiger" than a
    mystery Sketchfab object that might be a sword.
    """
    catalog = _cached_catalog()
    assets = catalog.get("assets") or []
    if not assets:
        return None

    category = _normalize_category(asset_type)
    candidates: list[tuple[int, dict]] = []
    for asset in assets:
        score = _score_asset(asset, subject, category)
        candidates.append((score, asset))

    # Prefer same-category results first, even at low score.
    if category:
        cat_hits = [(s, a) for s, a in candidates
                    if str(a.get("category") or "").lower() == category]
        if cat_hits:
            cat_hits.sort(key=lambda pair: pair[0], reverse=True)
            score, asset = cat_hits[0]
            print(
                f"[CURATED] soft fallback (category={category}) -> "
                f"{asset.get('id')!r} (score={score})",
                flush=True,
            )
            return asset

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    if candidates:
        score, asset = candidates[0]
        if score > 0:
            print(
                f"[CURATED] soft fallback -> {asset.get('id')!r} (score={score})",
                flush=True,
            )
            return asset
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Shape adapter — convert a curated entry into resolver's record shape
# ═══════════════════════════════════════════════════════════════════════════

def asset_to_resolver_record(asset: dict) -> dict:
    """
    Convert a curated catalog entry into the record shape the rest of
    the pipeline expects (asset_fetcher, asset_resolver, templates).
    This lets the curated path drop straight into ``resolved_assets``
    with no special-case code downstream.
    """
    if not isinstance(asset, dict):
        return {}

    path = str(asset.get("path") or "")
    if path and not Path(path).is_absolute():
        # Curated metadata stores paths relative to project root for
        # portability. Upgrade to absolute so Blender (any CWD) works.
        abs_path = (_PROJECT_ROOT / path).resolve()
        path = abs_path.as_posix()

    category = str(asset.get("category") or "prop").lower()
    # Map curated category back to the resolver's "type" vocabulary.
    cat_to_type = {
        "animal":      "animal",
        "character":   "character",
        "vehicle":     "vehicle",
        "environment": "environment",
        "prop":        "prop",
    }
    type_ = cat_to_type.get(category, "prop")

    has_animations = bool(asset.get("animations"))

    return {
        "id":            str(asset.get("id") or "curated_asset"),
        "type":          type_,
        "tags":          list(asset.get("keywords") or []),
        "path":          path,
        "source":        "curated",
        "license":       str(asset.get("license") or "unknown"),
        "name":          str(asset.get("name") or asset.get("id") or "curated"),
        "face_count":    int(asset.get("face_count") or 0),
        "query":         "",
        "scale_class":   str(asset.get("scale_class") or "medium"),
        "has_animation": has_animations,
        "is_rigged":     bool(asset.get("has_armature") or has_animations),
        "species":       asset.get("subcategory"),
        # Pass curated metadata through so animation_ops can use it.
        "curated_meta":  asset,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator for asset_agent.py
# ═══════════════════════════════════════════════════════════════════════════

def resolve_hero_from_catalog(manifest: dict) -> tuple[dict | None, int]:
    """
    Inspect the manifest's scene plan and return a curated hero (as a
    resolver record) + its score, or (None, 0) if no match.

    Returned record is already in the shape ``resolve_scene_assets`` uses,
    so callers can drop it straight into ``resolved_assets.models``.
    """
    scene_plan = manifest.get("scene_plan") or {}
    subject = str(
        scene_plan.get("focal_subject")
        or scene_plan.get("subject")
        or manifest.get("topic")
        or ""
    ).strip()
    if not subject:
        return (None, 0)

    # Pull asset_type hint if the director already decided one.
    asset_type_hint: str | None = None
    for key in ("hero_asset_type", "asset_type"):
        v = manifest.get(key)
        if isinstance(v, str) and v.strip():
            asset_type_hint = v
            break

    match = search_curated_library(subject, asset_type=asset_type_hint)
    if match is None:
        return (None, 0)

    score = _score_asset(match, subject, _normalize_category(asset_type_hint))
    return (asset_to_resolver_record(match), score)


__all__ = [
    "load_catalog",
    "invalidate_catalog_cache",
    "search_curated_library",
    "find_closest_curated_asset",
    "asset_to_resolver_record",
    "resolve_hero_from_catalog",
]
