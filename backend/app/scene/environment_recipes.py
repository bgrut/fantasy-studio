from __future__ import annotations

"""
environment_recipes.py
======================
Round 11: deterministic environment composition from curated pieces.

Instead of "search Sketchfab for city buildings and hope," every prompt
maps to a recipe that specifies the ground material, HDRI query, prop
list (curated asset IDs), and atmosphere. The builder runs through
``build_environment_from_recipe`` which reuses the existing
``environment_ops`` helpers — it does NOT re-implement them.

A recipe is a plain dict. Missing pieces are tolerated — if a prop id
isn't in the curated catalog yet, the builder logs and moves on. This
lets you ship recipes that reference future curated assets without
breaking renders today.
"""

import math
import random
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# The recipe catalog
# ═══════════════════════════════════════════════════════════════════════════
#
# Keys map to the ``environment`` field the LLM produces in scene_plan.
# Aliases are also registered for common synonyms. New recipes can be
# added freely — the resolver falls back to ``_DEFAULT_RECIPE`` on miss.

_RECIPES: dict[str, dict[str, Any]] = {
    "city": {
        "ground": "road_asphalt",
        "hdri_queries": ["city night", "urban street", "night"],
        "props":  ["city_block", "street_lamp", "traffic_light"],
        "atmosphere": "urban_haze",
    },
    "park": {
        "ground": "grass",
        "hdri_queries": ["sunny park", "park morning", "sunny"],
        "props":  ["park_trees", "park_bench"],
        "atmosphere": "light_mist",
    },
    "forest": {
        "ground": "terrain_ground",
        "hdri_queries": ["forest canopy", "forest", "overcast"],
        "props":  ["forest_trees", "rocks", "ferns"],
        "atmosphere": "forest_fog",
    },
    "highway": {
        "ground": "road_asphalt",
        "hdri_queries": ["sunset dramatic", "highway sunset", "sunset"],
        "props":  ["road_barriers", "road_lines"],
        "atmosphere": "heat_haze",
    },
    "ocean": {
        "ground": "water_surface",
        "hdri_queries": ["ocean sky", "beach", "sunset"],
        "props":  ["coral", "rocks_underwater"],
        "atmosphere": "underwater_blue",
    },
    "stage": {
        "ground": "studio_floor",
        "hdri_queries": ["studio", "studio neutral", "softbox"],
        "props":  [],
        "atmosphere": "stage_haze",
    },
    "mountain": {
        "ground": "terrain_ground",
        "hdri_queries": ["mountain sunset", "mountain", "golden hour"],
        "props":  ["mountain_rocks", "distant_peaks"],
        "atmosphere": "mountain_mist",
    },
    "desert": {
        "ground": "sand",
        "hdri_queries": ["desert sun", "desert", "day"],
        "props":  ["desert_rocks", "cacti"],
        "atmosphere": "heat_haze",
    },
    "jungle": {
        "ground": "terrain_ground",
        "hdri_queries": ["tropical canopy", "jungle", "forest"],
        "props":  ["jungle_trees", "vines", "tropical_plants"],
        "atmosphere": "humid_fog",
    },
    "space": {
        "ground": "studio_floor",
        "hdri_queries": ["space nebula", "stars", "night"],
        "props":  [],
        "atmosphere": "deep_space",
    },
    "street": {
        "ground": "road_asphalt",
        "hdri_queries": ["city street", "night", "urban"],
        "props":  ["street_lamp", "trash_can"],
        "atmosphere": "urban_haze",
    },
}

# Environment aliases used by the LLM / scene_plan.
_ALIASES = {
    "urban":      "city",
    "metropolis": "city",
    "road":       "highway",
    "beach":      "ocean",
    "sea":        "ocean",
    "underwater": "ocean",
    "studio":     "stage",
    "pedestal":   "stage",
    "woods":      "forest",
    "woodland":   "forest",
    "prairie":    "park",
    "meadow":     "park",
    "garden":     "park",
    "hill":       "mountain",
    "mountains":  "mountain",
    "dunes":      "desert",
    "rainforest": "jungle",
    "tropics":    "jungle",
    "tropical":   "jungle",
}

_DEFAULT_RECIPE = _RECIPES["park"]


def resolve_recipe(environment: str, scene_family: str = "") -> tuple[str, dict]:
    """
    Pick the best-matching recipe for the given environment / scene
    family. Returns ``(recipe_name, recipe_dict)``.
    """
    env = (environment or "").strip().lower()
    fam = (scene_family or "").strip().lower()
    if env in _RECIPES:
        return (env, _RECIPES[env])
    if env in _ALIASES:
        key = _ALIASES[env]
        return (key, _RECIPES[key])
    # Tokenised fallback: any recipe key appearing in the free-text
    # environment string wins.
    for key in _RECIPES:
        if key in env:
            return (key, _RECIPES[key])
    # Scene-family fallback.
    family_to_recipe = {
        "city_loop":       "city",
        "neon_news":       "city",
        "street_scene":    "street",
        "car_hero":        "highway",
        "ocean_scene":     "ocean",
        "scenic_landscape": "mountain",
        "character_stage":  "stage",
        "product_scene":    "stage",
        "product_pedestal": "stage",
    }
    if fam in family_to_recipe:
        key = family_to_recipe[fam]
        return (key, _RECIPES[key])
    return ("park", _DEFAULT_RECIPE)


# ═══════════════════════════════════════════════════════════════════════════
# Builder
# ═══════════════════════════════════════════════════════════════════════════

def _place_curated_prop(bpy, asset_record: dict, anchor=(0.0, 0.0, 0.0), idx: int = 0) -> bool:
    """
    Import a curated prop GLB and scatter it around the hero anchor.
    Returns True on successful import. The prop record is whatever
    ``asset_to_resolver_record`` produced.
    """
    path = asset_record.get("path")
    if not path:
        return False
    try:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path))
        new_objs = [o for o in bpy.data.objects if o not in before]
        if not new_objs:
            return False
        # Offset the prop so multiple props don't pile on top of each other.
        angle = (idx * 137.0) % 360.0  # golden-angle spread
        radius = 6.0 + (idx % 3) * 2.0
        rad = math.radians(angle)
        dx = math.cos(rad) * radius
        dy = math.sin(rad) * radius
        for obj in new_objs:
            if obj.parent is None:
                obj.location.x += anchor[0] + dx
                obj.location.y += anchor[1] + dy
                obj.location.z += anchor[2]
                # Randomise yaw so scattered trees don't look stamped.
                obj.rotation_euler.z += random.uniform(0.0, math.pi * 2.0)
        print(
            f"[RECIPE] placed prop {asset_record.get('id')!r} at "
            f"({anchor[0] + dx:.1f}, {anchor[1] + dy:.1f})",
            flush=True,
        )
        return True
    except Exception as e:
        print(f"[RECIPE] prop import failed ({path}): {e}", flush=True)
        return False


def build_environment_from_recipe(
    bpy,
    scene,
    manifest: dict,
    hero_center=(0.0, 0.0, 0.0),
) -> dict:
    """
    Compose a scene environment from a curated recipe. Returns a report
    describing what was applied. Missing curated props are tolerated —
    the Round 10 ``environment_ops`` helpers still guarantee ground +
    horizon even if the recipe has no props yet.

    This function is additive: it never clears template-built geometry.
    Call it as a gap-filler AFTER the template has run.
    """
    from .environment_ops import (
        apply_ground_material, add_atmosphere, setup_cinematic_lighting,
        add_contact_shadow, ensure_ground_and_horizon,
    )
    try:
        from ..services.curated_resolver import (
            search_curated_library, asset_to_resolver_record,
        )
        _HAS_CURATED = True
    except ImportError:
        _HAS_CURATED = False

    scene_plan = manifest.get("_scene_plan") or manifest.get("scene_plan") or {}
    environment = str(scene_plan.get("environment") or manifest.get("environment") or "")
    family = str(scene_plan.get("scene_family") or "")
    mood = str(scene_plan.get("mood") or "")
    tod = str(scene_plan.get("time_of_day") or "")

    recipe_name, recipe = resolve_recipe(environment, family)
    report: dict[str, Any] = {
        "recipe":        recipe_name,
        "ground":        None,
        "props_placed":  0,
        "props_missing": [],
        "atmosphere":    False,
        "lights_added":  0,
    }

    # 1. Ground material
    try:
        applied = apply_ground_material(bpy, scene, recipe["ground"])
        report["ground"] = recipe["ground"] if applied else None
    except Exception as e:
        print(f"[RECIPE] ground apply failed: {e}", flush=True)

    # 2. Atmosphere + 3-point lighting (Round 9 helpers)
    try:
        report["atmosphere"] = bool(add_atmosphere(bpy, scene, mood=mood, time_of_day=tod))
    except Exception as e:
        print(f"[RECIPE] atmosphere failed: {e}", flush=True)
    try:
        report["lights_added"] = setup_cinematic_lighting(
            bpy, scene, mood=mood, time_of_day=tod, hero_location=hero_center,
        )
    except Exception as e:
        print(f"[RECIPE] lighting failed: {e}", flush=True)

    # 3. Props — each is looked up in the curated catalog by ID.
    if _HAS_CURATED:
        for idx, prop_id in enumerate(recipe.get("props") or []):
            prop = search_curated_library(prop_id, asset_type="prop", min_score=1)
            if not prop:
                report["props_missing"].append(prop_id)
                print(f"[RECIPE] prop {prop_id!r} not in curated catalog yet", flush=True)
                continue
            record = asset_to_resolver_record(prop)
            if _place_curated_prop(bpy, record, anchor=hero_center, idx=idx):
                report["props_placed"] += 1
    else:
        report["props_missing"] = list(recipe.get("props") or [])

    # 4. Horizon (ground rescale + distant hills or cyc-wall)
    try:
        ensure_ground_and_horizon(bpy, scene, manifest, mood=mood, time_of_day=tod)
    except Exception as e:
        print(f"[RECIPE] ensure_ground_and_horizon failed: {e}", flush=True)

    print(
        f"[RECIPE] built environment '{recipe_name}': "
        f"ground={report['ground']} props={report['props_placed']}/"
        f"{len(recipe.get('props') or [])} atmos={report['atmosphere']}",
        flush=True,
    )
    return report


__all__ = ["resolve_recipe", "build_environment_from_recipe"]
