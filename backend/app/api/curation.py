from __future__ import annotations

"""
api/curation.py
===============
Round 12 — auto-curation control surface.

The curated asset library underpins Round 11's Priority-1 hero resolver.
Curating each asset by hand (one CLI invocation per subject) is fine for
10 assets but doesn't scale to a "Build Starter Library" button. This
router exposes:

    POST /api/curate/auto              kick off a background curation task
    GET  /api/curate/status/{id}       poll task progress
    GET  /api/curate/catalog           current curated catalog (json)
    POST /api/curate/rebuild-catalog   re-scan metadata.json files
    POST /api/curate/register-existing register the legacy registry +
                                       cache assets into the catalog

Each background task shells out to the existing CLI tools so the curation
pipeline (download → probe in headless Blender → normalise → catalog)
stays in one place: ``tools/curate_asset.py``. That guarantees the API
and the CLI never drift apart.

Tasks live in an in-memory dict keyed by short uuid. Status is "queued"
→ "running" → "complete" / "failed". Long-running auto-curation never
blocks the FastAPI event loop; everything happens on a daemon thread.
"""

import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/curate", tags=["curation"])

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TOOLS_DIR = _PROJECT_ROOT / "tools"
_CURATE_SCRIPT = _TOOLS_DIR / "curate_asset.py"
_BUILD_CATALOG_SCRIPT = _TOOLS_DIR / "build_catalog.py"
_REGISTER_SCRIPT = _TOOLS_DIR / "register_existing_assets.py"

# Per-subject timeout (Blender headless probe usually finishes in
# under 60s but a slow Sketchfab download + giant model can run long).
_PER_SUBJECT_TIMEOUT_S = 240


# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════

class CurationRequest(BaseModel):
    category: str = Field(
        description="Top-level category for every subject in this batch "
                    "(animal | vehicle | character | environment | prop). "
                    "Use 'mixed' to allow per-subject auto-categorisation.",
    )
    subjects: list[str] = Field(
        description="List of subjects to curate, e.g. ['dog', 'cat', 'horse']",
    )
    max_per_subject: int = Field(default=1, ge=1, le=3,
                                 description="How many models to download per subject")
    animated_only: bool = Field(default=True,
                                description="Prefer rigged/animated models")
    max_candidates: int = Field(default=12, ge=4, le=48,
                                description="How many Sketchfab results to score before picking")


class CurationStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    total: int
    downloaded: list[str]
    errors: list[str]
    started_at: float
    finished_at: Optional[float] = None


# ═══════════════════════════════════════════════════════════════════════════
# Task registry (in-memory; survives only as long as the process)
# ═══════════════════════════════════════════════════════════════════════════

_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


def _make_task(total: int) -> tuple[str, dict]:
    task_id = uuid.uuid4().hex[:8]
    task = {
        "task_id":     task_id,
        "status":      "queued",
        "progress":    0,
        "total":       total,
        "downloaded":  [],
        "errors":      [],
        "started_at":  time.time(),
        "finished_at": None,
    }
    with _tasks_lock:
        _tasks[task_id] = task
    return task_id, task


def _update(task: dict, **fields) -> None:
    with _tasks_lock:
        task.update(fields)


# ═══════════════════════════════════════════════════════════════════════════
# Auto-categorisation for "mixed" batches
# ═══════════════════════════════════════════════════════════════════════════

_MIXED_HINTS = {
    "animal":      {"dog", "cat", "horse", "tiger", "lion", "bear", "wolf",
                    "eagle", "dolphin", "whale", "fish", "bird", "deer",
                    "fox", "rabbit", "elephant", "giraffe", "shark", "snake"},
    "vehicle":     {"car", "truck", "motorcycle", "bike", "plane", "boat",
                    "helicopter", "tank", "racecar", "bus", "scooter"},
    "character":   {"robot", "knight", "warrior", "ninja", "wizard",
                    "soldier", "human", "person", "girl", "boy", "dancer",
                    "samurai", "viking", "pirate"},
    "environment": {"city", "building", "house", "castle", "tree", "forest",
                    "mountain", "rock", "rocks", "skyscraper", "tower",
                    "bridge", "ruins"},
    "prop":        {"chair", "table", "lamp", "sword", "gun", "shield",
                    "barrel", "crate", "book", "phone", "laptop", "vase",
                    "guitar", "bottle"},
}


def _auto_category(subject: str) -> str:
    s = (subject or "").lower()
    for cat, hints in _MIXED_HINTS.items():
        if any(word in s for word in hints):
            return cat
    return "prop"


# ═══════════════════════════════════════════════════════════════════════════
# Background worker
# ═══════════════════════════════════════════════════════════════════════════

def _run_subprocess(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Wrap subprocess.run so we always return a CompletedProcess-like result."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(_PROJECT_ROOT),
    )


def _curate_one(subject: str, category: str, animated: bool, max_candidates: int) -> tuple[bool, str]:
    """
    Curate a single subject. Returns (ok, message). On failure the
    message is the trimmed stderr or exception text.
    """
    if not _CURATE_SCRIPT.exists():
        return (False, f"curate script missing: {_CURATE_SCRIPT}")

    cmd = [
        sys.executable,
        str(_CURATE_SCRIPT),
        "--search",          subject,
        "--category",        category,
        "--subcategory",     subject.lower().replace(" ", "_"),
        "--keywords",        f"{subject},{category}",
        "--max-candidates",  str(max_candidates),
    ]
    if animated:
        cmd.append("--animated")

    try:
        proc = _run_subprocess(cmd, timeout=_PER_SUBJECT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return (False, f"timed out after {_PER_SUBJECT_TIMEOUT_S}s")
    except Exception as e:
        return (False, f"{type(e).__name__}: {e}")

    if proc.returncode == 0:
        return (True, (proc.stdout or "")[-300:])
    err = (proc.stderr or proc.stdout or "").strip().splitlines()
    tail = " | ".join(err[-3:])[:400] if err else f"exit {proc.returncode}"
    return (False, tail)


def _run_auto_curation(task: dict, req: CurationRequest) -> None:
    _update(task, status="running")
    try:
        for i, subject in enumerate(req.subjects):
            cat = req.category if req.category != "mixed" else _auto_category(subject)
            print(f"[AUTO_CURATE] [{i+1}/{len(req.subjects)}] subject={subject!r} cat={cat}",
                  flush=True)

            ok = False
            last_err = ""
            for attempt in range(req.max_per_subject):
                ok, msg = _curate_one(
                    subject=subject,
                    category=cat,
                    animated=req.animated_only,
                    max_candidates=req.max_candidates,
                )
                if ok:
                    label = f"{subject}" if attempt == 0 else f"{subject}#{attempt+1}"
                    with _tasks_lock:
                        task["downloaded"].append(label)
                    print(f"[AUTO_CURATE] OK -> {label}", flush=True)
                    break
                last_err = msg
                print(f"[AUTO_CURATE] attempt {attempt+1} failed: {msg}", flush=True)

            if not ok:
                with _tasks_lock:
                    task["errors"].append(f"{subject}: {last_err[:240]}")

            with _tasks_lock:
                task["progress"] = int(((i + 1) / max(len(req.subjects), 1)) * 100)

        # Final catalog rebuild + cache invalidation.
        try:
            if _BUILD_CATALOG_SCRIPT.exists():
                _run_subprocess([sys.executable, str(_BUILD_CATALOG_SCRIPT)], timeout=60)
        except Exception as e:
            print(f"[AUTO_CURATE] rebuild_catalog failed: {e}", flush=True)
        try:
            from ..services.curated_resolver import invalidate_catalog_cache
            invalidate_catalog_cache()
        except Exception:
            pass

        _update(task, status="complete", progress=100, finished_at=time.time())
        print(
            f"[AUTO_CURATE] task {task['task_id']} done: "
            f"{len(task['downloaded'])} ok / {len(task['errors'])} errors",
            flush=True,
        )
    except Exception as e:
        _update(task, status="failed", finished_at=time.time())
        with _tasks_lock:
            task["errors"].append(f"worker crashed: {type(e).__name__}: {e}")
        print(f"[AUTO_CURATE] task {task['task_id']} crashed: {e}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/auto")
def start_auto_curation(req: CurationRequest):
    if not req.subjects:
        raise HTTPException(status_code=400, detail="subjects must be non-empty")
    valid_cats = {"animal", "vehicle", "character", "environment", "prop", "mixed"}
    if req.category not in valid_cats:
        raise HTTPException(
            status_code=400,
            detail=f"category must be one of {sorted(valid_cats)}",
        )

    task_id, task = _make_task(total=len(req.subjects))
    t = threading.Thread(
        target=_run_auto_curation,
        args=(task, req),
        daemon=True,
        name=f"auto-curate-{task_id}",
    )
    t.start()
    return {"ok": True, "task_id": task_id, "total": len(req.subjects)}


@router.get("/status/{task_id}")
def get_curation_status(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
        snapshot = dict(task) if task else None
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    return {"ok": True, **snapshot}


@router.get("/tasks")
def list_curation_tasks():
    """List recent task ids + status. Useful for a UI list view."""
    with _tasks_lock:
        items = [
            {
                "task_id":   t["task_id"],
                "status":    t["status"],
                "progress":  t["progress"],
                "total":     t["total"],
                "ok_count":  len(t["downloaded"]),
                "err_count": len(t["errors"]),
                "started_at": t["started_at"],
            }
            for t in _tasks.values()
        ]
    items.sort(key=lambda x: x["started_at"], reverse=True)
    return {"ok": True, "tasks": items}


@router.get("/catalog")
def get_catalog():
    """Return the current curated catalog so the frontend can render it."""
    try:
        from ..services.curated_resolver import load_catalog
        catalog = load_catalog()
        # Group by category so the UI can show counts at a glance.
        groups: dict[str, int] = {}
        for a in catalog.get("assets") or []:
            c = str(a.get("category") or "unknown")
            groups[c] = groups.get(c, 0) + 1
        return {"ok": True, "catalog": catalog, "counts_by_category": groups}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"catalog load failed: {e}")


@router.post("/rebuild-catalog")
def rebuild_catalog():
    """Re-scan ``assets/curated/**/metadata.json`` and rebuild catalog.json."""
    if not _BUILD_CATALOG_SCRIPT.exists():
        raise HTTPException(status_code=500, detail="build_catalog.py is missing")
    try:
        proc = _run_subprocess([sys.executable, str(_BUILD_CATALOG_SCRIPT)], timeout=60)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"rebuild failed: {e}")

    try:
        from ..services.curated_resolver import invalidate_catalog_cache
        invalidate_catalog_cache()
    except Exception:
        pass

    return {
        "ok":     proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


@router.post("/register-existing")
def register_existing():
    """
    Scan the legacy ``asset_registry.json`` + asset cache folders and
    register them in the curated catalog. Idempotent — safe to re-run.
    """
    if not _REGISTER_SCRIPT.exists():
        raise HTTPException(status_code=500, detail="register_existing_assets.py is missing")
    try:
        proc = _run_subprocess([sys.executable, str(_REGISTER_SCRIPT)], timeout=120)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"register failed: {e}")

    try:
        from ..services.curated_resolver import invalidate_catalog_cache
        invalidate_catalog_cache()
    except Exception:
        pass

    return {
        "ok":     proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Convenience: starter-library subject preset
# ═══════════════════════════════════════════════════════════════════════════

STARTER_LIBRARY_SUBJECTS = [
    # animals
    "dog", "cat", "horse", "tiger", "eagle", "dolphin", "whale",
    # vehicles
    "sports car", "motorcycle", "truck",
    # characters
    "robot", "knight", "warrior",
    # environments
    "tree", "rock", "city building",
]


@router.get("/starter-library")
def starter_library_preset():
    """Returns the canonical Build Starter Library subject list."""
    return {"ok": True, "subjects": STARTER_LIBRARY_SUBJECTS}
