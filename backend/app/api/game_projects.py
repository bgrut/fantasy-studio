"""Phase 34 — Game Projects: collect built levels into ONE game and export it.

A project is a named, disk-persisted list of levels (each the RESOLVED spec of
a completed build — re-exports are exact, no LLM re-roll). Export emits a
self-contained game: hub menu (level select) + each level's build + next-level
progression on win, served live under /games and zipped for shipping.
"""
from __future__ import annotations

import html
import json
import shutil
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .game import GAME_JOBS_DIR, _jobs

router = APIRouter()

PROJECTS_DIR = GAME_JOBS_DIR / "projects"
PROJECTS_JSON = PROJECTS_DIR / "projects.json"
_plock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(PROJECTS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"next_id": 1, "projects": {}}


def _save(data: dict) -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_JSON.write_text(json.dumps(data, indent=1), encoding="utf-8")


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class LevelAdd(BaseModel):
    job_id: int


_HUB_CSS = """
html,body{margin:0;min-height:100%;background:#0b0e16;color:#eee;
font-family:system-ui,Segoe UI,Arial,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:48px 20px}
h1{font-size:34px;margin:0 0 6px;background:linear-gradient(90deg,#a78bfa,#ff5c8a);
-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:#807d99;margin-bottom:28px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
a.card{display:block;background:#131826;border:1px solid #ffffff14;border-radius:14px;
padding:18px;text-decoration:none;color:#eee;transition:transform .15s,border-color .15s}
a.card:hover{transform:translateY(-2px);border-color:#7c5cff66}
.lvl{font-family:monospace;font-size:11px;color:#7c5cff}
.name{font-weight:600;margin:6px 0 4px}
.meta{font-size:11px;color:#807d99}
.foot{margin-top:36px;font-size:11px;color:#4a4764}
"""


def _hub_html(name: str, levels: list[dict]) -> str:
    cards = []
    for i, lv in enumerate(levels):
        nxt = f"?next=../lvl_{i+2}/dist/" if i + 1 < len(levels) else ""
        cards.append(
            f'<a class="card" href="levels/lvl_{i+1}/dist/{nxt}">'
            f'<div class="lvl">LEVEL {i+1}</div>'
            f'<div class="name">{html.escape(lv.get("title") or "Untitled")}</div>'
            f'<div class="meta">world #{lv.get("seed", "?")} · {html.escape(lv.get("player") or "man")}</div></a>')
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(name)}</title><style>{_HUB_CSS}</style></head><body>'
            f'<div class="wrap"><h1>{html.escape(name)}</h1>'
            f'<div class="sub">{len(levels)} level{"s" if len(levels) != 1 else ""} · made with Fantasy Studio</div>'
            f'<div class="grid">{"".join(cards)}</div>'
            f'<div class="foot">Motion data from mocap.cs.cmu.edu · engine: three.js (MIT) + Rapier (Apache-2.0)</div>'
            f'</div></body></html>')


@router.post("/api/game/projects")
def create_project(req: ProjectCreate):
    with _plock:
        data = _load()
        pid = data["next_id"]; data["next_id"] += 1
        data["projects"][str(pid)] = {"id": pid, "name": req.name,
                                      "created_at": time.time(), "levels": []}
        _save(data)
    return {"ok": True, "project": data["projects"][str(pid)]}


@router.get("/api/game/projects")
def list_projects():
    data = _load()
    out = []
    for p in sorted(data["projects"].values(), key=lambda x: x["id"]):
        q = {k: v for k, v in p.items() if k != "levels"}
        q["level_count"] = len(p["levels"])
        q["level_titles"] = [lv.get("title") for lv in p["levels"]]
        out.append(q)
    return {"ok": True, "projects": out}


@router.post("/api/game/projects/{pid}/levels")
def add_level(pid: int, req: LevelAdd):
    job = _jobs.get(req.job_id)
    if not job or job.get("status") != "complete":
        raise HTTPException(status_code=400, detail="job not found or not complete")
    if not job.get("spec_resolved"):
        raise HTTPException(status_code=400, detail="job predates project support — rebuild it")
    with _plock:
        data = _load()
        p = data["projects"].get(str(pid))
        if not p:
            raise HTTPException(status_code=404, detail="project not found")
        p["levels"].append({
            "title": job.get("title"), "prompt": job.get("prompt"),
            "seed": job.get("seed"), "player": job.get("player"),
            "spec": job["spec_resolved"], "added_at": time.time(),
        })
        _save(data)
    return {"ok": True, "level_count": len(p["levels"]), "project_id": pid}


@router.delete("/api/game/projects/{pid}/levels/{index}")
def remove_level(pid: int, index: int):
    """Levels manager (2026-07-06): users can now SEE and PRUNE their game."""
    with _plock:
        data = _load()
        p = data["projects"].get(str(pid))
        if not p:
            raise HTTPException(status_code=404, detail="project not found")
        if not (0 <= index < len(p["levels"])):
            raise HTTPException(status_code=400, detail="level index out of range")
        removed = p["levels"].pop(index)
        _save(data)
    return {"ok": True, "removed": removed.get("title"),
            "level_count": len(p["levels"])}


@router.post("/api/game/projects/{pid}/export")
def export_project(pid: int):
    from app.game_export.spec import spec_from_dict
    from app.game_export.web_exporter import export_web_game
    from app.game_export.verify_game import verify_dist
    data = _load()
    p = data["projects"].get(str(pid))
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    if not p["levels"]:
        raise HTTPException(status_code=400, detail="project has no levels")
    proot = PROJECTS_DIR / f"project_{pid}"
    if proot.exists():
        shutil.rmtree(proot)
    checks = 0
    for i, lv in enumerate(p["levels"]):
        spec = spec_from_dict(lv["spec"])           # exact re-export, no LLM
        dist = export_web_game(spec, proot / "levels" / f"lvl_{i+1}", verbose=False)
        v = verify_dist(dist)
        if not v["ok"]:
            raise HTTPException(status_code=500,
                                detail=f"level {i+1} failed verify: {v['errors']}")
        checks += len(v["checks"])
    (proot / "index.html").write_text(_hub_html(p["name"], p["levels"]), encoding="utf-8")
    zip_path = shutil.make_archive(str(proot), "zip", root_dir=proot)
    mb = Path(zip_path).stat().st_size / 1e6
    return {"ok": True, "levels": len(p["levels"]), "checks": checks,
            "play_url": f"/games/projects/project_{pid}/",
            "zip": f"/api/game/projects/{pid}/download", "zip_mb": round(mb, 1)}


@router.get("/api/game/projects/{pid}/download")
def download_project(pid: int):
    data = _load()
    p = data["projects"].get(str(pid))
    zp = PROJECTS_DIR / f"project_{pid}.zip"
    if not (p and zp.exists()):
        raise HTTPException(status_code=404, detail="export the project first")
    safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in p["name"]).strip() or "game"
    return FileResponse(str(zp), media_type="application/zip",
                        filename=f"{safe}.zip")
