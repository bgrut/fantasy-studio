#!/usr/bin/env python3
"""V1.4.6 one-shot migration: split runtime usage stats out of
library.json into the gitignored library_stats.json.

Before: every render bumped ``use_count`` / ``last_rendered_ts`` in
``backend/app/data/library.json`` (a tracked file). That produced a
meaningless per-render git diff and leaked personal usage stats into
the public repo.

After running this script:
    - ``library.json`` no longer contains use_count / last_rendered_ts
      / last_used_at / first_rendered_ts on any entry.
    - Those fields move to ``backend/app/data/library_stats.json``
      keyed by asset id (gitignored — every install gets its own).
    - Renders bump the stats file via
      ``app/services/library_stats.bump_use_count``.

Usage:
    cd backend
    .\\venv\\Scripts\\python.exe scripts\\migrate_stats.py [--dry-run]

The script is idempotent — running it again after a successful
migration is a no-op (no fields to strip = nothing to do).

A timestamped backup of library.json is written next to the live
file before the cleaned version replaces it.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

# Resolve absolute paths from this script's location so it works
# whether invoked from repo root or backend/.
HERE = Path(__file__).resolve()
BACKEND_ROOT = HERE.parent.parent  # -> backend/
LIB_PATH = BACKEND_ROOT / "app" / "data" / "library.json"
STATS_PATH = BACKEND_ROOT / "app" / "data" / "library_stats.json"

# Fields stripped from library.json and persisted to library_stats.json.
# Mirrors library_stats._RUNTIME_FIELDS — keep in sync if extended.
RUNTIME_FIELDS = (
    "use_count",
    "last_rendered_ts",
    "last_used_at",
    "first_rendered_ts",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without touching files.",
    )
    args = parser.parse_args()

    if not LIB_PATH.exists():
        print(f"FAIL  library.json not found at {LIB_PATH}")
        return 2

    print(f"Source: {LIB_PATH}")
    print(f"Target stats file: {STATS_PATH}")
    print()

    with open(LIB_PATH, encoding="utf-8") as f:
        lib = json.load(f)

    assets = lib.get("assets") or []
    if not isinstance(assets, list):
        print(f"FAIL  library.json 'assets' is not a list (got {type(assets).__name__})")
        return 3

    # Load existing stats (if any) and merge — preserves any counts
    # already written by post-V1.4.6 renders since the last migration.
    if STATS_PATH.exists():
        try:
            with open(STATS_PATH, encoding="utf-8") as f:
                stats_data = json.load(f)
        except Exception as e:
            print(f"WARN  existing stats file unreadable ({e}); starting fresh")
            stats_data = {}
    else:
        stats_data = {}

    stats_data.setdefault("_meta", {
        "library_version": "1.4.6",
        "description": (
            "Per-user runtime usage stats for the asset library. "
            "Gitignored — every install gets its own."
        ),
    })
    stats_data["_meta"]["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    stats_bucket = stats_data.setdefault("stats", {})

    # Walk library.json, harvest runtime fields, strip from each entry.
    fields_seen = {f: 0 for f in RUNTIME_FIELDS}
    entries_touched = 0
    for entry in assets:
        if not isinstance(entry, dict):
            continue
        aid = entry.get("id")
        if not aid:
            continue
        per_id = stats_bucket.setdefault(aid, {})
        moved_any = False
        for field in RUNTIME_FIELDS:
            if field in entry:
                # Migrate value. If stats already has a value, prefer
                # the larger of the two (defensive — a post-migration
                # bump should win over a pre-migration snapshot).
                old = per_id.get(field)
                new = entry[field]
                if field == "use_count":
                    per_id[field] = max(int(old or 0), int(new or 0))
                else:
                    per_id[field] = old or new
                del entry[field]
                fields_seen[field] += 1
                moved_any = True
        if moved_any:
            entries_touched += 1

    print("Migration summary:")
    print(f"  entries touched:  {entries_touched} of {len(assets)}")
    for f, n in fields_seen.items():
        print(f"  {f:<22} stripped from {n} entries")
    print(f"  stats file will hold: {len(stats_bucket)} ids")
    print()

    if entries_touched == 0:
        print("OK  library.json already clean (no runtime fields present)")
        if args.dry_run:
            return 0
        # Still ensure the stats file exists so the loader has a target
        if not STATS_PATH.exists():
            STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(STATS_PATH, "w", encoding="utf-8") as f:
                json.dump(stats_data, f, indent=2)
            print(f"  wrote empty stats skeleton to {STATS_PATH}")
        return 0

    if args.dry_run:
        print("--dry-run: NO files written")
        return 0

    # Backup library.json, write cleaned version, write stats.
    bak_path = LIB_PATH.with_suffix(
        LIB_PATH.suffix + f".bak_v146_premigration_{int(time.time())}"
    )
    shutil.copy2(LIB_PATH, bak_path)
    print(f"  backup written: {bak_path.name}")

    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats_data, f, indent=2)
    print(f"  stats written: {STATS_PATH.name} ({len(stats_bucket)} ids)")

    with open(LIB_PATH, "w", encoding="utf-8") as f:
        json.dump(lib, f, indent=2)
    print(f"  cleaned library.json written")

    print()
    print("DONE  V1.4.6 migration complete.")
    print("      Next render will bump library_stats.json — verify with:")
    print("          git status backend/app/data/library.json")
    print("      should show no changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
