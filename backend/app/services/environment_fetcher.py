from __future__ import annotations

"""
environment_fetcher.py
======================
Fetch COMPLEX environment models (stadiums, restaurants, kitchens,
concert halls, arenas) from Sketchfab so scenes like "monkey dancing in
a baseball stadium" actually render the stadium, instead of a dancing
monkey on a gray infinite plane.

The standard asset pipeline (asset_agent → asset_resolver → asset_fetcher
→ sketchfab_fetcher) handles the HERO. It does NOT fetch sprawling
environment models. For simple environments (mountains, ocean, studio)
we rely on procedural HDRI + ground material, which works great. For
NAMED complex environments we need a hero-scale scene model placed
around the character.

This module:
1. Inspects the prompt / scene_recipe / directorial_manifest.
2. Decides whether the environment is "complex" (named venue) or
   "simple" (mountains/ocean/studio — procedural is fine).
3. If complex, calls sketchfab_fetcher.fetch_model with a query tuned
   for environments (no animation requirement, larger poly budget).
4. Returns the asset record so the caller can attach it to the manifest
   under ``environment_asset_path`` for the render template to place.

NOTE: This module only READS from the STABLE files (sketchfab_fetcher,
asset_query_generator). It does not modify them.
"""

from pathlib import Path

# Per-venue scale multipliers (×hero diagonal). Stadiums need MUCH more
# headroom than restaurants. Consumed by render_from_manifest.py's
# env importer via get_env_scale_multiplier().
_VENUE_SCALE_MULTIPLIER: dict[str, float] = {
    "stadium":          25.0,
    "baseball stadium": 25.0,
    "football stadium": 25.0,
    "basketball court": 12.0,
    "arena":            18.0,
    "gym":              6.0,
    "concert hall":     15.0,
    "theater":          12.0,
    "nightclub":        8.0,
    "restaurant":       8.0,
    "kitchen":          4.0,
    "diner":            6.0,
    "cafe":             6.0,
    "bar":              6.0,
    "mall":             20.0,
    "store":            8.0,
    "office":           8.0,
    "classroom":        6.0,
    "library":          10.0,
    "church":           15.0,
    "museum":           14.0,
    "warehouse":        15.0,
    "factory":          15.0,
    "castle":           20.0,
    "throne room":      12.0,
    "dungeon":          10.0,
    "temple":           15.0,
    "spaceship":        10.0,
    "park":             20.0,
    "playground":       10.0,
    "farm":             20.0,
    "garage":           8.0,
    "racetrack":        30.0,
}


def get_env_scale_multiplier(manifest: dict) -> float:
    """
    Return the ×hero-diagonal the environment should be scaled to.
    Falls back to 10.0 if the env isn't a known venue.
    """
    d = detect_complex_environment(manifest)
    if not d:
        return 10.0
    return _VENUE_SCALE_MULTIPLIER.get(d[0], 10.0)


# These are keywords that mean "I need a whole venue/scene/building
# model for the environment". If the user prompt or scene_recipe
# environment contains one of these, we should fetch a complex model.
# Keys are canonical names; values are ordered search queries (best
# first) to try against Sketchfab.
_COMPLEX_ENVIRONMENTS: dict[str, list[str]] = {
    # Sports venues
    "stadium":        ["baseball stadium 3d", "stadium scene", "sports stadium environment"],
    "baseball stadium": ["baseball stadium", "baseball field scene", "ballpark 3d"],
    "football stadium": ["football stadium", "soccer stadium", "sports arena"],
    "basketball court": ["basketball court scene", "basketball arena", "indoor basketball gym"],
    "arena":          ["sports arena 3d", "indoor arena scene", "stadium interior"],
    "gym":            ["gymnasium 3d", "indoor gym scene", "fitness gym environment"],
    # Food & dining
    "restaurant":     ["restaurant interior", "restaurant dining scene", "bistro interior 3d"],
    "kitchen":        ["kitchen scene 3d", "commercial kitchen", "restaurant kitchen interior"],
    "diner":          ["diner interior", "american diner 3d", "retro diner scene"],
    "cafe":           ["cafe interior", "coffee shop scene", "cozy cafe 3d"],
    "bar":            ["bar interior 3d", "pub scene", "nightclub bar"],
    # Performance
    "concert hall":   ["concert hall 3d", "theater interior", "auditorium scene"],
    "theater":        ["theater interior", "stage scene 3d", "auditorium"],
    "nightclub":      ["nightclub 3d", "club interior", "disco scene"],
    # Retail / public
    "mall":           ["shopping mall interior", "mall scene", "retail interior 3d"],
    "store":          ["store interior", "shop scene 3d", "retail storefront"],
    "office":         ["office interior", "corporate office 3d", "open office scene"],
    "classroom":      ["classroom 3d", "school classroom interior"],
    "library":        ["library interior", "library scene 3d"],
    "church":         ["church interior", "cathedral scene"],
    "museum":         ["museum interior", "gallery scene 3d"],
    # Action / adventure
    "warehouse":      ["warehouse interior", "warehouse 3d", "industrial warehouse"],
    "factory":        ["factory interior", "industrial factory scene"],
    "castle":         ["castle interior", "medieval castle 3d", "throne room"],
    "throne room":    ["throne room 3d", "castle throne room"],
    "dungeon":        ["dungeon interior", "medieval dungeon 3d"],
    "temple":         ["temple interior 3d", "ancient temple scene"],
    "spaceship":      ["spaceship interior", "sci-fi ship corridor", "spaceship bridge"],
    # Outdoor but bounded
    "park":           ["park scene 3d", "city park environment"],
    "playground":     ["playground 3d", "kids playground scene"],
    "farm":           ["farm scene 3d", "barn farm environment"],
    "garage":         ["garage interior", "workshop 3d", "auto garage scene"],
    "racetrack":      ["race track 3d", "racing circuit environment"],
}


def detect_complex_environment(manifest: dict) -> tuple[str, list[str]] | None:
    """
    Return (canonical_name, ordered_queries) if the scene needs a
    complex environment model, else None.

    Looks at (in priority order):
      1. manifest['topic'] / 'prompt' — the raw user text.
      2. manifest['scene_recipe']['environment']['type'] and
         ['style'], when scene_recipe is populated.
      3. manifest['_scene_plan']['environment'].
      4. manifest['environment_ground_type'].
    """
    # Collect every string the user or planner populated for "where".
    fragments: list[str] = []
    for key in ("topic", "prompt"):
        v = manifest.get(key)
        if v:
            fragments.append(str(v))

    recipe = manifest.get("scene_recipe") or {}
    env = recipe.get("environment") or {}
    for key in ("type", "style", "location", "venue", "description"):
        v = env.get(key)
        if v:
            fragments.append(str(v))

    plan = manifest.get("_scene_plan") or {}
    for key in ("environment", "environment_preset", "setting"):
        v = plan.get(key)
        if v:
            fragments.append(str(v))

    v = manifest.get("environment_ground_type")
    if v:
        fragments.append(str(v))

    blob = " ".join(fragments).lower()
    if not blob.strip():
        return None

    # Longest-match wins — "baseball stadium" beats "stadium".
    keys_by_len = sorted(_COMPLEX_ENVIRONMENTS, key=len, reverse=True)
    for key in keys_by_len:
        if key in blob:
            return key, list(_COMPLEX_ENVIRONMENTS[key])
    return None


def fetch_complex_environment(manifest: dict) -> dict | None:
    """
    If the manifest's scene calls for a complex environment and one
    isn't already resolved, try to fetch it from Sketchfab.

    Returns the asset record (dict with 'path', 'name', ...) on
    success, or None if skipped / failed. Never raises.

    The asset is ALSO written back into the manifest under
    ``environment_asset_path`` and into ``resolved_assets['models']
    ['environment']`` so templates that look for either can find it.
    """
    try:
        # Don't overwrite an environment that was resolved upstream.
        if manifest.get("environment_asset_path"):
            return None
        ra = manifest.get("resolved_assets") or {}
        ra_models = ra.get("models") or {}
        if isinstance(ra_models, dict) and ra_models.get("environment"):
            return None

        detection = detect_complex_environment(manifest)
        if not detection:
            return None
        canonical, queries = detection

        try:
            from .sketchfab_fetcher import fetch_model, is_available
        except Exception as e:
            print(f"[ENV_FETCH] sketchfab import failed: {e}", flush=True)
            return None
        if not is_available():
            print("[ENV_FETCH] sketchfab unavailable — skipping complex env fetch", flush=True)
            return None

        print(f"[ENV_FETCH] detected complex env={canonical!r} — trying queries", flush=True)
        # Append "landscape" to each query so Sketchfab returns actual
        # environment/scene results instead of characters or props.
        qualified_queries = []
        for q in queries:
            qualified_queries.append(q)
            # Add a landscape-qualified variant unless the query already
            # contains "environment", "landscape", or "interior".
            q_lower = q.lower()
            if not any(kw in q_lower for kw in ("environment", "landscape", "interior")):
                qualified_queries.append(f"{q} landscape")
        for q in qualified_queries:
            try:
                # Environments are BIG — allow up to 1M faces, static-ok.
                record = fetch_model(
                    q,
                    max_face_count=1_000_000,
                    animated=False,
                    asset_role="environment",
                )
            except Exception as e:
                print(f"[ENV_FETCH] {q!r} raised {e} — trying next", flush=True)
                continue
            if record and record.get("path"):
                # Write to both manifest slots so downstream code finds it.
                manifest["environment_asset_path"] = record["path"]
                manifest["environment_asset_name"] = record.get("name", canonical)
                manifest["environment_asset_scale_class"] = "xlarge"
                ra = manifest.setdefault("resolved_assets", {})
                models = ra.setdefault("models", {})
                if isinstance(models, dict):
                    env_list = models.setdefault("environment", [])
                    env_list.append({
                        "name": record.get("name", canonical),
                        "path": record["path"],
                        "source": record.get("source", "sketchfab"),
                        "scale_class": "xlarge",
                        "query": q,
                    })
                print(
                    f"[ENV_FETCH] ✓ environment resolved for '{canonical}': "
                    f"{record.get('name')} @ {record['path']}",
                    flush=True,
                )
                return record

        print(f"[ENV_FETCH] no environment match for {canonical!r}", flush=True)
        return None
    except Exception as e:
        print(f"[ENV_FETCH] fetch crashed (non-fatal): {e}", flush=True)
        return None
