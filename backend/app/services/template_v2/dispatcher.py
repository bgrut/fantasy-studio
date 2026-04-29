from __future__ import annotations

"""
dispatcher.py
=============
Given a render manifest, select the best-matching recipe from the registry.

Scoring is deterministic, additive, and weighted by specificity:
  - scene_family exact match:  +100   (strongest: LLM already classified it)
  - env_subject exact match:   +80    (when forced/auto-picked env is set)
  - env_subject_tags overlap:  +25 per tag (cap +75)
  - env_biome_hints overlap:   +15 per hint (cap +45)
  - hero_category match:       +40
  - hero_shape_class match:    +20
  - keywords_any hit:          +10 per token (cap +40)
  - keywords_all satisfied:    +60    (all or nothing)
  - llm_camera_style match:    +30
  - llm_shot_type match:       +30
  - has_forced_env agreement:  +20

No match returns (None, 0). Caller decides to fall back to V1.1.
"""

from typing import Any

from .registry import TemplateRegistry

MIN_SCORE_FOR_DISPATCH = 50  # below this → fall back to V1.1


# ── context extraction ────────────────────────────────────────────────

def _extract_context(manifest: dict) -> dict[str, Any]:
    sp = manifest.get("scene_plan") or {}
    env_entry = manifest.get("forced_environment_entry") or {}
    directorial = manifest.get("directorial_manifest") or {}
    llm_camera = (directorial.get("camera") or {})

    topic = str(manifest.get("topic", "")).lower()
    core = str(manifest.get("core_objective_prompt", "")).lower()
    prompt_tokens = set()
    import re as _re
    for t in _re.findall(r"[a-z]+", topic + " " + core):
        prompt_tokens.add(t)

    hero_cat = str(
        manifest.get("hero_asset_type") or sp.get("subject_type") or ""
    ).lower()

    return {
        "scene_family":     str(sp.get("scene_family") or "").lower(),
        "env_subject":      str(env_entry.get("subject") or "").lower(),
        "env_subject_tags": {str(t).lower() for t in (env_entry.get("subject_tags") or [])},
        "env_biome_hints":  {str(b).lower() for b in (env_entry.get("biome_hints") or [])},
        "env_shape_class":  str(env_entry.get("shape_class") or "").lower(),
        "hero_category":    hero_cat,
        "hero_shape_class": str(manifest.get("hero_shape_class") or "").lower(),
        "has_forced_env":   bool(
            manifest.get("forced_environment_id")
            or manifest.get("forced_environment_path")
            or manifest.get("forced_environment_entry")
        ),
        "prompt_tokens":    prompt_tokens,
        "llm_camera_style": str(llm_camera.get("style") or "").lower(),
        "llm_shot_type":    str(llm_camera.get("shot_type") or "").lower(),
    }


# ── scorer ─────────────────────────────────────────────────────────────

def _as_lowered_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [v.lower()]
    return [str(x).lower() for x in v]


def score_recipe(recipe: dict, context: dict) -> int:
    """Public for testing / introspection."""
    rules = recipe.get("applies_when") or {}
    score = 0

    fam = _as_lowered_list(rules.get("scene_family"))
    if fam and context["scene_family"] and context["scene_family"] in fam:
        score += 100

    subs = _as_lowered_list(rules.get("env_subject"))
    if subs and context["env_subject"] and context["env_subject"] in subs:
        score += 80

    rule_tags = _as_lowered_list(rules.get("env_subject_tags"))
    if rule_tags:
        hits = sum(1 for t in rule_tags if t in context["env_subject_tags"])
        score += min(hits * 25, 75)

    rule_biomes = _as_lowered_list(rules.get("env_biome_hints"))
    if rule_biomes:
        hits = sum(1 for b in rule_biomes if b in context["env_biome_hints"])
        score += min(hits * 15, 45)

    heros = _as_lowered_list(rules.get("hero_category"))
    if heros and context["hero_category"] and context["hero_category"] in heros:
        score += 40

    shapes = _as_lowered_list(rules.get("hero_shape_class"))
    if shapes and context["hero_shape_class"] and context["hero_shape_class"] in shapes:
        score += 20

    kw_any = _as_lowered_list(rules.get("keywords_any"))
    if kw_any:
        hits = sum(1 for k in kw_any if k in context["prompt_tokens"])
        score += min(hits * 10, 40)

    kw_all = _as_lowered_list(rules.get("keywords_all"))
    if kw_all:
        if all(k in context["prompt_tokens"] for k in kw_all):
            score += 60

    cam_styles = _as_lowered_list(rules.get("llm_camera_style"))
    if cam_styles and context["llm_camera_style"] and context["llm_camera_style"] in cam_styles:
        score += 30

    shot_types = _as_lowered_list(rules.get("llm_shot_type"))
    if shot_types and context["llm_shot_type"] and context["llm_shot_type"] in shot_types:
        score += 30

    if "has_forced_env" in rules:
        # Hard gate — a recipe that declares this rule is disqualified
        # when the context doesn't match.  Prevents env-specific recipes
        # from firing on prompts without an environment.
        if bool(rules["has_forced_env"]) != context["has_forced_env"]:
            return 0
        score += 20

    return score


# ── entry point ────────────────────────────────────────────────────────

def select_recipe(
    manifest: dict,
    registry: TemplateRegistry,
    min_score: int = MIN_SCORE_FOR_DISPATCH,
) -> tuple[dict | None, int, dict]:
    """Return (recipe, score, debug_info).

    ``recipe`` is None when no recipe scores above ``min_score``. Caller
    is expected to fall back to V1.1 behavior in that case.

    ``debug_info`` contains the scoring breakdown for the top candidates
    so logs can show WHY a recipe won.
    """
    context = _extract_context(manifest)
    scored = []
    for recipe in registry.iter_recipes():
        s = score_recipe(recipe, context)
        scored.append((s, recipe))
    scored.sort(key=lambda x: -x[0])

    debug = {
        "context": {k: (sorted(v) if isinstance(v, set) else v) for k, v in context.items()},
        "top": [(s, r.get("name")) for s, r in scored[:5]],
        "min_score": min_score,
    }

    if not scored or scored[0][0] < min_score:
        # Explicit "_default" recipe rescue, if present and registered
        default = registry.get_recipe("_default")
        if default is not None:
            debug["chose"] = "_default"
            return default, 0, debug
        debug["chose"] = None
        return None, 0, debug

    best_score, best = scored[0]
    debug["chose"] = best.get("name")
    return best, best_score, debug
