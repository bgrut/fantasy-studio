"""
Template tools — wrap the existing template_v2 system (Fork A).

The existing dispatcher.select_recipe() and executor.apply_recipe() operate
on a `manifest` dict. They don't touch bpy. So these tools are in-process:
they let the orchestrator preview / score / fetch curated recipes WITHOUT
firing the heavyweight render pipeline.

How the orchestrator uses these:
    1. User says "render a cyberpunk street scene with a hero bike"
    2. score_templates(prompt) → returns top 3 recipes ranked by relevance
    3. Orchestrator inspects the top recipe's layer assignments
    4. Either calls run_template(name) to materialize the manifest's
       scene_plan fields, OR cherry-picks layers and assembles its own plan
       using create_primitive/spawn_asset/add_light/etc.

Templates are a *recipe library*, not a black box. Orchestrator can mix-and-
match recipe layers with freehand ops.
"""

from typing import Optional
from ..registry import register_fn


# ───────────────────────────────────────────────────────────────────────
# Lazy import of template_v2 — keep registry importable even if backend
# modules aren't all on path (e.g. when running tests in isolation).
# ───────────────────────────────────────────────────────────────────────

_template_v2_cache = {}


def _get_template_v2():
    if _template_v2_cache.get("loaded"):
        return _template_v2_cache.get("module")
    try:
        # Try direct import first
        from app.services import template_v2  # type: ignore
        _template_v2_cache["loaded"] = True
        _template_v2_cache["module"] = template_v2
        return template_v2
    except ImportError:
        # Try sys.path hack
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parents[3]
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        try:
            from app.services import template_v2  # type: ignore
            _template_v2_cache["loaded"] = True
            _template_v2_cache["module"] = template_v2
            return template_v2
        except ImportError as e:
            _template_v2_cache["loaded"] = True
            _template_v2_cache["module"] = None
            _template_v2_cache["error"] = str(e)
            return None


def _get_registry():
    """Load the TemplateRegistry once."""
    if "registry" in _template_v2_cache:
        return _template_v2_cache["registry"]
    tv2 = _get_template_v2()
    if tv2 is None:
        return None
    try:
        reg = tv2.load_registry() if hasattr(tv2, "load_registry") else None
        _template_v2_cache["registry"] = reg
        return reg
    except Exception as e:
        _template_v2_cache["registry"] = None
        _template_v2_cache["registry_error"] = str(e)
        return None


# ───────────────────────────────────────────────────────────────────────
# Tools
# ───────────────────────────────────────────────────────────────────────

@register_fn(
    name="list_templates",
    description=(
        "List all curated scene recipes (templates) in the template_v2 system. "
        "Each recipe is a composition of layers (environment, lighting, camera, etc). "
        "Use score_templates to find the BEST match for a given prompt; use list_templates "
        "for browsing."
    ),
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    category="templates",
    side_effects=False,
)
def list_templates(params: dict) -> dict:
    reg = _get_registry()
    if reg is None:
        return {"error": "template_v2 not loadable", "details": _template_v2_cache.get("error")}

    if hasattr(reg, "iter_recipes"):
        recipes = [{"name": r.get("name"), "scene_family": r.get("scene_family"),
                    "env_subject": r.get("env_subject"), "tags": r.get("tags", [])}
                   for r in reg.iter_recipes()]
    else:
        recipes = []
    return {"count": len(recipes), "recipes": recipes}


@register_fn(
    name="score_templates",
    description=(
        "Rank templates by relevance to a manifest (subject, tags, keywords). "
        "Returns top-N with scores. Use the top result as a starting point — "
        "you can use the whole recipe via run_template, or cherry-pick its layers."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Hero subject (e.g. 'bike', 'castle')"},
            "scene_family": {"type": "string", "description": "Family hint (e.g. 'cyberpunk', 'fantasy')"},
            "tags": {"type": "array", "items": {"type": "string"}, "default": []},
            "keywords": {"type": "array", "items": {"type": "string"}, "default": []},
            "limit": {"type": "integer", "default": 3},
        },
        "additionalProperties": False,
    },
    category="templates",
    side_effects=False,
)
def score_templates(params: dict) -> dict:
    tv2 = _get_template_v2()
    reg = _get_registry()
    if tv2 is None or reg is None:
        return {"error": "template_v2 not loadable", "details": _template_v2_cache.get("error")}

    # Build a manifest-shaped context from params
    manifest = {
        "subject": params.get("subject", ""),
        "scene_family": params.get("scene_family", ""),
        "env_subject": params.get("subject", ""),
        "tags": params.get("tags", []),
        "keywords": params.get("keywords", []),
    }

    if not hasattr(tv2, "select_recipe"):
        return {"error": "template_v2.select_recipe not found"}

    # If the API supports scoring all, do that. Otherwise just return the best.
    try:
        best, score = tv2.select_recipe(manifest, reg)
    except Exception as e:
        return {"error": f"select_recipe failed: {e}"}

    limit = params.get("limit", 3)
    if limit == 1 or not hasattr(tv2, "score_recipe"):
        return {
            "best": {
                "name": (best or {}).get("name"),
                "score": score,
                "scene_family": (best or {}).get("scene_family"),
                "env_subject": (best or {}).get("env_subject"),
            }
        }

    # Score all and rank
    scored = []
    if hasattr(reg, "iter_recipes"):
        for recipe in reg.iter_recipes():
            try:
                s = tv2.score_recipe(recipe, manifest)
                scored.append((s, recipe))
            except Exception:
                continue
    scored.sort(key=lambda x: -x[0])
    return {
        "top": [
            {
                "name": r.get("name"),
                "score": s,
                "scene_family": r.get("scene_family"),
                "env_subject": r.get("env_subject"),
                "tags": r.get("tags", []),
            }
            for s, r in scored[:limit]
        ],
    }


@register_fn(
    name="run_template",
    description=(
        "Materialize a template's layer assignments into a manifest. "
        "Returns the scene_plan dict (environment_preset, camera_preset, lighting_preset, etc.) — "
        "the orchestrator can then translate those preset names into bridge calls. "
        "NOTE: this does NOT execute Blender ops directly — it returns the recipe's PLAN. "
        "Use the plan to decide which other tools to call."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Recipe name from list_templates / score_templates"},
            "manifest": {
                "type": "object",
                "description": "Optional initial manifest (subject, tags, etc.) — recipe layers are added to this",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    category="templates",
    side_effects=False,
)
def run_template(params: dict) -> dict:
    tv2 = _get_template_v2()
    reg = _get_registry()
    if tv2 is None or reg is None:
        return {"error": "template_v2 not loadable", "details": _template_v2_cache.get("error")}

    if not hasattr(reg, "get_recipe"):
        return {"error": "registry has no get_recipe method"}

    recipe = reg.get_recipe(params["name"])
    if recipe is None:
        return {"error": f"recipe '{params['name']}' not found"}

    manifest = dict(params.get("manifest", {}))

    if not hasattr(tv2, "apply_recipe"):
        return {"error": "template_v2.apply_recipe not found"}

    try:
        tv2.apply_recipe(manifest, recipe, reg)
    except Exception as e:
        return {"error": f"apply_recipe failed: {e}"}

    return {
        "recipe": params["name"],
        "scene_plan": manifest.get("scene_plan", {}),
        "applied_markers": {
            "_template_v2_recipe": manifest.get("_template_v2_recipe"),
            "_template_v2_applied": manifest.get("_template_v2_applied"),
        },
    }
