"""Phase 35 — Video Projects: collect rendered scenes into ONE film.

The video sibling of Game Projects: any finished render can be added as a
SCENE; export concatenates the scenes (ffmpeg, re-encoded to a uniform
timeline) into a single MP4 served under /outputs and downloadable. Scene
order is edit-able (move/remove). Character continuity across scenes comes
from the asset cache: the same subject phrase re-uses the same generated
actor, so your hero stays the same hero from scene to scene.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config import OUTPUT_DIR

router = APIRouter()

VPROJ_DIR = Path(OUTPUT_DIR) / "video_projects"
VPROJ_JSON = VPROJ_DIR / "projects.json"
_vlock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(VPROJ_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"next_id": 1, "projects": {}}


def _save(data: dict) -> None:
    VPROJ_DIR.mkdir(parents=True, exist_ok=True)
    VPROJ_JSON.write_text(json.dumps(data, indent=1), encoding="utf-8")


def _resolve_mp4(ref: str) -> Path:
    """Accept an /outputs/... url or an absolute/backend-relative path."""
    if ref.startswith("/outputs/"):
        p = Path(OUTPUT_DIR) / ref[len("/outputs/"):]
    else:
        p = Path(ref)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[2] / ref
    if not (p.exists() and p.suffix.lower() == ".mp4"):
        raise HTTPException(status_code=400, detail=f"mp4 not found: {ref}")
    return p


class VProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class SceneAdd(BaseModel):
    video: str                    # /outputs/... url or path to the scene mp4
    title: str | None = None
    prompt: str | None = None


class SceneMove(BaseModel):
    index: int                    # current position
    to: int                       # new position


@router.post("/api/video/projects")
def create_vproject(req: VProjectCreate):
    with _vlock:
        data = _load()
        pid = data["next_id"]; data["next_id"] += 1
        data["projects"][str(pid)] = {"id": pid, "name": req.name,
                                      "created_at": time.time(), "scenes": []}
        _save(data)
    return {"ok": True, "project": data["projects"][str(pid)]}


@router.get("/api/video/projects")
def list_vprojects():
    data = _load()
    out = []
    for p in sorted(data["projects"].values(), key=lambda x: x["id"]):
        out.append({"id": p["id"], "name": p["name"],
                    "scene_count": len(p["scenes"]),
                    "scenes": [{"title": s.get("title"), "prompt": s.get("prompt")}
                               for s in p["scenes"]]})
    return {"ok": True, "projects": out}


@router.post("/api/video/projects/{pid}/scenes")
def add_scene(pid: int, req: SceneAdd):
    src = _resolve_mp4(req.video)
    with _vlock:
        data = _load()
        p = data["projects"].get(str(pid))
        if not p:
            raise HTTPException(status_code=404, detail="project not found")
        # copy the scene INTO the project (renders get overwritten/cleaned)
        pdir = VPROJ_DIR / f"project_{pid}" / "scenes"
        pdir.mkdir(parents=True, exist_ok=True)
        dst = pdir / f"scene_{int(time.time()*1000)}.mp4"
        shutil.copy2(src, dst)
        p["scenes"].append({"file": str(dst), "title": req.title,
                            "prompt": req.prompt, "added_at": time.time()})
        _save(data)
    return {"ok": True, "scene_count": len(p["scenes"])}


@router.post("/api/video/projects/{pid}/scenes/move")
def move_scene(pid: int, req: SceneMove):
    with _vlock:
        data = _load()
        p = data["projects"].get(str(pid))
        if not p:
            raise HTTPException(status_code=404, detail="project not found")
        sc = p["scenes"]
        if not (0 <= req.index < len(sc) and 0 <= req.to < len(sc)):
            raise HTTPException(status_code=400, detail="index out of range")
        sc.insert(req.to, sc.pop(req.index))
        _save(data)
    return {"ok": True, "order": [s.get("title") for s in p["scenes"]]}


@router.delete("/api/video/projects/{pid}/scenes/{index}")
def remove_scene(pid: int, index: int):
    with _vlock:
        data = _load()
        p = data["projects"].get(str(pid))
        if not p:
            raise HTTPException(status_code=404, detail="project not found")
        if not (0 <= index < len(p["scenes"])):
            raise HTTPException(status_code=400, detail="index out of range")
        p["scenes"].pop(index)
        _save(data)
    return {"ok": True, "scene_count": len(p["scenes"])}


@router.post("/api/video/projects/{pid}/export")
def export_vproject(pid: int):
    data = _load()
    p = data["projects"].get(str(pid))
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    if not p["scenes"]:
        raise HTTPException(status_code=400, detail="project has no scenes")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="ffmpeg not found on PATH")
    pdir = VPROJ_DIR / f"project_{pid}"
    pdir.mkdir(parents=True, exist_ok=True)
    out_mp4 = pdir / f"{''.join(c if c.isalnum() or c in '-_ ' else '' for c in p['name']).strip() or 'video'}.mp4"
    # concat filter with re-encode: scenes may differ in fps/size; normalize to
    # the FIRST scene's dimensions, 24fps, yuv420p
    inputs, filters = [], []
    for i, s in enumerate(p["scenes"]):
        f = Path(s["file"])
        if not f.exists():
            raise HTTPException(status_code=500, detail=f"scene file missing: {f.name}")
        inputs += ["-i", str(f)]
        filters.append(f"[{i}:v]fps=24,scale=1280:720:force_original_aspect_ratio=decrease,"
                       f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]")
    n = len(p["scenes"])
    graph = ";".join(filters) + ";" + "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[out]"
    cmd = [ffmpeg, "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
           "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
           str(out_mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not out_mp4.exists():
        raise HTTPException(status_code=500, detail=f"ffmpeg failed: {r.stderr[-400:]}")
    mb = out_mp4.stat().st_size / 1e6
    rel = out_mp4.relative_to(Path(OUTPUT_DIR)).as_posix()
    return {"ok": True, "scenes": n, "mp4_mb": round(mb, 1),
            "play_url": f"/outputs/{rel}",
            "download": f"/api/video/projects/{pid}/download"}


@router.get("/api/video/projects/{pid}/download")
def download_vproject(pid: int):
    data = _load()
    p = data["projects"].get(str(pid))
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    pdir = VPROJ_DIR / f"project_{pid}"
    mp4s = sorted(pdir.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not mp4s:
        raise HTTPException(status_code=404, detail="export the project first")
    return FileResponse(str(mp4s[0]), media_type="video/mp4", filename=mp4s[0].name)
