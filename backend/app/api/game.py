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


def _record_start(prompt: str) -> int | None:
    """Insert a render_jobs row so game builds show up LIVE in the pipeline
    bar and land in Gallery/Insights like every video run. Never raises."""
    try:
        from app.db import get_conn
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO render_jobs(project_name, topic, template_name, status, provider_name) "
                "VALUES ('game', ?, '__game__', 'rendering', 'GameExport')",
                (prompt,))
            return cur.lastrowid
    except Exception:
        return None


def _record_finish(row_id: int | None, ok: bool, play_url: str | None,
                   error: str | None) -> None:
    if row_id is None:
        return
    try:
        from app.db import get_conn
        with get_conn() as conn:
            conn.execute(
                "UPDATE render_jobs SET status=?, output_url=?, error_text=?, "
                "updated_at=datetime('now') WHERE id=?",
                ("complete" if ok else "failed", play_url, error, row_id))
    except Exception:
        pass


class GameExportRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    player: str | None = None    # override; None = cast from the prompt (extractor)
    godot: bool = False          # also emit a Godot 4 project
    seed: int | None = None      # world-layout seed; None = fresh random level


def _run_job(job_id: int, req: GameExportRequest) -> None:
    job = _jobs[job_id]
    row_id = _record_start(req.prompt)     # metrics: live row in the pipeline bar

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
        # PLAYER CASTING (accuracy-first, like the video hero): explicit
        # override > the prompt's extracted subject > man. Falls through the
        # ladder with a visible note whenever the cast changes.
        want = (req.player or spec.player.name or "man").strip().lower()
        from app.game_export.bake import ensure_playable
        from app.game_export.generate import guess_pattern
        cast = want
        if guess_pattern(want) == "vehicle":                 # cars DRIVE, no rig needed
            player_glb = library.resolve(want)
            if player_glb:
                spec.player.mode = "drive"
                if abs(spec.player.walk_speed - 2.0) < 1e-6:
                    spec.player.walk_speed = 9.0             # cruise
                if abs(spec.player.run_speed - 5.0) < 1e-6:
                    spec.player.run_speed = 19.0             # boost
        else:
            player_glb = ensure_playable(want, verbose=False)  # rig+animate on first use
        if not player_glb:
            try:
                from app.game_export.generate import ensure_asset
                ensure_asset(want)                # generates when GPU present
                player_glb = ensure_playable(want, verbose=False)
            except Exception as ge:
                job.setdefault("notes", []).append(
                    f"player '{want}' unavailable ({type(ge).__name__}) — cast as man")
        if not player_glb:
            job.setdefault("notes", []).append(f"cast fell back: {want} -> man")
            player_glb = library.resolve("man")
            cast = "man"
        if not player_glb:
            raise RuntimeError("no player asset in library (assets/library.json)")
        spec.player.asset = player_glb
        spec.player.name = cast
        if abs(spec.player.height_m - 1.75) < 1e-6:      # untouched default -> species height
            spec.player.height_m = library.default_height(cast)
        job["player"] = cast
        if not spec.world.scatter:
            spec.world.scatter = [ScatterSpec(**s) for s in game_scatter(spec.world.name)]
        kept = []
        for ent in spec.entities:
            # prefer the ANIMATED variant (real gait — no gliding); static fallback
            glb = ensure_playable(ent.name, verbose=False) or library.resolve(ent.name)
            if glb:
                ent.asset = glb
                if ent.height_m == 1.0:
                    ent.height_m = library.default_height(ent.name)
                kept.append(ent)
            else:
                job.setdefault("notes", []).append(
                    f"entity '{ent.name}' not in library yet — skipped")
        spec.entities = kept

        # RACE SANITY: a race step needs opponent VEHICLES — synthesize them
        # from the player's own kind when the extractor didn't cast any.
        from app.game_export.spec import EntitySpec
        for ob in spec.objectives:
            if ob.kind == "race" and not any(e.behavior == "vehicle" for e in spec.entities):
                okind = cast if guess_pattern(cast) == "vehicle" else "car"
                oglb = library.resolve(okind)
                if oglb:
                    spec.entities.append(EntitySpec(
                        name=okind, asset=oglb, behavior="vehicle",
                        count=min(ob.count, 8), speed=6.5,
                        height_m=library.default_height(okind)))

        # grass: off for cities and snow (quality-pack gate)
        from app.game_export.dressing import wants_grass
        spec.world.grass = wants_grass(spec.world.name, spec.world.weather)

        # MISSION SANITY: defeat steps need hostiles that actually resolved.
        # Clamp counts to what exists; drop unwinnable steps with a note.
        total_hostiles = sum(e.count for e in spec.entities if e.behavior == "hostile")
        sane = []
        for ob in spec.objectives:
            if ob.kind == "defeat":
                if total_hostiles <= 0:
                    job.setdefault("notes", []).append(
                        f"'defeat {ob.label}' dropped — no enemies could be cast")
                    continue
                ob.count = min(ob.count, total_hostiles)
            sane.append(ob)
        spec.objectives = sane

        stage("designing level")
        from app.game_export.level import build_level, build_osm_city, detect_place
        n_obj = sum(o.count for o in spec.objectives if o.kind == "collect")
        is_city = any(k in (spec.world.name or "").lower() for k in ("city", "street", "town"))
        # REAL CITIES (shared with video's OSM system): a named place in the
        # prompt swaps procedural building scatter for actual OSM footprints.
        # Real blocks are ~100-250m — the world grows to hold a real district.
        place = detect_place(req.prompt) if is_city else None
        if place:
            spec.world.size_m = max(spec.world.size_m, 360.0)
        spec.world.level = build_level(
            spec.seed, spec.world.size_m, n_objectives=n_obj,
            amplitude_m=0.35 if is_city else 2.4)   # cities are near-flat
        if place:
            stage(f"fetching {place} map (OpenStreetMap)")
            osm = build_osm_city(place, spec.world.size_m)
            if osm:
                spec.world.level["osm"] = osm
                # streets are the level: the mission path FOLLOWS the road
                # route (race rivals, collectibles and the goal pin to it) and
                # the ground is dead flat so nothing pokes through the asphalt
                route = osm.get("route")
                if route:
                    spec.world.level["path"] = route
                    spec.world.level["goal"] = list(route[-1])
                    n = len(route)
                    spec.world.level["collect_points"] = [
                        list(route[int((k + 1) / (n_obj + 1) * (n - 1))])
                        for k in range(n_obj)]
                    g = spec.world.level["grid_n"]
                    spec.world.level["heights"] = [0.0] * (g * g)
                spec.world.scatter = [s for s in spec.world.scatter
                                      if "building" not in Path(s.asset).name]
                job.setdefault("notes", []).append(
                    f"real-city map: {place} ({len(osm['buildings'])} buildings, "
                    f"{len(osm['roads'])} roads, route={'yes' if route else 'no'}, "
                    f"© OpenStreetMap contributors)")
            else:
                job.setdefault("notes", []).append(
                    f"OSM fetch for '{place}' unavailable — procedural city used")

        stage("building")
        # RESOLVED spec (absolute asset paths) — lets Game Projects re-export
        # this exact level later without re-running extraction
        job["spec_resolved"] = spec.model_dump()
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
        _record_finish(row_id, True, job["play_url"], None)
    except Exception as e:
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {e}"
        job["trace"] = traceback.format_exc()[-1500:]
        stage("failed")
        _record_finish(row_id, False, None, job["error"])


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
