from __future__ import annotations

import os
import re
import requests
from pathlib import Path
from typing import Any

from .registry_io import upsert_asset
from .json_utils import safe_response_json

API_BASE = "https://api.polyhaven.com"


def _headers() -> dict[str, str]:
    ua = os.getenv("POLYHAVEN_USER_AGENT", "").strip()
    if not ua:
        raise RuntimeError("POLYHAVEN_USER_AGENT is not set")
    return {"User-Agent": ua}


def _get_json(url: str, params: dict | None = None) -> dict | list:
    r = requests.get(url, headers=_headers(), params=params, timeout=60)
    r.raise_for_status()
    # safe_response_json tolerates a leading UTF-8 BOM that the strict
    # r.json() decoder would otherwise crash on.
    return safe_response_json(r)


def _slug_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _score_asset(query: str, asset_id: str, asset_meta: dict) -> int:
    q = _slug_words(query)
    words = set()
    words |= _slug_words(asset_id)
    words |= _slug_words(asset_meta.get("name", ""))
    for tag in asset_meta.get("tags", []) or []:
        words |= _slug_words(str(tag))
    for cat in asset_meta.get("categories", []) or []:
        words |= _slug_words(str(cat))

    score = len(q.intersection(words))

    # small boosts
    if "night" in q and "night" in words:
        score += 2
    if "city" in q and ("urban" in words or "city" in words):
        score += 2
    if "wet" in q and ("road" in words or "asphalt" in words):
        score += 2

    return score


def _recursive_urls(node: Any) -> list[str]:
    urls: list[str] = []

    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
            else:
                urls.extend(_recursive_urls(v))
    elif isinstance(node, list):
        for item in node:
            urls.extend(_recursive_urls(item))

    return urls


def _download_file(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=_headers(), stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 512):
                if chunk:
                    f.write(chunk)
    return dest


def search_assets(asset_type: str, query: str, categories: list[str] | None = None, limit: int = 10) -> list[dict]:
    params = {"type": asset_type}
    if categories:
        params["categories"] = ",".join(categories)

    data = _get_json(f"{API_BASE}/assets", params=params)
    # /assets returns an object keyed by asset id according to Poly Haven's public API docs/swagger
    results = []
    if isinstance(data, dict):
        for asset_id, meta in data.items():
            score = _score_asset(query, asset_id, meta or {})
            if score > 0:
                results.append({
                    "id": asset_id,
                    "meta": meta or {},
                    "score": score,
                })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


_FAMILY_HDRI_FALLBACKS: tuple[str, ...] = (
    "outdoor", "sky", "sunset", "sunrise", "day", "night",
    "park", "forest", "city", "street", "studio", "ocean", "beach",
    "mountain", "desert", "urban",
)


def _expand_hdri_queries(query: str) -> list[str]:
    """
    Build a cascade of HDRI search queries from the original. We start
    specific (the caller's exact string), then peel off qualifier words
    so at least one query is likely to return results. Dedup while
    preserving order. Returns at most ~8 distinct queries.
    """
    if not query:
        return list(_FAMILY_HDRI_FALLBACKS)

    q = query.strip().lower()
    cascade: list[str] = [q]

    # Single-word family/tod hints that usually have PolyHaven coverage.
    hot_words = (
        "sunset", "sunrise", "night", "dusk", "dawn",
        "park", "forest", "city", "street", "studio",
        "ocean", "sea", "beach", "mountain", "desert",
        "snow", "autumn", "spring", "summer", "winter",
        "overcast", "cloudy", "foggy", "stormy",
    )
    tokens = [t for t in re.split(r"[^a-z0-9]+", q) if t]
    for tok in tokens:
        if tok in hot_words and tok not in cascade:
            cascade.append(tok)

    # Pairwise hot-word combos ("sunset park", "night street") —
    # frequently tagged by PolyHaven authors.
    for i, a in enumerate(tokens):
        if a not in hot_words:
            continue
        for b in tokens[i + 1:]:
            if b in hot_words:
                combo = f"{a} {b}"
                if combo not in cascade:
                    cascade.append(combo)

    # Final family fallbacks so we basically never return empty.
    for gen in _FAMILY_HDRI_FALLBACKS:
        if gen not in cascade:
            cascade.append(gen)

    return cascade[:12]


def fetch_hdri(query: str, preferred_resolution: str = "4k") -> dict | None:
    """
    Try the user-supplied query first. If nothing scores, walk down a
    cascade of family/time-of-day generics so we almost always return a
    usable HDRI. The scoring in ``_score_asset`` still decides the best
    match within each query, so specific beats generic.
    """
    cascade = _expand_hdri_queries(query)
    hits: list[dict] = []
    winning_q: str = ""

    # First attempt — the caller's query with the night/urban category
    # bias (preserves legacy behaviour for those two common prompts).
    try:
        hits = search_assets("hdris", query, categories=["night", "urban"])
    except Exception as e:
        print(f"DEBUG PolyHaven HDRI initial search failed ({query!r}): {e}", flush=True)
        hits = []
    if hits:
        winning_q = query

    if not hits:
        for q in cascade:
            try:
                hits = search_assets("hdris", q)
            except Exception as e:
                print(f"DEBUG PolyHaven HDRI cascade failed ({q!r}): {e}", flush=True)
                continue
            if hits:
                winning_q = q
                break

    if not hits:
        print(f"DEBUG PolyHaven HDRI cascade exhausted for {query!r}", flush=True)
        return None

    if winning_q and winning_q != query:
        print(
            f"[POLYHAVEN] HDRI cascade: original={query!r} won_with={winning_q!r}",
            flush=True,
        )

    asset_id = hits[0]["id"]
    files = _get_json(f"{API_BASE}/files/{asset_id}")
    urls = _recursive_urls(files)

    # prefer EXR, then HDR
    exr_urls = [u for u in urls if f"/{preferred_resolution}/" in u and u.lower().endswith(".exr")]
    hdr_urls = [u for u in urls if f"/{preferred_resolution}/" in u and u.lower().endswith(".hdr")]
    fallback_exr = [u for u in urls if u.lower().endswith(".exr")]
    fallback_hdr = [u for u in urls if u.lower().endswith(".hdr")]

    chosen = (exr_urls or hdr_urls or fallback_exr or fallback_hdr)
    if not chosen:
        return None

    url = chosen[0]
    ext = ".exr" if url.lower().endswith(".exr") else ".hdr"
    local_path = Path("assets/cache/hdris") / f"{asset_id}{ext}"
    _download_file(url, Path.cwd() / local_path)

    record = {
        "id": asset_id,
        "type": "hdri",
        "tags": hits[0]["meta"].get("tags", []) + hits[0]["meta"].get("categories", []),
        "path": str(local_path).replace("\\", "/"),
        "source": "polyhaven",
    }
    upsert_asset("hdris", record)
    return record


def fetch_texture_set(query: str, preferred_resolution: str = "4k") -> dict | None:
    hits = search_assets("textures", query)
    if not hits:
        return None

    asset_id = hits[0]["id"]
    files = _get_json(f"{API_BASE}/files/{asset_id}")
    urls = _recursive_urls(files)

    local_dir = Path("assets/cache/textures") / asset_id
    abs_local_dir = Path.cwd() / local_dir
    abs_local_dir.mkdir(parents=True, exist_ok=True)

    # crude but effective map matching
    chosen = {"base_color": None, "roughness": None, "normal": None, "height": None}

    for url in urls:
        low = url.lower()
        if f"/{preferred_resolution}/" not in low and preferred_resolution not in low:
            continue

        if ("diff" in low or "albedo" in low or "basecolor" in low or "color" in low) and chosen["base_color"] is None:
            chosen["base_color"] = url
        elif "rough" in low and chosen["roughness"] is None:
            chosen["roughness"] = url
        elif ("nor" in low or "normal" in low) and chosen["normal"] is None:
            chosen["normal"] = url
        elif ("disp" in low or "height" in low) and chosen["height"] is None:
            chosen["height"] = url

    if not chosen["base_color"]:
        return None

    downloaded = {}
    for key, url in chosen.items():
        if not url:
            continue
        suffix = Path(url).suffix or ".bin"
        name = {
            "base_color": f"basecolor{suffix}",
            "roughness": f"roughness{suffix}",
            "normal": f"normal{suffix}",
            "height": f"height{suffix}",
        }[key]
        _download_file(url, abs_local_dir / name)
        downloaded[key] = str((local_dir / name).as_posix())

    record = {
        "id": asset_id,
        "type": "texture_set",
        "tags": hits[0]["meta"].get("tags", []) + hits[0]["meta"].get("categories", []),
        "base_color": downloaded.get("base_color"),
        "roughness": downloaded.get("roughness"),
        "normal": downloaded.get("normal"),
        "height": downloaded.get("height"),
        "source": "polyhaven",
    }
    upsert_asset("textures", record)
    return record