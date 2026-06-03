"""
POST /api/orchestrate  —  Studio Orchestrator endpoint

Wraps the local-LLM orchestrator (app.orchestrator) so the frontend can call
it the same way it calls the legacy /api/render-jobs and /api/render/preview
endpoints. Reuses the existing render_jobs SQLite table so PipelineStatus
polling Just Works (no separate progress system needed).

Job lifecycle:
    1. POST /api/orchestrate {prompt, render_tier?, duration_seconds?, fps?}
    2. INSERT row into render_jobs with status='queued', template_name='__orchestrator__'
    3. Daemon thread runs orchestrator → updates status to planning → rendering → complete|failed
    4. On complete: writes output_url and local_output_path
    5. Frontend polls /api/pipeline/status (existing) OR /api/render-jobs/{id} (existing)
    6. Frontend displays /outputs/<mp4-name> via existing /outputs static mount
"""

import os
import shutil
import sqlite3
import threading
import traceback
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..db import get_conn
from ..config import OUTPUT_DIR

router = APIRouter(prefix="/api", tags=["orchestrate"])


# ───────────────────────────────────────────────────────────────────────
# Request / Response schemas
# ───────────────────────────────────────────────────────────────────────

class OrchestrateRequest(BaseModel):
    prompt: str = Field(..., description="English description of the scene/video to generate")
    project_name: Optional[str] = None
    duration_seconds: int = Field(5, ge=1, le=30, description="Video duration in seconds (animation mode only)")
    fps: int = Field(24, ge=12, le=60)
    render_tier: str = Field("fast", description="preview (EEVEE 16spp) | fast (EEVEE 64spp) | standard (CYCLES 64spp) | cinematic (CYCLES 256spp)")
    style: str = Field("photoreal", description="photoreal | cartoon | anime | painting | claymation — controls overall aesthetic")
    model: Optional[str] = Field(None, description="Override Ollama model (e.g. 'llama3.1:8b')")


class OrchestrateResponse(BaseModel):
    job_id: int
    status: str
    prompt: str
    template_name: str = "__orchestrator__"


# ───────────────────────────────────────────────────────────────────────
# Background worker
# ───────────────────────────────────────────────────────────────────────

def _orchestrate_job(job_id: int, req: OrchestrateRequest) -> None:
    """Run the orchestrator for one job, update render_jobs row, copy MP4 to /outputs."""
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE render_jobs SET status='planning', updated_at=datetime('now') WHERE id=?",
                (job_id,),
            )
            conn.execute(
                "INSERT INTO job_events(job_id, stage, message) VALUES (?, 'planning', 'orchestrator started')",
                (job_id,),
            )
            conn.commit()

        # Import lazily so any import error doesn't take down the API process
        from ..orchestrator import render_from_prompt

        with get_conn() as conn:
            conn.execute(
                "UPDATE render_jobs SET status='rendering', updated_at=datetime('now') WHERE id=?",
                (job_id,),
            )
            conn.execute(
                "INSERT INTO job_events(job_id, stage, message) VALUES (?, 'rendering', ?)",
                (job_id, f"orchestrator (slot mode) running (prompt: {req.prompt[:60]}...)"),
            )
            conn.commit()

        # Phase 9: slot-based pipeline (Sora-style). Reliable, fast.
        # Returns a dict (not a LoopResult). See app/orchestrator/__init__.py.
        # Append style + tier context so the slot extractor + composer see them
        full_prompt = req.prompt
        if req.style and req.style != "photoreal":
            full_prompt = f"{req.prompt} [style: {req.style}]"
        result_dict = render_from_prompt(
            prompt=full_prompt,
            mode="slots",
            model=req.model,
            verbose=False,
        )
        # Inject tier as an override in case the LLM didn't pick it
        result_dict.setdefault("requested_tier", req.render_tier)
        result_dict.setdefault("requested_style", req.style)

        artifact_src = result_dict.get("video_path") or result_dict.get("render_path")
        if not artifact_src or not Path(artifact_src).exists():
            raise RuntimeError(
                f"orchestrator produced no artifact. "
                f"errors={result_dict.get('errors')}, slots={result_dict.get('slots')}"
            )

        # Copy artifact into OUTPUT_DIR so /outputs/<name> can serve it
        src = Path(artifact_src)
        dst_name = f"orch_{job_id}_{src.name}"
        dst = Path(OUTPUT_DIR) / dst_name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        output_url = f"/outputs/{dst_name}"

        with get_conn() as conn:
            conn.execute(
                """
                UPDATE render_jobs
                SET status='complete',
                    local_output_path=?,
                    output_url=?,
                    updated_at=datetime('now')
                WHERE id=?
                """,
                (str(dst), output_url, job_id),
            )
            steps_run = result_dict.get("steps_run") or []
            duration_s = result_dict.get("duration_s") or 0.0
            conn.execute(
                "INSERT INTO job_events(job_id, stage, message) VALUES (?, 'complete', ?)",
                (job_id, f"orchestrator finished — {len(steps_run)} composer steps in {duration_s:.1f}s"),
            )
            conn.commit()

    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        trace = traceback.format_exc()
        try:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE render_jobs SET status='failed', updated_at=datetime('now') WHERE id=?",
                    (job_id,),
                )
                conn.execute(
                    "INSERT INTO job_events(job_id, stage, message) VALUES (?, 'failed', ?)",
                    (job_id, err),
                )
                conn.commit()
        except Exception:
            pass
        print(f"[orchestrate job {job_id}] FAILED: {err}\n{trace}")


# ───────────────────────────────────────────────────────────────────────
# Endpoint
# ───────────────────────────────────────────────────────────────────────

@router.post("/orchestrate", response_model=OrchestrateResponse, status_code=status.HTTP_201_CREATED)
def submit_orchestrate(req: OrchestrateRequest) -> OrchestrateResponse:
    """Submit a prompt to the local-LLM orchestrator. Returns immediately with a job_id;
    poll /api/render-jobs/{job_id} or /api/pipeline/status for progress."""
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO render_jobs(project_name, topic, template_name, status, provider_name)
            VALUES (?, ?, ?, 'queued', 'orchestrator')
            """,
            (
                req.project_name or "orchestrator",
                req.prompt,
                "__orchestrator__",
            ),
        )
        job_id = cur.lastrowid
        conn.execute(
            "INSERT INTO job_events(job_id, stage, message) VALUES (?, 'queued', 'orchestrate submitted')",
            (job_id,),
        )
        conn.commit()

    # Kick off background thread (matches the pattern used by /api/render-jobs)
    threading.Thread(target=_orchestrate_job, args=(job_id, req), daemon=True).start()

    return OrchestrateResponse(
        job_id=job_id,
        status="queued",
        prompt=req.prompt,
    )


@router.get("/orchestrate/health")
def orchestrate_health() -> dict:
    """Quick liveness check for orchestrator deps: Ollama reachable? Bridge reachable?"""
    out = {"ollama": False, "bridge": False, "errors": []}
    try:
        from ..orchestrator import OllamaClient
        out["ollama"] = OllamaClient().is_alive()
    except Exception as e:
        out["errors"].append(f"ollama: {e}")
    try:
        from ..mcp import bridge
        bridge.connect(timeout=2.0)
        out["bridge"] = bridge.ping(timeout=2.0)
    except Exception as e:
        out["errors"].append(f"bridge: {e}")
    out["ready"] = out["ollama"] and out["bridge"]
    return out
