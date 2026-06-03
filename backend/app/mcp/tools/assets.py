"""
Asset library tools.

find_assets() runs IN-PROCESS — reads asset_registry.json directly, scores
by tag overlap, returns top-N candidates. No bridge call needed.

spawn_asset() resolves the .blend path in-process, then calls the bridge
to append_blend_collection + tag_as_hero.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any

from .. import blender_bridge as bridge
from ..registry import register_fn


# ───────────────────────────────────────────────────────────────────────
# Registry loader (in-process — no bridge needed)
# ───────────────────────────────────────────────────────────────────────

# Path discovery: walk up from this file to find backend root, then look in conventional locations.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]  # app/mcp/tools/assets.py → backend/
_CANDIDATE_REGISTRY_PATHS = [
    _BACKEND_ROOT / "assets" / "manifests" / "asset_registry.json",
    _BACKEND_ROOT / "app" / "data" / "library.json",
    _BACKEND_ROOT / "app" / "data" / "asset_registry.json",
]

_registry_cache: Dict[str, Any] = {}


def _load_registry() -> Dict[str, Any]:
    """Load and cache the asset registry. Caller can clear cache via _registry_cache.clear()."""
    if _registry_cache.get("data") is not None:
        return _registry_cache["data"]

    for path in _CANDIDATE_REGISTRY_PATHS:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _registry_cache["data"] = data
            _registry_cache["path"] = str(path)
            return data

    # Fallback to empty structure so callers don't crash
    _registry_cache["data"] = {"models": [], "hdris": [], "materials": []}
    _registry_cache["path"] = None
    return _registry_cache["data"]


def _score_entry(entry: Dict[str, Any], tags: List[str], subject: str = "") -> float:
    """Tag overlap + subject substring match."""
    entry_tags = [t.lower() for t in entry.get("style", []) or entry.get("tags", []) or []]
    query_tags = [t.lower() for t in tags]
    overlap = sum(1 for t in query_tags if t in entry_tags)

    name = entry.get("name", "").lower()
    subject_lc = subject.lower()
    name_hit = 0.85 if subject_lc and subject_lc in name else 0.0

    return overlap + name_hit


# ───────────────────────────────────────────────────────────────────────
# Tool: find_assets — search library by tags / subject, no bpy needed
# ───────────────────────────────────────────────────────────────────────

@register_fn(
    name="find_assets",
    description=(
        "Search the Fantasy Studio asset library by tags and/or subject. "
        "Returns top-N candidate assets, each with name, path, tags, and a relevance score. "
        "Use this BEFORE spawn_asset — pick the best match, then spawn it. "
        "Example query: tags=['vehicle','sci-fi'], subject='bike'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "asset_type": {
                "type": "string",
                "description": "'models' (3D meshes), 'hdris' (environment maps), or 'materials'",
                "default": "models",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Style/category tags to match (e.g. ['sci-fi','vehicle','futuristic'])",
            },
            "subject": {
                "type": "string",
                "description": "Subject hint that matches asset name (e.g. 'bike', 'castle', 'tree')",
            },
            "limit": {"type": "integer", "default": 5, "description": "Max results to return"},
        },
        "additionalProperties": False,
    },
    category="assets",
    side_effects=False,
)
def find_assets(params: dict) -> list:
    asset_type = params.get("asset_type", "models")
    tags = params.get("tags", []) or []
    subject = params.get("subject", "") or ""
    limit = int(params.get("limit", 5))

    registry = _load_registry()
    pool = registry.get(asset_type, []) or []

    scored = []
    for entry in pool:
        s = _score_entry(entry, tags, subject)
        if s > 0:
            scored.append((s, entry))

    scored.sort(key=lambda x: -x[0])
    out = []
    for score, entry in scored[:limit]:
        out.append({
            "name": entry.get("name", "<unnamed>"),
            "path": entry.get("path") or entry.get("blend_path") or entry.get("filepath"),
            "tags": entry.get("style", entry.get("tags", [])),
            "asset_type": asset_type,
            "score": round(score, 3),
            # surface a 'collection_name' if the registry tracks it — needed for append
            "collection_name": entry.get("collection") or entry.get("collection_name"),
        })
    return out


# ───────────────────────────────────────────────────────────────────────
# Tool: spawn_asset — resolve path, call bridge to append + tag as hero
# ───────────────────────────────────────────────────────────────────────

def _resolve_asset_path(path_str: str) -> str:
    """Resolve a registry path to an absolute filesystem path."""
    p = Path(path_str)
    if p.is_absolute() and p.exists():
        return str(p)

    # Try relative to backend root
    rel = _BACKEND_ROOT / path_str
    if rel.exists():
        return str(rel)

    # Try the common 'assets/' prefix
    rel2 = _BACKEND_ROOT / "assets" / path_str
    if rel2.exists():
        return str(rel2)

    raise FileNotFoundError(f"asset path not resolvable: {path_str}")


@register_fn(
    name="spawn_asset",
    description=(
        "Import an asset from the library into the current scene. "
        "Requires path (from find_assets result) and collection_name (the collection "
        "to append from the .blend file). Optionally tags as hero for HERO_VERIFY. "
        "Returns the spawned object names."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the .blend file (from find_assets)"},
            "collection_name": {"type": "string", "description": "Name of the collection inside the .blend to import"},
            "location": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3, "maxItems": 3,
                "description": "World location to place the asset's parent [x,y,z]",
                "default": [0, 0, 0],
            },
            "tag_as_hero": {"type": "boolean", "default": False, "description": "Tag for HERO_VERIFY gate"},
            "link": {"type": "boolean", "default": False, "description": "Link (lightweight) vs append (full copy)"},
        },
        "required": ["path", "collection_name"],
        "additionalProperties": False,
    },
    category="assets",
    side_effects=True,
)
def spawn_asset(params: dict) -> dict:
    abs_path = _resolve_asset_path(params["path"])
    coll_name = params["collection_name"]
    location = params.get("location", [0, 0, 0])
    tag_hero = params.get("tag_as_hero", False)
    link = params.get("link", False)

    # Step 1: append the collection
    append_result = bridge.call("append_blend_collection", {
        "blend_path": abs_path,
        "collection_name": coll_name,
        "link": link,
    })

    # Step 2: position the first imported object (treat as parent anchor)
    object_names = append_result.get("object_names", [])
    primary_name = object_names[0] if object_names else None

    if primary_name and location != [0, 0, 0]:
        bridge.call("transform_object", {"name": primary_name, "location": location})

    # Step 3: hero tag if requested
    tagged = None
    if tag_hero and primary_name:
        tagged = bridge.call("tag_as_hero", {"object": primary_name, "descend": True})

    return {
        "collection": append_result.get("collection"),
        "object_names": object_names,
        "primary": primary_name,
        "tagged": tagged,
        "source_path": abs_path,
    }


@register_fn(
    name="reload_asset_registry",
    description="Force-reload the asset registry from disk. Use after editing library.json externally.",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    category="assets",
    side_effects=False,
)
def reload_asset_registry(params: dict) -> dict:
    _registry_cache.clear()
    data = _load_registry()
    return {
        "path": _registry_cache.get("path"),
        "models": len(data.get("models", [])),
        "hdris": len(data.get("hdris", [])),
        "materials": len(data.get("materials", [])),
    }
