#!/usr/bin/env python3
"""
tools/heal_library.py
=====================
One-off: run the V1.2 healing pipeline over every existing asset in
``app/data/library.json`` and write healed metadata back.

Backs up the library before writing.  Checkpoints every 20 entries so a
crash doesn't lose progress.  Non-destructive to the underlying asset
files — healing only writes metadata.

Usage:
    python tools/heal_library.py
    python tools/heal_library.py --only-missing     (skip entries that already have healer_version)
    python tools/heal_library.py --category environment
    python tools/heal_library.py --limit 10
    python tools/heal_library.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.asset_healer import heal_asset, HEALER_VERSION  # noqa: E402

LIBRARY_PATH = ROOT / "app" / "data" / "library.json"
BACKUP_PATH = ROOT / "app" / "data" / "library.json.bak_preheal"


def _resolve_abs(path: str) -> Path | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / path
    return p if p.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only-missing", action="store_true",
                    help="skip entries that already have healer_version")
    ap.add_argument("--category", default="",
                    help="only heal entries in this category")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N heals (0 = all)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print decisions, don't write library.json")
    ap.add_argument("--timeout", type=int, default=90,
                    help="per-asset blender timeout (s)")
    args = ap.parse_args()

    if not LIBRARY_PATH.exists():
        print(f"[HEAL] library not found: {LIBRARY_PATH}", file=sys.stderr)
        return 1

    data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "assets" in data:
        assets = data["assets"]
        schema_v2 = True
    elif isinstance(data, list):
        assets = data
        schema_v2 = False
    else:
        print(f"[HEAL] unexpected library shape: {type(data)}", file=sys.stderr)
        return 1

    if not args.dry_run:
        shutil.copy2(LIBRARY_PATH, BACKUP_PATH)
        print(f"[HEAL] backed up library to {BACKUP_PATH.name}", flush=True)

    stats = {
        "total":                len(assets),
        "attempted":            0,
        "provisional_ready":    0,
        "healed_with_warnings": 0,
        "skipped_already":      0,
        "skipped_missing_file": 0,
        "skipped_category":     0,
        "failed":               0,
        "by_issue":             {},
        "by_shape":             {},
    }

    t_start = time.time()
    cat_filter = (args.category or "").lower()
    limit = args.limit or 0
    count_done = 0

    for i, entry in enumerate(assets):
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id", f"idx_{i}")

        if cat_filter and str(entry.get("category") or "").lower() != cat_filter:
            stats["skipped_category"] += 1
            continue
        if args.only_missing and entry.get("healer_version"):
            stats["skipped_already"] += 1
            continue

        path_raw = entry.get("path", "")
        abs_path = _resolve_abs(str(path_raw))
        if abs_path is None:
            print(f"[HEAL] {i+1}/{len(assets)} {eid} MISSING: {path_raw}", flush=True)
            stats["skipped_missing_file"] += 1
            continue

        print(f"[HEAL] {i+1}/{len(assets)} healing: {eid}", flush=True)
        try:
            healed = heal_asset(
                str(abs_path),
                proposed_category=entry.get("category"),
                inspector_timeout=args.timeout,
            )
        except Exception as e:
            print(f"[HEAL] {eid} crashed: {e}", flush=True)
            stats["failed"] += 1
            continue

        stats["attempted"] += 1

        if not args.dry_run:
            for key, value in healed.items():
                entry[key] = value

        if healed.get("provisional_ready"):
            stats["provisional_ready"] += 1
        elif healed.get("heal_notes"):
            stats["healed_with_warnings"] += 1
        if healed.get("orientation_issue"):
            k = str(healed["orientation_issue"])
            stats["by_issue"][k] = stats["by_issue"].get(k, 0) + 1
        if healed.get("material_issues"):
            stats["by_issue"]["material_issues"] = (
                stats["by_issue"].get("material_issues", 0) + 1
            )
        shape = healed.get("shape_class") or "none"
        stats["by_shape"][shape] = stats["by_shape"].get(shape, 0) + 1

        count_done += 1
        # Checkpoint every 20 heals
        if not args.dry_run and count_done % 20 == 0:
            LIBRARY_PATH.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
            print(f"[HEAL] checkpoint saved at {count_done} heals", flush=True)

        if limit and count_done >= limit:
            print(f"[HEAL] --limit {limit} reached, stopping", flush=True)
            break

    if not args.dry_run:
        LIBRARY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("[HEAL] final write to library.json complete", flush=True)

    elapsed = time.time() - t_start
    print()
    print("=" * 60)
    print(f"[HEAL] COMPLETE in {elapsed:.1f}s (healer v{HEALER_VERSION})")
    print(f"[HEAL] total entries:      {stats['total']}")
    print(f"[HEAL] attempted:          {stats['attempted']}")
    print(f"[HEAL] provisional ready:  {stats['provisional_ready']}")
    print(f"[HEAL] with warnings:      {stats['healed_with_warnings']}")
    print(f"[HEAL] failed:             {stats['failed']}")
    print(f"[HEAL] skipped (file):     {stats['skipped_missing_file']}")
    print(f"[HEAL] skipped (already):  {stats['skipped_already']}")
    print(f"[HEAL] skipped (category): {stats['skipped_category']}")
    print("[HEAL] issues:")
    for k, v in sorted(stats["by_issue"].items(), key=lambda kv: -kv[1]):
        print(f"[HEAL]   {k}: {v}")
    print("[HEAL] shape classes:")
    for k, v in sorted(stats["by_shape"].items(), key=lambda kv: -kv[1]):
        print(f"[HEAL]   {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
