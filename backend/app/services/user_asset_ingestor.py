from __future__ import annotations

"""
user_asset_ingestor.py
======================
Ingest user-uploaded assets so they can be used by the asset agent
exactly like provider-fetched ones.

Pipeline
--------
    validate -> normalize -> probe -> classify -> register

1. validate
   - Reject zero-byte / empty files.
   - Reject filenames with traversal characters.
   - Reject extensions outside the supported set (glb, gltf, fbx, obj,
     blend, hdr, exr, png, jpg, jpeg, ktx2).
   - Enforce a configurable max file size.

2. normalize
   - Models in glb / gltf / fbx / obj are passed through the existing
     ``blender_normalizer.normalize_to_blend()`` so the rest of the
     pipeline always sees a .blend file with consistent units, scale,
     and origin.
   - HDRIs and textures are copied through unchanged but moved into the
     canonical cache layout (assets/cache/<group>/<id>/...).

3. probe
   - For models: parse the produced .blend (or fall back to file size
     heuristics) to estimate face count and bounding box.
   - For textures and HDRIs: read header to record resolution if
     possible.

4. classify
   - Use the LLM via ``llm_service.structured_query`` to assign
     semantic tags (e.g. "car", "vehicle", "futuristic", "luxury").
   - On any LLM failure, fall back to filename-derived tags so the
     asset is still searchable.

5. register
   - Insert the final record into the asset registry via
     ``registry_io.upsert_asset`` so it shows up in
     ``GET /api/assets/library`` and is picked up by the asset
     resolver on the next render.

The ingestor is purely a service module — it never reaches into the
HTTP layer. The accompanying upload endpoint lives in
``app/api/uploads.py``.
"""

import hashlib
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registry_io import upsert_asset
from .blender_normalizer import normalize_to_blend
from .llm_service import structured_query, is_available as llm_available


# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

MAX_UPLOAD_BYTES = 750 * 1024 * 1024  # 750 MB

MODEL_EXTS    = {".glb", ".gltf", ".fbx", ".obj", ".blend"}
HDRI_EXTS     = {".hdr", ".exr"}
TEXTURE_EXTS  = {".png", ".jpg", ".jpeg", ".ktx2", ".tif", ".tiff", ".webp"}

ALL_EXTS = MODEL_EXTS | HDRI_EXTS | TEXTURE_EXTS

CACHE_ROOT_REL = Path("assets/cache")
USER_GROUP_PREFIX = "user_"


# ═══════════════════════════════════════════════════════════════════════════
# Errors / result type
# ═══════════════════════════════════════════════════════════════════════════

class IngestError(Exception):
    """Raised when an upload cannot be ingested. Always carries a user-safe message."""


@dataclass
class IngestResult:
    ok: bool
    asset_type: str           # "model" | "hdri" | "texture"
    record: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# 1. Validate
# ═══════════════════════════════════════════════════════════════════════════

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    """Strip path separators and unsafe characters from a user-provided name."""
    base = Path(name).name  # drops any directory traversal
    if not base:
        raise IngestError("filename is empty")
    return _FILENAME_SAFE_RE.sub("_", base)


def _classify_extension(ext: str) -> str:
    ext = ext.lower()
    if ext in MODEL_EXTS:
        return "model"
    if ext in HDRI_EXTS:
        return "hdri"
    if ext in TEXTURE_EXTS:
        return "texture"
    raise IngestError(f"unsupported file extension: {ext}")


def validate_upload(filename: str, size_bytes: int) -> tuple[str, str]:
    """
    Validate the basics of an upload before any disk write.
    Returns ``(safe_filename, asset_type)``.
    """
    if size_bytes <= 0:
        raise IngestError("uploaded file is empty")
    if size_bytes > MAX_UPLOAD_BYTES:
        raise IngestError(
            f"uploaded file is too large ({size_bytes} bytes, max {MAX_UPLOAD_BYTES})"
        )

    safe = _safe_filename(filename)
    ext = Path(safe).suffix.lower()
    if ext not in ALL_EXTS:
        raise IngestError(f"unsupported file extension: {ext}")

    asset_type = _classify_extension(ext)
    return safe, asset_type


# ═══════════════════════════════════════════════════════════════════════════
# 2. Normalize
# ═══════════════════════════════════════════════════════════════════════════

def _hash_id(path: Path, label: str) -> str:
    """Stable, content-derived id so re-uploading the same file is idempotent."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return f"{label}_{h.hexdigest()[:16]}"


def _cache_dir_for(asset_type: str, asset_id: str) -> Path:
    """Local-relative cache dir following the same layout the fetchers use."""
    group = {
        "model":   "models/user",
        "hdri":    "hdris/user",
        "texture": "textures/user",
    }[asset_type]
    return CACHE_ROOT_REL / group / asset_id


def normalize_asset(
    staged_path: Path,
    safe_filename: str,
    asset_type: str,
) -> tuple[Path, dict[str, Any]]:
    """
    Move the staged upload into the canonical cache location and, for
    models, run the Blender normalizer to produce a clean .blend.

    Returns ``(final_path, normalize_report)``.
    """
    asset_id = _hash_id(staged_path, USER_GROUP_PREFIX.rstrip("_"))
    cache_dir = _cache_dir_for(asset_type, asset_id)
    abs_cache_dir = Path.cwd() / cache_dir
    abs_cache_dir.mkdir(parents=True, exist_ok=True)

    final_input = abs_cache_dir / safe_filename
    if final_input.resolve() != staged_path.resolve():
        shutil.move(str(staged_path), str(final_input))

    report: dict[str, Any] = {"asset_id": asset_id, "input": str(final_input)}

    if asset_type != "model":
        return final_input, report

    # Models go through the Blender normalizer so the renderer always
    # sees a .blend with consistent units / scale / origin.
    if final_input.suffix.lower() == ".blend":
        # Already a .blend — nothing to normalize, just return as-is.
        report["normalized"] = False
        return final_input, report

    out_blend = abs_cache_dir / f"{final_input.stem}.normalized.blend"
    norm = normalize_to_blend(str(final_input), str(out_blend))
    report["normalize"] = {
        "ok": norm.get("ok"),
        "error": norm.get("error"),
    }
    if not norm.get("ok"):
        # Normalization failed — keep the raw asset around so the resolver
        # can still try to use it, but flag it.
        report["normalized"] = False
        return final_input, report

    report["normalized"] = True
    return out_blend, report


# ═══════════════════════════════════════════════════════════════════════════
# 3. Probe
# ═══════════════════════════════════════════════════════════════════════════

def probe_asset(final_path: Path, asset_type: str) -> dict[str, Any]:
    """
    Best-effort metadata probe. Never raises — returns whatever it can
    pull off the file with stdlib only.
    """
    info: dict[str, Any] = {
        "size_bytes": final_path.stat().st_size if final_path.exists() else 0,
        "ext": final_path.suffix.lower(),
    }

    if asset_type == "texture":
        # Try Pillow if it's installed; otherwise skip silently.
        try:
            from PIL import Image  # type: ignore

            with Image.open(final_path) as im:
                info["width"] = im.width
                info["height"] = im.height
                info["mode"] = im.mode
        except Exception:
            pass
    elif asset_type == "hdri":
        # Pillow handles .hdr but not always .exr; try anyway.
        try:
            from PIL import Image  # type: ignore

            with Image.open(final_path) as im:
                info["width"] = im.width
                info["height"] = im.height
        except Exception:
            pass
    elif asset_type == "model":
        # Crude face-count estimate from filesize. The renderer can do
        # the precise probe later via Blender if it cares.
        size_kb = info["size_bytes"] / 1024.0
        info["estimated_face_count"] = int(size_kb * 30)  # ~30 faces / KB
    return info


# ═══════════════════════════════════════════════════════════════════════════
# 4. Classify
# ═══════════════════════════════════════════════════════════════════════════

_CLASSIFY_SCHEMA = {
    "primary_label": "single noun describing the subject",
    "tags":          ["short search tags"],
    "style":         "realism|stylized|cartoon|low_poly|sci_fi|fantasy|other",
    "scene_role":    "hero|prop|environment|texture|hdri|other",
}

_CLASSIFY_SYSTEM = (
    "You classify uploaded 3D assets for an animation engine. Given a "
    "filename and basic probe info, return a primary label, 4-8 search "
    "tags an asset library would use, the style category, and the most "
    "likely scene role. Return JSON only."
)


def _filename_tags(filename: str) -> list[str]:
    """Cheap fallback tagger when the LLM is unavailable."""
    stem = Path(filename).stem.lower()
    parts = re.split(r"[^a-z0-9]+", stem)
    return [p for p in parts if p and len(p) > 1]


def classify_asset(
    safe_filename: str,
    asset_type: str,
    probe_info: dict[str, Any],
) -> dict[str, Any]:
    """
    Ask the LLM to assign semantic tags. Falls back to filename-derived
    tokens if the LLM is offline or returns garbage.
    """
    fallback = {
        "primary_label": Path(safe_filename).stem,
        "tags":          _filename_tags(safe_filename) or [asset_type],
        "style":         "other",
        "scene_role":    {"model": "hero", "hdri": "hdri", "texture": "texture"}[asset_type],
        "source":        "fallback",
    }

    if not llm_available():
        return fallback

    user_prompt = (
        f"Filename: {safe_filename}\n"
        f"Asset type: {asset_type}\n"
        f"Probe info: {probe_info}\n\n"
        "Classify this asset."
    )
    parsed = structured_query(_CLASSIFY_SYSTEM, user_prompt, schema=_CLASSIFY_SCHEMA)
    if not parsed:
        return fallback

    tags = parsed.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(t).strip().lower() for t in tags if str(t).strip()]
    if not tags:
        tags = fallback["tags"]

    return {
        "primary_label": str(parsed.get("primary_label") or fallback["primary_label"]),
        "tags":          tags,
        "style":         str(parsed.get("style") or fallback["style"]),
        "scene_role":    str(parsed.get("scene_role") or fallback["scene_role"]),
        "source":        "llm",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. Register + top-level entry point
# ═══════════════════════════════════════════════════════════════════════════

_TYPE_TO_GROUP = {
    "model":   "models",
    "hdri":    "hdris",
    "texture": "textures",
}


def _build_record(
    asset_id: str,
    asset_type: str,
    final_path: Path,
    probe: dict[str, Any],
    classification: dict[str, Any],
    safe_filename: str,
    normalize_report: dict[str, Any],
) -> dict[str, Any]:
    rel_path = final_path.relative_to(Path.cwd()).as_posix()
    return {
        "id":             asset_id,
        "type":           asset_type,
        "name":           classification["primary_label"],
        "tags":           classification["tags"],
        "style":          classification["style"],
        "scene_role":     classification["scene_role"],
        "path":           rel_path,
        "source":         "user_upload",
        "filename":       safe_filename,
        "probe":          probe,
        "normalized":     bool(normalize_report.get("normalized")),
        "uploaded_at":    int(time.time()),
        "classification_source": classification["source"],
    }


def ingest_uploaded_file(staged_path: Path, original_filename: str) -> IngestResult:
    """
    Top-level entry point. Takes a path to a temp file already on disk
    (e.g. written by the FastAPI upload endpoint) plus the original
    filename the user provided.

    Always returns an IngestResult — never raises. Validation errors
    populate ``error``; everything else either populates ``record`` or
    appends to ``warnings``.
    """
    warnings: list[str] = []
    try:
        size_bytes = staged_path.stat().st_size
        safe_name, asset_type = validate_upload(original_filename, size_bytes)
    except IngestError as e:
        # Best-effort cleanup on validation failure
        try:
            if staged_path.exists():
                staged_path.unlink()
        except OSError:
            pass
        return IngestResult(ok=False, asset_type="", error=str(e))

    try:
        final_path, normalize_report = normalize_asset(staged_path, safe_name, asset_type)
    except Exception as e:
        return IngestResult(
            ok=False,
            asset_type=asset_type,
            error=f"normalize failed: {type(e).__name__}: {e}",
        )

    if asset_type == "model" and not normalize_report.get("normalized"):
        if normalize_report.get("normalize", {}).get("error"):
            warnings.append(
                f"normalize failed: {normalize_report['normalize']['error']} — keeping raw upload"
            )

    probe = probe_asset(final_path, asset_type)
    classification = classify_asset(safe_name, asset_type, probe)
    record = _build_record(
        asset_id=normalize_report["asset_id"],
        asset_type=asset_type,
        final_path=final_path,
        probe=probe,
        classification=classification,
        safe_filename=safe_name,
        normalize_report=normalize_report,
    )

    # V1.2: run the healing gate on user-uploaded models (non-destructive).
    if asset_type == "model":
        try:
            from .asset_healer import heal_asset as _heal_asset
            _healed = _heal_asset(
                str(final_path),
                proposed_category=(classification or {}).get("category"),
            )
            for _k, _v in (_healed or {}).items():
                record[_k] = _v
            if not _healed.get("provisional_ready"):
                warnings.append(
                    f"heal: provisional_ready=False notes={_healed.get('heal_notes')}"
                )
        except Exception as _heal_err:
            warnings.append(f"heal failed: {_heal_err}")

    try:
        upsert_asset(_TYPE_TO_GROUP[asset_type], record)
    except Exception as e:
        return IngestResult(
            ok=False,
            asset_type=asset_type,
            record=record,
            warnings=warnings,
            error=f"registry write failed: {type(e).__name__}: {e}",
        )

    print(
        f"[INGEST] {asset_type} id={record['id']} tags={classification['tags']} "
        f"src={classification['source']}",
        flush=True,
    )
    return IngestResult(ok=True, asset_type=asset_type, record=record, warnings=warnings)
