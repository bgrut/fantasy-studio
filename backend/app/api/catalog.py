from __future__ import annotations

"""
api/catalog.py
==============
Community template catalog endpoints.

    GET  /api/templates/catalog          full catalog
    GET  /api/templates/catalog/search   filtered search
    POST /api/templates/submit           stub for future submission
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..config import ROOT


router = APIRouter(prefix="/api/templates", tags=["catalog"])

CATALOG_PATH = ROOT / "assets" / "manifests" / "community_catalog.json"


def _load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        return {"catalog_version": "0.0.0", "templates": []}
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"catalog_version": "0.0.0", "templates": []}


@router.get("/catalog")
def get_catalog():
    catalog = _load_catalog()
    return {
        "ok": True,
        "catalog_version": catalog.get("catalog_version"),
        "count": len(catalog.get("templates", [])),
        "templates": catalog.get("templates", []),
    }


@router.get("/catalog/search")
def search_catalog(
    q: str = "",
    family: Optional[str] = None,
    price: Optional[str] = None,
    sort: str = "rating",
):
    catalog = _load_catalog()
    templates = catalog.get("templates", [])

    if q:
        q_lower = q.lower()
        templates = [
            t for t in templates
            if q_lower in t.get("name", "").lower()
            or q_lower in t.get("description", "").lower()
            or any(q_lower in tag for tag in t.get("tags", []))
        ]

    if family:
        templates = [t for t in templates if t.get("scene_family") == family]

    if price == "free":
        templates = [t for t in templates if t.get("price", "").lower() == "free"]
    elif price == "paid":
        templates = [t for t in templates if t.get("price", "").lower() != "free"]

    if sort == "rating":
        templates.sort(key=lambda t: t.get("rating", 0), reverse=True)
    elif sort == "downloads":
        templates.sort(key=lambda t: t.get("downloads", 0), reverse=True)
    elif sort == "newest":
        templates.sort(key=lambda t: t.get("version", "0"), reverse=True)

    return {
        "ok": True,
        "count": len(templates),
        "templates": templates,
    }


class SubmissionMeta(BaseModel):
    author: str = ""
    description: str = ""


@router.post("/submit")
async def submit_template(file: UploadFile = File(...)):
    """
    Stub for community template submission. Saves the uploaded .zip
    locally for future review. Does NOT install or validate.
    """
    submissions_dir = ROOT / "data" / "submissions"
    submissions_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "unnamed.zip").name
    dest = submissions_dir / safe_name

    try:
        with open(dest, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save failed: {e}")

    return {
        "ok": True,
        "message": "Template submitted for review",
        "filename": safe_name,
        "path": str(dest),
    }
