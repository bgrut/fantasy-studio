#!/usr/bin/env python3
"""
register_existing_assets.py
===========================
Round 12 — bridge between the legacy registry and the curated catalog.

The project already has 48 hand-curated models tracked in
``assets/manifests/asset_registry.json`` (see Round 1-9 work) plus a
bunch of HDRIs sitting on disk. The Round 11 curated_resolver only
reads ``assets/curated/catalog.json`` though — so without this bridge
the resolver sees an empty library and falls back to Sketchfab even
when we already own a perfect local model.

This script merges three sources into ``assets/curated/catalog.json``:

  1. ``assets/manifests/asset_registry.json`` — preferred. Each entry
     already carries tags, type, species, is_rigged, scale_class.
  2. Free-floating ``.blend`` / ``.glb`` / ``.gltf`` under
     ``assets/cache/models/`` that the registry doesn't mention.
     Category and keywords are inferred from the path.
  3. Free-floating ``.hdr`` / ``.exr`` under ``assets/hdri/`` and
     ``assets/hdris/``.

Existing curated entries written by ``tools/curate_asset.py`` are
PRESERVED. Entries with a ``source`` of ``"existing"`` (the marker
this script writes) are refreshed each run so re-running picks up new
files; entries without that marker are left untouched.

Usage
-----
    python tools/register_existing_assets.py

Re-run any time after dropping new files into the cache. It is safe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CATALOG_PATH = _PROJECT_ROOT / "assets" / "curated" / "catalog.json"
_REGISTRY_PATH = _PROJECT_ROOT / "assets" / "manifests" / "asset_registry.json"
_MODEL_DIRS = [
    _PROJECT_ROOT / "assets" / "cache" / "models",
]
_HDRI_DIRS = [
    _PROJECT_ROOT / "assets" / "hdri",
    _PROJECT_ROOT / "assets" / "hdris",
]
_MODEL_EXTS = ("*.blend", "*.glb", "*.gltf")
_HDRI_EXTS = ("*.hdr", "*.exr")

# Skip Sketchfab UID dump folders by default — they have no human-readable
# name and would clutter the catalog with "scene" entries.
_SKIP_DIR_PARTS = {"sketchfab"}

# Map registry "type" → curated "category".
_TYPE_TO_CATEGORY = {
    "animal":      "animal",
    "character":   "character",
    "humanoid":    "character",
    "person":      "character",
    "vehicle":     "vehicle",
    "car":         "vehicle",
    "building":    "environment",
    "environment": "environment",
    "product":     "prop",
    "prop":        "prop",
    "sign":        "prop",
}


# ═══════════════════════════════════════════════════════════════════════════
# Round 13 — tested-asset whitelist
# ═══════════════════════════════════════════════════════════════════════════
#
# THE RULE: only hand-picked template assets are marked ``tested: true``.
# Everything else (random Sketchfab cache leftovers) goes in with
# ``tested: false`` so the curated injector in asset_agent.py leaves
# them alone.
#
# Heuristics used:
#   - IDs that start with ``sketchfab_<32-hex-uid>`` are never tested.
#   - Explicit allow list ``_TESTED_IDS`` for the hand-curated template
#     models that power car_hero / street_scene / scenic_landscape /
#     ocean_scene / product_scene.
#   - HDRIs are always tested (they're hand-picked PolyHaven files).

_TESTED_IDS: set[str] = {
    # vehicles — powers car_hero template
    "ferrari_01", "bmw_01",
    # characters / animals — powers street_scene (cat) and ocean_scene (whale/ocean_character)
    "cat_02", "cat_03", "cat_04", "cat_05",
    "ocean_character_01", "ocean_character_02", "ocean_character_03",
    # environments — powers scenic_landscape / ocean_scene
    "mountain_01", "glacial_lake_01", "ocean_01",
    # buildings — powers city_loop / street_scene
    "city_01", "city_02", "city_03",
    # products — powers product_scene / product_pedestal
    "product_01",
}

_UNTESTED_ID_PREFIXES = ("sketchfab_",)


def _is_tested_id(asset_id: str, category: str = "") -> bool:
    """Decide whether a catalog entry qualifies as a tested template asset."""
    if not asset_id:
        return False
    aid = asset_id.lower()
    if any(aid.startswith(p) for p in _UNTESTED_ID_PREFIXES):
        return False
    if aid in _TESTED_IDS:
        return True
    # HDRIs registered via this script are always hand-picked.
    if category == "hdri":
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[REGISTER] cannot read {path}: {e}", flush=True)
        return None


def _rel_to_root(path: Path) -> str:
    """Catalog stores paths relative to project root, forward-slash style."""
    try:
        return path.resolve().relative_to(_PROJECT_ROOT).as_posix()
    except Exception:
        return path.as_posix()


def _norm_path(s: str) -> str:
    return str(s).replace("\\", "/").lower()


def _infer_category_from_path(rel_path: str) -> str:
    p = _norm_path(rel_path)
    if "/characters/" in p:
        if any(k in p for k in ("cat", "dog", "bear", "horse", "tiger", "wolf", "deer", "fox", "lion", "ocean")):
            return "animal"
        return "character"
    if "/cars/" in p or "/vehicles/" in p or "ferrari" in p:
        return "vehicle"
    if "/city/" in p or "/environments/" in p or "/buildings/" in p:
        return "environment"
    if "/products/" in p:
        return "prop"
    if "/props/" in p:
        return "prop"
    return "prop"


def _infer_subcategory(stem: str) -> str:
    s = stem.lower().replace("-", "_")
    # Strip trailing _NN counters: "cat_02" -> "cat".
    parts = s.split("_")
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return "_".join(parts) if parts else s


def _generate_keywords(stem: str, category: str, subcategory: str = "") -> list[str]:
    raw = stem.lower().replace("-", " ").replace("_", " ").split()
    words = {w for w in raw if len(w) > 2 and not w.isdigit()}
    if category:
        words.add(category)
    if subcategory:
        for piece in subcategory.split("_"):
            if len(piece) > 2:
                words.add(piece)
    return sorted(words)


def _infer_hdri_subcategory(stem: str) -> str:
    s = stem.lower()
    if any(w in s for w in ("sunset", "golden", "warm")):
        return "sunset"
    if any(w in s for w in ("night", "moon", "city_night", "qwantani_night")):
        return "night"
    if any(w in s for w in ("forest", "tree", "canopy", "jungle")):
        return "forest"
    if any(w in s for w in ("studio", "neutral", "white", "softbox")):
        return "studio"
    if any(w in s for w in ("cloud", "overcast")):
        return "overcast"
    if any(w in s for w in ("desert", "sand")):
        return "desert"
    if any(w in s for w in ("ocean", "beach", "sea", "dock", "shanghai_bund")):
        return "ocean"
    if any(w in s for w in ("city", "street", "urban")):
        return "city"
    return "day"


# ═══════════════════════════════════════════════════════════════════════════
# Source 1 — registry
# ═══════════════════════════════════════════════════════════════════════════

def _entries_from_registry() -> list[dict]:
    data = _read_json(_REGISTRY_PATH)
    if not isinstance(data, dict):
        return []
    entries: list[dict] = []

    for m in data.get("models") or []:
        if not isinstance(m, dict):
            continue
        path = m.get("path")
        if not path:
            continue
        abs_path = (_PROJECT_ROOT / path).resolve()
        if not abs_path.exists():
            print(f"[REGISTER] registry entry {m.get('id')!r} missing on disk: {path}",
                  flush=True)
            continue

        type_ = str(m.get("type") or "prop").lower()
        category = _TYPE_TO_CATEGORY.get(type_, "prop")
        subcat = m.get("species") or _infer_subcategory(Path(path).stem)
        tags = list(m.get("tags") or [])
        keywords = sorted({*tags, *_generate_keywords(Path(path).stem, category, str(subcat))})

        asset_id = str(m.get("id") or Path(path).stem)
        entries.append({
            "id":            asset_id,
            "name":          asset_id.replace("_", " ").title(),
            "path":          _rel_to_root(abs_path),
            "category":      category,
            "subcategory":   str(subcat) if subcat else "",
            "keywords":      keywords,
            "has_armature":  bool(m.get("is_rigged", False)),
            "animations":    {},
            "scale_class":   m.get("scale_class") or "medium",
            "license":       m.get("license") or "unknown",
            "face_count":    int(m.get("face_count") or 0),
            "tested":        _is_tested_id(asset_id, category),
            "source":        "existing",
            "registry_type": type_,
        })

    for h in data.get("hdris") or []:
        if not isinstance(h, dict):
            continue
        path = h.get("path")
        if not path:
            continue
        abs_path = (_PROJECT_ROOT / path).resolve()
        if not abs_path.exists():
            continue
        stem = Path(path).stem
        subcat = _infer_hdri_subcategory(stem)
        tags = list(h.get("tags") or [])
        keywords = sorted({*tags, *_generate_keywords(stem, "hdri", subcat)})
        hdri_id = f"hdri_{(h.get('id') or stem).lower()}"
        entries.append({
            "id":          hdri_id,
            "name":        stem.replace("_", " ").title(),
            "path":        _rel_to_root(abs_path),
            "category":    "hdri",
            "subcategory": subcat,
            "keywords":    keywords,
            "tested":      _is_tested_id(hdri_id, "hdri"),
            "source":      "existing",
        })

    return entries


# ═══════════════════════════════════════════════════════════════════════════
# Source 2 — disk scan (gap-filler)
# ═══════════════════════════════════════════════════════════════════════════

def _entries_from_disk(known_paths: set[str]) -> list[dict]:
    entries: list[dict] = []

    for model_dir in _MODEL_DIRS:
        if not model_dir.exists():
            continue
        for ext in _MODEL_EXTS:
            for f in model_dir.rglob(ext):
                # Skip Sketchfab dump folders.
                parts_lower = {p.lower() for p in f.parts}
                if parts_lower & _SKIP_DIR_PARTS:
                    continue
                rel = _rel_to_root(f)
                if rel in known_paths:
                    continue
                stem = f.stem
                category = _infer_category_from_path(rel)
                subcat = _infer_subcategory(stem)
                entries.append({
                    "id":           stem.lower().replace(" ", "_"),
                    "name":         stem.replace("_", " ").title(),
                    "path":         rel,
                    "category":     category,
                    "subcategory":  subcat,
                    "keywords":     _generate_keywords(stem, category, subcat),
                    "has_armature": False,
                    "animations":   {},
                    "scale_class":  "medium",
                    "license":      "unknown",
                    "tested":       False,
                    "source":       "existing",
                })
                known_paths.add(rel)

    for hdri_dir in _HDRI_DIRS:
        if not hdri_dir.exists():
            continue
        for ext in _HDRI_EXTS:
            for f in hdri_dir.glob(ext):
                rel = _rel_to_root(f)
                if rel in known_paths:
                    continue
                stem = f.stem
                subcat = _infer_hdri_subcategory(stem)
                hdri_id = f"hdri_{stem.lower()}"
                entries.append({
                    "id":          hdri_id,
                    "name":        stem.replace("_", " ").title(),
                    "path":        rel,
                    "category":    "hdri",
                    "subcategory": subcat,
                    "keywords":    _generate_keywords(stem, "hdri", subcat),
                    "tested":      _is_tested_id(hdri_id, "hdri"),
                    "source":      "existing",
                })
                known_paths.add(rel)

    return entries


# ═══════════════════════════════════════════════════════════════════════════
# Catalog merge — preserve curate_asset.py entries
# ═══════════════════════════════════════════════════════════════════════════

def _load_existing_catalog() -> dict:
    data = _read_json(_CATALOG_PATH)
    if not isinstance(data, dict) or not isinstance(data.get("assets"), list):
        return {"version": 1, "assets": []}
    return data


def _merge(existing_catalog: dict, new_entries: list[dict]) -> dict:
    """
    Keep entries authored by ``curate_asset.py`` (no source=='existing'
    marker) untouched. Replace prior ``source=='existing'`` entries
    with the freshly-scanned set.
    """
    preserved = [
        a for a in (existing_catalog.get("assets") or [])
        if isinstance(a, dict) and str(a.get("source") or "").lower() != "existing"
    ]
    # De-dupe new entries against preserved by id (curated wins).
    preserved_ids = {str(a.get("id")).lower() for a in preserved if a.get("id")}
    deduped = [a for a in new_entries if str(a.get("id")).lower() not in preserved_ids]

    merged = preserved + deduped
    merged.sort(key=lambda a: (a.get("category", ""), a.get("subcategory", ""), a.get("id", "")))

    return {
        "version":      1,
        "generated_at": existing_catalog.get("generated_at"),
        "assets":       merged,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    print(f"[REGISTER] project root: {_PROJECT_ROOT}", flush=True)
    print(f"[REGISTER] catalog path: {_CATALOG_PATH}", flush=True)

    registry_entries = _entries_from_registry()
    print(f"[REGISTER] from asset_registry.json: {len(registry_entries)}", flush=True)

    known_paths = {e["path"] for e in registry_entries if e.get("path")}
    disk_entries = _entries_from_disk(known_paths)
    print(f"[REGISTER] from disk scan (extras):  {len(disk_entries)}", flush=True)

    new_entries = registry_entries + disk_entries

    existing = _load_existing_catalog()
    preserved_count = sum(
        1 for a in (existing.get("assets") or [])
        if isinstance(a, dict) and str(a.get("source") or "").lower() != "existing"
    )
    print(f"[REGISTER] preserving curated entries: {preserved_count}", flush=True)

    merged = _merge(existing, new_entries)

    _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CATALOG_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    by_cat: dict[str, int] = {}
    for a in merged["assets"]:
        c = a.get("category", "unknown")
        by_cat[c] = by_cat.get(c, 0) + 1

    print("=" * 72)
    print(f"[REGISTER] wrote {_CATALOG_PATH}")
    print(f"  total assets in catalog: {len(merged['assets'])}")
    for cat, n in sorted(by_cat.items()):
        print(f"    {cat:14s} {n}")
    print("=" * 72)

    # Best-effort: invalidate the resolver cache if the backend is in-process.
    try:
        from app.services.curated_resolver import invalidate_catalog_cache
        invalidate_catalog_cache()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
