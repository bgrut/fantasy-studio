from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "assets" / "manifests" / "asset_registry.json"


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"hdris": [], "textures": [], "models": []}
    # utf-8-sig silently strips a leading BOM if present, otherwise
    # behaves as plain utf-8. Some editors on Windows save the registry
    # file with a BOM, which made json.loads crash with
    # "Unexpected UTF-8 BOM" and took down the whole fetch pipeline.
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))


def save_registry(registry: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def upsert_asset(group: str, asset: dict) -> None:
    registry = load_registry()
    items = registry.setdefault(group, [])

    existing_idx = None
    for i, item in enumerate(items):
        if item.get("id") == asset.get("id"):
            existing_idx = i
            break

    if existing_idx is None:
        items.append(asset)
    else:
        items[existing_idx] = asset

    save_registry(registry)