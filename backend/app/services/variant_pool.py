"""
variant_pool.py
===============
Per-installation variant rotation for subject-indexed asset pools.

When Objaverse (or any fetcher) returns ranked candidates for a subject,
we persist the top-N to a JSON pool. On the next render for the same
subject, candidates are re-ranked using a recency penalty so we rotate
through variants instead of picking the same "sleepy tabby" every time.

Public API:
    register_variants(subject, candidates) -> None
    pick_variant(subject, base_ranked) -> dict | None
    mark_used(subject, variant_id) -> None

Non-fatal: every function wraps I/O in try/except and falls through to
base ranking on pool corruption.  The pool lives at
``assets/cache/variant_pool.json`` — scoped to this installation.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_POOL_PATH = _ROOT / "assets" / "cache" / "variant_pool.json"

# Recency penalty thresholds (hours → penalty)
_RECENCY_HOURS_IMMEDIATE = 1.0    # penalty=100 if used in last hour
_RECENCY_HOURS_DAY = 24.0         # penalty=50 if used in last 24h
_RECENCY_HOURS_WEEK = 168.0       # penalty=15 if used in last week
_USAGE_PENALTY_CAP = 30           # max penalty from use_count * 5


def _load_pool() -> dict:
    try:
        if _POOL_PATH.exists():
            return json.loads(_POOL_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[VARIANT_POOL] load failed ({e}) — starting fresh", flush=True)
    return {}


def _save_pool(pool: dict) -> bool:
    try:
        _POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _POOL_PATH.write_text(json.dumps(pool, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[VARIANT_POOL] save failed: {e}", flush=True)
        return False


def _key(subject: str) -> str:
    return (subject or "").lower().strip()


def register_variants(subject: str, candidates: list) -> None:
    """Record the top candidates for a subject.

    Idempotent per (subject, variant_id) — existing variants are not
    overwritten; only new ones are appended. Preserves accumulated
    use_count and last_used_ts across renders.
    """
    if not subject or not candidates:
        return
    key = _key(subject)
    pool = _load_pool()
    bucket = pool.setdefault(key, {"variants": {}, "last_used": {}})
    variants = bucket["variants"]
    now = time.time()

    added = 0
    for c in candidates[:5]:
        if not isinstance(c, dict):
            continue
        vid = str(c.get("id") or c.get("uid") or c.get("path") or "").strip()
        if not vid:
            continue
        if vid in variants:
            continue  # preserve existing counters
        variants[vid] = {
            "name":          c.get("name", ""),
            "score":         c.get("score", 0),
            "path":          c.get("path"),
            "tags":          list(c.get("tags") or []),
            "source":        c.get("source", ""),
            "use_count":     0,
            "first_seen_ts": now,
        }
        added += 1

    if added:
        _save_pool(pool)
        print(
            f"[VARIANT_POOL] registered {added} new variant(s) for "
            f"subject={key!r} (pool size={len(variants)})",
            flush=True,
        )


def pick_variant(subject: str, base_ranked: list) -> Any:
    """Re-rank ``base_ranked`` by applying a recency penalty from the pool.

    ``base_ranked`` is a list of dicts with at least ``id`` and ``score``.
    Returns the winning dict (original reference preserved) or None if
    empty.  The first render for a subject has no pool entries, so the
    base ranking is returned unchanged.
    """
    if not base_ranked:
        return None
    key = _key(subject)
    pool = _load_pool()
    bucket = pool.get(key)
    if not bucket:
        return base_ranked[0]

    variants = bucket.get("variants", {}) or {}
    last_used = bucket.get("last_used", {}) or {}
    now = time.time()

    scored = []
    for cand in base_ranked:
        if not isinstance(cand, dict):
            continue
        vid = str(cand.get("id") or cand.get("uid") or cand.get("path") or "").strip()
        base_score = float(cand.get("score", 0) or 0)
        v = variants.get(vid, {})
        use_count = int(v.get("use_count", 0))
        last_ts = float(last_used.get(vid, 0) or 0)
        hours_since_use = ((now - last_ts) / 3600.0) if last_ts > 0 else 99999.0

        recency_penalty = 0
        if hours_since_use < _RECENCY_HOURS_IMMEDIATE:
            recency_penalty = 100
        elif hours_since_use < _RECENCY_HOURS_DAY:
            recency_penalty = 50
        elif hours_since_use < _RECENCY_HOURS_WEEK:
            recency_penalty = 15

        usage_penalty = min(use_count * 5, _USAGE_PENALTY_CAP)
        final = base_score - recency_penalty - usage_penalty
        scored.append((final, cand, {
            "base":         base_score,
            "recency_pen":  recency_penalty,
            "usage_pen":    usage_penalty,
            "use_count":    use_count,
            "hours_ago":    round(hours_since_use, 1) if hours_since_use < 99999 else None,
        }))

    if not scored:
        return base_ranked[0]

    scored.sort(key=lambda t: t[0], reverse=True)
    # Log top 3 so rotation is visible in traces
    for final, cand, breakdown in scored[:3]:
        print(
            f"[VARIANT_POOL] cand={cand.get('name', '?')!r} "
            f"final={final:.1f} ({breakdown})",
            flush=True,
        )
    return scored[0][1]


def get_session_history(subject: str, window_hours: float = 2.0) -> list:
    """Return variant IDs used for this subject within the last window_hours,
    most recent first.  Used by ``pick_with_diversity`` to force rotation
    across renders in the same session."""
    pool = _load_pool()
    key = _key(subject)
    bucket = pool.get(key)
    if not bucket:
        return []
    now = time.time()
    history = []
    for vid, ts in (bucket.get("last_used") or {}).items():
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            continue
        if (now - ts) / 3600.0 < window_hours:
            history.append((ts, vid))
    history.sort(reverse=True)  # most recent first
    return [vid for _, vid in history]


def consecutive_same_subject_count(subject: str, window_hours: float = 2.0) -> int:
    """How many times has this subject been requested within window_hours?
    Used for the 'three-in-a-row reset' rule in ``pick_with_diversity``."""
    return len(get_session_history(subject, window_hours))


# V1.3.7 Fix 1: subject alias map. Normalizes prompt subjects and asset
# subject fields onto a single canonical token before scoring so that
# "elephants" / "an elephant" / "elephant" all hit the same bucket.
# Keep this map small and conservative — entries should be safe
# bidirectional canonicalizations that don't change semantic meaning.
_SUBJECT_ALIASES: dict[str, str] = {
    # plurals → singular
    "elephants": "elephant",
    "horses": "horse",
    "cows": "cow",
    "cats": "cat",
    "dogs": "dog",
    "birds": "bird",
    "wolves": "wolf",
    "lions": "lion",
    "tigers": "tiger",
    "bears": "bear",
    "deer": "deer",
    "rhinoceroses": "rhinoceros",
    "rhinos": "rhinoceros",
    "rhino": "rhinoceros",
    "ferraris": "ferrari",
    "bmws": "bmw",
    "trucks": "truck",
    "planes": "plane",
    "ships": "ship",
    "boats": "boat",
    "trees": "tree",
    "mountains": "mountain",
    "deserts": "desert",
    "forests": "forest",
    "oceans": "ocean",
    "cities": "city",
    # broad → category
    "car":      "vehicle",
    "cars":     "vehicle",
    "automobile": "vehicle",
    "auto":     "vehicle",
    "person":   "character",
    "people":   "character",
    "human":    "character",
    "humans":   "character",
    "animal":   "character",
    "animals":  "character",
    "creature": "character",
    "monster":  "character",
    "scenery":  "environment",
    "landscape": "environment",
    "terrain":  "environment",
}

# Filler tokens we strip when normalizing the prompt-side subject.  Keeps
# "a horse" and "the elephant" from missing exact matches.
_SUBJECT_STOPWORDS = frozenset({
    "a", "an", "the", "some", "this", "that", "these", "those",
    "of", "with",
})


def _normalize_subject(s: str | None) -> str:
    """Lowercase, strip stopwords, and apply the alias map. Returns empty
    string if input is empty or only stopwords."""
    if not s:
        return ""
    raw = str(s).lower().strip()
    if not raw:
        return ""
    # Drop punctuation cheaply
    import re as _re
    raw = _re.sub(r"[^a-z0-9_\s\-]+", " ", raw).strip()
    parts = [p for p in raw.split() if p and p not in _SUBJECT_STOPWORDS]
    if not parts:
        return ""
    canonical = " ".join(parts)
    if canonical in _SUBJECT_ALIASES:
        return _SUBJECT_ALIASES[canonical]
    # Single-token alias
    if len(parts) == 1 and parts[0] in _SUBJECT_ALIASES:
        return _SUBJECT_ALIASES[parts[0]]
    return canonical


def _score_entry_for_subject(entry: dict, requested_norm: str) -> float:
    """V1.3.7 scoring rubric (post-normalization):
      1.0  — exact subject match
      0.85 — exact tag match
      0.40..0.75 — partial subject substring (3+ char overlap)
      0.30..0.60 — partial tag substring
      0.0  — no signal
    """
    if not requested_norm:
        return 0.0
    subj_raw = str(entry.get("subject") or entry.get("name") or "")
    subj = _normalize_subject(subj_raw)
    tags_norm = set()
    for t in (entry.get("tags") or entry.get("subject_tags") or []):
        tn = _normalize_subject(t)
        if tn:
            tags_norm.add(tn)
    # 1. exact subject (normalized)
    if subj and subj == requested_norm:
        return 1.0
    # 2. exact tag (normalized)
    if requested_norm in tags_norm:
        return 0.85
    best = 0.0
    # 3. partial subject substring with 3+ char overlap
    if subj and len(requested_norm) >= 3 and len(subj) >= 3 \
            and (requested_norm in subj or subj in requested_norm):
        ratio = min(len(requested_norm), len(subj)) / max(
            len(requested_norm), len(subj), 1
        )
        best = max(best, 0.40 + 0.35 * ratio)  # 0.40..0.75
    # 4. partial tag substring
    for t in tags_norm:
        if len(t) >= 3 and len(requested_norm) >= 3 and \
                (requested_norm in t or t in requested_norm):
            ratio = min(len(requested_norm), len(t)) / max(
                len(requested_norm), len(t), 1
            )
            best = max(best, 0.30 + 0.30 * ratio)  # 0.30..0.60
    return best


def _filter_pool_by_subject(pool: list, requested_subject: str) -> list:
    """V1.3.7 — score, threshold, and **sort** the pool so the highest-
    confidence match is at index 0. Threshold lowered to 0.30 from V1.3.6's
    over-defensive 0.50.

    Empty pool or empty ``requested_subject`` → pool unchanged (caller
    decides what to do with that).
    """
    if not requested_subject or not pool:
        return pool
    requested_norm = _normalize_subject(requested_subject)
    if not requested_norm:
        return pool

    MIN_CONFIDENCE = 0.30
    scored = [(e, _score_entry_for_subject(e, requested_norm)) for e in pool]
    scored = [(e, s) for (e, s) in scored if s >= MIN_CONFIDENCE]
    # Highest score first; stable on ties.
    scored.sort(key=lambda t: -t[1])
    return [e for (e, _s) in scored]


def pick_with_diversity(
    subject: str,
    accepted_candidates: list,
    session_seed: int | None = None,
) -> Any:
    """Diversity-aware picker.

    ``accepted_candidates`` is the list of assets that passed the subject
    gate, already ranked by base score.  Returns the chosen candidate.

    Strategy:
      - Consecutive count 0  → first time: random pick from top-K accepted
      - Consecutive count 1 or 2 → exclude last-used variant(s), random pick from remainder
      - Consecutive count >=3 → reset; return top-ranked (user wants this subject)

    ``session_seed`` is optional; when omitted, the global random module is
    used.  Caller can pass a deterministic seed (e.g. hash(prompt + nonce))
    for reproducibility.

    V1.3 final resolver fix: before any diversity logic, filter the pool
    to entries whose subject or tags actually match ``subject``.  When
    the filter empties the pool, return None so the library resolver
    defers to the downstream fetcher (Objaverse / Sketchfab) instead of
    returning a wrong-subject random pick.
    """
    import random as _r
    if not accepted_candidates:
        return None

    # Subject filter — bug fix for cross-subject cat/BMW random selection.
    _orig_size = len(accepted_candidates)
    _filtered = _filter_pool_by_subject(accepted_candidates, subject)
    if not _filtered:
        print(
            f"[VARIANT_DIVERSITY] no library entries match subject={subject!r} — "
            f"deferring to Objaverse",
            flush=True,
        )
        return None
    if len(_filtered) != _orig_size:
        print(
            f"[VARIANT_DIVERSITY] subject-filter: {_orig_size} -> "
            f"{len(_filtered)} matches for {subject!r}",
            flush=True,
        )
    accepted_candidates = _filtered

    # V1.3.7: log [MATCHER] picked + runner-up so bad picks are debuggable.
    # _filter_pool_by_subject already returns the pool sorted by score
    # descending, so accepted_candidates[0] is the highest-confidence match.
    _req_norm = _normalize_subject(subject)
    _pick_score = _score_entry_for_subject(accepted_candidates[0], _req_norm)
    _pick_subj = (
        accepted_candidates[0].get("subject")
        or accepted_candidates[0].get("name")
        or accepted_candidates[0].get("id") or "?"
    )
    if len(accepted_candidates) > 1:
        _ru = accepted_candidates[1]
        _ru_score = _score_entry_for_subject(_ru, _req_norm)
        _ru_subj = (
            _ru.get("subject") or _ru.get("name") or _ru.get("id") or "?"
        )
        _ru_str = f" runner_up={_ru_subj} (score={_ru_score:.2f})"
    else:
        _ru_str = ""
    _pick_reason = (
        "exact_subject" if _pick_score >= 0.99
        else "exact_tag" if _pick_score >= 0.85 - 1e-6
        else "subject_substring" if _pick_score >= 0.40
        else "tag_substring"
    )
    print(
        f"[MATCHER] picked={_pick_subj} (score={_pick_score:.2f}, "
        f"{_pick_reason}){_ru_str}",
        flush=True,
    )
    # Exact-subject short-circuit: if the top match is an exact (post-
    # normalization) subject hit, return it directly. Diversity rotation
    # only applies among ties of equal/near-equal confidence — letting a
    # 1.0 exact match get randomized away from is what allowed
    # "elephant" → rhinoceros in V1.3.6.
    if _pick_score >= 0.99:
        # Allow diversity ONLY when there are multiple exact matches.
        _exact_pool = [
            e for e in accepted_candidates
            if _score_entry_for_subject(e, _req_norm) >= 0.99
        ]
        if len(_exact_pool) == 1:
            return _exact_pool[0]
        # Multiple exact matches → fall through to diversity logic, but
        # restrict the candidate pool to exact-only.
        accepted_candidates = _exact_pool

    history = get_session_history(subject)
    consecutive = len(history)
    top_k = min(5, len(accepted_candidates))
    pool = accepted_candidates[:top_k]

    print(
        f"[VARIANT_DIVERSITY] subject={subject!r} "
        f"accepted_pool={len(accepted_candidates)} top_k={top_k} "
        f"consecutive_recent={consecutive}",
        flush=True,
    )

    rng = _r.Random(session_seed) if session_seed is not None else _r.Random()

    if consecutive == 0:
        chosen = rng.choice(pool)
        _name = chosen.get("name") or chosen.get("id") or "?"
        print(
            f"[VARIANT_DIVERSITY] first-time pick (random from top {top_k}): "
            f"{_name!r}",
            flush=True,
        )
        return chosen

    if consecutive >= 3:
        chosen = accepted_candidates[0]
        _name = chosen.get("name") or chosen.get("id") or "?"
        print(
            f"[VARIANT_DIVERSITY] 3-in-a-row reset — returning to top-ranked: "
            f"{_name!r}",
            flush=True,
        )
        return chosen

    # consecutive == 1 or 2: exclude recent, random from remainder
    recent_ids = set(history)
    filtered = [c for c in pool if str(c.get("id") or c.get("uid") or "") not in recent_ids]
    if not filtered:
        # Top-K entirely recent — try the full accepted list
        filtered = [
            c for c in accepted_candidates
            if str(c.get("id") or c.get("uid") or "") not in recent_ids
        ]
    if not filtered:
        # Genuinely exhausted — random from pool, allow recent
        chosen = rng.choice(pool)
        _name = chosen.get("name") or chosen.get("id") or "?"
        print(
            f"[VARIANT_DIVERSITY] pool exhausted of non-recent — "
            f"random pick: {_name!r}",
            flush=True,
        )
        return chosen

    chosen = rng.choice(filtered[:top_k])
    _name = chosen.get("name") or chosen.get("id") or "?"
    print(
        f"[VARIANT_DIVERSITY] forcing diversity "
        f"(excluded {len(recent_ids)} recent): {_name!r}",
        flush=True,
    )
    return chosen


def mark_used(subject: str, variant_id: str) -> None:
    """Increment use_count and last_used_ts for a variant."""
    if not subject or not variant_id:
        return
    key = _key(subject)
    pool = _load_pool()
    bucket = pool.get(key)
    if not bucket:
        return
    variants = bucket.setdefault("variants", {})
    last_used = bucket.setdefault("last_used", {})
    if variant_id in variants:
        variants[variant_id]["use_count"] = int(variants[variant_id].get("use_count", 0)) + 1
        last_used[variant_id] = time.time()
        _save_pool(pool)
        print(
            f"[VARIANT_POOL] mark_used subject={key!r} variant={variant_id!r} "
            f"use_count={variants[variant_id]['use_count']}",
            flush=True,
        )
