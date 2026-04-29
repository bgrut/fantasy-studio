"""V1.4.6 — Per-user runtime usage stats for the asset library.

Background
----------
Pre-V1.4.6, ``library.json`` carried both static asset metadata
(orientation, shape_class, subject tags, …) AND per-user runtime
counters (``use_count``, ``last_rendered_ts``, etc.). Every render
mutated the latter, producing meaningless per-render diffs and
leaking personal usage stats into the public repo.

This module separates concerns:

- ``library.json`` stays tracked and **static** (curated metadata)
- ``library_stats.json`` is **gitignored** and holds only counters

The split is transparent to readers: ``merge_stats_into(entries)``
folds the stats back onto a freshly-loaded library at runtime so
existing call sites that read ``entry["use_count"]`` keep working.

File layout
-----------
::

    backend/app/data/library_stats.json
    {
      "_meta": {
        "library_version": "1.4.6",
        "last_updated": "2026-04-30T12:34:56Z",
        "description": "Per-user runtime usage stats. Gitignored."
      },
      "stats": {
        "<asset_id>": {
          "use_count": 13,
          "last_rendered_ts": 1745962400.123,
          "last_used_at": "2026-04-30T11:22:33",
          "first_rendered_ts": 1740000000.0
        }
      }
    }

API
---
- :func:`load_stats` — read the file, return ``{}`` on miss.
- :func:`save_stats` — write atomically (``.tmp`` + rename).
- :func:`bump_use_count` — atomic single-key increment + return new count.
- :func:`get_stats` — single-id lookup.
- :func:`merge_stats_into` — overlay onto a list of library entries.

Thread-safety: a process-local ``Lock`` serialises writes. Multiple
backend workers on one machine are safe; multiple machines pointing
at the same file are not (don't do that).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

# Absolute path resolves from this file's location so the module
# works whether the backend is launched from repo root, /backend, or
# anywhere else.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATS_PATH = _DATA_DIR / "library_stats.json"

_RUNTIME_FIELDS = (
    "use_count",
    "last_rendered_ts",
    "last_used_at",
    "first_rendered_ts",
)

_lock = Lock()


def _empty() -> dict:
    return {
        "_meta": {
            "library_version": "1.4.6",
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "description": (
                "Per-user runtime usage stats for the asset library. "
                "This file is gitignored — every install gets its own. "
                "Static metadata lives in library.json (tracked)."
            ),
        },
        "stats": {},
    }


def load_stats() -> dict:
    """Load the stats file, returning an empty skeleton on miss."""
    if not STATS_PATH.exists():
        return _empty()
    try:
        with open(STATS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "stats" not in data:
            # Corrupt — reset.
            return _empty()
        # Be forgiving with older one-shot variants.
        data.setdefault("_meta", _empty()["_meta"])
        return data
    except Exception as e:
        print(
            f"[LIBRARY_STATS] load failed ({e}); starting fresh",
            flush=True,
        )
        return _empty()


def save_stats(data: dict) -> None:
    """Atomic write: dump to ``<path>.tmp``, then ``os.replace``."""
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data.setdefault("_meta", {})["last_updated"] = time.strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    tmp = STATS_PATH.with_suffix(STATS_PATH.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, STATS_PATH)
    except Exception as e:
        print(
            f"[LIBRARY_STATS] save failed ({e}); stats unchanged",
            flush=True,
        )
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


def get_stats(asset_id: str) -> dict:
    """Return the stats sub-dict for one asset, or ``{}`` if absent."""
    data = load_stats()
    return dict(data.get("stats", {}).get(asset_id) or {})


def bump_use_count(
    asset_id: str,
    *,
    ts: float | None = None,
) -> int:
    """Increment ``use_count`` for ``asset_id``. Sets first/last
    rendered timestamps. Returns the new count.

    Thread-safe. Atomic with respect to other callers on the same
    process.
    """
    if not asset_id:
        return 0
    now = time.time() if ts is None else float(ts)
    with _lock:
        data = load_stats()
        stats = data.setdefault("stats", {})
        entry = stats.setdefault(asset_id, {})
        new_count = int(entry.get("use_count", 0)) + 1
        entry["use_count"] = new_count
        entry.setdefault("first_rendered_ts", now)
        entry["last_rendered_ts"] = now
        entry["last_used_at"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(now)
        )
        save_stats(data)
    return new_count


def merge_stats_into(entries: Iterable[dict]) -> list[dict]:
    """Overlay the stats file onto a list of library entries in-place.

    Each entry's ``use_count`` and timestamp fields are populated from
    ``library_stats.json`` if present; otherwise they default to 0
    (count) or stay missing (timestamps). Returns the same list for
    caller convenience.

    Idempotent — calling twice on the same list is a no-op.
    """
    data = load_stats()
    stats = data.get("stats") or {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        aid = entry.get("id")
        if not aid:
            entry.setdefault("use_count", 0)
            continue
        s = stats.get(aid) or {}
        # Stats overrides any drifted residue still in library.json,
        # but absent stats fall back to 0 (use_count) so legacy
        # consumers that branch on a literal int never see None.
        entry["use_count"] = int(s.get("use_count", entry.get("use_count", 0)) or 0)
        for f in ("last_rendered_ts", "last_used_at", "first_rendered_ts"):
            v = s.get(f) if f in s else entry.get(f)
            if v is not None:
                entry[f] = v
    return list(entries) if not isinstance(entries, list) else entries


# ── Convenience helpers used by the migration script ────────────────

def runtime_field_names() -> tuple[str, ...]:
    """The set of fields that live in ``library_stats.json``, exposed
    for the migration script + any tooling that needs to strip them
    from a library snapshot."""
    return tuple(_RUNTIME_FIELDS)
