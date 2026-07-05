"""Phase 38 — Story Director API: one prompt → planned scenes → rendered
film, auto-assembled as a Video Project.

POST /api/story {prompt, scenes?} → {job_id, project_id}. A daemon thread:
  1. plan_story()            — Ollama beat sheet (deterministic fallback)
  2. render each scene       — the SAME slot pipeline as /api/orchestrate,
                               strictly sequential (CPU/iGPU-safe)
  3. add scenes to a Video Project (Phase 35) as they finish — partial
     progress is never lost; the user can re-order / re-render in the UI
  4. export the concat film  — the project's own ffmpeg export

Progress rides the render_jobs table ('__story__' rows) so the pipeline bar,
Gallery and Insights see films like every other run.
"""
from __future__ import annotations

import shutil
import threading
import time
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import OUTPUT_DIR
from ..db import get_conn

router = APIRouter()

_jobs: dict[int, dict] = {}
_next = 1
_lock = threading.Lock()


class StoryRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    scenes: int = Field(3, ge=2, le=5)      # beats in the film
    render_tier: str = "fast"
    model: str | None = None


def _row_start(prompt: str) -> int | None:
    try:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO render_jobs(project_name, topic, template_name, status, provider_name) "
                "VALUES ('story', ?, '__story__', 'rendering', 'StoryDirector')", (prompt,))
            return cur.lastrowid
    except Exception:
        return None


def _row_finish(row_id: int | None, ok: bool, url: str | None, err: str | None) -> None:
    if row_id is None:
        return
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE render_jobs SET status=?, output_url=?, error_text=?, "
                "updated_at=datetime('now') WHERE id=?",
                ("complete" if ok else "failed", url, err, row_id))
    except Exception:
        pass


def _run(job_id: int, req: StoryRequest) -> None:
    job = _jobs[job_id]
    row = _row_start(req.prompt)

    def stage(s: str) -> None:
        job["stage"] = s
        job["updated_at"] = time.time()

    try:
        from app.orchestrator import render_from_prompt
        from app.orchestrator.story_director import plan_story
        from . import video_projects as vp

        stage("planning (beat sheet)")
        plan = plan_story(req.prompt, n_scenes=req.scenes, model=req.model)
        job["plan"] = plan

        # the film IS a Video Project — the user can re-order / extend it later
        with vp._vlock:
            data = vp._load()
            pid = data["next_id"]; data["next_id"] += 1
            data["projects"][str(pid)] = {"id": pid, "name": plan["title"],
                                          "created_at": time.time(), "scenes": []}
            vp._save(data)
        job["project_id"] = pid

        done = 0
        for i, sc in enumerate(plan["scenes"]):
            stage(f"rendering scene {i + 1}/{len(plan['scenes'])}: {sc['title']}")
            try:
                # SEQUENTIAL renders only (iGPU/CPU lesson: never parallel Blender)
                result = render_from_prompt(prompt=sc["prompt"], mode="slots",
                                            model=req.model, verbose=False)
                src = result.get("video_path") or result.get("render_path")
                if not src or not Path(src).exists():
                    raise RuntimeError(f"no artifact ({result.get('errors')})")
                dst = Path(OUTPUT_DIR) / f"story_{job_id}_scene{i + 1}.mp4"
                shutil.copy2(src, dst)
                with vp._vlock:
                    data = vp._load()
                    p = data["projects"][str(pid)]
                    sdir = vp.VPROJ_DIR / f"project_{pid}" / "scenes"
                    sdir.mkdir(parents=True, exist_ok=True)
                    sdst = sdir / f"scene_{int(time.time() * 1000)}.mp4"
                    shutil.copy2(dst, sdst)
                    p["scenes"].append({"file": str(sdst), "title": sc["title"],
                                        "prompt": sc["prompt"], "added_at": time.time()})
                    vp._save(data)
                done += 1
                job["scenes_done"] = done
            except Exception as se:
                job.setdefault("notes", []).append(
                    f"scene {i + 1} '{sc['title']}' failed: {type(se).__name__}: {se}")

        if done == 0:
            raise RuntimeError("every scene render failed — see notes")

        stage("assembling film (ffmpeg)")
        exp = vp.export_vproject(pid)          # concat + normalize (Phase 35)
        job["status"] = "complete"
        job["play_url"] = exp["play_url"]
        job["download"] = exp["download"]
        stage("done")
        _row_finish(row, True, exp["play_url"], None)
    except Exception as e:
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {e}"
        job["trace"] = traceback.format_exc()[-1500:]
        stage("failed")
        _row_finish(row, False, None, job["error"])


@router.post("/api/story")
def submit_story(req: StoryRequest):
    global _next
    with _lock:
        job_id = _next; _next += 1
        _jobs[job_id] = {"id": job_id, "prompt": req.prompt, "status": "running",
                         "stage": "queued", "created_at": time.time(),
                         "updated_at": time.time()}
    threading.Thread(target=_run, args=(job_id, req), daemon=True).start()
    return {"ok": True, "job_id": job_id}


@router.get("/api/story/jobs/{job_id}")
def get_story_job(job_id: int):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="story job not found")
    return {"ok": True, "job": {k: v for k, v in job.items() if k != "trace"},
            "trace": job.get("trace")}


@router.get("/api/story/jobs")
def list_story_jobs():
    return {"ok": True, "jobs": sorted(_jobs.values(), key=lambda j: -j["id"])[:50]}


@router.post("/api/story/plan")
def preview_plan(req: StoryRequest):
    """Plan WITHOUT rendering — the frontend shows the beat sheet for approval
    (edit scene prompts, then render each via the normal flow if preferred)."""
    from app.orchestrator.story_director import plan_story
    return {"ok": True, "plan": plan_story(req.prompt, n_scenes=req.scenes,
                                           model=req.model)}
