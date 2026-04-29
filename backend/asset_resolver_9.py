from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "assets" / "manifests" / "asset_registry.json"

# ---------------------------------------------------------------------------
# Species affinity tables
# Each entry: (species_keyword_in_prompt, asset_tag_that_matches, bonus)
# ---------------------------------------------------------------------------
_SPECIES_AFFINITY: list[tuple[str, str, int]] = [
    ("cat",       "cat",       60),
    ("cat",       "feline",    50),
    ("cats",      "cat",       60),
    ("cats",      "feline",    50),
    ("dog",       "dog",       60),
    ("dog",       "canine",    50),
    ("bear",      "bear",      60),
    ("yeti",      "yeti",      60),
    ("yeti",      "creature",  20),
    ("human",     "human",     60),
    ("human",     "person",    50),
    ("human",     "biped",     20),
    ("person",    "person",    60),
    ("person",    "human",     50),
    ("person",    "biped",     20),
    ("fish",      "fish",      60),
    ("fish",      "marine",    40),
    ("whale",     "whale",     60),
    ("shark",     "shark",     60),
    ("shark",     "fish",      20),
    ("watch",     "watch",     60),
    ("watch",     "timepiece", 40),
    ("car",       "car",       60),
    ("car",       "vehicle",   50),
    # Scenic/landscape keywords → environment assets
    ("mountain",  "mountain",  70),
    ("mountain",  "landscape", 40),
    ("landscape", "landscape", 60),
    ("landscape", "mountain",  30),
    ("forest",    "forest",    60),
    ("forest",    "nature",    30),
]

_SPECIES_PENALTIES: list[tuple[str, str, int]] = [
    ("cat",    "fish",    -60),
    ("cat",    "dog",     -30),
    ("cat",    "human",   -20),
    ("cats",   "fish",    -60),
    ("cats",   "dog",     -30),
    ("dog",    "fish",    -60),
    ("dog",    "cat",     -30),
    ("dog",    "human",   -20),
    ("bear",   "fish",    -50),
    ("bear",   "cat",     -30),
    ("bear",   "dog",     -30),
    ("yeti",   "fish",    -50),
    ("yeti",   "cat",     -30),
    ("human",  "fish",    -60),
    ("human",  "cat",     -30),
    ("human",  "dog",     -30),
    ("person", "fish",    -60),
    ("person", "cat",     -30),
    ("person", "dog",     -30),
    ("fish",   "cat",     -60),
    ("fish",   "dog",     -60),
    ("fish",   "human",   -60),
    ("watch",  "fish",    -60),
    ("watch",  "cat",     -40),
    ("car",    "fish",    -60),
]


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Asset registry not found: {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))


def _tag_overlap_score(asset_tags: list[str], wanted_tags: list[str]) -> int:
    a = {str(x).lower() for x in asset_tags or []}
    b = {str(x).lower() for x in wanted_tags or []}
    return len(a.intersection(b)) * 10


def _name_match_score(asset: dict, wanted_tags: list[str]) -> int:
    name = str(asset.get("name", "") or asset.get("id", "")).lower()
    return sum(10 for tag in wanted_tags if str(tag).lower() in name)


def _extract_prompt_species(manifest: dict) -> set[str]:
    raw = " ".join([
        str(manifest.get("topic", "")),
        str(manifest.get("core_objective_prompt", "")),
    ]).lower()

    debug_notes = manifest.get("scene_plan", {}).get("debug_notes", []) or []
    for note in debug_notes:
        if note.startswith("subject_species="):
            raw += " " + note.split("=", 1)[1]

    found: set[str] = set()
    for kw in ("cat", "cats", "dog", "bear", "yeti", "human", "person",
               "fish", "whale", "shark", "watch", "car",
               "mountain", "landscape", "forest"):
        if kw in raw:
            found.add(kw)

    return found


def _species_score(asset: dict, prompt_species: set[str]) -> int:
    asset_tags = {str(x).lower() for x in asset.get("tags", []) or []}
    score = 0

    for (species_kw, asset_tag, bonus) in _SPECIES_AFFINITY:
        if species_kw in prompt_species and asset_tag in asset_tags:
            score += bonus

    for (species_kw, asset_tag, penalty) in _SPECIES_PENALTIES:
        if species_kw in prompt_species and asset_tag in asset_tags:
            score += penalty

    return score


def _select_best_models(
    models: list[dict],
    asset_type: str,
    wanted_tags: list[str],
    count: int,
    manifest: dict,
) -> list[dict]:
    candidates = [m for m in models if str(m.get("type", "")).lower() == asset_type.lower()]

    prompt_species = _extract_prompt_species(manifest)

    scored: list[tuple[int, str, dict]] = []
    for item in candidates:
        score = (
            _tag_overlap_score(item.get("tags", []), wanted_tags)
            + _name_match_score(item, wanted_tags)
            + _species_score(item, prompt_species)
        )
        secondary = str(item.get("name", item.get("id", "")))
        scored.append((score, secondary, item))

    scored.sort(key=lambda x: (-x[0], x[1]))

    seen_ids: set[str] = set()
    result: list[dict] = []
    for _, _, item in scored:
        uid = str(item.get("id", item.get("name", id(item))))
        if uid not in seen_ids:
            seen_ids.add(uid)
            result.append(item)
        if len(result) >= count:
            break

    return result


def _select_best_hdri(hdris: list[dict], wanted_tags: list[str], count: int = 1) -> list[dict]:
    scored: list[tuple[int, str, dict]] = []
    for item in hdris:
        score = _tag_overlap_score(item.get("tags", []), wanted_tags)
        secondary = str(item.get("name", item.get("id", "")))
        scored.append((score, secondary, item))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item for _, _, item in scored[:count]]


def _select_best_textures(textures: list[dict], wanted_tags: list[str], count: int = 1) -> list[dict]:
    scored: list[tuple[int, str, dict]] = []
    for item in textures:
        score = _tag_overlap_score(item.get("tags", []), wanted_tags)
        secondary = str(item.get("name", item.get("id", "")))
        scored.append((score, secondary, item))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item for _, _, item in scored[:count]]


def _bucket_model(asset: dict, resolved_models: dict) -> None:
    """
    Route an asset dict into the correct bucket within resolved_models.

    Environment assets (mountains, landscapes, scenic plates) now land in
    their own "environments" bucket so scenic_landscape.py can access them
    via resolved["models"]["environments"] without conflating them with
    buildings or props.
    """
    t = str(asset.get("type", "")).lower()

    if t == "environment":
        resolved_models["environments"].append(asset)
    elif t == "building":
        resolved_models["buildings"].append(asset)
    elif t == "character":
        resolved_models["characters"].append(asset)
    elif t in ("car", "vehicle"):
        resolved_models["cars"].append(asset)
    elif t == "prop":
        resolved_models["props"].append(asset)
    elif t == "product":
        resolved_models["products"].append(asset)
    elif t == "sign":
        resolved_models["signs"].append(asset)
    else:
        # Unknown type — put in props so it's never silently dropped
        resolved_models["props"].append(asset)


def resolve_scene_assets(manifest: dict) -> dict:
    registry = _load_registry()

    hdris    = registry.get("hdris",    []) or []
    textures = registry.get("textures", []) or []
    models   = registry.get("models",   []) or []

    scene_plan   = manifest.get("scene_plan", {}) or {}
    requirements = scene_plan.get("asset_requirements", []) or []

    resolved: dict = {
        "hdris":    [],
        "textures": [],
        "models": {
            "buildings":    [],
            "characters":   [],
            "cars":         [],
            "props":        [],
            "products":     [],
            "signs":        [],
            "environments": [],   # mountains, scenic landscape plates, env heroes
        },
    }

    for req in requirements:
        asset_type  = str(req.get("asset_type", "")).lower()
        count       = int(req.get("count", 1))
        wanted_tags = list(req.get("tags", []) or [])

        if asset_type == "hdri":
            resolved["hdris"].extend(_select_best_hdri(hdris, wanted_tags, count))
        elif asset_type == "texture":
            resolved["textures"].extend(_select_best_textures(textures, wanted_tags, count))
        else:
            selected = _select_best_models(models, asset_type, wanted_tags, count, manifest)
            for item in selected:
                _bucket_model(item, resolved["models"])

    if not resolved["hdris"] and hdris:
        resolved["hdris"].append(hdris[0])

    if not resolved["textures"] and textures:
        resolved["textures"].append(textures[0])

    return resolved
