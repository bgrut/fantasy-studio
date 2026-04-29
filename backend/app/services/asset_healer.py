"""
asset_healer.py
===============
V1.2 — Asset Healing Pipeline.

Runs at EVERY asset ingest point (Downloads folder, Sketchfab agent,
Objaverse agent, user upload).  Normalizes metadata, detects
orientation, infers scale, validates materials, classifies shape.

Design rules:
  - NEVER modifies the original asset file.  All corrections are stored
    as metadata in library.json and applied at runtime by the render
    pipeline via _apply_healed_transforms().
  - Fail loud (heal_notes list), fix when safe, flag when uncertain.
  - Additive: preserves all existing library fields; adds new ones.
  - Idempotent: running heal on an already-healed entry just refreshes
    the metadata.

Entry point:
    from app.services.asset_healer import heal_asset
    result = heal_asset(asset_path, proposed_category="environment")
    library_entry.update(result)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Resolve Blender the same way the render pipeline does — settings first,
# then config fallback, then well-known paths.
def _resolve_blender_exe() -> str:
    try:
        from ..main import get_setting  # type: ignore
        from ..config import BLENDER_EXE as _CFG_EXE  # type: ignore
        exe = get_setting("blender_executable_path", _CFG_EXE)
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    for candidate in (
        r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",
    ):
        if os.path.exists(candidate):
            return candidate
    return r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"


BLENDER_EXE = _resolve_blender_exe()
HEALER_BLENDER_SCRIPT = Path(__file__).parent / "_healer_blender_inspector.py"
HEALER_VERSION = "1.0"


def heal_asset(
    asset_path: str,
    proposed_category: Optional[str] = None,
    inspector_timeout: int = 90,
) -> dict:
    """Run the full healing pipeline on a single asset.

    Returns a dict of fields to merge into a library.json entry.  The
    dict always contains ``healer_version``, ``heal_notes`` (list),
    ``launch_ready`` (False), and ``provisional_ready`` (bool).
    """
    notes: list[str] = []
    metadata: dict = {
        "healer_version":   HEALER_VERSION,
        "launch_ready":     False,   # human confirms
        "provisional_ready": False,  # auto-set below
        "heal_notes":       notes,
    }

    # Stage 1a: format + existence + size
    if not _validate_format(asset_path, notes):
        return metadata

    # Stage 1b: Blender subprocess inspection
    inspection = _run_blender_inspector(asset_path, notes, inspector_timeout)
    if not inspection:
        return metadata

    metadata.update({
        "bbox_min":         inspection.get("bbox_min"),
        "bbox_max":         inspection.get("bbox_max"),
        "bbox_dims":        inspection.get("bbox_dims"),
        "centroid":         inspection.get("centroid"),
        "mesh_count":       inspection.get("mesh_count", 0),
        "vertex_count":     inspection.get("vertex_count", 0),
        "has_armature":     inspection.get("has_armature", False),
        "material_issues":  inspection.get("material_issues", []),
    })
    dims = inspection.get("bbox_dims") or [0.0, 0.0, 0.0]
    metadata["real_world_size_m"] = float(max(dims)) if dims else 0.0

    # Stage 1c: classify shape using Blender-measured dims (more accurate
    # than pygltflib because it walks node transforms).
    metadata["shape_class"] = _classify_shape(inspection, proposed_category)

    # Stage 1d: infer category when caller didn't provide one
    metadata["inferred_category"] = (
        proposed_category
        or _infer_category(asset_path, inspection, metadata["shape_class"])
    )

    # Stage 1e: orientation detection + auto-fix rotation
    orient = _detect_orientation(inspection, metadata["inferred_category"])
    metadata["orientation_issue"] = orient["issue"]
    metadata["orientation_fix_rotation_euler"] = orient["fix_rotation"]
    if orient["issue"]:
        notes.append(
            f"orientation: {orient['issue']} -> auto-fix "
            f"rotation {orient['fix_rotation']}"
        )

    # Stage 1f: ground-offset (runtime snaps bottom to z=0)
    metadata["ground_offset_z"] = _compute_ground_offset(inspection)

    # Stage 1g: quality score
    metadata["quality_score"] = _compute_quality_score(metadata)

    # Stage 1h: thumbnail — deferred to V1.2.1 (scripts/generate_thumbnails.py
    # already exists and can run separately).  Leaving hook in place.
    metadata["thumbnail_path"] = None

    # Stage 1i: provisional_ready gate
    metadata["provisional_ready"] = bool(
        metadata["quality_score"] >= 60
        and not metadata.get("material_issues")
        and metadata["mesh_count"] > 0
    )
    if metadata["provisional_ready"]:
        notes.append(
            "passed all auto-checks -> provisional_ready=True "
            "(awaits human launch_ready confirmation)"
        )
    else:
        notes.append(
            f"flagged: quality={metadata['quality_score']} "
            f"meshes={metadata['mesh_count']} "
            f"material_issues={len(metadata.get('material_issues') or [])}"
        )
    return metadata


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

_SUPPORTED_EXT = (".glb", ".gltf", ".blend", ".fbx", ".obj")


def _validate_format(path: str, notes: list) -> bool:
    ext = Path(path).suffix.lower()
    if ext not in _SUPPORTED_EXT:
        notes.append(f"unsupported format: {ext}")
        return False
    if not os.path.exists(path):
        notes.append(f"file not found: {path}")
        return False
    size = os.path.getsize(path)
    if size < 100:
        notes.append(f"file too small ({size} bytes) - likely corrupt")
        return False
    return True


def _run_blender_inspector(
    path: str,
    notes: list,
    timeout: int,
) -> dict | None:
    """Launch Blender in headless mode to inspect the asset.
    Runs _healer_blender_inspector.py which writes a JSON result."""
    if not os.path.exists(BLENDER_EXE):
        notes.append(f"blender executable not found: {BLENDER_EXE}")
        return None
    if not HEALER_BLENDER_SCRIPT.exists():
        notes.append(f"inspector script missing: {HEALER_BLENDER_SCRIPT}")
        return None

    tmpf = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    out_path = tmpf.name
    tmpf.close()
    try:
        result = subprocess.run(
            [
                BLENDER_EXE,
                "-b",
                "--factory-startup",
                "--python", str(HEALER_BLENDER_SCRIPT),
                "--",
                path,
                out_path,
            ],
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            notes.append(
                f"blender inspector failed (rc={result.returncode}): "
                f"{(result.stderr or '')[-300:]}"
            )
            return None
        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            notes.append("blender inspector produced no output JSON")
            return None
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("error"):
            notes.append(f"inspector reported: {data['error']}")
            return None
        return data
    except subprocess.TimeoutExpired:
        notes.append(f"blender inspector timed out ({timeout}s)")
        return None
    except Exception as e:
        notes.append(f"blender inspector error: {e}")
        return None
    finally:
        try:
            os.unlink(out_path)
        except Exception:
            pass


def _classify_shape(inspection: dict, proposed_category: Optional[str]) -> str:
    dims_list = inspection.get("per_mesh_dims") or []
    if not dims_list:
        return "unclassified"

    # per-mesh flat detection
    flat_count = 0
    analyzed = 0
    for d in dims_list:
        try:
            m = max(d)
            if m < 0.001:
                continue
            analyzed += 1
            if min(d) < 0.10 * m:
                flat_count += 1
        except Exception:
            continue
    if analyzed == 0:
        return "unclassified"
    flat_pct = flat_count / analyzed
    real_size = max((max(d) for d in dims_list), default=0.0)

    if flat_pct >= 0.60:
        return "flat_map"

    cat = (proposed_category or "").lower()
    if cat == "environment":
        if real_size > 20.0 and len(dims_list) >= 3:
            return "3d_terrain"
        return "3d_small_env"
    if cat == "character" or (not cat and inspection.get("has_armature")):
        first = dims_list[0]
        if first[2] > max(first[0], first[1]) * 1.3:
            return "character_upright"
        return "character_generic"
    if cat == "vehicle":
        return "vehicle_generic"
    if cat == "prop":
        return "prop_generic"
    return "unclassified"


def _infer_category(path: str, inspection: dict, shape_class: str) -> str:
    p = path.lower().replace("\\", "/")
    if "/environment" in p or "/environments" in p:
        return "environment"
    if "/character" in p or "/characters" in p:
        return "character"
    if "/vehicle" in p or "/vehicles" in p or "/cars" in p:
        return "vehicle"
    if "/prop" in p or "/props" in p:
        return "prop"
    if shape_class in ("flat_map", "3d_terrain", "3d_small_env"):
        return "environment"
    if shape_class.startswith("character"):
        return "character"
    return "unknown"


def _detect_orientation(inspection: dict, category: str) -> dict:
    """Detect upside-down / on-side / vertical-env issues.
    Returns ``{"issue": str|None, "fix_rotation": [rx,ry,rz] rad | None}``."""
    bbox_min = inspection.get("bbox_min") or [0.0, 0.0, 0.0]
    bbox_max = inspection.get("bbox_max") or [0.0, 0.0, 0.0]
    centroid = inspection.get("centroid") or [0.0, 0.0, 0.0]
    dims = [bbox_max[i] - bbox_min[i] for i in range(3)]

    cat = (category or "").lower()

    # Character / vehicle checks
    if cat in ("character", "vehicle"):
        bbox_h = dims[2]
        if bbox_h > 0.001:
            normalized_cz = (centroid[2] - bbox_min[2]) / bbox_h
            # Centroid in top quarter = upside down
            if normalized_cz > 0.75:
                return {
                    "issue":        "upside_down_z",
                    "fix_rotation": [3.14159265, 0.0, 0.0],
                }
        if cat == "character":
            # Laid on side: horizontal dim massively larger than height
            if dims[0] > dims[2] * 1.5 and dims[0] >= dims[1]:
                return {
                    "issue":        "character_on_side_x",
                    "fix_rotation": [0.0, 1.5707963, 0.0],
                }
            if dims[1] > dims[2] * 1.5:
                return {
                    "issue":        "character_on_side_y",
                    "fix_rotation": [1.5707963, 0.0, 0.0],
                }

    # Environment checks
    if cat == "environment":
        if bbox_max[2] < 0:
            return {
                "issue":        "env_entirely_below_origin",
                "fix_rotation": None,  # not safely auto-fixable; flag only
            }
        if (
            dims[2] > max(dims[0], dims[1]) * 1.5
            and max(dims[0], dims[1]) < 50.0
        ):
            return {
                "issue":        "env_vertical_orientation",
                "fix_rotation": [1.5707963, 0.0, 0.0],
            }

    return {"issue": None, "fix_rotation": None}


def _compute_ground_offset(inspection: dict) -> float:
    bbox_min = inspection.get("bbox_min") or [0.0, 0.0, 0.0]
    try:
        return float(bbox_min[2])
    except Exception:
        return 0.0


def _compute_quality_score(metadata: dict) -> int:
    score = 50
    if (metadata.get("mesh_count") or 0) > 0:
        score += 15
    if (metadata.get("vertex_count") or 0) > 100:
        score += 10
    if not metadata.get("material_issues"):
        score += 15
    if metadata.get("shape_class") not in (None, "", "unclassified"):
        score += 10
    if metadata.get("orientation_issue"):
        score -= 10
    return max(0, min(100, score))


__all__ = ["heal_asset", "HEALER_VERSION", "BLENDER_EXE"]
