from __future__ import annotations

"""
api/library.py
==============
Round 3 — read-only library lookup endpoints for the frontend.

    GET /api/library/match?q=canyon&category=environment&limit=12
        Return top-N library matches for a free-text query, scored
        against subject / subject_tags / biome_hints (+ optional
        auto-pick env-keyword scoring if category=environment).

This endpoint exists so the frontend can preview what auto-pick would
choose, or let the user see library hits before committing.  Purely
read-only; no side effects on the library.
"""

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.asset_agent import (
    _library_env_entries,
    _score_env_entry,
    _extract_env_keyword,
)


router = APIRouter(prefix="/api/library", tags=["library"])


class LibraryMatchHit(BaseModel):
    id: str
    category: str
    subject: str | None = None
    shape_class: str | None = None
    subject_tags: list[str] = []
    biome_hints: list[str] = []
    score: int
    thumbnail_url: str | None = None
    path: str | None = None


class LibraryMatchResponse(BaseModel):
    ok: bool
    q: str
    category: str
    keyword: str | None = None
    total: int
    hits: list[LibraryMatchHit]


def _score_generic(entry: dict, query_tokens: list[str]) -> int:
    """Token-overlap scoring for non-environment categories."""
    if not query_tokens:
        return 0
    score = 0
    subject = str(entry.get("subject") or "").lower()
    tags = [str(t).lower() for t in (entry.get("subject_tags") or [])]
    for tok in query_tokens:
        if not tok:
            continue
        if tok == subject:
            score += 50
        elif tok in subject:
            score += 20
        for t in tags:
            if tok == t:
                score += 15
            elif tok in t:
                score += 5
    return score


def _load_all_entries() -> list[dict]:
    try:
        import json as _json
        root = Path(__file__).resolve().parents[2]
        lib_path = root / "app" / "data" / "library.json"
        if not lib_path.exists():
            return []
        data = _json.loads(lib_path.read_text(encoding="utf-8"))
        out: list[dict] = []
        for a in data.get("assets", []):
            if not isinstance(a, dict):
                continue
            p = str(a.get("path") or "")
            if not p:
                continue
            full = Path(p)
            if not full.is_absolute():
                full = root / p
            if not full.exists():
                continue
            rec = dict(a)
            rec["_absolute_path"] = str(full)
            out.append(rec)
        return out
    except Exception:
        return []


@router.get("/match", response_model=LibraryMatchResponse)
def library_match(
    q: str = "",
    category: str = "",
    limit: int = 12,
) -> LibraryMatchResponse:
    """Return top library entries matching the free-text query.

    - ``category`` filters to a category. Accepts a single value
      ("environment", "character", "vehicle", "prop", "hdri") OR a
      comma-separated list (e.g. "character,vehicle,prop") so the
      Studio's hero slot can include any non-environment asset.
      Empty = all.
    - For ``category=environment`` the scorer uses the Round 3
      env-keyword map (canyon/mountain/city/...) so it mirrors the
      auto-pick logic 1:1. Multi-category queries that include
      "environment" alongside others use generic token-overlap scoring.
    """
    q_norm = (q or "").strip().lower()
    cat_norm = (category or "").strip().lower()
    # v1.4 follow-up — multi-category support. Splits "a,b,c" into a set.
    cat_set = {c.strip() for c in cat_norm.split(",") if c.strip()}
    limit = max(1, min(int(limit or 12), 100))

    # Single-category environment path keeps the round-3 env-keyword scorer.
    if cat_set == {"environment"}:
        entries = _library_env_entries()
        kw = _extract_env_keyword(q_norm) if q_norm else None
        if kw:
            scored = [(e, _score_env_entry(e, kw)) for e in entries]
        else:
            # Fall back to token-overlap scoring against subject/tags
            toks = [t for t in q_norm.split() if t]
            scored = [(e, _score_generic(e, toks)) for e in entries]
    else:
        entries = _load_all_entries()
        if cat_set:
            entries = [
                e for e in entries
                if str(e.get("category") or "").lower() in cat_set
            ]
        toks = [t for t in q_norm.split() if t]
        scored = [(e, _score_generic(e, toks)) for e in entries]
        kw = None

    scored = [(e, s) for (e, s) in scored if s > 0]
    scored.sort(key=lambda x: -x[1])
    top = scored[:limit]

    hits = [
        LibraryMatchHit(
            id=str(e.get("id") or ""),
            category=str(e.get("category") or ""),
            subject=e.get("subject"),
            shape_class=e.get("shape_class"),
            subject_tags=list(e.get("subject_tags") or []),
            biome_hints=list(e.get("biome_hints") or []),
            score=s,
            thumbnail_url=(
                f"/api/assets/thumbnail/{e.get('id')}"
                if e.get("id") else None
            ),
            path=e.get("path"),
        )
        for (e, s) in top
    ]

    return LibraryMatchResponse(
        ok=True,
        q=q,
        category=cat_norm or "all",
        keyword=kw,
        total=len(scored),
        hits=hits,
    )


# ────────────────────────────────────────────────────────────────────────
# v1.3.7 — paginated browse for the frontend "Change cast" library browser.
# Read-only; thin paginator over _load_all_entries() with substring search
# against subject + subject_tags + id. No pipeline impact.
# ────────────────────────────────────────────────────────────────────────


class LibraryBrowseAsset(BaseModel):
    id: str
    category: str
    subject: str | None = None
    shape_class: str | None = None
    subject_tags: list[str] = []
    biome_hints: list[str] = []
    thumbnail_url: str | None = None
    path: str | None = None


class LibraryBrowseResponse(BaseModel):
    ok: bool
    category: str
    page: int
    per_page: int
    total: int
    pages: int
    search: str | None = None
    assets: list[LibraryBrowseAsset]


@router.get("/browse", response_model=LibraryBrowseResponse)
def library_browse(
    category: str = "",
    page: int = 1,
    per_page: int = 12,
    search: str = "",
) -> LibraryBrowseResponse:
    """Paginated browse of the library.

    Query params:
      - ``category`` — exact match against asset category (character/
        environment/prop/vehicle/hdri). Empty = all.
      - ``page`` — 1-indexed.
      - ``per_page`` — clamped to [1, 50].
      - ``search`` — case-insensitive substring filter against
        ``subject + subject_tags + id``.

    Returns a stable shape ``{ok, category, page, per_page, total, pages,
    search, assets[]}`` with ``assets`` empty when out of range.
    """
    cat_norm = (category or "").strip().lower()
    # v1.4 follow-up — accept "a,b,c" so the Studio's hero slot can browse
    # character + vehicle + prop in one paginated stream.
    cat_set = {c.strip() for c in cat_norm.split(",") if c.strip()}
    search_norm = (search or "").strip().lower()
    per_page = max(1, min(int(per_page or 12), 50))
    page = max(1, int(page or 1))

    entries = _load_all_entries()

    if cat_set:
        entries = [
            e for e in entries
            if str(e.get("category") or "").lower() in cat_set
        ]

    if search_norm:
        def _matches(e: dict) -> bool:
            haystack: list[str] = []
            haystack.append(str(e.get("subject") or "").lower())
            haystack.append(str(e.get("id") or "").lower())
            for t in (e.get("subject_tags") or []):
                haystack.append(str(t).lower())
            for t in (e.get("biome_hints") or []):
                haystack.append(str(t).lower())
            return any(search_norm in h for h in haystack if h)

        entries = [e for e in entries if _matches(e)]

    # Stable order: by use_count desc, then id asc, so pagination is consistent.
    entries.sort(
        key=lambda e: (-int(e.get("use_count") or 0), str(e.get("id") or "")),
    )

    total = len(entries)
    pages = (total + per_page - 1) // per_page if total else 0
    start = (page - 1) * per_page
    page_slice = entries[start:start + per_page]

    assets = [
        LibraryBrowseAsset(
            id=str(e.get("id") or ""),
            category=str(e.get("category") or ""),
            subject=e.get("subject"),
            shape_class=e.get("shape_class"),
            subject_tags=list(e.get("subject_tags") or []),
            biome_hints=list(e.get("biome_hints") or []),
            thumbnail_url=(
                f"/api/assets/thumbnail/{e.get('id')}"
                if e.get("id") else None
            ),
            path=e.get("path"),
        )
        for e in page_slice
    ]

    return LibraryBrowseResponse(
        ok=True,
        category=cat_norm or "all",
        page=page,
        per_page=per_page,
        total=total,
        pages=pages,
        search=search_norm or None,
        assets=assets,
    )
