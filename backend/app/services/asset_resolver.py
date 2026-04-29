from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "assets" / "manifests" / "asset_registry.json"

# Species we recognise in user prompts. Expanded to cover every species the
# local registry actually carries (see tools/register_existing_assets.py +
# asset_registry.json) so that asking for a dolphin, lion, dog, etc. triggers
# strict species filtering and pulls the matching local asset rather than
# falling back to Sketchfab for something we already have on disk.
_SPECIES = [
    # mammals
    "cat", "dog", "bear", "yeti", "lion", "tiger", "wolf", "fox",
    "horse", "elephant", "rabbit", "deer", "monkey", "gorilla",
    # people
    "human", "person", "man", "woman", "girl", "boy",
    # aquatic
    "fish", "whale", "shark", "dolphin",
    # birds
    "bird", "eagle", "owl",
]


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Asset registry not found: {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))


def _text_blob(manifest: dict) -> str:
    return " ".join([
        str(manifest.get("topic", "")),
        str(manifest.get("core_objective_prompt", "")),
    ]).lower()


def _extract_requested_species(manifest: dict) -> str | None:
    text = _text_blob(manifest)
    for species in _SPECIES:
        if species in text:
            return species
    return None


def _tag_overlap_score(asset_tags: list[str], wanted_tags: list[str]) -> int:
    a = {str(x).lower() for x in asset_tags or []}
    b = {str(x).lower() for x in wanted_tags or []}
    return len(a.intersection(b))


def _name_match_score(asset: dict, wanted_tags: list[str]) -> int:
    hay = f"{asset.get('id', '')} {asset.get('path', '')}".lower()
    score = 0
    for tag in wanted_tags or []:
        if str(tag).lower() in hay:
            score += 3
    return score


def _species_penalty_or_bonus(asset: dict, manifest: dict) -> int:
    requested = _extract_requested_species(manifest)
    if not requested:
        return 0

    tags = {str(x).lower() for x in asset.get("tags", []) or []}
    if requested in tags:
        return 100

    if any(spec in tags for spec in _SPECIES if spec != requested):
        return -100

    return 0


# Words that must NEVER be treated as subject identifiers. Stopwords,
# actions, and scene/backdrop nouns — none of these indicate what the hero
# asset actually is. Keeping this list explicit means "robot in a city"
# doesn't match cat_02.blend via the word "city" inside the cat's path.
_SUBJECT_STOPWORDS = {
    "a", "an", "the", "some", "any", "one", "two", "three",
    "of", "in", "on", "at", "to", "for", "with", "and", "or",
    "is", "are", "was", "were", "be", "been", "being",
    "into", "onto", "over", "under", "through", "across",
    "up", "down", "from", "by", "off", "around", "near", "above",
}
_SUBJECT_GENERIC = {
    # actions — these aren't subject identifiers
    "walking", "walk", "running", "run", "dancing", "dance", "dances",
    "swimming", "swim", "flying", "fly", "jumping", "jump",
    "fighting", "fight", "sitting", "sit", "standing", "stand",
    "riding", "ride", "driving", "drive", "racing", "race",
    "soaring", "soar", "playing", "play", "singing", "sing",
    "talking", "talk", "moving", "move",
    # settings / backdrops — these describe environment, not subject
    "city", "street", "road", "highway", "park", "stage", "studio",
    "platform", "mountain", "mountains", "ocean", "sea", "beach",
    "forest", "landscape", "scene", "environment", "sunset", "sunrise",
    "night", "day", "hour", "golden", "sky", "cloud", "clouds",
    "background", "backdrop",
}


def _extract_subject_keywords(manifest: dict) -> list[str]:
    """
    Pull identifying subject words from the user's prompt — what the hero
    IS, not what it's doing or where it is. Used to reject local candidates
    whose identity has no overlap with the requested subject (e.g. the
    sleeping cat when the user asked for a robot).
    """
    text = _text_blob(manifest)
    focal = str(manifest.get("scene_plan", {}).get("focal_subject", "") or "")
    text = f"{text} {focal}".lower()
    raw = [w.strip(".,!?:;\"'`()[]{}<>") for w in text.split()]
    keywords: list[str] = []
    for w in raw:
        if not w or len(w) <= 2:
            continue
        if w in _SUBJECT_STOPWORDS or w in _SUBJECT_GENERIC:
            continue
        keywords.append(w)
    return keywords


def _asset_identity_blob(asset: dict) -> str:
    parts: list[str] = [
        str(asset.get("id", "")),
        str(asset.get("name", "")),
        str(asset.get("path", "")),
        str(asset.get("species", "")),
    ]
    for field in ("tags", "keywords"):
        parts.extend(str(x) for x in (asset.get(field) or []))
    return " ".join(parts).lower()


def _strict_subject_filter(candidates: list[dict], manifest: dict, asset_type: str) -> list[dict]:
    """
    When the user's subject isn't a recognised species (e.g. "robot",
    "dragon", "astronaut"), drop character-type candidates whose identity
    has NO overlap with any subject keyword. Returning [] here triggers the
    Sketchfab fetch path instead of silently substituting whatever
    character happens to live in the local registry.
    """
    if str(asset_type).lower() not in ("character", "animal", "humanoid"):
        return candidates
    # Already handled upstream when a known species is present.
    if _extract_requested_species(manifest):
        return candidates

    keywords = _extract_subject_keywords(manifest)
    if not keywords:
        return candidates

    strict = [
        item for item in candidates
        if any(kw in _asset_identity_blob(item) for kw in keywords)
    ]
    return strict


def _strict_species_filter(candidates: list[dict], manifest: dict, asset_type: str) -> list[dict]:
    # Only enforce species filtering for character-type assets. Apply to the
    # whole character/animal/humanoid equivalence class so that asking for a
    # dog doesn't accidentally return an animal whose tags happen to mention
    # "dog" (sketchfab titles are notoriously noisy — a Halloween cat model
    # has "dog" and "bone" in its tags, for example).
    if str(asset_type).lower() not in ("character", "animal", "humanoid"):
        return candidates

    requested = _extract_requested_species(manifest)
    if not requested:
        return candidates

    # Priority 1: explicit species field match. This is the authoritative
    # signal — an entry whose ``species`` is literally "dog" is a dog, and
    # we should never prefer a tag-mention match over it.
    species_matches = [
        item for item in candidates
        if str(item.get("species") or "").lower() == requested
    ]
    if species_matches:
        return species_matches

    # Priority 2: fall back to tag-mention match only when no species match
    # exists. This keeps us from returning nothing when the registry's
    # species field is empty on every candidate.
    tag_matches = [
        item for item in candidates
        if requested in {str(x).lower() for x in item.get("tags", []) or []}
    ]
    return tag_matches


# Round 13 follow-up: treat character / humanoid / animal as an interchangeable
# set when selecting candidates. ``_bucket_model`` already funnels all three
# into the "characters" bucket, so the selection layer has to use the same
# equivalence or we silently ignore local dog / dolphin / lion assets and
# fall through to Sketchfab even when the registry already has what we need.
# Same idea for vehicles (the registry uses "vehicle" for most, but "car" for
# a handful, and templates look in both buckets).
_TYPE_EQUIVALENCE: dict[str, set[str]] = {
    "character": {"character", "humanoid", "animal"},
    "animal":    {"character", "humanoid", "animal"},
    "humanoid":  {"character", "humanoid", "animal"},
    "vehicle":   {"vehicle", "car"},
    "car":       {"vehicle", "car"},
}


def _types_for(asset_type: str) -> set[str]:
    key = str(asset_type or "").lower()
    return _TYPE_EQUIVALENCE.get(key, {key})


def _select_best_models(models: list[dict], asset_type: str, wanted_tags: list[str], count: int, manifest: dict) -> list[dict]:
    allowed = _types_for(asset_type)
    candidates = [m for m in models if str(m.get("type", "")).lower() in allowed]
    candidates = _strict_species_filter(candidates, manifest, asset_type)
    candidates = _strict_subject_filter(candidates, manifest, asset_type)

    scored = []
    for item in candidates:
        score = 0
        score += _tag_overlap_score(item.get("tags", []), wanted_tags) * 10
        score += _name_match_score(item, wanted_tags)
        score += _species_penalty_or_bonus(item, manifest)
        scored.append((score, str(item.get("id", "")), item))

    scored.sort(key=lambda x: (-x[0], x[1]))

    selected = [item for score, asset_id, item in scored if score >= 0]
    if not selected:
        selected = [item for score, asset_id, item in scored]

    selected = selected[:count]

    # Duplicate best matching asset until requested count is met.
    # This avoids fallback stand-ins when the prompt wants 3 cats but only 2 cat files exist.
    if selected and len(selected) < count:
        idx = 0
        originals = list(selected)
        while len(selected) < count:
            selected.append(originals[idx % len(originals)].copy())
            idx += 1

    return selected


def _select_best_hdri(hdris: list[dict], wanted_tags: list[str], count: int = 1) -> list[dict]:
    scored = []
    for item in hdris:
        score = _tag_overlap_score(item.get("tags", []), wanted_tags)
        scored.append((score, str(item.get("id", "")), item))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item for _, _, item in scored[:count]]


def _select_best_textures(textures: list[dict], wanted_tags: list[str], count: int = 1) -> list[dict]:
    scored = []
    for item in textures:
        score = _tag_overlap_score(item.get("tags", []), wanted_tags)
        scored.append((score, str(item.get("id", "")), item))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item for _, _, item in scored[:count]]


def _bucket_model(asset: dict, resolved_models: dict):
    t = str(asset.get("type", "")).lower()

    if t == "building":
        resolved_models["buildings"].append(asset)
    elif t in ("character", "humanoid", "animal"):
        resolved_models["characters"].append(asset)
    elif t == "car":
        resolved_models["cars"].append(asset)
    elif t == "vehicle":
        resolved_models["vehicles"].append(asset)
    elif t == "environment":
        resolved_models["environments"].append(asset)
    elif t == "prop":
        resolved_models["props"].append(asset)
    elif t == "product":
        resolved_models["products"].append(asset)
    elif t == "sign":
        resolved_models["signs"].append(asset)
    elif t == "model":
        # Generic "model" type from Sketchfab — route based on scene context
        resolved_models["props"].append(asset)
    else:
        resolved_models["props"].append(asset)


def _empty_model_buckets() -> dict:
    return {
        "buildings": [],
        "characters": [],
        "cars": [],
        "vehicles": [],
        "environments": [],
        "props": [],
        "products": [],
        "signs": [],
    }


def bucket_flat_models(flat_list: list[dict], resolved_models: dict | None = None) -> dict:
    """
    Take a flat list of model records (as returned by asset_fetcher) and
    bucket them into the dict structure that templates expect.
    If resolved_models already has bucketed data, merge into it.
    """
    if resolved_models is None:
        resolved_models = _empty_model_buckets()
    for asset in flat_list:
        _bucket_model(asset, resolved_models)
    return resolved_models


def resolve_scene_assets(manifest: dict) -> dict:
    registry = _load_registry()

    hdris = registry.get("hdris", []) or []
    textures = registry.get("textures", []) or []
    models = registry.get("models", []) or []

    scene_plan = manifest.get("scene_plan", {}) or {}
    requirements = scene_plan.get("asset_requirements", []) or []

    resolved = {
        "hdris": [],
        "textures": [],
        "models": {
            "buildings": [],
            "characters": [],
            "cars": [],
            "vehicles": [],
            "environments": [],
            "props": [],
            "products": [],
            "signs": [],
        }
    }

    for req in requirements:
        asset_type = str(req.get("asset_type", "")).lower()
        count = int(req.get("count", 1))
        wanted_tags = req.get("tags", []) or []

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







