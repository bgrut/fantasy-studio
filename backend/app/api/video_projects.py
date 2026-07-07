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


def _scene_url(s: dict) -> str | None:
    """Scene files live under OUTPUT_DIR, which is mounted at /outputs —
    every scene is directly playable in the app."""
    try:
        return "/outputs/" + Path(s["file"]).relative_to(Path(OUTPUT_DIR)).as_posix()
    except Exception:
        return None


@router.get("/api/video/projects")
def list_vprojects():
    data = _load()
    out = []
    for p in sorted(data["projects"].values(), key=lambda x: x["id"]):
        out.append({"id": p["id"], "name": p["name"],
                    "scene_count": len(p["scenes"]),
                    "scenes": [{"title": s.get("title"), "prompt": s.get("prompt"),
                                "video": _scene_url(s), "edit": s.get("edit")}
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


class SceneEdit(BaseModel):
    change: str = Field(min_length=3, max_length=2000)


def _rewrite_prompt(original: str, change: str) -> str:
    """R-ITER for video: apply a plain-language change to a scene prompt.
    Ollama rewrite with a deterministic append fallback — an edit must never
    fail just because the LLM is offline."""
    try:
        from app.orchestrator.ollama_client import OllamaClient
        client = OllamaClient()
        if client.is_alive():
            resp = client.chat([
                {"role": "system", "content":
                    "Rewrite the scene prompt applying the requested change. "
                    "Keep the SAME subject wording (asset cache continuity) unless "
                    "the change replaces it. Output ONLY the new prompt, one line."},
                {"role": "user", "content": f"PROMPT: {original}\nCHANGE: {change}"},
            ])
            raw = (resp.get("content") or resp.get("message", {}).get("content", "")) \
                if isinstance(resp, dict) else str(resp)
            new = " ".join(raw.strip().strip('"').split())
            if 5 <= len(new) <= 500:
                return new
    except Exception:
        pass
    return f"{original.rstrip('. ')}. {change}"


def _rerender_scene(pid: int, index: int, new_prompt: str) -> None:
    """Background: render the edited prompt through the SAME pipeline that
    made the scene, then swap the mp4 in place (new filename so players
    never serve a stale cache)."""
    def _mark(status: str, **kw) -> None:
        with _vlock:
            data = _load()
            p = data["projects"].get(str(pid))
            if p and 0 <= index < len(p["scenes"]):
                p["scenes"][index]["edit"] = {"status": status,
                                              "prompt": new_prompt, **kw}
                _save(data)
    try:
        from app.orchestrator import render_from_prompt
        result = render_from_prompt(prompt=new_prompt, mode="slots", verbose=False)
        src = result.get("video_path") or result.get("render_path")
        if not src or not Path(src).exists():
            raise RuntimeError(f"no artifact: {result.get('errors')}")
        with _vlock:
            data = _load()
            p = data["projects"].get(str(pid))
            if not (p and 0 <= index < len(p["scenes"])):
                return
            s = p["scenes"][index]
            pdir = VPROJ_DIR / f"project_{pid}" / "scenes"
            pdir.mkdir(parents=True, exist_ok=True)
            dst = pdir / f"scene_{int(time.time()*1000)}.mp4"
            shutil.copy2(src, dst)
            old = Path(s["file"])
            s["file"] = str(dst)
            s["prompt"] = new_prompt
            s["title"] = new_prompt[:60]
            s["edit"] = {"status": "done", "prompt": new_prompt}
            _save(data)
        try:
            if old.exists() and old.parent == dst.parent:
                old.unlink()
        except Exception:
            pass
    except Exception as e:
        _mark("failed", error=f"{type(e).__name__}: {str(e)[:300]}")


@router.post("/api/video/projects/{pid}/scenes/{index}/edit")
def edit_scene(pid: int, index: int, req: SceneEdit):
    """Phase 43 — Inspector for video: 'change this scene…' re-renders the
    scene from an edited prompt and swaps it into the film. Same-hero
    continuity comes from the asset cache (same subject phrase = same actor)."""
    with _vlock:
        data = _load()
        p = data["projects"].get(str(pid))
        if not p:
            raise HTTPException(status_code=404, detail="project not found")
        if not (0 <= index < len(p["scenes"])):
            raise HTTPException(status_code=400, detail="scene index out of range")
        s = p["scenes"][index]
        if not s.get("prompt"):
            raise HTTPException(status_code=400,
                                detail="this scene has no saved prompt to edit — re-add it from a render")
        if (s.get("edit") or {}).get("status") == "running":
            raise HTTPException(status_code=409, detail="this scene is already re-rendering")
        new_prompt = _rewrite_prompt(s["prompt"], req.change)
        s["edit"] = {"status": "running", "prompt": new_prompt,
                     "change": req.change, "started_at": time.time()}
        _save(data)
    threading.Thread(target=_rerender_scene, args=(pid, index, new_prompt),
                     daemon=True).start()
    return {"ok": True, "new_prompt": new_prompt}


@router.post("/api/video/projects/{pid}/reveal")
def reveal_vproject(pid: int):
    """Open Explorer at the exported film (the desktop shell has no download
    UI — same fix as the game side)."""
    data = _load()
    p = data["projects"].get(str(pid))
    pdir = VPROJ_DIR / f"project_{pid}"
    mp4s = sorted(pdir.glob("*.mp4"), key=lambda f: f.stat().st_mtime,
                  reverse=True) if (p and pdir.exists()) else []
    if not mp4s:
        raise HTTPException(status_code=404, detail="export the film first")
    subprocess.Popen(["explorer", f"/select,{mp4s[0].resolve()}"])
    return {"ok": True, "path": str(mp4s[0])}


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
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in p["name"]).strip() or "video"
    out_mp4 = pdir / f"{safe_name}.mp4"
    files = []
    for s in p["scenes"]:
        f = Path(s["file"])
        if not f.exists():
            raise HTTPException(status_code=500, detail=f"scene file missing: {f.name}")
        files.append(f)
    n = len(files)

    def _norm(i: int) -> str:
        return (f"[{i}:v]fps=24,scale=1280:720:force_original_aspect_ratio=decrease,"
                f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]")

    # R1.6 (realism plan): FILM export — 2s title card + 0.5s crossfades
    # between scenes. Falls back to the plain concat on any hiccup (missing
    # ffprobe, weird durations) so export can never regress.
    r = None
    try:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise RuntimeError("no ffprobe")
        durs = []
        for f in files:
            pr = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                                 "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True, timeout=30)
            durs.append(max(float(pr.stdout.strip()), 0.6))
        FADE = 0.5
        title = p["name"].replace("\\", "").replace("'", "").replace(":", " ")[:48]
        inputs = ["-f", "lavfi", "-i",
                  f"color=c=0x0c0c14:s=1280x720:d=2.2:r=24"]
        for f in files:
            inputs += ["-i", str(f)]
        filters = [
            "[0:v]drawtext=fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
            f"text='{title}':fontcolor=0xEDEAF6:fontsize=56:"
            "x=(w-text_w)/2:y=(h-text_h)/2,setsar=1[v0]"]
        for i in range(n):
            filters.append(_norm(i + 1).replace(f"[v{i + 1}]", f"[v{i + 1}]"))
        # xfade chain: title(2.2s) -> scene1 -> scene2 ... cumulative offsets
        seq_durs = [2.2] + durs
        chain = "[v0]"
        acc = 0.0
        for i in range(1, n + 1):
            acc += seq_durs[i - 1] - FADE
            outl = "[out]" if i == n else f"[x{i}]"
            filters.append(f"{chain}[v{i}]xfade=transition=fade:duration={FADE}:offset={acc:.3f}{outl}")
            chain = f"[x{i}]"
        graph = ";".join(filters)
        cmd = [ffmpeg, "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
               "-c:v", "libx264", "-preset", "fast", "-crf", "19",
               "-pix_fmt", "yuv420p", str(out_mp4)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not out_mp4.exists():
            raise RuntimeError(f"xfade export failed: {r.stderr[-300:]}")
    except Exception:
        # plain concat fallback — the pre-R1.6 behavior, verbatim
        inputs, filters = [], []
        for i, f in enumerate(files):
            inputs += ["-i", str(f)]
            filters.append(_norm(i))
        graph = (";".join(filters) + ";" + "".join(f"[v{i}]" for i in range(n))
                 + f"concat=n={n}:v=1:a=0[out]")
        cmd = [ffmpeg, "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
               "-c:v", "libx264", "-preset", "fast", "-crf", "19",
               "-pix_fmt", "yuv420p", str(out_mp4)]
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
