from __future__ import annotations

"""
api/exports.py
==============
WS6 — Multi-format export endpoints.

    GET  /api/export/{job_id}/formats        list available formats for a job
    POST /api/export/{job_id}/{format}       run an export and return a URL
    GET  /api/export/{job_id}/{format}       same, idempotent (cached file)
"""

from fastapi import APIRouter, HTTPException

from ..db import get_conn
from ..services.export_service import (
    SUPPORTED_FORMATS,
    export_render,
    result_to_dict,
)


router = APIRouter(prefix="/api/export", tags=["exports"])


def _job_or_404(job_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, status, local_output_path FROM render_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="render job not found")
    if not row["local_output_path"]:
        raise HTTPException(status_code=409, detail="render job has no output file yet")
    return {
        "id": row["id"],
        "status": row["status"],
        "local_output_path": row["local_output_path"],
    }


def _ffmpeg_exe() -> str | None:
    from ..main import get_setting
    return get_setting("ffmpeg_executable_path", "") or None


@router.get("/{job_id}/formats")
def list_formats(job_id: int):
    job = _job_or_404(job_id)
    return {
        "ok": True,
        "job_id": job_id,
        "formats": sorted(SUPPORTED_FORMATS),
        "source_mp4": job["local_output_path"],
    }


@router.post("/{job_id}/{fmt}")
def run_export(job_id: int, fmt: str):
    job = _job_or_404(job_id)
    if fmt not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail=f"unknown format: {fmt}")

    result = export_render(
        job_id=job_id,
        mp4_path=job["local_output_path"],
        fmt=fmt,
        ffmpeg_exe=_ffmpeg_exe(),
    )
    return {"ok": result.ok, "job_id": job_id, "result": result_to_dict(result)}


@router.get("/{job_id}/{fmt}")
def get_export(job_id: int, fmt: str):
    """Idempotent variant — runs the exporter, but cached files return instantly."""
    return run_export(job_id, fmt)
