from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "assets" / "manifests" / "asset_registry.json"


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"models": [], "hdris": [], "materials": []}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _score_entry(entry: dict, tags: list[str]) -> int:
    entry_tags = [str(x).lower() for x in entry.get("style", [])]
    score = 0
    for tag in tags:
        if tag in entry_tags:
            score += 1
    return score


def find_best_assets(asset_type: str, tags: list[str], limit: int = 5) -> list[dict]:
    registry = load_registry()
    pool = registry.get(asset_type, [])
    tags = [t.lower() for t in tags]

    ranked = sorted(
        pool,
        key=lambda e: _score_entry(e, tags),
        reverse=True
    )
    ranked = [r for r in ranked if _score_entry(r, tags) > 0]
    return ranked[:limit]
