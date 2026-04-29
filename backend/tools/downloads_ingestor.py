#!/usr/bin/env python3
"""
tools/downloads_ingestor.py
===========================
V1.2.5 Part C — watch the user's Downloads folder for new 3D assets,
heal them through the V1.2 pipeline, register them in library.json.

Non-destructive to Downloads: files are COPIED, not moved.  Dedups by
filename + file size; identical repeat scans are no-ops.  Skips anything
already in ``app/data/downloads_processed.json``.

Usage:
    python tools/downloads_ingestor.py scan     # one-off scan
    python tools/downloads_ingestor.py watch    # daemon mode
    python tools/downloads_ingestor.py status   # show processed-log stats

Config:
    --downloads <path>    Override Downloads folder (defaults to ~/Downloads)
    --interval <seconds>  Watch-mode poll interval (default 10)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.asset_healer import heal_asset  # noqa: E402

DEFAULT_DOWNLOADS = Path.home() / "Downloads"
LIBRARY_PATH = ROOT / "app" / "data" / "library.json"
PROCESSED_LOG = ROOT / "app" / "data" / "downloads_processed.json"
BACKUP_PATH = ROOT / "app" / "data" / "library.json.bak_downloads"
THUMBS_DIR = ROOT / "assets" / "thumbnails"
TRIAGE_WORKER = ROOT / "tools" / "_triage_blender_worker.py"


def _resolve_blender_exe() -> str | None:
    for c in (
        r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",
    ):
        if Path(c).exists():
            return c
    return None


def _generate_thumbnail_for(entry: dict) -> bool:
    """Render a single 256x256 Eevee thumbnail for a just-ingested asset.
    Reuses the triage worker; ~1-3s per asset.  Best-effort: errors are
    logged but never block ingest.
    """
    blender = _resolve_blender_exe()
    if not blender or not TRIAGE_WORKER.exists():
        return False
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    import tempfile as _tf
    job_payload = [{
        "id": entry.get("id"),
        "path": str((ROOT / entry["path"]).resolve()),
        "orientation_fix_rotation_euler": entry.get("orientation_fix_rotation_euler"),
        "ground_offset_z": entry.get("ground_offset_z"),
        "category": entry.get("category"),
    }]
    with _tf.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        f.write(json.dumps(job_payload))
        job_file = f.name
    try:
        import subprocess as _sp
        r = _sp.run(
            [blender, "-b", "--factory-startup",
             "--python", str(TRIAGE_WORKER), "--",
             job_file, str(THUMBS_DIR)],
            capture_output=True, text=True, timeout=120,
        )
        return r.returncode == 0 and (THUMBS_DIR / f"{entry.get('id')}.png").exists()
    except Exception as e:
        print(f"[THUMB] failed for {entry.get('id')}: {e}", flush=True)
        return False
    finally:
        try:
            Path(job_file).unlink()
        except Exception:
            pass

SUPPORTED_EXT = (".glb", ".gltf", ".fbx", ".obj", ".blend")
# Extensions of 3D assets we'll search for inside ZIP archives.  Order
# matters — the ZIP adapter prefers .glb over .gltf when both exist.
ARCHIVE_PRIMARY_EXTS = (".glb", ".gltf", ".fbx", ".obj", ".blend")
ARCHIVE_EXT = ".zip"

# V1.3.6 zip-ingestion staging dirs
INGEST_STAGING = ROOT / "assets" / "_ingest_staging"
# These two live INSIDE the watched Downloads folder so the user can
# review/restore them by hand.  Resolved at call time via the
# ``downloads_dir`` argument so a custom ``--downloads`` still works.
INGEST_COMPLETED_NAME = "_ingest_completed"
INGEST_FAILED_NAME = "_ingest_failed"

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "character": [
        "character", "human", "person", "man", "woman", "cat", "dog",
        "animal", "creature", "monster", "robot", "alien", "deer", "horse",
        "bird", "eagle", "dragon", "warrior", "knight", "wolf", "lion",
        "tiger", "bear", "whale", "elephant", "shark", "penguin", "fox",
        "rabbit", "rhinoceros", "rhino",
    ],
    "environment": [
        "environment", "terrain", "landscape", "scene", "mountain", "canyon",
        "desert", "forest", "city", "beach", "ocean", "valley", "cave",
        "island", "castle", "ruins", "temple", "glacier", "arctic",
        "rooftop", "cityscape", "skybox",
    ],
    "vehicle": [
        "car", "vehicle", "truck", "ferrari", "bmw", "porsche", "plane",
        "ship", "boat", "motorcycle", "bicycle", "tank", "aston",
        "lamborghini", "mclaren", "mustang", "toyota", "honda",
    ],
    "prop": [
        "prop", "weapon", "sword", "gun", "tool", "furniture", "chair",
        "table", "barrel", "crate", "sign", "lamp", "torch", "banner",
        "bottle", "book", "scroll",
    ],
}

CATEGORY_DIR = {
    "character":   "characters",
    "environment": "environments",
    "vehicle":     "vehicles",
    "prop":        "props",
    "unknown":     "unknown",
}


# ─────────────────────────────────────────────────────────────────────────

def _load_library() -> tuple[object, list[dict], bool]:
    raw = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "assets" in raw:
        return raw, raw["assets"], True
    if isinstance(raw, list):
        return raw, raw, False
    raise RuntimeError(f"unexpected library shape: {type(raw)}")


def _save_library(raw) -> None:
    shutil.copy2(LIBRARY_PATH, BACKUP_PATH)
    LIBRARY_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def _load_processed() -> set[str]:
    if not PROCESSED_LOG.exists():
        return set()
    try:
        return set(json.loads(PROCESSED_LOG.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_processed(processed: set[str]) -> None:
    PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_LOG.write_text(
        json.dumps(sorted(processed), indent=2), encoding="utf-8"
    )


def infer_category(filename: str) -> str:
    name = filename.lower()
    scores: dict[str, int] = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in kws if kw in name)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "unknown"


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem.lower()
    import re
    stem = re.sub(r"[^a-z0-9_]+", "_", stem).strip("_")
    return stem or "asset"


def _dedup_path(dest_dir: Path, filename: str) -> Path:
    p = dest_dir / filename
    if not p.exists():
        return p
    stem = p.stem
    suffix = p.suffix
    i = 1
    while (dest_dir / f"{stem}_{i}{suffix}").exists():
        i += 1
    return dest_dir / f"{stem}_{i}{suffix}"


def ingest_file(src: Path) -> Optional[dict]:
    """Heal + register one asset. Returns the new library entry or None."""
    ext = src.suffix.lower()
    if ext not in SUPPORTED_EXT:
        return None
    if not src.exists():
        return None

    category = infer_category(src.name)
    cache_dir = ROOT / "assets" / "cache" / "models" / CATEGORY_DIR[category]
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Dedup: if a same-size file with same name already lives in the cache,
    # skip entirely.
    candidate = cache_dir / src.name
    if (
        candidate.exists()
        and candidate.stat().st_size == src.stat().st_size
    ):
        print(f"[INGEST] skip (already cached same size): {src.name}", flush=True)
        return None

    dest = _dedup_path(cache_dir, src.name)
    shutil.copy2(src, dest)
    print(f"[INGEST] copied {src.name} -> {dest.relative_to(ROOT)}", flush=True)

    # Heal
    healed = heal_asset(str(dest), proposed_category=category)

    stem = _safe_stem(dest.name)
    # Keep IDs unique enough across repeated downloads
    asset_id = f"lib_{category}_{stem}"

    # Make path library-relative
    try:
        rel_path = str(dest.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        rel_path = str(dest).replace("\\", "/")

    entry: dict = {
        "id":            asset_id,
        "path":          rel_path,
        "category":      category,
        "source":        "downloads_ingest",
        "ingested_at":   time.strftime("%Y-%m-%d %H:%M:%S"),
        "subject":       stem.split("_")[0] if "_" in stem else stem,
        "subject_tags":  [category],
        "use_count":     0,
    }
    # Merge healer fields
    for k, v in (healed or {}).items():
        entry[k] = v
    return entry


def register_in_library(entry: dict) -> bool:
    raw, assets, _ = _load_library()
    existing_ids = {
        e.get("id") for e in assets if isinstance(e, dict)
    }
    if entry["id"] in existing_ids:
        # Bump id with timestamp if duplicate
        entry = dict(entry)
        entry["id"] = f"{entry['id']}_{int(time.time())}"
    assets.append(entry)
    _save_library(raw)
    return True


def _quarantine_zip(src: Path, downloads_dir: Path, kind: str,
                    error_text: str | None = None) -> Path | None:
    """Move ``src`` into ``downloads_dir/<kind>/`` (kind = completed|failed).
    On failure: also writes ``<archive>.error.txt`` next to it with the
    traceback. Best-effort — never raises.
    """
    try:
        target_dir = downloads_dir / (
            INGEST_FAILED_NAME if kind == "failed" else INGEST_COMPLETED_NAME
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _dedup_path(target_dir, src.name)
        shutil.move(str(src), str(target))
        if kind == "failed" and error_text:
            try:
                (target.with_suffix(target.suffix + ".error.txt")).write_text(
                    error_text, encoding="utf-8"
                )
            except Exception:
                pass
        print(
            f"[INGEST_ZIP] moved {src.name} -> "
            f"{target.relative_to(downloads_dir)}",
            flush=True,
        )
        return target
    except Exception as e:
        print(
            f"[INGEST_ZIP] quarantine failed for {src.name} "
            f"(kind={kind}): {e}",
            flush=True,
        )
        return None


def _find_primary_in_extracted(extract_root: Path) -> Path | None:
    """Locate the primary 3D asset inside an extracted archive.

    Strategy: prefer .glb, then .gltf, then other supported exts. Among
    candidates of the same priority, pick the one in the shallowest path
    (fewest path components) — Sketchfab archives often nest a
    ``source/...`` directory of less-useful duplicates.
    """
    candidates: list[tuple[int, int, Path]] = []
    for path in extract_root.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in ARCHIVE_PRIMARY_EXTS:
            continue
        # Skip obvious noise — e.g. "scene_orig.glb" backups some tools
        # emit. Keep this conservative; primary detection is critical.
        if path.name.lower().startswith("._"):
            continue
        prio = ARCHIVE_PRIMARY_EXTS.index(ext)
        depth = len(path.relative_to(extract_root).parts)
        candidates.append((prio, depth, path))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (t[0], t[1], str(t[2]).lower()))
    return candidates[0][2]


def ingest_zip(src: Path, downloads_dir: Path) -> Optional[dict]:
    """Adapter: extract a .zip from Downloads, locate the primary asset,
    delegate to :func:`ingest_file`, then stamp archive provenance on
    the resulting library entry. Returns the entry or None.

    On any failure the original .zip is moved to
    ``<downloads>/_ingest_failed/`` with a sibling ``.error.txt``. On
    success the .zip is moved to ``<downloads>/_ingest_completed/`` so
    the watcher won't reprocess it.
    """
    import traceback as _tb
    import zipfile as _zf

    print(f"[INGEST_ZIP] detected archive: {src.name}", flush=True)
    if not src.exists():
        return None
    if src.suffix.lower() != ARCHIVE_EXT:
        return None

    archive_basename = src.stem
    staging_root = INGEST_STAGING / archive_basename
    # Fresh staging directory each run — clean any previous half-extract.
    if staging_root.exists():
        try:
            shutil.rmtree(staging_root)
        except Exception:
            pass
    staging_root.mkdir(parents=True, exist_ok=True)

    # Extract
    try:
        with _zf.ZipFile(src, "r") as zf:
            # Defensive: zip-slip — refuse archives whose member paths
            # escape the staging root.
            for member in zf.namelist():
                norm = Path(member)
                if norm.is_absolute() or ".." in norm.parts:
                    raise RuntimeError(
                        f"refusing unsafe archive member: {member!r}"
                    )
            zf.extractall(staging_root)
        print(
            f"[INGEST_ZIP] extracted to "
            f"{staging_root.relative_to(ROOT)}",
            flush=True,
        )
    except Exception as e:
        err = _tb.format_exc()
        print(f"[INGEST_ZIP] extraction failed for {src.name}: {e}\n{err}",
              flush=True)
        _quarantine_zip(src, downloads_dir, "failed", err)
        return None

    # Locate primary
    primary = _find_primary_in_extracted(staging_root)
    if primary is None:
        print(
            f"[INGEST_ZIP] no 3D asset in archive, skipping: {src.name}",
            flush=True,
        )
        _quarantine_zip(
            src, downloads_dir, "failed",
            f"no 3D asset (.glb/.gltf/.fbx/.obj/.blend) found in archive",
        )
        return None

    print(
        f"[INGEST_ZIP] primary asset: "
        f"{primary.relative_to(staging_root)} (ext={primary.suffix.lower()})",
        flush=True,
    )

    # Delegate to the existing single-file ingest pipeline. Same code
    # path as loose-file ingestion — heal → register-ready entry.
    try:
        entry = ingest_file(primary)
    except Exception as e:
        err = _tb.format_exc()
        print(
            f"[INGEST_ZIP] ingest_file failed for "
            f"{primary.name} (from {src.name}): {e}\n{err}",
            flush=True,
        )
        _quarantine_zip(src, downloads_dir, "failed", err)
        return None

    if entry is None:
        # ingest_file returned None — either unsupported ext (impossible
        # given filter) or already-cached. Treat as a soft success and
        # move the archive to completed so we don't see it again.
        print(
            f"[INGEST_ZIP] ingest_file returned None for {primary.name} "
            f"(likely already cached); marking archive complete",
            flush=True,
        )
        _quarantine_zip(src, downloads_dir, "completed")
        return None

    # Stamp archive provenance on the entry before the caller registers.
    entry["source_path"] = src.name
    entry["extracted_from_archive"] = True
    return entry


def scan_once(downloads_dir: Path) -> dict:
    import traceback as _tb
    processed = _load_processed()
    stats = {"new": 0, "ingested": 0, "skipped": 0}

    found: list[Path] = []
    for ext in SUPPORTED_EXT:
        found.extend(downloads_dir.glob(f"*{ext}"))
        found.extend(downloads_dir.glob(f"*{ext.upper()}"))
    # V1.3.6: also pick up archive files for ZIP ingestion.
    found.extend(downloads_dir.glob(f"*{ARCHIVE_EXT}"))
    found.extend(downloads_dir.glob(f"*{ARCHIVE_EXT.upper()}"))
    # Dedupe — Windows is case-insensitive, so "*.zip" and "*.ZIP"
    # return the same files, which previously made every archive
    # appear twice in ``new_files`` (the second pass then crashed on
    # ``src.stat()`` because the first pass had already moved it to
    # _ingest_completed/_ingest_failed). Preserve order via a dict.
    found = list(dict.fromkeys(found))

    new_files = [f for f in found if str(f) not in processed]
    print(
        f"[SCAN] downloads={downloads_dir} "
        f"found={len(found)} new={len(new_files)}",
        flush=True,
    )

    for src in new_files:
        stats["new"] += 1
        is_zip = src.suffix.lower() == ARCHIVE_EXT
        try:
            # Defensive: file may have been moved by an earlier
            # iteration (e.g. a zip already quarantined to
            # _ingest_completed/) or by an external tool. Skip cleanly.
            if not src.exists():
                print(
                    f"[SCAN] skipping {src.name} (no longer present)",
                    flush=True,
                )
                continue
            # Stability probe: skip files that might still be downloading
            # (size changes across a 1s sleep means in-flight).
            s0 = src.stat().st_size
            time.sleep(0.5)
            if not src.exists():
                continue
            s1 = src.stat().st_size
            if s1 != s0 or s1 < 200:
                print(f"[SCAN] skipping {src.name} (unstable / tiny)", flush=True)
                continue

            if is_zip:
                entry = ingest_zip(src, downloads_dir)
            else:
                entry = ingest_file(src)

            if entry is None:
                stats["skipped"] += 1
            else:
                register_in_library(entry)
                stats["ingested"] += 1
                print(
                    f"[INGEST] registered {entry['id']} "
                    f"category={entry['category']} "
                    f"shape={entry.get('shape_class')!r} "
                    f"provisional_ready={entry.get('provisional_ready')}",
                    flush=True,
                )
                # Auto-thumbnail (best-effort; ingest succeeds either way)
                if _generate_thumbnail_for(entry):
                    print(f"[THUMB] wrote {entry['id']}.png", flush=True)
                # On successful zip ingest, archive the original .zip
                # so the watcher won't reprocess it on restart.
                if is_zip and src.exists():
                    _quarantine_zip(src, downloads_dir, "completed")
        except Exception as e:
            err = _tb.format_exc()
            print(f"[SCAN] error on {src.name}: {e}\n{err}", flush=True)
            if is_zip and src.exists():
                _quarantine_zip(src, downloads_dir, "failed", err)
        finally:
            processed.add(str(src))
            _save_processed(processed)

    print(
        f"[SCAN] complete: new={stats['new']} "
        f"ingested={stats['ingested']} skipped={stats['skipped']}",
        flush=True,
    )
    return stats


def _count_pending(downloads_dir: Path) -> int:
    """Count loose .glb / .zip files in ``downloads_dir`` not yet recorded
    in the processed-log. Used for the backfill banner."""
    processed = _load_processed()
    pending: list[Path] = []
    for ext in SUPPORTED_EXT + (ARCHIVE_EXT,):
        pending.extend(downloads_dir.glob(f"*{ext}"))
        pending.extend(downloads_dir.glob(f"*{ext.upper()}"))
    pending = list(dict.fromkeys(pending))  # de-dupe case-insensitive matches
    pending = [p for p in pending if str(p) not in processed]
    return len(pending)


def watch(downloads_dir: Path, interval: int) -> None:
    print(f"[WATCH] monitoring {downloads_dir} (interval={interval}s). Ctrl+C to stop.", flush=True)
    # V1.3.6 backfill: drain whatever is already sitting in Downloads
    # before entering steady-state polling. ``scan_once`` already does
    # the work — this just announces the pass.
    try:
        _pending = _count_pending(downloads_dir)
        if _pending:
            print(
                f"[INGEST_BACKFILL] processing {_pending} pending "
                f"file(s) at startup",
                flush=True,
            )
        else:
            print(
                "[INGEST_BACKFILL] no pending files at startup",
                flush=True,
            )
        scan_once(downloads_dir)
    except Exception as e:
        import traceback as _tb
        print(
            f"[INGEST_BACKFILL] failed: {e}\n{_tb.format_exc()}",
            flush=True,
        )
    while True:
        try:
            scan_once(downloads_dir)
        except Exception as e:
            import traceback as _tb
            print(f"[WATCH] scan error: {e}\n{_tb.format_exc()}", flush=True)
        time.sleep(max(1, interval))


def cmd_status() -> None:
    processed = _load_processed()
    print(f"processed entries: {len(processed)}")
    print(f"processed log:     {PROCESSED_LOG}")
    print(f"library:           {LIBRARY_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", nargs="?", default="scan",
                    choices=["scan", "watch", "status"])
    ap.add_argument("--downloads", default=str(DEFAULT_DOWNLOADS),
                    help="Downloads folder to watch")
    ap.add_argument("--interval", type=int, default=10,
                    help="watch-mode poll seconds (default 10)")
    args = ap.parse_args()

    downloads_dir = Path(args.downloads).expanduser()
    if args.cmd in ("scan", "watch") and not downloads_dir.exists():
        print(f"[DOWNLOADS] folder not found: {downloads_dir}", file=sys.stderr)
        return 1

    if args.cmd == "scan":
        scan_once(downloads_dir)
    elif args.cmd == "watch":
        try:
            watch(downloads_dir, args.interval)
        except KeyboardInterrupt:
            print("\n[WATCH] stopped")
    elif args.cmd == "status":
        cmd_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
