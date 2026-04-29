from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "assets" / "manifests" / "asset_registry.json"


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"hdris": [], "textures": [], "models": []}
    # utf-8-sig silently strips a leading BOM if present. Needed because
    # the registry file is edited by humans/tools that can add a BOM.
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))


def _score_tags(candidate_tags: list[str], wanted_tags: list[str]) -> int:
    cand = {str(x).lower() for x in candidate_tags}
    wanted = {str(x).lower() for x in wanted_tags}
    return len(cand.intersection(wanted))


def search_assets(group: str, wanted_tags: list[str], limit: int = 5) -> list[dict]:
    registry = load_registry()
    items = registry.get(group, [])
    ranked = sorted(
        items,
        key=lambda item: _score_tags(item.get("tags", []), wanted_tags),
        reverse=True,
    )
    ranked = [x for x in ranked if _score_tags(x.get("tags", []), wanted_tags) > 0]
    return ranked[:limit]


def first_asset(group: str, wanted_tags: list[str]) -> dict | None:
    hits = search_assets(group, wanted_tags, limit=1)
    return hits[0] if hits else None