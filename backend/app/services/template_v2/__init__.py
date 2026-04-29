"""
app.services.template_v2
=========================
V1.3 — Template System v2.

Three public entry points:

    from app.services.template_v2 import (
        load_registry,   # load + validate all layers/recipes
        select_recipe,   # pick best recipe for a manifest
        apply_recipe,    # map recipe → scene_plan fields (Fork A)
    )

Design notes (Fork A, v1.3.0):
- Layers are pure JSON; they don't touch bpy.
- The executor is a preset-mapper: it translates a recipe into the
  scene_plan fields that the existing V1.1 preset system already
  consumes (environment_preset, camera_preset, lighting_preset,
  animation_style, etc.). No change to render_from_manifest.py.
- Later rounds can swap the executor for one that directly drives
  Blender ops, or an Unreal backend.
"""
from __future__ import annotations

from .registry import TemplateRegistry, load_registry
from .dispatcher import select_recipe, score_recipe
from .executor import apply_recipe

__all__ = [
    "TemplateRegistry",
    "load_registry",
    "select_recipe",
    "score_recipe",
    "apply_recipe",
]
