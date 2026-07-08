"""Phase 46 — Community Marketplace bridge: publish games and characters to
the user's own Cloudflare share worker, browse the community feed, install
shared characters into the local library.

The PUBLISH_TOKEN never touches the frontend: the desktop app talks to this
router, and this router talks to the worker. Config (worker URL + token) is
saved once from the Marketplace page into renders/share_config.json — a
gitignored, local-only file.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import OUTPUT_DIR
from .game import GAME_JOBS_DIR
from app.game_export import library

router = APIRouter()

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SHARE_CFG = Path(OUTPUT_DIR) / "share_config.json"
PROJECTS_DIR = GAME_JOBS_DIR / "projects"
_pub_lock = threading.Lock()
_pub_state: dict = {"status": "idle"}     # one publish at a time (big uploads)


def _cfg() -> dict:
    try:
        return json.loads(SHARE_CFG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _require_cfg() -> tuple[str, str]:
    c = _cfg()
    url, tok = (c.get("url") or "").rstrip("/"), c.get("token") or ""
    if not (url and tok):
        raise HTTPException(status_code=400,
                            detail="share worker not configured — open Marketplace → Setup")
    return url, tok


def _hdrs(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


class ShareConfig(BaseModel):
    url: str = Field(min_length=8, max_length=300)
    token: str = Field(min_length=8, max_length=300)
    author: str = Field(default="anonymous", max_length=40)


@router.get("/api/share/status")
def share_status():
    c = _cfg()
    return {"ok": True, "configured": bool(c.get("url") and c.get("token")),
            "url": c.get("url"), "author": c.get("author") or "anonymous",
            "publish": _pub_state}


@router.post("/api/share/config")
def share_config(req: ShareConfig):
    # verify the worker answers before saving — a typo'd URL should fail HERE
    base = req.url.rstrip("/")
    try:
        r = requests.get(base + "/", timeout=10)
        if "fantasy-studio-share" not in r.text:
            raise ValueError("that URL is not a Fantasy Studio share worker")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400,
                            detail=f"could not reach the worker: {e}")
    SHARE_CFG.parent.mkdir(parents=True, exist_ok=True)
    SHARE_CFG.write_text(json.dumps(
        {"url": base, "token": req.token, "author": req.author.strip() or "anonymous"},
        indent=1), encoding="utf-8")
    return {"ok": True, "url": base}


@router.get("/api/share/feed")
def share_feed():
    """Proxy the community feed (keeps the app same-origin, no CORS games)."""
    url, _ = _require_cfg()
    try:
        r = requests.get(f"{url}/api/feed", timeout=15)
        r.raise_for_status()
        return r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"feed unavailable: {e}")


class PublishGame(BaseModel):
    project_id: int
    title: str | None = None
    description: str = Field(default="", max_length=300)


class PublishCharacter(BaseModel):
    kind: str = Field(min_length=2, max_length=40)
    description: str = Field(default="", max_length=300)


def _upload_tree(url: str, tok: str, api_kind: str, item_id: str, root: Path) -> int:
    n = 0
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        _pub_state.update({"status": "uploading", "file": rel, "done": n})
        r = requests.put(f"{url}/api/{api_kind}/{item_id}/files/{rel}",
                         data=f.read_bytes(), headers=_hdrs(tok), timeout=300)
        r.raise_for_status()
        n += 1
    return n


@router.post("/api/share/publish/game")
def publish_game(req: PublishGame):
    """Upload an EXPORTED project (hub + levels) and list it on the feed.
    Export the project first — this publishes exactly those files."""
    url, tok = _require_cfg()
    proot = PROJECTS_DIR / f"project_{req.project_id}"
    if not (proot / "index.html").exists():
        raise HTTPException(status_code=400,
                            detail="export the project first (Export game), then publish")
    with _pub_lock:
        try:
            _pub_state.clear()
            _pub_state.update({"status": "starting"})
            r = requests.post(f"{url}/api/games", headers=_hdrs(tok), timeout=30)
            r.raise_for_status()
            gid = r.json()["id"]
            n = _upload_tree(url, tok, "games", gid, proot)
            author = _cfg().get("author") or "anonymous"
            r = requests.post(f"{url}/api/games/{gid}/publish", headers=_hdrs(tok),
                              json={"title": req.title or f"project {req.project_id}",
                                    "author": author,
                                    "description": req.description}, timeout=30)
            r.raise_for_status()
            out = r.json()
            _pub_state.update({"status": "done", "url": out["url"], "files": n})
            return {"ok": True, "url": out["url"], "files": n}
        except HTTPException:
            _pub_state.update({"status": "failed"})
            raise
        except Exception as e:
            _pub_state.update({"status": "failed", "error": str(e)[:200]})
            raise HTTPException(status_code=502, detail=f"publish failed: {e}")


@router.post("/api/share/publish/character")
def publish_character(req: PublishCharacter):
    """Share one library character (its GLB + rigged variant if present)."""
    url, tok = _require_cfg()
    kind = req.kind.lower().strip()
    glb = library.resolve(kind)
    if not glb:
        raise HTTPException(status_code=404, detail=f"'{kind}' is not in your library")
    with _pub_lock:
        try:
            _pub_state.clear()
            _pub_state.update({"status": "starting"})
            r = requests.post(f"{url}/api/characters", headers=_hdrs(tok), timeout=30)
            r.raise_for_status()
            cid = r.json()["id"]
            files = {"character.glb": Path(glb)}
            anim = BACKEND_ROOT / "assets" / "library" / f"{kind}_anim.glb"
            if anim.exists():
                files["character_anim.glb"] = anim
            n = 0
            for rel, f in files.items():
                _pub_state.update({"status": "uploading", "file": rel})
                rr = requests.put(f"{url}/api/characters/{cid}/files/{rel}",
                                  data=f.read_bytes(), headers=_hdrs(tok), timeout=300)
                rr.raise_for_status()
                n += 1
            author = _cfg().get("author") or "anonymous"
            r = requests.post(f"{url}/api/characters/{cid}/publish", headers=_hdrs(tok),
                              json={"title": kind, "character_kind": kind,
                                    "author": author,
                                    "description": req.description}, timeout=30)
            r.raise_for_status()
            out = r.json()
            _pub_state.update({"status": "done", "url": out["url"], "files": n})
            return {"ok": True, "url": out["url"], "files": n}
        except HTTPException:
            _pub_state.update({"status": "failed"})
            raise
        except Exception as e:
            _pub_state.update({"status": "failed", "error": str(e)[:200]})
            raise HTTPException(status_code=502, detail=f"publish failed: {e}")


class InstallCharacter(BaseModel):
    id: str = Field(min_length=4, max_length=40)


@router.post("/api/share/install/character")
def install_character(req: InstallCharacter):
    """Download a community character into the local library — it becomes a
    castable kind like any generated one."""
    url, _ = _require_cfg()
    try:
        m = requests.get(f"{url}/c/{req.id}/manifest.json", timeout=15)
        m.raise_for_status()
        man = m.json()
        kind = (man.get("character_kind") or man.get("title") or "").lower().strip()
        if not kind or not kind.replace(" ", "").replace("-", "").isalnum():
            raise ValueError("manifest has no valid character kind")
        if library.resolve(kind):
            return {"ok": True, "kind": kind, "note": "already in your library"}
        dest_dir = BACKEND_ROOT / "assets" / "library"
        dest_dir.mkdir(parents=True, exist_ok=True)
        g = requests.get(f"{url}/c/{req.id}/character.glb", timeout=300)
        g.raise_for_status()
        dest = dest_dir / f"{kind}.glb"
        dest.write_bytes(g.content)
        a = requests.get(f"{url}/c/{req.id}/character_anim.glb", timeout=300)
        if a.status_code == 200:
            (dest_dir / f"{kind}_anim.glb").write_bytes(a.content)
        library.register(kind, dest, ready=True)
        return {"ok": True, "kind": kind,
                "note": f"'{kind}' installed — it's castable in prompts now "
                        f"(shared by {man.get('author', 'anonymous')}, CC-BY-4.0)"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"install failed: {e}")
