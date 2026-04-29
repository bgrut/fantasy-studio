"""
library_curator.py
==================
Auto-curate successful fetches into a rich-schema library.

Lives parallel to the existing keyword-indexed ``app/data/curated_assets.json``
(which remains untouched) as a list of rich entries at
``app/data/library.json``.  Every successful Objaverse/Sketchfab fetch
that passes the subject gate gets promoted here with metadata the
asset agent can query on later renders.

Public API:
    promote_to_curated(asset_path, subject, fetch_metadata, render_metadata) -> dict | None
    query_library(subject, visual_hints=None, category=None, limit=10) -> list
    mark_tested(asset_id) -> bool    (auto-called after 2 successful uses)
    extract_visual_hints(prompt) -> list
    derive_subject_tags(subject, fetch_metadata) -> list

Library schema — list of rich entries at ``app/data/library.json``:
    {
      "version": 1,
      "assets": [
        {
          "id": "objaverse_cat_1744839600",
          "subject": "cat",
          "subject_tags": ["cat", "feline", "animal", "pet", "orange"],
          "visual_descriptors": ["orange", "realistic"],
          "path": "assets/cache/models/objaverse/<hash>.glb",
          "type": "animal",
          "scale_class": "small",
          "source": "objaverse",
          "source_metadata": {...},
          "quality_flags": {...},
          "tested": false,
          "use_count": 1,
          "first_rendered_ts": 1744839600,
          "last_rendered_ts": 1744839600,
          "bounds_meters": [0.5, 0.3, 0.25]
        },
        ...
      ]
    }

Non-fatal: every function wraps I/O in try/except.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_LIBRARY_PATH = _ROOT / "app" / "data" / "library.json"

_SCHEMA_VERSION = 1
_AUTO_TEST_THRESHOLD = 2  # use_count >= N → tested=True


# ═══════════════════════════════════════════════════════════════════════════
# I/O helpers
# ═══════════════════════════════════════════════════════════════════════════

def _load_library() -> dict:
    """Load library.json and overlay V1.4.6 runtime stats from
    ``library_stats.json``. Callers see a unified view: each entry's
    ``use_count`` / ``last_rendered_ts`` / ``last_used_at`` fields are
    populated from the gitignored stats file, not from library.json
    itself (which is now static and never mutated at render time).
    """
    try:
        if _LIBRARY_PATH.exists():
            data = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "assets" in data:
                # V1.4.6: merge runtime stats overlay
                try:
                    from . import library_stats as _ls
                    _ls.merge_stats_into(data["assets"])
                except Exception as _e:
                    print(
                        f"[LIBRARY] stats merge skipped ({_e}); "
                        f"reads will see use_count=0 across the board",
                        flush=True,
                    )
                return data
    except Exception as e:
        print(f"[LIBRARY] load failed ({e}) — starting fresh", flush=True)
    return {"version": _SCHEMA_VERSION, "assets": []}


def _save_library(lib: dict) -> bool:
    try:
        _LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LIBRARY_PATH.write_text(
            json.dumps(lib, indent=2, sort_keys=False),
            encoding="utf-8",
        )
        return True
    except Exception as e:
        print(f"[LIBRARY] save failed: {e}", flush=True)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Tag + descriptor derivation
# ═══════════════════════════════════════════════════════════════════════════

_CATEGORY_MAP = {
    "cat":       ["feline", "animal", "pet", "mammal"],
    "dog":       ["canine", "animal", "pet", "mammal"],
    "eagle":     ["bird", "raptor", "animal"],
    "hawk":      ["bird", "raptor", "animal"],
    "owl":       ["bird", "raptor", "animal"],
    "horse":     ["equine", "animal", "mammal", "large"],
    "elephant":  ["pachyderm", "animal", "mammal", "large"],
    "hippo":     ["pachyderm", "animal", "mammal", "large"],
    "hippopotamus": ["pachyderm", "animal", "mammal", "large"],
    "lion":      ["feline", "big_cat", "animal", "predator"],
    "tiger":     ["feline", "big_cat", "animal", "predator"],
    "leopard":   ["feline", "big_cat", "animal", "predator"],
    "cheetah":   ["feline", "big_cat", "animal", "predator"],
    "bear":      ["mammal", "animal", "predator", "large"],
    "wolf":      ["canine", "animal", "predator", "mammal"],
    "fox":       ["canine", "animal", "mammal"],
    "deer":      ["animal", "mammal"],
    "rabbit":    ["animal", "mammal", "small"],
    "dolphin":   ["cetacean", "animal", "aquatic", "mammal"],
    "whale":     ["cetacean", "animal", "aquatic", "mammal", "large"],
    "shark":     ["fish", "animal", "aquatic", "predator"],
    "pelican":   ["bird", "animal", "seabird"],
    "dinosaur":  ["reptile", "animal", "large", "extinct"],
    "lizard":    ["reptile", "animal"],
    "snake":     ["reptile", "animal"],

    "ferrari":   ["car", "vehicle", "sportscar", "luxury"],
    "bmw":       ["car", "vehicle", "luxury", "sedan"],
    "porsche":   ["car", "vehicle", "sportscar", "luxury"],
    "lamborghini": ["car", "vehicle", "sportscar", "luxury", "exotic"],
    "audi":      ["car", "vehicle", "luxury"],
    "mustang":   ["car", "vehicle", "muscle_car"],
    "corvette":  ["car", "vehicle", "sportscar"],
    "supra":     ["car", "vehicle", "sportscar", "jdm"],
    "tesla":     ["car", "vehicle", "electric"],
    "truck":     ["vehicle", "cargo"],
    "motorcycle": ["vehicle", "two_wheeler"],

    "robot":     ["character", "mechanical", "sci_fi"],
    "knight":    ["character", "humanoid", "medieval"],
}

_COLOR_WORDS = (
    "orange", "black", "white", "grey", "gray", "brown", "tabby", "ginger",
    "red", "blue", "green", "yellow", "golden", "silver", "beige", "tan",
    "calico", "striped", "spotted",
)

_STYLE_WORDS = (
    "realistic", "cartoon", "low_poly", "low-poly", "stylized", "anime",
    "photoreal", "photorealistic", "detailed", "simplified",
)


def derive_subject_tags(subject: str, fetch_metadata: dict | None) -> list:
    """Build a deduplicated tag set from subject + fetch metadata."""
    fm = fetch_metadata or {}
    tags: set = set()
    s_lower = (subject or "").lower().strip()
    if s_lower:
        tags.add(s_lower)
        for tok in s_lower.replace("_", " ").replace("-", " ").split():
            if len(tok) > 2:
                tags.add(tok)

    # Original name tokens
    name = str(fm.get("name") or "").lower()
    for tok in name.replace("_", " ").replace("-", " ").split():
        if len(tok) > 2:
            tags.add(tok)

    # Existing tags from fetch
    for t in fm.get("tags") or []:
        if isinstance(t, str):
            tags.add(t.lower())

    # Category inference — any key-word inside subject triggers its category
    for key, cat_tags in _CATEGORY_MAP.items():
        if key in s_lower:
            tags.update(cat_tags)

    return sorted(t for t in tags if t)


def _infer_visual_descriptors(fetch_metadata: dict | None) -> list:
    """Heuristic color/style descriptors from name + tags."""
    fm = fetch_metadata or {}
    text_parts = [str(fm.get("name") or ""), str(fm.get("description") or "")]
    text_parts.extend(str(t) for t in (fm.get("tags") or []))
    text = " ".join(text_parts).lower()
    out: list = []
    for c in _COLOR_WORDS:
        if re.search(r"\b" + re.escape(c) + r"\b", text):
            out.append(c)
    for s in _STYLE_WORDS:
        if s in text:
            out.append(s.replace("-", "_"))
    return out


def extract_visual_hints(prompt: str) -> list:
    """Return color/style hints from a user prompt.  Used to bias library
    retrieval (e.g. 'orange cat' should prefer the orange cat variant)."""
    if not prompt:
        return []
    p_lower = prompt.lower()
    tokens = set(p_lower.replace(",", " ").replace(".", " ").split())
    hints: list = []
    for c in _COLOR_WORDS:
        if c in tokens:
            hints.append(c)
    for s in _STYLE_WORDS:
        if s in p_lower:
            hints.append(s.replace("-", "_"))
    return hints


# ═══════════════════════════════════════════════════════════════════════════
# Promote + query
# ═══════════════════════════════════════════════════════════════════════════

def promote_to_curated(
    asset_path: str,
    subject: str,
    fetch_metadata: dict | None = None,
    render_metadata: dict | None = None,
) -> dict | None:
    """Promote a successfully-rendered asset to the rich library.

    Idempotent by path — re-promoting the same asset just bumps use_count
    and (at use_count >= 2) flips tested=True.
    """
    if not asset_path or not subject:
        print(
            f"[LIBRARY] promote skipped — missing path or subject "
            f"(path={asset_path!r}, subject={subject!r})",
            flush=True,
        )
        return None

    fm = fetch_metadata or {}
    rm = render_metadata or {}
    now = time.time()
    lib = _load_library()
    assets = lib.setdefault("assets", [])

    # Upsert by path
    existing = None
    for a in assets:
        if str(a.get("path")) == str(asset_path):
            existing = a
            break

    if existing is not None:
        # V1.4.6: route runtime stats to gitignored library_stats.json
        # so library.json stays static (no per-render diff noise).
        try:
            from . import library_stats as _ls
            new_count = _ls.bump_use_count(str(existing["id"]), ts=now)
        except Exception as _e:
            # Fall back to legacy in-place bump if stats module fails
            # (keeps the pipeline working; render still completes).
            print(
                f"[LIBRARY] stats bump failed ({_e}); falling back to "
                f"legacy in-library write",
                flush=True,
            )
            existing["use_count"] = int(existing.get("use_count", 0)) + 1
            existing["last_rendered_ts"] = now
            new_count = existing["use_count"]
            _save_library(lib)
        else:
            # Mirror onto the in-memory entry so callers reading the
            # return value see the bumped values, but DO NOT write the
            # library file back — those fields now live in stats.
            existing["use_count"] = new_count
            existing["last_rendered_ts"] = now

        # Tested promotion is a one-time structural change — that DOES
        # belong in library.json (it's not per-render drift).
        if (
            not existing.get("tested", False)
            and new_count >= _AUTO_TEST_THRESHOLD
        ):
            existing["tested"] = True
            _save_library(lib)
            print(
                f"[LIBRARY] id={existing['id']!r} promoted to tested=True "
                f"(use_count={new_count})",
                flush=True,
            )
        print(
            f"[LIBRARY] updated use_count for id={existing['id']!r} "
            f"-> {new_count} (stats.json)",
            flush=True,
        )
        return existing

    # New entry
    src = str(fm.get("source") or "unknown")
    safe_subject = re.sub(r"[^a-zA-Z0-9]+", "_", (subject or "asset"))[:32].strip("_") or "asset"
    new_id = f"{src}_{safe_subject}_{int(now)}"

    new_entry = {
        "id":                new_id,
        "subject":           (subject or "").lower(),
        "subject_tags":      derive_subject_tags(subject, fm),
        "visual_descriptors": _infer_visual_descriptors(fm),
        "path":              str(asset_path),
        "type":              fm.get("type", "unknown"),
        "scale_class":       rm.get("scale_class", "medium"),
        "source":            src,
        "source_metadata":   {
            "original_name":   fm.get("name"),
            "uid":             fm.get("uid"),
            "original_score":  fm.get("score"),
            "url":             fm.get("url"),
            "license":         fm.get("license"),
            "fetched_ts":      now,
        },
        "quality_flags":     rm.get("quality_flags", {}),
        "tested":            False,
        # V1.4.6: use_count / *_rendered_ts no longer ride in library.json.
        # The bump_use_count call below populates library_stats.json
        # immediately after this entry is created.
        "bounds_meters":     rm.get("bounds_meters"),
    }

    # V1.2: every new library entry goes through the healing gate.  This
    # runs a Blender subprocess (~2-5s) to measure + classify + detect
    # orientation issues.  Failures are non-fatal — the entry lands
    # un-healed and the one-off heal_library tool can sweep it later.
    try:
        from .asset_healer import heal_asset as _heal_asset
        _healed = _heal_asset(
            str(asset_path),
            proposed_category=fm.get("category") or fm.get("type"),
        )
        for _k, _v in (_healed or {}).items():
            new_entry[_k] = _v
        print(
            f"[LIBRARY] heal metadata attached to {new_id!r}: "
            f"provisional_ready={new_entry.get('provisional_ready')} "
            f"shape={new_entry.get('shape_class')!r} "
            f"orientation={new_entry.get('orientation_issue')!r}",
            flush=True,
        )
    except Exception as _heal_err:
        print(
            f"[LIBRARY] heal failed for {new_id!r} (non-fatal): {_heal_err}",
            flush=True,
        )

    assets.append(new_entry)
    _save_library(lib)
    # V1.4.6: kick off the stats counter at 1 in the gitignored
    # stats file so reads see use_count=1 immediately. Mirror onto
    # the returned dict so callers don't have to re-load.
    try:
        from . import library_stats as _ls
        _new_count = _ls.bump_use_count(new_id, ts=now)
        new_entry["use_count"] = _new_count
        new_entry["first_rendered_ts"] = now
        new_entry["last_rendered_ts"] = now
    except Exception as _stats_err:
        print(
            f"[LIBRARY] initial stats bump failed for {new_id!r} "
            f"(non-fatal): {_stats_err}",
            flush=True,
        )
        new_entry["use_count"] = 1
    print(
        f"[LIBRARY] promoted id={new_id!r} subject={subject!r} "
        f"source={src} tags={new_entry['subject_tags'][:5]}",
        flush=True,
    )
    return new_entry


def query_library(
    subject: str,
    visual_hints: list | None = None,
    category: str | None = None,
    limit: int = 10,
) -> list:
    """Return library entries matching the subject, ranked by relevance.

    Scoring:
      - +100 subject string appears in entry.subject
      - +10 per overlapping token between subject and subject_tags
      - +20 per overlapping visual hint with entry.visual_descriptors
      - +15 if entry.tested is True
      - +5 if entry.source is curated/local (higher trust)
    """
    lib = _load_library()
    s_lower = (subject or "").lower().strip()
    if not s_lower:
        return []
    subject_tokens = set(s_lower.replace("_", " ").replace("-", " ").split())
    hint_set = {(h or "").lower() for h in (visual_hints or []) if h}
    cat_lower = (category or "").lower().strip()

    scored: list = []
    for entry in lib.get("assets", []):
        if not isinstance(entry, dict):
            continue
        score = 0
        e_subject = str(entry.get("subject") or "").lower()
        e_tags = {str(t).lower() for t in (entry.get("subject_tags") or [])}
        e_desc = {str(d).lower() for d in (entry.get("visual_descriptors") or [])}

        if s_lower and s_lower in e_subject:
            score += 100
        tag_overlap = subject_tokens & e_tags
        score += 10 * len(tag_overlap)
        if hint_set:
            hint_overlap = hint_set & e_desc
            score += 20 * len(hint_overlap)
        if entry.get("tested"):
            score += 15
        if entry.get("source") in ("local", "curated"):
            score += 5
        # Category filter (optional)
        if cat_lower:
            if cat_lower not in e_tags and cat_lower != entry.get("type", "").lower():
                continue
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [e for _, e in scored[:limit]]


def query_library_strict(
    subject: str,
    *,
    brand: str | None = None,
    model: str | None = None,
    visual_hints: list | None = None,
    category: str | None = None,
    quality_filter: list | None = None,
    limit: int = 20,
) -> list:
    """Unified-schema v2 query with brand+model filtering + quality filter.

    When ``brand`` and ``model`` are both provided, only entries whose
    ``brand`` and ``model`` fields match (case-insensitive) are returned.
    This is the path that closes the "Porsche 911 → Ferrari" bypass.

    ``quality_filter`` defaults to ``["tested", "unverified"]``; pass
    ``["tested"]`` for the strict pool used by the diversity picker.
    """
    lib = _load_library()
    s_lower = (subject or "").lower().strip()
    qset = set(quality_filter or ["tested", "unverified"])
    b_lower = (brand or "").lower().strip() or None
    m_lower = (model or "").lower().strip() or None
    c_lower = (category or "").lower().strip() or None
    hint_set = {(h or "").lower() for h in (visual_hints or []) if h}
    subject_tokens = set(s_lower.replace("_", " ").replace("-", " ").split())

    scored: list = []
    for entry in lib.get("assets", []):
        if not isinstance(entry, dict):
            continue
        # Quality gate (v2 schema 'quality' + legacy 'tested' fallback)
        q = entry.get("quality")
        if q is None:
            q = "tested" if entry.get("tested") else "unverified"
        if q not in qset:
            continue

        # Category filter (soft — only skip if explicit mismatch)
        if c_lower:
            e_cat = str(entry.get("category") or "").lower()
            if e_cat and e_cat != c_lower:
                # Also allow via tags intersection (character→animal via tags)
                e_tags = {str(t).lower() for t in (entry.get("subject_tags") or [])}
                if c_lower not in e_tags:
                    continue

        # Brand + model STRICT filter (for brand+model queries)
        if b_lower and m_lower:
            e_brand = str(entry.get("brand") or "").lower()
            e_model = str(entry.get("model") or "").lower()
            # Also check subject_tags + name for backwards compat
            e_tags = {str(t).lower() for t in (entry.get("subject_tags") or [])}
            e_blob = (
                f"{entry.get('subject', '')} "
                f"{' '.join(entry.get('subject_tags') or [])} "
                f"{entry.get('path', '')}"
            ).lower()
            brand_hit = (e_brand == b_lower) or (b_lower in e_tags) or (b_lower in e_blob)
            model_hit = (e_model == m_lower) or (m_lower in e_tags) or (m_lower in e_blob)
            if not (brand_hit and model_hit):
                continue

        # Score
        score = 0
        e_subject = str(entry.get("subject") or "").lower()
        e_tags = {str(t).lower() for t in (entry.get("subject_tags") or [])}
        e_desc = {str(d).lower() for d in (entry.get("visual_descriptors") or [])}

        if s_lower and s_lower in e_subject:
            score += 100
        tag_overlap = subject_tokens & e_tags
        score += 10 * len(tag_overlap)
        if hint_set:
            hint_overlap = hint_set & e_desc
            score += 25 * len(hint_overlap)
        if q == "tested":
            score += 20
        if entry.get("source") in ("curated", "user_upload"):
            score += 5
        # Brand-only match (non-strict) still gets bonus
        if b_lower and not m_lower:
            if str(entry.get("brand") or "").lower() == b_lower:
                score += 40

        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda t: (t[0], int(t[1].get("use_count", 0))), reverse=True)
    return [e for _, e in scored[:limit]]


def mark_tested(asset_id: str) -> bool:
    """Manually flip an asset's tested flag."""
    lib = _load_library()
    for a in lib.get("assets", []):
        if a.get("id") == asset_id:
            a["tested"] = True
            _save_library(lib)
            print(f"[LIBRARY] manually tested id={asset_id!r}", flush=True)
            return True
    return False


def library_stats() -> dict:
    """Return a summary of the library state (for diagnostic logs)."""
    lib = _load_library()
    assets = lib.get("assets", [])
    by_subject: dict = {}
    by_source: dict = {}
    for a in assets:
        s = a.get("subject", "unknown")
        by_subject[s] = by_subject.get(s, 0) + 1
        src = a.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1
    tested_count = sum(1 for a in assets if a.get("tested"))
    return {
        "total":       len(assets),
        "tested":      tested_count,
        "by_subject":  by_subject,
        "by_source":   by_source,
    }
