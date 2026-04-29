#!/usr/bin/env python3
"""
build_catalog.py
================
Scan ``assets/curated/**/metadata.json`` and regenerate
``assets/curated/catalog.json``. Useful after manually editing a
metadata file, or after copying curated folders between machines.

Usage
-----
    python tools/build_catalog.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CURATED_ROOT = _PROJECT_ROOT / "assets" / "curated"
_CATALOG_PATH = _CURATED_ROOT / "catalog.json"


def _load_metadata(path: Path) -> dict | None:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"[CATALOG] skip (read error) {path}: {e}", flush=True)
        return None
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[CATALOG] skip (json error) {path}: {e}", flush=True)
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("id"):
        print(f"[CATALOG] skip (no id) {path}", flush=True)
        return None
    return data


def main() -> int:
    if not _CURATED_ROOT.exists():
        print(f"[CATALOG] curated root does not exist: {_CURATED_ROOT}", flush=True)
        return 1

    assets: list[dict] = []
    for metadata_file in _CURATED_ROOT.rglob("metadata.json"):
        data = _load_metadata(metadata_file)
        if data is None:
            continue
        # Sanity check: the file it points at should actually exist.
        asset_path = data.get("path")
        if asset_path:
            abs_path = (_PROJECT_ROOT / asset_path).resolve()
            if not abs_path.exists():
                print(
                    f"[CATALOG] WARNING: catalog entry {data['id']!r} "
                    f"references missing file {asset_path!r} — keeping anyway",
                    flush=True,
                )
        assets.append(data)

    assets.sort(key=lambda a: (a.get("category", ""), a.get("subcategory", ""), a.get("id", "")))

    catalog = {
        "version": 1,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "assets": assets,
    }
    _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CATALOG_PATH.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 72)
    print(f"[CATALOG] wrote {_CATALOG_PATH}")
    print(f"  total assets: {len(assets)}")
    by_cat: dict[str, int] = {}
    for a in assets:
        cat = a.get("category", "unknown")
        by_cat[cat] = by_cat.get(cat, 0) + 1
    for cat, count in sorted(by_cat.items()):
        print(f"    {cat:12s} {count}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
