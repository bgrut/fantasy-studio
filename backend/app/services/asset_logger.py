"""
Asset Library Logger — records every model pull for curation.

Every time the pipeline downloads a model from Objaverse or Sketchfab,
this module logs it to ``app/data/asset_library.json`` with the subject,
source, UID, file path, dimensions, vertex count, and a ``status`` field
(default ``"untested"``).

Users can later mark entries as ``"good"`` or ``"bad"`` through the
frontend or by editing the JSON directly. Entries marked ``"bad"`` are
returned by ``is_blacklisted()`` so the fetch pipeline skips them on
future runs.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any

ASSET_LOG_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "asset_library.json"
)
_lock = Lock()


def log_asset(
    subject: str,
    source: str,
    uid: str,
    name: str,
    file_path: str,
    dims: list[float] | None = None,
    verts: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log a fetched asset for future curation.

    Thread-safe — multiple render workers can call this concurrently.
    """
    with _lock:
        library = _load_library()

        key = f"{source}_{uid}"

        if key not in library["assets"]:
            entry: dict[str, Any] = {
                "subject": subject,
                "source": source,
                "uid": uid,
                "name": name,
                "file_path": file_path,
                "dims": dims,
                "verts": verts,
                "status": "untested",
                "times_used": 1,
                "first_seen": time.strftime("%Y-%m-%d %H:%M"),
                "last_used": time.strftime("%Y-%m-%d %H:%M"),
                "notes": "",
            }
            if extra:
                entry.update(extra)
            library["assets"][key] = entry
            print(
                f"[ASSET_LOG] new asset: {name} ({source}/{uid}) "
                f"for subject {subject!r}",
                flush=True,
            )
        else:
            library["assets"][key]["times_used"] += 1
            library["assets"][key]["last_used"] = time.strftime(
                "%Y-%m-%d %H:%M"
            )
            print(
                f"[ASSET_LOG] repeat use: {name} ({source}/{uid}) "
                f"count={library['assets'][key]['times_used']}",
                flush=True,
            )

        _save_library(library)


def is_blacklisted(source: str, uid: str) -> bool:
    """Check if an asset has been marked as bad."""
    library = _load_library()
    key = f"{source}_{uid}"
    entry = library["assets"].get(key, {})
    return entry.get("status") == "bad"


def get_good_asset(subject: str) -> dict | None:
    """Find a previously-approved asset for this subject."""
    library = _load_library()
    subject_lower = (subject or "").lower()

    for _key, entry in library["assets"].items():
        if (
            entry.get("status") == "good"
            and (entry.get("subject") or "").lower() == subject_lower
        ):
            return entry

    return None


def _load_library() -> dict:
    if ASSET_LOG_PATH.exists():
        try:
            with open(ASSET_LOG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "assets": {},
        "_meta": {"description": "Auto-logged asset library"},
    }


def _save_library(library: dict) -> None:
    ASSET_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ASSET_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(library, f, indent=2)
