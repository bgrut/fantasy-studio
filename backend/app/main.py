from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import HOST, PORT, LOCAL_RENDER_MODE, BLENDER_EXE, OUTPUT_DIR
from .db import get_conn, init_db
from .schemas import SettingsPayload, RenderJobCreate
from .blender_runner import run_mock_render, run_blender_ai_render
from .api.assets import router as assets_router
from .api.uploads import router as uploads_router
from .api.templates import router as templates_router
from .api.render_extras import router as render_extras_router
from .api.exports import router as exports_router
from .api.llm_diag import router as llm_diag_router
from .api.catalog import router as catalog_router
from .api.curation import router as curation_router
from .api.pipeline import router as pipeline_router
from .api.library import router as library_router

app = FastAPI(title="FantasyLab Blender Lane Backend")
app.include_router(assets_router)
app.include_router(uploads_router)
app.include_router(templates_router)
app.include_router(render_extras_router)
app.include_router(exports_router)
app.include_router(llm_diag_router)
app.include_router(catalog_router)
app.include_router(curation_router)
app.include_router(pipeline_router)
app.include_router(library_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


def row_to_dict(row):
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def add_event(job_id: int, stage: str, message: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO job_events(job_id, stage, message) VALUES (?, ?, ?)",
            (job_id, stage, message),
        )


def get_setting(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    return row["value"]


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )


def process_job(job_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM render_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return

    add_event(job_id, "planning", "Render job picked up by worker")

    with get_conn() as conn:
        conn.execute(
            "UPDATE render_jobs SET status='planning', updated_at=datetime('now') WHERE id=?",
            (job_id,),
        )

    local_render_mode = get_setting("local_render_mode", "1") == "1"

    with get_conn() as conn:
        conn.execute(
            "UPDATE render_jobs SET status='rendering', updated_at=datetime('now') WHERE id=?",
            (job_id,),
        )

    add_event(job_id, "rendering", "Render started")

    if local_render_mode:
        blender_exe = get_setting("blender_executable_path", BLENDER_EXE)
        ffmpeg_exe = get_setting("ffmpeg_executable_path", "") or None

        # Parse directorial controls from DB column (JSON or None)
        import json as _json
        directorial_controls = None
        raw_ctrl = row["directorial_controls"] if "directorial_controls" in row.keys() else None
        if raw_ctrl:
            try:
                directorial_controls = _json.loads(raw_ctrl)
            except Exception:
                pass

        result = run_blender_ai_render(
            row["topic"],
            row["template_name"],
            blender_exe,
            ffmpeg_exe,
            directorial_controls=directorial_controls,
        )
        provider_name = "LocalBlenderCliProvider"
    else:
        result = run_mock_render(row["topic"], row["template_name"])
        provider_name = "MockRenderProvider"

    if result["ok"]:
        output_path = result["output_path"]
        output_name = Path(output_path).name
        output_url = f"/outputs/{output_name}"

        with get_conn() as conn:
            conn.execute(
                """
                UPDATE render_jobs
                SET status='complete',
                    provider_name=?,
                    local_output_path=?,
                    output_url=?,
                    stdout_log=?,
                    stderr_log=?,
                    error_text=NULL,
                    updated_at=datetime('now')
                WHERE id=?
                """,
                (
                    provider_name,
                    output_path,
                    output_url,
                    result.get("stdout", ""),
                    result.get("stderr", ""),
                    job_id,
                ),
            )
        add_event(job_id, "complete", f"Render completed via {provider_name}")
    else:
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE render_jobs
                SET status='failed',
                    provider_name=?,
                    stdout_log=?,
                    stderr_log=?,
                    error_text=?,
                    updated_at=datetime('now')
                WHERE id=?
                """,
                (
                    provider_name,
                    result.get("stdout", ""),
                    result.get("stderr", ""),
                    result.get("error", "Unknown render failure"),
                    job_id,
                ),
            )
        add_event(job_id, "failed", result.get("error", "Unknown render failure"))


@app.on_event("startup")
def startup():
    init_db()
    if get_setting("blender_executable_path") is None:
        set_setting("blender_executable_path", BLENDER_EXE)
    if get_setting("ffmpeg_executable_path") is None:
        set_setting("ffmpeg_executable_path", "")
    if get_setting("local_render_mode") is None:
        set_setting("local_render_mode", "1" if LOCAL_RENDER_MODE else "0")


@app.get("/api/health")
def health():
    with get_conn() as conn:
        counts = {
            "queued": conn.execute("SELECT COUNT(*) c FROM render_jobs WHERE status='queued'").fetchone()["c"],
            "planning": conn.execute("SELECT COUNT(*) c FROM render_jobs WHERE status='planning'").fetchone()["c"],
            "rendering": conn.execute("SELECT COUNT(*) c FROM render_jobs WHERE status='rendering'").fetchone()["c"],
            "complete": conn.execute("SELECT COUNT(*) c FROM render_jobs WHERE status='complete'").fetchone()["c"],
            "failed": conn.execute("SELECT COUNT(*) c FROM render_jobs WHERE status='failed'").fetchone()["c"],
        }

    return {
        "ok": True,
        "service": "blender_lane_backend",
        "counts": counts,
        "settings": {
            "blender_executable_path": get_setting("blender_executable_path"),
            "ffmpeg_executable_path": get_setting("ffmpeg_executable_path"),
            "local_render_mode": get_setting("local_render_mode") == "1",
        },
    }


@app.get("/api/settings")
def get_settings():
    return {
        "blender_executable_path": get_setting("blender_executable_path"),
        "ffmpeg_executable_path": get_setting("ffmpeg_executable_path"),
        "local_render_mode": get_setting("local_render_mode") == "1",
    }


@app.post("/api/settings")
def update_settings(payload: SettingsPayload):
    if payload.blender_executable_path is not None:
        set_setting("blender_executable_path", payload.blender_executable_path)
    if payload.ffmpeg_executable_path is not None:
        set_setting("ffmpeg_executable_path", payload.ffmpeg_executable_path)
    if payload.local_render_mode is not None:
        set_setting("local_render_mode", "1" if payload.local_render_mode else "0")

    return {"ok": True, "settings": get_settings()}


@app.post("/api/render-jobs")
def create_render_job(payload: RenderJobCreate):
    # Serialize directorial controls to JSON for storage (if provided)
    import json as _json
    controls_json = None
    if payload.directorial_controls:
        controls_json = _json.dumps(payload.directorial_controls.model_dump(exclude_none=True))

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO render_jobs(project_name, topic, template_name, status, provider_name, directorial_controls)
            VALUES (?, ?, ?, 'queued', 'Pending', ?)
            """,
            (payload.project_name, payload.topic, payload.template_name, controls_json),
        )
        job_id = cur.lastrowid

    add_event(job_id, "queued", "Job created")

    t = threading.Thread(target=process_job, args=(job_id,), daemon=True)
    t.start()

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM render_jobs WHERE id = ?", (job_id,)).fetchone()

    return {"ok": True, "job": row_to_dict(row)}


@app.get("/api/render-jobs")
def list_render_jobs():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM render_jobs ORDER BY id DESC").fetchall()
    return {"ok": True, "jobs": [row_to_dict(r) for r in rows]}


@app.get("/api/render-jobs/{job_id}")
def get_render_job(job_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM render_jobs WHERE id = ?", (job_id,)).fetchone()
        events = conn.execute(
            "SELECT * FROM job_events WHERE job_id = ? ORDER BY id ASC",
            (job_id,),
        ).fetchall()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "ok": True,
        "job": row_to_dict(row),
        "events": [row_to_dict(e) for e in events],
    }


def _manifest_path_for_job(row) -> Path | None:
    """
    Extract the manifest path for a render job.

    blender_runner writes ``MANIFEST_PATH: <path>`` as the first line of
    the combined stdout log. Parse it out so downstream endpoints
    (credits / recipe) can re-read the manifest without needing to change
    the schema.
    """
    stdout = (row["stdout_log"] if row else "") or ""
    for line in stdout.splitlines()[:5]:
        if line.startswith("MANIFEST_PATH:"):
            candidate = line.split(":", 1)[1].strip()
            if candidate:
                p = Path(candidate)
                if p.exists():
                    return p
    return None


def _load_job_manifest(job_id: int) -> dict | None:
    import json as _json
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM render_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    mp = _manifest_path_for_job(row)
    if mp is None:
        return None
    try:
        return _json.loads(mp.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


@app.get("/api/render-jobs/{job_id}/credits")
def get_render_job_credits(job_id: int):
    """
    Return attribution credits for every CC-licensed asset the job used.
    Reads resolved_assets from the manifest on disk (written by the
    render pipeline) and feeds it through app.services.credits.
    """
    try:
        from .services.credits import generate_credits
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"credits module unavailable: {e}")

    manifest = _load_job_manifest(job_id)
    if manifest is None:
        return {
            "ok": True,
            "job_id": job_id,
            "credits": {
                "required": False,
                "text": "No manifest found for this job yet.",
                "items": [],
            },
        }
    return {"ok": True, "job_id": job_id, "credits": generate_credits(manifest)}


@app.get("/api/render-jobs/{job_id}/recipe")
def get_render_job_recipe(job_id: int):
    """
    Return the scene recipe the render pipeline produced. This is the
    decomposition of the prompt into hero/env/ground/sky/atmosphere/
    lighting/camera/props/compositor used by the Scene Breakdown panel.
    """
    manifest = _load_job_manifest(job_id)
    if manifest is None:
        return {"ok": True, "job_id": job_id, "recipe": None}
    return {
        "ok": True,
        "job_id": job_id,
        "recipe": manifest.get("scene_recipe") or None,
        "scene_plan": manifest.get("_scene_plan") or None,
    }


@app.post("/api/render-jobs/{job_id}/retry")
def retry_render_job(job_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM render_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        conn.execute(
            """
            UPDATE render_jobs
            SET status='queued',
                retry_count=retry_count+1,
                error_text=NULL,
                updated_at=datetime('now')
            WHERE id=?
            """,
            (job_id,),
        )

    add_event(job_id, "retry", "Manual retry requested")

    t = threading.Thread(target=process_job, args=(job_id,), daemon=True)
    t.start()

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM render_jobs WHERE id = ?", (job_id,)).fetchone()

    return {"ok": True, "job": row_to_dict(row)}

