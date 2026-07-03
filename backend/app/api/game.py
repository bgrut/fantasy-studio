"""Game-mode API (Phase 30): prompt → playable web game, served back to the
frontend. Mirrors the render-jobs UX (submit → poll → play) but games build in
seconds and need NO GPU (library assets), so this works while the video lane's
generation is GPU-blocked.

Jobs are in-memory (games rebuild in ~30s; no DB migration risk). Built games
are served by the /games static mount added in main.py.
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GAME_JOBS_DIR = BACKEND_ROOT / "renders" / "game_jobs"

_jobs: dict[int, dict] = {}
_next_id = 1
_lock = threading.Lock()


class GameExportRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    player: str = "man"          # library kind for the controllable character
    godot: bool = False          # also emit a Godot 4 project
    seed: int | None = None      # world-layout seed; None = fresh random level


def _run_job(job_id: int, req: GameExportRequest) -> None:
    job = _jobs[job_id]

    def stage(s: str) -> None:
        job["stage"] = s
        job["updated_at"] = time.time()

    try:
        from app.game_export import library
        from app.game_export.extractor import extract_game_spec
        from app.game_export.dressing import game_scatter
        from app.game_export.spec import ScatterSpec
        from app.game_export.verify_game import verify_dist
        from app.game_export.web_exporter import export_web_game

        stage("extracting")
        spec = extract_game_spec(req.prompt, verbose=False)
        job["title"] = spec.title

        # LEVEL VARIETY: every build gets a fresh world layout (scatter,
        # collectible ring, NPC spawns all derive from this seed). Rebuild =
        # a NEW level; pass an explicit seed to reproduce a favorite one.
        import random as _random
        spec.seed = req.seed if req.seed is not None else _random.randint(1, 999_999)
        job["seed"] = spec.seed

        stage("resolving assets")
        player_glb = library.resolve(req.player) or library.resolve("man")
        if not player_glb:
            raise RuntimeError("no player asset in library (assets/library.json)")
        spec.player.asset = player_glb
        if not spec.world.scatter:
            spec.world.scatter = [ScatterSpec(**s) for s in game_scatter(spec.world.name)]
        kept = []
        for ent in spec.entities:
            glb = library.resolve(ent.name)
            if glb:
                ent.asset = glb
                if ent.height_m == 1.0:
                    ent.height_m = library.default_height(ent.name)
                kept.append(ent)
            else:
                job.setdefault("notes", []).append(
                    f"entity '{ent.name}' not in library yet — skipped")
        spec.entities = kept

        stage("designing level")
        from app.game_export.level import build_level
        n_obj = sum(o.count for o in spec.objectives if o.kind == "collect")
        spec.world.level = build_level(spec.seed, spec.world.size_m, n_objectives=n_obj)

        stage("building")
        out_dir = GAME_JOBS_DIR / f"job_{job_id}"
        dist = export_web_game(spec, out_dir, verbose=False)

        stage("verifying")
        v = verify_dist(dist)
        if not v["ok"]:
            raise RuntimeError(f"verify failed: {v['errors']}")

        if req.godot:
            stage("emitting godot project")
            from app.game_export.godot_exporter import export_godot_game
            export_godot_game(spec, out_dir, verbose=False)
            job["godot_path"] = str(out_dir / "godot")

        job["status"] = "complete"
        job["play_url"] = f"/games/job_{job_id}/dist/"
        job["checks"] = len(v["checks"])
        stage("done")
    except Exception as e:
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {e}"
        job["trace"] = traceback.format_exc()[-1500:]
        stage("failed")


@router.post("/api/game/export")
def export_game(req: GameExportRequest):
    global _next_id
    with _lock:
        job_id = _next_id
        _next_id += 1
        _jobs[job_id] = {
            "id": job_id, "prompt": req.prompt, "status": "running",
            "stage": "queued", "created_at": time.time(), "updated_at": time.time(),
        }
    t = threading.Thread(target=_run_job, args=(job_id, req), daemon=True)
    t.start()
    return {"ok": True, "job_id": job_id}


@router.get("/api/game/jobs/{job_id}")
def get_game_job(job_id: int):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="game job not found")
    return {"ok": True, "job": {k: v for k, v in job.items() if k != "trace"},
            "trace": job.get("trace")}


@router.get("/api/game/jobs")
def list_game_jobs():
    return {"ok": True, "jobs": sorted(_jobs.values(), key=lambda j: -j["id"])[:50]}


@router.get("/api/game/library")
def get_library():
    """The generated-asset catalog (the user's creations ARE the marketplace).
    Raw entries are generations awaiting first-use optimization."""
    import json as _json
    from app.game_export import library as lib
    out = []
    try:
        data = _json.loads(lib.LIBRARY_JSON.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    for kind, entry in sorted(data.items()):
        rel = entry if isinstance(entry, str) else entry.get("raw", "")
        p = lib.BACKEND_ROOT / rel
        out.append({
            "kind": kind,
            "ready": isinstance(entry, str),
            "path": rel,
            "size_mb": round(p.stat().st_size / 1e6, 1) if p.exists() else None,
            "source": "generated",
        })
    return {"ok": True, "assets": out, "count": len(out)}


@router.get("/api/game/health")
def game_health():
    """Game mode works without a GPU — report what's available."""
    from app.game_export import library as lib
    kinds = []
    try:
        import json as _json
        kinds = list(_json.loads(lib.LIBRARY_JSON.read_text(encoding="utf-8")).keys())
    except Exception:
        pass
    ollama = False
    try:
        from app.orchestrator.llm import OllamaClient
        ollama = OllamaClient().is_alive()
    except Exception:
        pass
    return {"ok": True, "gpu_free": True, "ollama": ollama, "library_kinds": kinds}
