#!/usr/bin/env python3
"""
migrate_to_unified_library.py
=============================
One-shot migration that folds three competing asset stores into one
unified source of truth at ``app/data/library.json``.

Stores consolidated:
    1. assets/manifests/asset_registry.json  (local file registry, Store 1)
    2. app/data/curated_assets.json          (keyword-indexed legacy, Store 2)
    3. app/data/library.json                 (existing rich entries, Store 3)

Rules:
    - Dedup by path. Merge metadata when two stores reference the same file.
    - Preference when merging: existing library.json (richest) > curated > registry.
    - Local registry entries migrate with ``quality=tested`` (they're files
      that already work) and ``source=curated``.
    - Curated-list entries with explicit ``tested=True`` migrate as
      ``quality=tested``; otherwise ``quality=unverified``.
    - ``needs_curation`` entries in curated_assets.json are skipped (they
      are placeholders, not real assets).
    - Vehicle keyword synonyms that all route to ``ferrari_01`` are
      deduped to a single ferrari_01 entry with brand='ferrari'.
    - Writes ``library.json.bak_premigration`` before overwriting.

Usage:
    python scripts/migrate_to_unified_library.py
    python scripts/migrate_to_unified_library.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "assets" / "manifests" / "asset_registry.json"
CURATED_PATH = ROOT / "app" / "data" / "curated_assets.json"
LIBRARY_PATH = ROOT / "app" / "data" / "library.json"
BACKUP_PATH = ROOT / "app" / "data" / "library.json.bak_premigration"


_BRAND_TOKENS = {
    "porsche", "ferrari", "bmw", "toyota", "ford", "chevrolet", "mercedes",
    "audi", "lamborghini", "bugatti", "mclaren", "aston", "nissan", "honda",
    "mazda", "tesla", "dodge", "kia", "hyundai", "volkswagen", "jaguar",
}
_MODEL_TOKENS = {
    "911", "718", "gt3", "m3", "m4", "m5", "supra", "miata", "mustang",
    "corvette", "camaro", "camry", "civic", "f150", "huracan", "aventador",
    "cayenne", "cayman", "taycan", "f40", "f50", "enzo", "488",
}

_CATEGORY_FROM_TYPE = {
    "vehicle":   "vehicle",
    "car":       "vehicle",
    "truck":     "vehicle",
    "character": "character",
    "animal":    "character",
    "creature":  "character",
    "bird":      "character",
    "building":  "environment",
    "environment": "environment",
    "prop":      "prop",
    "product":   "prop",
}

_SUBJECT_TAG_CATEGORIES = {
    "cat":     ["cat", "feline", "animal", "pet"],
    "dog":     ["dog", "canine", "animal", "pet"],
    "horse":   ["horse", "equine", "animal"],
    "bear":    ["bear", "mammal", "animal", "large"],
    "eagle":   ["eagle", "bird", "raptor", "animal"],
    "ferrari": ["ferrari", "car", "vehicle", "sports_car", "luxury"],
    "bmw":     ["bmw", "car", "vehicle", "luxury"],
    "porsche": ["porsche", "car", "vehicle", "sports_car", "luxury"],
    "monkey":  ["monkey", "primate", "animal"],
    "robot":   ["robot", "mechanical", "character"],
    "dolphin": ["dolphin", "aquatic", "animal", "mammal"],
    "ocean":   ["ocean", "water", "environment"],
    "city":    ["city", "building", "urban", "environment"],
    "elephant": ["elephant", "mammal", "animal", "large"],
}


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[MIGRATE] warning: failed to read {path}: {e}", file=sys.stderr)
        return default


def _extract_subject_from_path(path: str) -> tuple[str, list, list, str | None, str | None]:
    """Return (subject, subject_tags, visual_descriptors, brand, model) from a path."""
    p = Path(path)
    stem = p.stem.lower()
    # Strip common suffixes like _01, _02, .001
    import re
    stem_clean = re.sub(r"_\d+$|\.\d+$", "", stem)
    tokens = stem_clean.replace("-", "_").split("_")
    tokens = [t for t in tokens if t and len(t) > 1]

    brand = next((t for t in tokens if t in _BRAND_TOKENS), None)
    model = next((t for t in tokens if t in _MODEL_TOKENS or t.isdigit()), None)

    # Subject = first non-brand meaningful token
    subject = None
    for t in tokens:
        if t not in _BRAND_TOKENS and t not in _MODEL_TOKENS:
            subject = t
            break
    if subject is None and tokens:
        subject = tokens[0]
    if subject is None:
        subject = stem_clean

    # Category-hint tags
    tags = []
    if subject in _SUBJECT_TAG_CATEGORIES:
        tags.extend(_SUBJECT_TAG_CATEGORIES[subject])
    elif brand and brand in _SUBJECT_TAG_CATEGORIES:
        tags.extend(_SUBJECT_TAG_CATEGORIES[brand])
    tags.extend(tokens)
    tags = sorted(set(t for t in tags if t and t not in ("blend", "gltf", "fbx")))

    # Folder category (characters/ vehicles/ animals/)
    try:
        parent = p.parent.name.lower()
        if parent in ("vehicles", "cars"):
            tags = sorted(set(tags + ["vehicle", "car"]))
        elif parent in ("characters", "animals"):
            tags = sorted(set(tags + ["character", "animal"]))
        elif parent == "environments":
            tags = sorted(set(tags + ["environment"]))
        elif parent == "city":
            tags = sorted(set(tags + ["city", "urban", "environment"]))
    except Exception:
        pass

    # Visual descriptors: colors + styles in filename
    COLORS = ("orange", "black", "white", "red", "blue", "green", "yellow",
              "brown", "grey", "gray", "silver", "golden", "tabby", "ginger")
    STYLES = ("realistic", "cartoon", "stylized", "low_poly", "photoreal")
    descriptors = [t for t in tokens if t in COLORS or t in STYLES]

    return subject, tags, descriptors, brand, model


def _category_from_type(type_str: str, path: str) -> str:
    t = (type_str or "").lower()
    if t in _CATEGORY_FROM_TYPE:
        return _CATEGORY_FROM_TYPE[t]
    parent = Path(path).parent.name.lower() if path else ""
    if parent in ("vehicles", "cars"):
        return "vehicle"
    if parent in ("characters", "animals"):
        return "character"
    if parent == "environments":
        return "environment"
    return "unknown"


def _entry_from_registry_model(m: dict) -> dict:
    """Convert an asset_registry.json model entry into unified library schema."""
    now = int(time.time())
    path = str(m.get("path") or "")
    subject, subject_tags, visual_descs, brand, model = _extract_subject_from_path(path)
    # Registry has its own tags — merge them
    reg_tags = [str(t).lower() for t in (m.get("tags") or [])]
    subject_tags = sorted(set(subject_tags + reg_tags))
    category = _category_from_type(str(m.get("type") or ""), path)
    eid = f"lib_registry_{m.get('id', Path(path).stem)}"
    return {
        "id":                 eid,
        "path":               path,
        "subject":            subject,
        "subject_tags":       subject_tags,
        "visual_descriptors": visual_descs,
        "category":           category,
        "scale_class":        m.get("scale_class", "medium"),
        "source":             "curated",  # these .blend files work → they're curated
        "quality":            "tested",
        "use_count":          0,
        "last_used_at":       None,
        "added_at":           now,
        "brand":              brand,
        "model":              model,
        "notes":              f"migrated from asset_registry.json (id={m.get('id')})",
        "registry_metadata":  {
            "blend_kind":  m.get("blend_kind"),
            "blend_name":  m.get("blend_name"),
            "is_rigged":   bool(m.get("is_rigged")),
            "has_animation": bool(m.get("has_animation")),
            "species":     m.get("species"),
        },
    }


def _entry_from_curated(category: str, keyword: str, entry: dict) -> dict | None:
    """Convert a curated_assets.json keyword entry into unified schema.
    Returns None for ``needs_curation`` / placeholder entries."""
    if not isinstance(entry, dict):
        return None
    now = int(time.time())

    if entry.get("use_local"):
        local_key = str(entry.get("local_key") or "")
        if not local_key:
            return None
        # Resolve local_key to a path we know about.  Most are .blend files
        # under assets/cache/models/{category}/.
        candidate_paths = [
            ROOT / "assets" / "cache" / "models" / "vehicles" / f"{local_key}.blend",
            ROOT / "assets" / "cache" / "models" / "characters" / f"{local_key}.blend",
            ROOT / "assets" / "cache" / "models" / "animals" / f"{local_key}.blend",
        ]
        resolved = next((p for p in candidate_paths if p.exists()), None)
        path = str(resolved.relative_to(ROOT)) if resolved else f"assets/cache/models/{category}/{local_key}.blend"
        subject, subject_tags, visual_descs, brand, model = _extract_subject_from_path(path)
        subject = keyword  # curated keyword is a stronger subject label
        eid = f"lib_curated_{local_key}_{keyword.replace(' ', '_')}"
        return {
            "id":                 eid,
            "path":               path,
            "subject":            subject,
            "subject_tags":       sorted(set(subject_tags + [keyword])),
            "visual_descriptors": visual_descs,
            "category":           "vehicle" if category == "vehicles" else category.rstrip("s"),
            "scale_class":        "medium",
            "source":             "curated",
            "quality":            "tested" if resolved else "unverified",
            "use_count":          0,
            "last_used_at":       None,
            "added_at":           now,
            "brand":              brand,
            "model":              model,
            "notes":              f"migrated from curated_assets.json ({category}/{keyword})",
        }
    elif entry.get("use_sketchfab"):
        uid = str(entry.get("sketchfab_uid") or "")
        if not uid:
            return None
        # Sketchfab path follows the cache pattern
        path = f"assets/cache/models/sketchfab/{uid}.glb"
        subject = keyword
        tags = _SUBJECT_TAG_CATEGORIES.get(keyword, [keyword])
        eid = f"lib_curated_sketchfab_{keyword}_{uid[:8]}"
        return {
            "id":                 eid,
            "path":               path,
            "subject":            subject,
            "subject_tags":       sorted(set(tags + [keyword])),
            "visual_descriptors": [],
            "category":           category.rstrip("s") if category != "vehicles" else "vehicle",
            "scale_class":        "medium",
            "source":             "sketchfab",
            "quality":            "unverified",  # sketchfab entries not explicitly tested
            "use_count":          0,
            "last_used_at":       None,
            "added_at":           now,
            "brand":              None,
            "model":              None,
            "sketchfab_uid":      uid,
            "notes":              f"migrated from curated_assets.json sketchfab entry ({keyword})",
        }
    return None


def _load_existing_library() -> dict:
    data = _load_json(LIBRARY_PATH, {"version": 1, "assets": []})
    if not isinstance(data, dict):
        data = {"version": 1, "assets": []}
    data.setdefault("version", 1)
    data.setdefault("assets", [])
    return data


def _normalize_existing_entry(entry: dict) -> dict:
    """Ensure a round-5 library entry has all unified-schema fields."""
    e = dict(entry)
    # Legacy 'tested' boolean → 'quality' enum
    if "quality" not in e:
        e["quality"] = "tested" if e.get("tested") else "unverified"
    e.setdefault("category", "unknown")
    e.setdefault("brand", None)
    e.setdefault("model", None)
    e.setdefault("subject_tags", e.get("subject_tags") or [])
    e.setdefault("visual_descriptors", e.get("visual_descriptors") or [])
    e.setdefault("notes", e.get("notes") or "")
    e.setdefault("use_count", int(e.get("use_count", 0)))
    e.setdefault("added_at", int(e.get("first_rendered_ts") or time.time()))
    # last_used -> last_used_at
    if "last_used_at" not in e:
        e["last_used_at"] = e.get("last_rendered_ts")
    return e


def _merge_entries(existing: dict, new: dict) -> dict:
    """Merge two entries that share a path.  Preserves tested + use_count
    from whichever entry has them higher; unions tags."""
    merged = dict(existing)
    # Prefer the richer source: curated > sketchfab > objaverse > unknown
    SRC_RANK = {"curated": 4, "user_upload": 3, "sketchfab": 2, "objaverse": 1, "cached": 0}
    cur_rank = SRC_RANK.get(str(merged.get("source")), 0)
    new_rank = SRC_RANK.get(str(new.get("source")), 0)
    if new_rank > cur_rank:
        merged["source"] = new.get("source")

    # quality: "tested" wins
    if new.get("quality") == "tested" or merged.get("quality") == "tested":
        merged["quality"] = "tested"

    merged["use_count"] = max(
        int(merged.get("use_count", 0)), int(new.get("use_count", 0))
    )
    merged["subject_tags"] = sorted(set(
        (merged.get("subject_tags") or []) + (new.get("subject_tags") or [])
    ))
    merged["visual_descriptors"] = sorted(set(
        (merged.get("visual_descriptors") or []) + (new.get("visual_descriptors") or [])
    ))
    # Brand/model: prefer non-null
    if not merged.get("brand"):
        merged["brand"] = new.get("brand")
    if not merged.get("model"):
        merged["model"] = new.get("model")
    # Subject: prefer the shorter one (more canonical)
    ns, cs = new.get("subject") or "", merged.get("subject") or ""
    if ns and (not cs or (len(ns) < len(cs) and " " not in ns)):
        merged["subject"] = ns
    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("[MIGRATE] starting unified-library migration")

    # ── Load all three stores ────────────────────────────────────────
    registry = _load_json(REGISTRY_PATH, {"models": []})
    curated = _load_json(CURATED_PATH, {})
    library = _load_existing_library()

    registry_models = registry.get("models", []) or []
    print(f"[MIGRATE] loaded: registry={len(registry_models)} models, "
          f"curated={sum(len(v) for k,v in curated.items() if k != '_meta' and isinstance(v, dict))} entries, "
          f"library={len(library.get('assets', []))} existing")

    # ── Build unified entries ────────────────────────────────────────
    unified: dict[str, dict] = {}  # path -> entry
    counts = {"registry": 0, "curated": 0, "library_existing": 0, "deduped": 0}

    # 1. Existing library entries first (they have accumulated use_count)
    for entry in library.get("assets", []):
        if not isinstance(entry, dict):
            continue
        e = _normalize_existing_entry(entry)
        path = str(e.get("path") or "")
        if not path:
            continue
        if path in unified:
            unified[path] = _merge_entries(unified[path], e)
            counts["deduped"] += 1
        else:
            unified[path] = e
            counts["library_existing"] += 1

    # 2. Asset registry (local filesystem)
    for m in registry_models:
        e = _entry_from_registry_model(m)
        path = e["path"]
        if not path:
            continue
        if path in unified:
            unified[path] = _merge_entries(unified[path], e)
            counts["deduped"] += 1
        else:
            unified[path] = e
            counts["registry"] += 1

    # 3. Curated keyword-indexed legacy
    for cat, entries in curated.items():
        if cat in ("_meta", "needs_curation"):
            continue
        if not isinstance(entries, dict):
            continue
        for keyword, entry in entries.items():
            e = _entry_from_curated(cat, keyword, entry)
            if e is None:
                continue
            path = e["path"]
            if path in unified:
                unified[path] = _merge_entries(unified[path], e)
                counts["deduped"] += 1
            else:
                unified[path] = e
                counts["curated"] += 1

    total = len(unified)
    print(
        f"[MIGRATE] local_registry_found={counts['registry']}, "
        f"curated_migrated={counts['curated']}, "
        f"library_existing={counts['library_existing']}, "
        f"deduped={counts['deduped']}, total_unified={total}"
    )

    if args.dry_run:
        print("[MIGRATE] DRY RUN — no files written")
        return

    # ── Back up existing library.json ────────────────────────────────
    if LIBRARY_PATH.exists():
        shutil.copy2(LIBRARY_PATH, BACKUP_PATH)
        print(f"[MIGRATE] backed up existing library.json to {BACKUP_PATH.name}")

    # ── Write unified library ────────────────────────────────────────
    assets_list = sorted(unified.values(), key=lambda e: (
        0 if e.get("quality") == "tested" else 1,
        -int(e.get("use_count", 0)),
        e.get("subject", ""),
    ))
    out = {
        "version":       2,
        "schema":        "unified_v2",
        "migrated_at":   int(time.time()),
        "migration_summary": counts,
        "assets":        assets_list,
    }
    LIBRARY_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[MIGRATE] wrote {total} unified entries to {LIBRARY_PATH}")

    # Quality breakdown
    tested = sum(1 for e in assets_list if e.get("quality") == "tested")
    unverified = sum(1 for e in assets_list if e.get("quality") == "unverified")
    print(f"[MIGRATE] quality: tested={tested}, unverified={unverified}")


if __name__ == "__main__":
    main()
