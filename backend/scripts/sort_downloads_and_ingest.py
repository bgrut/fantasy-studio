#!/usr/bin/env python3
"""
sort_downloads_and_ingest.py
============================
One-shot: sort today's downloads into assets/inbox/{category}/ folders
and immediately run the bulk ingest tool.

Workflow:
    1. Scan ``C:\\Users\\bgrut\\Downloads\\`` for files modified today.
    2. Classify each file by filename substring (lowercase).
    3. Move (not copy) into the matching inbox category folder.
       Unknown filenames go to ``assets/inbox/_unsorted/`` for review.
    4. Run ``python scripts/ingest_assets.py --tier tested``.
    5. Report library.json entry counts before/after.

Usage:
    python scripts/sort_downloads_and_ingest.py --dry-run
    python scripts/sort_downloads_and_ingest.py
    python scripts/sort_downloads_and_ingest.py --downloads D:/other/path
    python scripts/sort_downloads_and_ingest.py --date 2026-04-21
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOWNLOADS = Path(os.path.expanduser("~")) / "Downloads"
INBOX = ROOT / "assets" / "inbox"
LIBRARY_PATH = ROOT / "app" / "data" / "library.json"

# Classification rules — ordered; FIRST MATCH WINS.  Each rule is
# (dest_folder_name, [substring patterns]).  Matching is lowercase
# substring against the filename (basename).  The "exclude" lists
# prevent false positives like "wildcat" hitting the cats bucket.
_RULES: list = [
    ("hdris",        None),                                  # extension-based; see code
    ("cats", {
        "include":   ["cat", "kitten", "tiger", "lion"],
        "exclude":   ["wildcat", "category", "dandelion", "scatter"],
    }),
    ("dogs", {
        "include":   ["dog", "puppy"],
        "exclude":   ["godzilla"],  # doesn't match but be safe
    }),
    ("environments", {
        "include": [
            "landscape", "terrain", "skybox", "rooftop", "cityscape",
            "castle", "houses", "city_at_night", "mountain_road",
            "thunderstorm", "hyperspace", "iceland", "canyon", "glacier",
            "mossygrassy", "fantasy_landscape", "desert_landscape",
            "winter_landscape",
        ],
        "exclude": [],
    }),
    ("props", {
        "include":   ["flower", "bush", "sunflower", "margarita"],
        "exclude":   [],
    }),
    ("vehicles", {
        "include": [
            "ferrari", "porsche", "lambo", "bugatti", "mclaren", "bmw",
            "audi", "toyota", "ford", "aston", "mustang", "corvette",
            "mercedes", "nissan", "tesla", "chevrolet", "honda",
            "racing_car", "sportback", "f1",
            "car", "_gt_",
        ],
        "exclude":   [],
    }),
    ("animals", {
        "include": [
            "eagle", "lizard", "horse", "bear", "whale", "rhino",
            "hyena", "goat", "rabbit", "crocodile", "rooster", "wolf",
            "deer", "godzilla", "sperm_whale", "polar_bear", "komodo",
        ],
        "exclude":   [],
    }),
]

_HDRI_EXTS = (".exr", ".hdr")
_SUPPORTED_EXTS = (".glb", ".gltf", ".blend", ".fbx", ".obj", ".zip", ".exr", ".hdr")


def _classify(filename: str) -> str:
    """Return the inbox folder name (category) for a filename, or '_unsorted'."""
    name = filename.lower()
    ext = Path(name).suffix

    # HDRI by extension first
    if ext in _HDRI_EXTS:
        return "hdris"

    for folder, cfg in _RULES:
        if cfg is None:
            continue  # hdris handled above
        if any(x in name for x in cfg.get("exclude", [])):
            continue
        if any(kw in name for kw in cfg.get("include", [])):
            return folder

    return "_unsorted"


def _files_modified_on_date(folder: Path, target_date: _dt.date) -> list:
    """Return files in folder (non-recursive) whose mtime date matches target_date."""
    if not folder.exists():
        return []
    out: list = []
    for item in folder.iterdir():
        if not item.is_file():
            continue
        if item.suffix.lower() not in _SUPPORTED_EXTS:
            continue
        try:
            mtime = _dt.date.fromtimestamp(item.stat().st_mtime)
            if mtime == target_date:
                out.append(item)
        except Exception:
            continue
    return sorted(out, key=lambda p: p.name.lower())


def _load_library_count() -> int:
    try:
        if not LIBRARY_PATH.exists():
            return 0
        data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
        return len(data.get("assets", []) or [])
    except Exception as e:
        print(f"[SORT] warning: couldn't read library.json count: {e}", flush=True)
        return -1


def _is_already_in_inbox(path: Path) -> bool:
    """True if the path is already inside assets/inbox (don't re-process)."""
    try:
        path.relative_to(INBOX)
        return True
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="show the sort breakdown without moving files")
    parser.add_argument("--downloads", default=str(DEFAULT_DOWNLOADS),
                        help="override source downloads folder")
    parser.add_argument("--date", default=None,
                        help="override target date (YYYY-MM-DD). defaults to today.")
    parser.add_argument("--skip-ingest", action="store_true",
                        help="sort only; don't auto-run ingest afterwards")
    parser.add_argument("--tier", default="tested",
                        choices=["tested", "unverified"],
                        help="quality tier for ingest (default: tested)")
    args = parser.parse_args()

    downloads = Path(args.downloads)
    if not downloads.exists():
        print(f"[SORT] ERROR: downloads folder not found: {downloads}", flush=True)
        sys.exit(1)

    if args.date:
        try:
            target_date = _dt.date.fromisoformat(args.date)
        except ValueError:
            print(f"[SORT] ERROR: bad date format: {args.date} (want YYYY-MM-DD)", flush=True)
            sys.exit(1)
    else:
        target_date = _dt.date.today()

    print(f"[SORT] scanning {downloads} for files modified on {target_date.isoformat()}")

    files = _files_modified_on_date(downloads, target_date)
    # Exclude anything already inside the inbox (handles accidental re-runs)
    files = [f for f in files if not _is_already_in_inbox(f)]

    if not files:
        print(f"[SORT] no files from {target_date.isoformat()} "
              f"in {downloads} (supported: {_SUPPORTED_EXTS})", flush=True)
        return

    print(f"[SORT] scanned {downloads} — {len(files)} files from {target_date.isoformat()}")

    # Classify
    category_files: dict = {}
    for f in files:
        cat = _classify(f.name)
        category_files.setdefault(cat, []).append(f)

    # Pre-ingest summary
    known_order = [
        "cats", "dogs", "animals", "vehicles", "environments", "props", "hdris", "_unsorted"
    ]
    for cat in known_order:
        items = category_files.get(cat, [])
        print(f"[SORT]   {cat + '/':<16} {len(items):>3} files")
    for cat, items in category_files.items():
        if cat not in known_order:
            print(f"[SORT]   {cat + '/':<16} {len(items):>3} files")
    print(f"[SORT] total sorted: {sum(len(v) for v in category_files.values())}")

    # Show _unsorted contents so Brandon can review
    if category_files.get("_unsorted"):
        print(f"[SORT] _unsorted/ contents (review manually):")
        for f in category_files["_unsorted"]:
            print(f"[SORT]     {f.name}")

    if args.dry_run:
        print("[SORT] DRY RUN — no files moved.")
        print("[SORT]   Per-file classification:")
        for cat in known_order:
            for f in category_files.get(cat, []):
                print(f"[SORT]     {f.name} -> {cat}/")
        return

    # Before counts
    before_count = _load_library_count()
    print(f"[SORT] library.json entries before: {before_count}")

    # ── Move files ───────────────────────────────────────────────────
    moved = 0
    move_errors: list = []
    for cat, items in category_files.items():
        dest_dir = INBOX / cat
        dest_dir.mkdir(parents=True, exist_ok=True)
        for src in items:
            dest = dest_dir / src.name
            try:
                if dest.exists():
                    # Name collision — add timestamp suffix
                    stem = dest.stem
                    suf = dest.suffix
                    dest = dest_dir / f"{stem}_{int(src.stat().st_mtime)}{suf}"
                shutil.move(str(src), str(dest))
                print(f"[SORT] {src.name} -> {cat}/")
                moved += 1
            except Exception as e:
                move_errors.append((src.name, str(e)))
                print(f"[SORT] ERROR: {src.name} — {e}", flush=True)
                print(traceback.format_exc(), flush=True)

    print(f"[SORT] moved {moved}/{len(files)} files")
    if move_errors:
        print(f"[SORT] errors: {len(move_errors)}")

    if args.skip_ingest:
        print("[SORT] --skip-ingest set; not running ingest")
        return

    # ── Run the ingest tool ──────────────────────────────────────────
    print(f"[SORT] invoking ingest: scripts/ingest_assets.py --tier {args.tier}")
    try:
        # Use the same Python interpreter that's running us
        proc = subprocess.run(
            [sys.executable, "scripts/ingest_assets.py", "--tier", args.tier],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # Stream combined output
        combined = (proc.stdout or "") + (proc.stderr or "")
        ingest_lines = []
        for line in combined.splitlines():
            if "[INGEST]" in line:
                ingest_lines.append(line)
                print(line, flush=True)
        if proc.returncode != 0:
            print(f"[SORT] ingest exited with code {proc.returncode}", flush=True)
    except Exception as e:
        print(f"[SORT] ERROR running ingest: {e}", flush=True)
        print(traceback.format_exc(), flush=True)

    # ── Final library count ──────────────────────────────────────────
    after_count = _load_library_count()
    delta = after_count - before_count if before_count >= 0 else "?"
    print(f"[SORT] library.json entries: {before_count} -> {after_count} (+{delta})")


if __name__ == "__main__":
    main()
