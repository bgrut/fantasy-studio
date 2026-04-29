#!/usr/bin/env python3
"""
classify_library_assets.py
==========================
One-off classifier.  Reads every GLB/GLTF in ``app/data/library.json``,
measures per-mesh dimensions from the GLB's embedded accessor min/max
fields (no Blender needed — pygltflib is ~10x faster), classifies the
asset's shape, and writes ``shape_class`` + ``real_world_size_m`` +
``mesh_count`` + ``classification_notes`` back to library.json.

The runtime render pipeline reads ``shape_class`` first and only falls
back to per-mesh analysis if missing.  This lets us classify once and
trust the answer across every render.

Run:
    python tools/classify_library_assets.py
    python tools/classify_library_assets.py --dry-run
    python tools/classify_library_assets.py --force  (re-classify all, not just missing)

Requires: pygltflib  (``pip install pygltflib``)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "app" / "data" / "library.json"
BACKUP_PATH = ROOT / "app" / "data" / "library.json.bak_preclassifier"


# ═══════════════════════════════════════════════════════════════════════════
# GLB mesh dimension extraction — lightweight, no Blender, no pygltflib
# ═══════════════════════════════════════════════════════════════════════════
# GLB is a binary container: header(12) + chunks of (length+type+data).
# First chunk is always JSON describing scenes/meshes/accessors.
# Each accessor has min/max arrays (3 floats for POSITION) — that's all
# we need for per-mesh bbox.  We avoid pygltflib to keep the tool
# dependency-free on Brandon's system.
# ═══════════════════════════════════════════════════════════════════════════

def _read_glb_json(glb_path: Path) -> dict | None:
    """Parse the first JSON chunk of a GLB.  Returns dict or None."""
    try:
        with open(glb_path, "rb") as f:
            magic = f.read(4)
            if magic != b"glTF":
                return None
            f.read(8)  # version + total length
            json_chunk_len = struct.unpack("<I", f.read(4))[0]
            f.read(4)  # chunk type ("JSON")
            payload = f.read(json_chunk_len)
            return json.loads(payload.decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"[CLASSIFIER]   GLB parse error: {e}", flush=True)
        return None


def _read_gltf_json(gltf_path: Path) -> dict | None:
    """Parse a .gltf (JSON text) file."""
    try:
        return json.loads(gltf_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        print(f"[CLASSIFIER]   GLTF parse error: {e}", flush=True)
        return None


def compute_mesh_dims_from_glb(glb_path: Path) -> list:
    """Return list of (width, depth, height) tuples, one per mesh primitive.

    Reads POSITION accessor min/max from the GLTF JSON — this is the
    per-primitive local-space bbox.  Fast, no vertex-buffer decoding.
    """
    ext = glb_path.suffix.lower()
    if ext == ".glb":
        data = _read_glb_json(glb_path)
    elif ext == ".gltf":
        data = _read_gltf_json(glb_path)
    else:
        return []
    if not data:
        return []

    accessors = data.get("accessors") or []
    meshes = data.get("meshes") or []
    dims_list: list = []
    for mesh in meshes:
        for prim in (mesh.get("primitives") or []):
            attrs = prim.get("attributes") or {}
            pos_idx = attrs.get("POSITION")
            if pos_idx is None or pos_idx < 0 or pos_idx >= len(accessors):
                continue
            acc = accessors[pos_idx]
            mn = acc.get("min")
            mx = acc.get("max")
            if not mn or not mx or len(mn) < 3 or len(mx) < 3:
                continue
            try:
                dims = (
                    float(mx[0]) - float(mn[0]),
                    float(mx[1]) - float(mn[1]),
                    float(mx[2]) - float(mn[2]),
                )
                dims_list.append(dims)
            except (ValueError, TypeError):
                continue
    return dims_list


# ═══════════════════════════════════════════════════════════════════════════
# Shape classifier
# ═══════════════════════════════════════════════════════════════════════════

def classify_shape(dims_list: list, category: str) -> tuple:
    """Return (shape_class, real_world_size_m, notes)."""
    if not dims_list:
        return ("unclassified", 0.0, "no mesh geometry readable")

    # Per-mesh flat analysis (same rule as runtime A1)
    flat_count = 0
    analyzed = 0
    for dims in dims_list:
        sorted_d = sorted(dims)
        if max(sorted_d) < 0.001:
            continue
        analyzed += 1
        thin_ratio = sorted_d[0] / max(sorted_d[2], 0.001)
        if thin_ratio < 0.10:
            flat_count += 1

    if analyzed == 0:
        return ("unclassified", 0.0, "all meshes zero-dim")

    flat_pct = flat_count / analyzed
    all_dims = [d for dims in dims_list for d in dims]
    real_size = max(all_dims) if all_dims else 0.0

    # Flat map wins for any category if majority are flat planes
    if flat_pct >= 0.60:
        return (
            "flat_map",
            real_size,
            f"{flat_count}/{analyzed} meshes flat planes",
        )

    cat = (category or "").lower()

    if cat == "environment":
        if real_size > 20.0 and len(dims_list) >= 3:
            return (
                "3d_terrain",
                real_size,
                f"{len(dims_list)} meshes, extent {real_size:.1f}m",
            )
        return (
            "3d_small_env",
            real_size,
            f"{len(dims_list)} meshes, extent {real_size:.1f}m (small for environment)",
        )

    if cat == "character":
        # upright aspect (height > 1.3 × max(w,d)) → upright character
        first = dims_list[0]
        if first[2] > max(first[0], first[1]) * 1.3:
            return (
                "character_upright",
                real_size,
                "upright aspect ratio",
            )
        return (
            "character_generic",
            real_size,
            f"{len(dims_list)} meshes",
        )

    if cat == "vehicle":
        return ("vehicle_generic", real_size, f"extent {real_size:.1f}m")

    if cat == "prop":
        return ("prop_generic", real_size, f"extent {real_size:.1f}m")

    return (
        "unclassified",
        real_size,
        f"category={category}, extent={real_size:.1f}m",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="don't write library.json, just print decisions")
    parser.add_argument("--force", action="store_true",
                        help="re-classify even entries that already have shape_class")
    args = parser.parse_args()

    if not LIBRARY_PATH.exists():
        print(f"[CLASSIFIER] library not found: {LIBRARY_PATH}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    # Library schema is {"assets": [...]} from round 7 onwards
    if isinstance(data, dict) and "assets" in data:
        assets = data["assets"]
        schema_v2 = True
    elif isinstance(data, list):
        assets = data
        schema_v2 = False
    else:
        print(f"[CLASSIFIER] unexpected library shape: {type(data)}", file=sys.stderr)
        sys.exit(1)

    # Backup before any writes
    if not args.dry_run:
        shutil.copy2(LIBRARY_PATH, BACKUP_PATH)
        print(f"[CLASSIFIER] backed up library to {BACKUP_PATH.name}", flush=True)

    stats = {
        "total": len(assets),
        "classified": 0,
        "already_had":  0,
        "skipped_format": 0,
        "skipped_missing_file": 0,
        "errored": 0,
        "by_shape": {},
    }

    t_start = time.time()
    for entry in assets:
        if not isinstance(entry, dict):
            stats["errored"] += 1
            continue
        eid = entry.get("id", "?")

        if not args.force and entry.get("shape_class"):
            stats["already_had"] += 1
            stats["by_shape"].setdefault(entry["shape_class"], 0)
            stats["by_shape"][entry["shape_class"]] += 1
            continue

        path = entry.get("path", "")
        if not path:
            stats["errored"] += 1
            continue

        p = Path(path)
        if not p.is_absolute():
            p = ROOT / path
        if not p.exists():
            print(f"[CLASSIFIER] SKIP: {eid} — path not found: {path}", flush=True)
            stats["skipped_missing_file"] += 1
            continue

        if p.suffix.lower() not in (".glb", ".gltf"):
            stats["skipped_format"] += 1
            continue

        dims_list = compute_mesh_dims_from_glb(p)
        category = entry.get("category", "unknown")
        shape_class, real_size, notes = classify_shape(dims_list, category)

        entry["shape_class"] = shape_class
        entry["real_world_size_m"] = round(real_size, 3)
        entry["mesh_count"] = len(dims_list)
        entry["classification_notes"] = notes

        stats["classified"] += 1
        stats["by_shape"][shape_class] = stats["by_shape"].get(shape_class, 0) + 1
        print(
            f"[CLASSIFIER] {eid:<60} -> shape={shape_class:<20} "
            f"size={real_size:6.2f}m meshes={len(dims_list)}",
            flush=True,
        )

    elapsed = time.time() - t_start

    if args.dry_run:
        print(f"\n[CLASSIFIER] DRY RUN — library.json NOT modified")
    else:
        LIBRARY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"\n[CLASSIFIER] wrote updated library.json")

    print(f"[CLASSIFIER] COMPLETE in {elapsed:.1f}s")
    print(f"[CLASSIFIER] total:              {stats['total']}")
    print(f"[CLASSIFIER] classified:         {stats['classified']}")
    print(f"[CLASSIFIER] already had class:  {stats['already_had']}")
    print(f"[CLASSIFIER] skipped (format):   {stats['skipped_format']}")
    print(f"[CLASSIFIER] skipped (missing):  {stats['skipped_missing_file']}")
    print(f"[CLASSIFIER] errored:            {stats['errored']}")
    print(f"[CLASSIFIER] by shape:")
    for k, v in sorted(stats["by_shape"].items(), key=lambda kv: -kv[1]):
        print(f"[CLASSIFIER]   {k}: {v}")


if __name__ == "__main__":
    main()
