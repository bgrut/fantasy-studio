from __future__ import annotations

"""
api/assets.py
=============
HTTP endpoints for the asset agent. The frontend uses these to:

  - Search PolyHaven / Sketchfab for HDRIs, textures, and downloadable
    3D models. (``GET /api/assets/search``)
  - Trigger an explicit download of a specific search hit so it lands in
    the local cache + asset registry. (``POST /api/assets/download``)
  - Browse what is currently in the local registry, optionally filtered
    by type or tag. (``GET /api/assets/library``)
  - Generate provider queries for a given scene plan / directorial
    manifest, useful for previewing what the asset agent would fetch
    before kicking off a full render. (``POST /api/assets/query``)

These endpoints are deliberately thin — they wrap the existing
service-layer functions so the same code paths used by the render
pipeline are reachable from the frontend. The router is mounted from
``app/main.py`` via ``app.include_router(assets_router)``.
"""

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..services.polyhaven_fetcher import (
    fetch_hdri,
    fetch_texture_set,
    search_assets as polyhaven_search,
)
from ..services.sketchfab_fetcher import (
    fetch_model,
    is_available as sketchfab_available,
    search_models as sketchfab_search,
)
from ..services.asset_query_generator import generate_asset_queries
from ..services.registry_io import load_registry
from ..services.library_curator import query_library_strict, extract_visual_hints
from ..services.variant_pool import pick_with_diversity

_ROOT = Path(__file__).resolve().parents[2]
_THUMBNAIL_DIR = _ROOT / "assets" / "thumbnails"


router = APIRouter(prefix="/api/assets", tags=["assets"])


# ═══════════════════════════════════════════════════════════════════════════
# Request / response models
# ═══════════════════════════════════════════════════════════════════════════

AssetType = Literal["hdri", "texture", "model"]


class AssetSearchResult(BaseModel):
    id: str
    name: str | None = None
    score: int = 0
    source: str
    license: str | None = None
    thumbnail: str | None = None
    face_count: int | None = None


class AssetSearchResponse(BaseModel):
    ok: bool
    asset_type: AssetType
    query: str
    source: str
    results: list[AssetSearchResult]


class AssetDownloadRequest(BaseModel):
    asset_type: AssetType
    query: str = Field(..., min_length=1, description="Search query used to pick the asset")


class AssetDownloadResponse(BaseModel):
    ok: bool
    asset_type: AssetType
    record: dict[str, Any] | None = None
    error: str | None = None


class AssetLibraryResponse(BaseModel):
    ok: bool
    counts: dict[str, int]
    items: dict[str, list[dict[str, Any]]]


class AssetQueryRequest(BaseModel):
    scene_plan: dict[str, Any] = Field(default_factory=dict)
    directorial_manifest: dict[str, Any] | None = None


class AssetQueryResponse(BaseModel):
    ok: bool
    source: str
    notes: str
    hero_model: list[str]
    environment: list[str]
    ground_texture: list[str]
    props: list[str]


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _polyhaven_to_result(asset_type: AssetType, hit: dict) -> AssetSearchResult:
    meta = hit.get("meta") or {}
    return AssetSearchResult(
        id=str(hit.get("id")),
        name=str(meta.get("name") or hit.get("id")),
        score=int(hit.get("score") or 0),
        source="polyhaven",
        license="cc0",
        thumbnail=None,
    )


def _sketchfab_to_result(hit: dict) -> AssetSearchResult:
    return AssetSearchResult(
        id=str(hit.get("uid") or ""),
        name=hit.get("name"),
        score=int(hit.get("score") or 0),
        source="sketchfab",
        license=hit.get("license"),
        thumbnail=hit.get("thumbnail"),
        face_count=hit.get("face_count"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/search", response_model=AssetSearchResponse)
def search_assets(
    asset_type: AssetType,
    query: str,
    limit: int = 12,
) -> AssetSearchResponse:
    """
    Search the matching provider for the asset type.

    - ``hdri`` and ``texture`` query PolyHaven.
    - ``model`` queries Sketchfab (downloadable, CC0/CC-BY only).
      If ``SKETCHFAB_API_TOKEN`` is unset, returns an empty result list
      with ``source='sketchfab_unavailable'`` so the frontend can render
      a helpful message instead of a stack trace.
    """
    query = (query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    if asset_type == "model":
        if not sketchfab_available():
            return AssetSearchResponse(
                ok=True,
                asset_type=asset_type,
                query=query,
                source="sketchfab_unavailable",
                results=[],
            )
        hits = sketchfab_search(query, limit=limit)
        return AssetSearchResponse(
            ok=True,
            asset_type=asset_type,
            query=query,
            source="sketchfab",
            results=[_sketchfab_to_result(h) for h in hits],
        )

    poly_type = "hdris" if asset_type == "hdri" else "textures"
    try:
        hits = polyhaven_search(poly_type, query, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"polyhaven search failed: {e}")

    return AssetSearchResponse(
        ok=True,
        asset_type=asset_type,
        query=query,
        source="polyhaven",
        results=[_polyhaven_to_result(asset_type, h) for h in hits],
    )


@router.post("/download", response_model=AssetDownloadResponse)
def download_asset(payload: AssetDownloadRequest) -> AssetDownloadResponse:
    """
    Trigger an immediate fetch of the best match for ``query``. The
    downloaded asset is cached locally and registered in the asset
    registry, so subsequent renders will pick it up automatically.
    """
    try:
        if payload.asset_type == "hdri":
            record = fetch_hdri(payload.query)
        elif payload.asset_type == "texture":
            record = fetch_texture_set(payload.query)
        elif payload.asset_type == "model":
            if not sketchfab_available():
                return AssetDownloadResponse(
                    ok=False,
                    asset_type=payload.asset_type,
                    error="sketchfab_unavailable: set SKETCHFAB_API_TOKEN",
                )
            record = fetch_model(payload.query)
        else:  # pragma: no cover — guarded by Literal
            raise HTTPException(status_code=400, detail="invalid asset_type")
    except Exception as e:
        return AssetDownloadResponse(
            ok=False,
            asset_type=payload.asset_type,
            error=f"{type(e).__name__}: {e}",
        )

    if not record:
        return AssetDownloadResponse(
            ok=False,
            asset_type=payload.asset_type,
            error="no usable asset found for query",
        )
    return AssetDownloadResponse(
        ok=True,
        asset_type=payload.asset_type,
        record=record,
    )


@router.get("/library", response_model=AssetLibraryResponse)
def list_library(
    asset_type: AssetType | None = None,
    tag: str | None = None,
) -> AssetLibraryResponse:
    """
    Return everything currently in the local asset registry. Optional
    filters: ``asset_type`` (hdri/texture/model) and ``tag`` (substring
    match against the record's ``tags`` list).
    """
    registry = load_registry()
    type_to_group = {
        "hdri": "hdris",
        "texture": "textures",
        "model": "models",
    }

    items: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    for group, records in registry.items():
        if not isinstance(records, list):
            continue
        if asset_type and type_to_group.get(asset_type) != group:
            continue
        if tag:
            tag_lc = tag.strip().lower()
            filtered = [
                r for r in records
                if any(tag_lc in str(t).lower() for t in (r.get("tags") or []))
            ]
        else:
            filtered = list(records)
        items[group] = filtered
        counts[group] = len(filtered)

    return AssetLibraryResponse(ok=True, counts=counts, items=items)


@router.post("/query", response_model=AssetQueryResponse)
def preview_queries(payload: AssetQueryRequest) -> AssetQueryResponse:
    """
    Run the LLM-driven query generator over a scene plan + directorial
    manifest and return the queries it would feed to the providers.
    Useful for letting the user inspect / override before a render.
    """
    qs = generate_asset_queries(payload.scene_plan, payload.directorial_manifest)
    return AssetQueryResponse(
        ok=True,
        source=qs.source,
        notes=qs.notes,
        hero_model=qs.hero_model,
        environment=qs.environment,
        ground_texture=qs.ground_texture,
        props=qs.props,
    )


# ═══════════════════════════════════════════════════════════════════════════
# V1 polish — Asset Picker (match endpoint + thumbnail serving)
# ═══════════════════════════════════════════════════════════════════════════

_BRAND_TOKENS_PICKER = {
    "porsche", "ferrari", "bmw", "toyota", "ford", "chevrolet", "mercedes",
    "audi", "lamborghini", "bugatti", "mclaren", "aston", "nissan", "honda",
    "mazda", "tesla", "dodge", "jaguar",
}
_MODEL_TOKENS_PICKER = {
    "911", "718", "gt3", "m3", "m4", "m5", "supra", "mustang", "corvette",
    "camry", "civic", "f40", "f50", "enzo", "488", "veyron", "huracan",
    "aventador", "720s", "db11",
}


class AssetMatch(BaseModel):
    id: str
    title: str
    subject: str | None = None
    visual_descriptors: list[str] = Field(default_factory=list)
    subject_tags: list[str] = Field(default_factory=list)
    category: str | None = None
    brand: str | None = None
    model: str | None = None
    thumbnail_url: str | None = None
    thumbnail_path: str | None = None
    quality: str | None = None
    use_count: int = 0
    attribution: dict[str, Any] | None = None
    score: int = 0


class AssetMatchResponse(BaseModel):
    ok: bool
    subject_detected: str | None
    visual_hints: list[str]
    brand_detected: str | None = None
    model_detected: str | None = None
    specific_subject: bool = False
    matches: list[AssetMatch]
    auto_pick_id: str | None
    reason: str


@router.get("/match", response_model=AssetMatchResponse)
def match_assets(prompt: str, limit: int = 12) -> AssetMatchResponse:
    """Return top library matches for a prompt WITHOUT rendering.

    Used by the Asset Picker UI — user sees matched thumbnails before
    committing a render.  Reuses ``query_library_strict`` +
    ``pick_with_diversity`` so the AI's auto-pick is the same one the
    resolver would choose.
    """
    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    prompt_lc = prompt.strip().lower()
    tokens = prompt_lc.split()

    # Subject extraction — pick the first "meaningful" token that looks
    # like an asset noun.  For the picker this is best-effort; the
    # resolver does a more sophisticated extraction elsewhere.
    STOP = {"a", "an", "the", "of", "in", "on", "at", "and", "or", "with",
            "at", "in", "to", "my", "your", "our", "this", "that"}
    meaningful = [t for t in tokens if t not in STOP and len(t) > 2]
    subject = meaningful[0] if meaningful else prompt_lc

    # Brand / model detection
    brand = next((t for t in tokens if t in _BRAND_TOKENS_PICKER), None)
    model = next(
        (t for t in tokens
         if t in _MODEL_TOKENS_PICKER or (t.isdigit() and len(t) >= 3)),
        None,
    )
    specific = bool(brand and model)

    hints = extract_visual_hints(prompt_lc)

    # Query library
    if specific:
        hits = query_library_strict(
            subject, brand=brand, model=model,
            visual_hints=hints,
            quality_filter=["tested", "unverified"],
            limit=limit,
        )
    else:
        hits = query_library_strict(
            subject, visual_hints=hints,
            quality_filter=["tested", "unverified"],
            limit=limit,
        )

    # If specific brand+model had no exact hits, widen to the brand alone
    # so the UI can offer "we don't have a Porsche 911, but we have these
    # similar sports cars"
    fallback_note = ""
    if specific and not hits and brand:
        hits = query_library_strict(
            brand, quality_filter=["tested", "unverified"], limit=limit,
        )
        fallback_note = f"no exact match for '{brand} {model}' — showing {brand} fallbacks"

    # Apply diversity pick to select the auto-pick
    pool_entries = [
        {
            "id":     h.get("id"),
            "uid":    h.get("id"),
            "name":   h.get("subject"),
            "score":  100 if h.get("quality") == "tested" else 50,
            "path":   h.get("path"),
            "tags":   h.get("subject_tags", []),
        }
        for h in hits
    ]
    auto_pick = pick_with_diversity(subject, pool_entries) if pool_entries else None
    auto_pick_id = auto_pick.get("id") if auto_pick else None

    reason = "highest subject match + diversity pool pick"
    if fallback_note:
        reason = fallback_note
    elif not hits:
        reason = "no library matches — resolver would hit Objaverse/Sketchfab"

    # Build response
    matches: list = []
    for h in hits:
        eid = h.get("id") or ""
        attr = h.get("attribution") or {}
        title = (
            attr.get("title")
            or (h.get("subject") or "").title()
            or eid
        )
        # Thumbnail URL — only populated if the file exists
        thumb_url = None
        thumb_path_str = h.get("thumbnail_path")
        if eid:
            expected = _THUMBNAIL_DIR / f"{eid}.png"
            if expected.exists():
                thumb_url = f"/api/assets/thumbnail/{eid}"
        matches.append(AssetMatch(
            id=eid,
            title=str(title),
            subject=h.get("subject"),
            visual_descriptors=list(h.get("visual_descriptors") or []),
            subject_tags=list(h.get("subject_tags") or []),
            category=h.get("category"),
            brand=h.get("brand"),
            model=h.get("model"),
            thumbnail_url=thumb_url,
            thumbnail_path=thumb_path_str,
            quality=h.get("quality"),
            use_count=int(h.get("use_count", 0)),
            attribution={
                "author":  attr.get("author"),
                "license": attr.get("license"),
                "source":  attr.get("source"),
            } if attr else None,
        ))

    return AssetMatchResponse(
        ok=True,
        subject_detected=subject,
        visual_hints=hints,
        brand_detected=brand,
        model_detected=model,
        specific_subject=specific,
        matches=matches,
        auto_pick_id=auto_pick_id,
        reason=reason,
    )


@router.get("/thumbnail/{asset_id}")
def get_thumbnail(asset_id: str):
    """Serve a PNG thumbnail for a library asset.

    Thumbnails are generated one-shot by ``scripts/generate_thumbnails.py``
    and cached at ``assets/thumbnails/<asset_id>.png``.  Aggressive
    cache headers (1 year) since thumbnails are immutable once
    generated — if an asset changes, use a new id.
    """
    # Sanitize: only allow library ids we'd generate ourselves
    import re
    if not re.match(r"^[A-Za-z0-9_-]{1,128}$", asset_id):
        raise HTTPException(status_code=400, detail="invalid asset_id")
    path = _THUMBNAIL_DIR / f"{asset_id}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="thumbnail not found")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/library/browse")
def browse_library(
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List library entries by category (for the frontend Assets tab).

    Returns entries sorted by use_count desc, then added_at desc.
    ``category`` filter: character/vehicle/environment/prop/hdri/unknown.
    """
    import json as _json
    lib_path = _ROOT / "app" / "data" / "library.json"
    if not lib_path.exists():
        return {"total": 0, "items": []}
    data = _json.loads(lib_path.read_text(encoding="utf-8"))
    assets = data.get("assets", [])

    if category:
        assets = [a for a in assets if str(a.get("category") or "").lower() == category.lower()]

    # Sort by use_count desc then added_at desc
    assets.sort(
        key=lambda a: (int(a.get("use_count", 0)), int(a.get("added_at", 0))),
        reverse=True,
    )
    total = len(assets)
    page = assets[offset:offset + limit]

    items: list = []
    for a in page:
        eid = a.get("id") or ""
        attr = a.get("attribution") or {}
        thumb_url = None
        if eid:
            expected = _THUMBNAIL_DIR / f"{eid}.png"
            if expected.exists():
                thumb_url = f"/api/assets/thumbnail/{eid}"
        items.append({
            "id":                 eid,
            "title":              attr.get("title") or (a.get("subject") or "").title() or eid,
            "subject":            a.get("subject"),
            "category":           a.get("category"),
            "quality":            a.get("quality"),
            "use_count":          int(a.get("use_count", 0)),
            "brand":              a.get("brand"),
            "model":              a.get("model"),
            "visual_descriptors": a.get("visual_descriptors") or [],
            "subject_tags":       a.get("subject_tags") or [],
            "thumbnail_url":      thumb_url,
            "attribution": {
                "author":  attr.get("author"),
                "license": attr.get("license"),
                "source":  attr.get("source"),
            } if attr else None,
        })

    return {"total": total, "items": items, "offset": offset, "limit": limit}


@router.get("/library/counts")
def library_counts():
    """Category count breakdown for the Assets-tab header."""
    import json as _json
    lib_path = _ROOT / "app" / "data" / "library.json"
    if not lib_path.exists():
        return {"total": 0, "by_category": {}}
    data = _json.loads(lib_path.read_text(encoding="utf-8"))
    assets = data.get("assets", [])
    by_cat: dict = {}
    for a in assets:
        c = str(a.get("category") or "unknown")
        by_cat[c] = by_cat.get(c, 0) + 1
    return {"total": len(assets), "by_category": by_cat}
