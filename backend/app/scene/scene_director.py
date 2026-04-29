from __future__ import annotations

"""
scene_director.py
=================
Accepts a manifest (and optional prompt text) and produces a structured
``scene_plan`` dict that builders can consume.

The scene_plan contains:
  - scene_family       (str)  e.g. "car_hero", "street_scene"
  - camera_preset      (str)  key into CAMERA_PRESETS
  - lighting_preset    (str)  key into LIGHTING_PRESETS
  - environment_preset (str)  key into ENVIRONMENT_PRESETS
  - animation_style    (str)  e.g. "turntable", "idle", "swim_school"
  - overrides          (dict) per-scene tweaks injected by the director

The director does NOT call bpy.  It is pure logic that runs before any
Blender scene construction, making it testable without Blender.

Usage:
    from app.scene.scene_director import direct_scene

    scene_plan = direct_scene(manifest)
    # scene_plan is now available for builders to consume
"""

from .cinematic_presets import FAMILY_DEFAULTS, CAMERA_PRESETS, LIGHTING_PRESETS, ENVIRONMENT_PRESETS


# ═══════════════════════════════════════════════════════════════════════════
# Directorial Controls Mapping
# ═══════════════════════════════════════════════════════════════════════════
# Maps user-facing control values to internal preset/animation overrides.
# Priority: user control > prompt inference > family default

# motion_style -> animation_style override
_MOTION_STYLE_MAP: dict[str, str] = {
    "static":   "static_hero",
    "driving":  "vehicle_drive",
    "walking":  "character_walk",
    "dancing":  "character_dance",
    "drifting": "vehicle_drift",
}

# camera_style -> camera_preset override
_CAMERA_STYLE_MAP: dict[str, str] = {
    "orbit":    "low_orbit",
    "tracking": "hero_push_in",
    "follow":   "hero_push_in",
    "handheld": "cinematic_reveal",
    "reveal":   "cinematic_reveal",
}

# scene_dynamics -> composition overlay
_DYNAMICS_VOLUMETRIC: dict[str, str] = {
    "static":      "minimal",
    "subtle":      "subtle",
    "cinematic":   "medium",
    "high_energy": "heavy",
}

# character_behavior -> animation_style override (character families only)
_CHAR_BEHAVIOR_MAP: dict[str, str] = {
    "idle":    "static_hero",
    "walk":    "character_walk",
    "dance":   "character_dance",
    "perform": "character_performance",
}

# energy_level -> motion intensity multiplier (consumed by motion system)
_ENERGY_LEVEL_MAP: dict[str, float] = {
    "calm":      0.5,
    "cinematic": 1.0,
    "high":      1.5,
    "chaotic":   2.0,
}


def _apply_directorial_controls(manifest: dict, plan: dict) -> dict:
    """
    Apply user-guided directorial controls over the AI-inferred plan.

    Reads ``manifest["directorial_controls"]`` and overrides plan values
    where the user has expressed a preference.  Returns the mutated plan.
    """
    controls = manifest.get("directorial_controls")
    if not controls:
        return plan

    print(f"[DIRECTOR] applying user controls: {controls}", flush=True)

    # motion_style
    motion = controls.get("motion_style")
    if motion and motion in _MOTION_STYLE_MAP:
        plan["animation_style"] = _MOTION_STYLE_MAP[motion]
        plan["_motion_style"] = motion

    # camera_style
    cam = controls.get("camera_style")
    if cam and cam in _CAMERA_STYLE_MAP:
        preset_key = _CAMERA_STYLE_MAP[cam]
        if preset_key in CAMERA_PRESETS:
            plan["camera_preset"] = preset_key
        plan["_camera_style"] = cam

    # scene_dynamics
    dynamics = controls.get("scene_dynamics")
    if dynamics and dynamics in _DYNAMICS_VOLUMETRIC:
        plan.setdefault("composition", {})["volumetric_strength"] = _DYNAMICS_VOLUMETRIC[dynamics]
        plan["_scene_dynamics"] = dynamics

    # character_behavior
    char_beh = controls.get("character_behavior")
    if char_beh and char_beh in _CHAR_BEHAVIOR_MAP:
        plan["animation_style"] = _CHAR_BEHAVIOR_MAP[char_beh]
        plan["_character_behavior"] = char_beh

    # energy_level
    energy = controls.get("energy_level")
    if energy and energy in _ENERGY_LEVEL_MAP:
        plan["energy_multiplier"] = _ENERGY_LEVEL_MAP[energy]
        plan["_energy_level"] = energy

    return plan


# ═══════════════════════════════════════════════════════════════════════════
# Shot Grammar / Cinematic Intent
# ═══════════════════════════════════════════════════════════════════════════
# Each shot type describes *what the audience should feel*, not camera coords.
# The director maps shot types to concrete camera/lighting presets.

SHOT_TYPES: dict[str, dict] = {
    "establishing_wide": {
        "description": "Wide shot revealing the full environment and scale",
        "camera": "wide_establishing",
        "fill_factor": 0.82,
        "height_bias": 0.40,
        "composition_notes": "subject fills middle third, sky visible above, ground below",
    },
    "hero_reveal": {
        "description": "Medium shot that reveals the hero subject with cinematic weight",
        "camera": "cinematic_reveal",
        "fill_factor": 0.62,
        "height_bias": 0.50,
        "composition_notes": "subject centered, shallow DOF feel, slow reveal motion",
    },
    "low_angle_hero": {
        "description": "Low camera looking up at subject -- makes it imposing/powerful",
        "camera": "low_orbit",
        "fill_factor": 0.72,
        "height_bias": 0.38,
        "composition_notes": "camera below eye-line, subject dominates frame, minimal sky",
    },
    "environmental_push": {
        "description": "Push-in through environment toward subjects -- immersive",
        "camera": "hero_push_in",
        "fill_factor": 0.65,
        "height_bias": 0.45,
        "composition_notes": "foreground elements pass by camera, subjects grow in frame",
    },
    "product_macro_orbit": {
        "description": "Tight orbit around a product -- luxury/detail reveal",
        "camera": "cinematic_reveal",
        "fill_factor": 0.62,
        "height_bias": 0.50,
        "composition_notes": "product fills frame, soft studio background, slow orbit",
    },
    "underwater_reveal": {
        "description": "Slow drift through underwater scene with volumetric depth",
        "camera": "underwater_drift",
        "fill_factor": 0.88,
        "height_bias": 0.52,
        "composition_notes": "subjects emerge from haze, god-rays from above, blue depth",
    },
    "stage_performance": {
        "description": "Character performance on studio stage -- clean and focused",
        "camera": "stage_arc",
        "fill_factor": 0.58,
        "height_bias": 0.50,
        "composition_notes": "characters fill vertical frame, studio backdrop, rim lighting",
    },
}

# Family -> default shot type
_FAMILY_SHOT_TYPE: dict[str, str] = {
    "car_hero":          "low_angle_hero",
    "street_scene":      "environmental_push",
    "scenic_landscape":  "establishing_wide",
    "ocean_scene":       "underwater_reveal",
    "character_stage":   "stage_performance",
    "product_scene":     "product_macro_orbit",
}


def _infer_shot_type(manifest: dict, family: str) -> str:
    """Determine shot type from manifest hints or family defaults."""
    # Explicit shot_type in scene_plan takes priority
    scene_plan = manifest.get("scene_plan", {}) or {}
    explicit = scene_plan.get("shot_type")
    if explicit and explicit in SHOT_TYPES:
        return str(explicit)

    # Check debug_notes
    for note in (scene_plan.get("debug_notes", []) or []):
        note_str = str(note).lower()
        if note_str.startswith("shot_type="):
            val = note_str.split("=", 1)[1].strip()
            if val in SHOT_TYPES:
                return val

    return _FAMILY_SHOT_TYPE.get(family, "hero_reveal")


# ═══════════════════════════════════════════════════════════════════════════
# Family-aware composition hints
# ═══════════════════════════════════════════════════════════════════════════
# These hints tell builders HOW to compose their specific content.
# Not bpy calls -- pure data for builders to consume.

_FAMILY_COMPOSITION: dict[str, dict] = {
    "car_hero": {
        "grounding": "road",
        "subject_scale_feel": "imposing",
        "foreground_elements": False,
        "volumetric_strength": "subtle",
        "notes": "Car should feel road-grounded not podium-grounded. Low camera sells weight.",
    },
    "street_scene": {
        "grounding": "urban_road",
        "subject_scale_feel": "integrated",
        "foreground_elements": True,
        "volumetric_strength": "medium",
        "notes": "Characters must feel part of the city. Buildings wrap around, not float behind.",
    },
    "scenic_landscape": {
        "grounding": "terrain_blend",
        "subject_scale_feel": "epic",
        "foreground_elements": True,
        "volumetric_strength": "heavy",
        "notes": "Mountain blends into terrain via hillocks+fog. No visible flat base.",
    },
    "ocean_scene": {
        "grounding": "submerged",
        "subject_scale_feel": "majestic",
        "foreground_elements": False,
        "volumetric_strength": "heavy",
        "notes": "Subjects emerge from deep blue haze. Strong volumetric is essential.",
    },
    "character_stage": {
        "grounding": "studio_floor",
        "subject_scale_feel": "premium",
        "foreground_elements": False,
        "volumetric_strength": "subtle",
        "notes": "Clean studio feel. Infinity cove eliminates hard edges.",
    },
    "product_scene": {
        "grounding": "pedestal",
        "subject_scale_feel": "intimate",
        "foreground_elements": False,
        "volumetric_strength": "minimal",
        "notes": "Product is precious. Tight framing, soft studio light, no distractions.",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Family inference
# ═══════════════════════════════════════════════════════════════════════════

_TEMPLATE_TO_FAMILY: dict[str, str] = {
    "car_hero":          "car_hero",
    "street_scene":      "street_scene",
    "scenic_landscape":  "scenic_landscape",
    "ocean_scene":       "ocean_scene",
    "character_stage":   "character_stage",
    "product_scene":     "product_scene",
    "product_pedestal":  "product_scene",
    "city_loop":         "street_scene",
    "neon_news":         "street_scene",
}


def _infer_family(manifest: dict) -> str:
    """Determine scene family from template_name or manifest contents."""
    template = str(manifest.get("template_name", "")).lower()
    family = _TEMPLATE_TO_FAMILY.get(template)
    if family:
        return family

    # Fallback: inspect resolved assets to guess
    resolved = manifest.get("resolved_assets", {}) or {}
    models = resolved.get("models", {}) or {}

    if models.get("vehicles") or models.get("cars"):
        return "car_hero"
    if models.get("environments"):
        return "scenic_landscape"
    if models.get("characters"):
        # Check for ocean creatures
        chars = models.get("characters", []) or []
        species_set = set()
        for c in chars:
            sp = str(c.get("species", "")).lower()
            if sp:
                species_set.add(sp)
            for tag in (c.get("tags", []) or []):
                species_set.add(str(tag).lower())
        if species_set & {"whale", "shark", "fish", "dolphin", "turtle"}:
            return "ocean_scene"
        return "character_stage"
    if models.get("products"):
        return "product_scene"

    return "street_scene"


# ═══════════════════════════════════════════════════════════════════════════
# Animation style inference
# ═══════════════════════════════════════════════════════════════════════════

_FAMILY_DEFAULT_ANIMATION: dict[str, str] = {
    "car_hero":          "static_hero",
    "street_scene":      "character_performance",
    "scenic_landscape":  "static_establishing",
    "ocean_scene":       "swim_school",
    "character_stage":   "character_performance",
    "product_scene":     "product_turntable",
}


def _infer_animation_style(manifest: dict, family: str) -> str:
    """Pick animation style from manifest hints or family defaults."""
    # Explicit mode in manifest takes priority
    scene_plan = manifest.get("scene_plan", {}) or {}
    explicit = scene_plan.get("animation_mode")
    if explicit:
        return str(explicit)

    # Check animation_instructions for action hints
    instructions = manifest.get("animation_instructions", []) or []
    for inst in instructions:
        action = str(inst.get("action", "")).lower()
        if action in ("dance", "bounce", "sway", "talk"):
            return "character_performance"
        if action in ("rotate", "turntable", "spin"):
            return "product_turntable"
        if action in ("swim", "float", "glide"):
            return "swim_school"

    return _FAMILY_DEFAULT_ANIMATION.get(family, "idle")


# ═══════════════════════════════════════════════════════════════════════════
# Override injection (Part 7)
# ═══════════════════════════════════════════════════════════════════════════

def _build_overrides(manifest: dict, family: str) -> dict:
    """
    Inspect manifest for custom per-scene overrides.

    Sources checked (in order of priority):
      1. manifest["scene_plan"]["director_overrides"]  -- explicit dict
      2. manifest["scene_plan"]["debug_notes"]         -- string hints
    """
    overrides: dict = {}
    scene_plan = manifest.get("scene_plan", {}) or {}

    # Direct overrides dict
    director_ovr = scene_plan.get("director_overrides", {}) or {}
    if director_ovr:
        overrides.update(director_ovr)

    # Parse debug_notes for camera/lighting hints
    for note in (scene_plan.get("debug_notes", []) or []):
        note_str = str(note).lower()
        if note_str.startswith("camera_preset="):
            val = note_str.split("=", 1)[1].strip()
            if val in CAMERA_PRESETS:
                overrides["camera_preset"] = val
        elif note_str.startswith("lighting_preset="):
            val = note_str.split("=", 1)[1].strip()
            if val in LIGHTING_PRESETS:
                overrides["lighting_preset"] = val
        elif note_str.startswith("environment_preset="):
            val = note_str.split("=", 1)[1].strip()
            if val in ENVIRONMENT_PRESETS:
                overrides["environment_preset"] = val

    return overrides


# ═══════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════

def direct_scene(manifest: dict) -> dict:
    """
    Analyze manifest and return a structured scene_plan dict.

    The scene_plan is the single source of truth for how the scene should
    be built.  Builders read from it rather than re-parsing the manifest.

    Returns
    -------
    dict with keys:
        scene_family, camera_preset, lighting_preset, environment_preset,
        animation_style, overrides
    """
    family = _infer_family(manifest)
    defaults = FAMILY_DEFAULTS.get(family, {
        "camera": "cinematic_reveal",
        "lighting": "studio_five_point",
        "environment": "reflective_ground",
    })

    animation_style = _infer_animation_style(manifest, family)
    overrides = _build_overrides(manifest, family)

    shot_type = _infer_shot_type(manifest, family)
    shot_info = SHOT_TYPES.get(shot_type, {})
    composition = _FAMILY_COMPOSITION.get(family, {})

    # ── V1.3 Template System v2 overlay ────────────────────────────────
    # When the V1.3 dispatcher ran earlier in the pipeline it wrote
    # preset hints into manifest["scene_plan"].  Those hints take
    # precedence over FAMILY_DEFAULTS but NOT over user directorial
    # controls (which still win via `overrides.pop(...)` below).
    #
    # Precedence (top wins):
    #   1. overrides from manifest["directorial_controls"]  (user)
    #   2. v13 preset fields from manifest["scene_plan"]    (V1.3 recipe)
    #   3. shot_info / FAMILY_DEFAULTS                      (V1.1 family)
    v13 = manifest.get("scene_plan") or {}

    # Shot type can override camera preset if not already overridden
    camera_preset = overrides.pop(
        "camera_preset",
        v13.get("camera_preset")
            or shot_info.get("camera", defaults.get("camera", "cinematic_reveal")),
    )

    plan = {
        "scene_family":       family,
        "shot_type":          v13.get("shot_type") or shot_type,
        "camera_preset":      camera_preset,
        "lighting_preset":    overrides.pop(
                                 "lighting_preset",
                                 v13.get("lighting_preset")
                                     or defaults.get("lighting", "studio_five_point"),
                             ),
        "environment_preset": overrides.pop(
                                 "environment_preset",
                                 v13.get("environment_preset")
                                     or defaults.get("environment", "reflective_ground"),
                             ),
        "animation_style":    v13.get("animation_style") or animation_style,
        "post_preset":        v13.get("post_preset"),  # new passthrough for V1.3
        "composition":        composition,
        "shot_info":          shot_info,
        "overrides":          overrides,
        "energy_multiplier":  1.0,
    }

    # ── Apply user-guided directorial controls (highest priority) ──────
    plan = _apply_directorial_controls(manifest, plan)

    print(
        f"[DIRECTOR] scene_plan: family={plan['scene_family']} "
        f"shot={plan['shot_type']} cam={plan['camera_preset']} "
        f"light={plan['lighting_preset']} env={plan['environment_preset']} "
        f"anim={plan['animation_style']} energy={plan.get('energy_multiplier', 1.0)}",
        flush=True,
    )

    # V1.3 bridge visibility — fires only when the V1.3 executor actually
    # applied a real recipe (never for `_default`, never when flag is OFF).
    if manifest.get("_template_v2_applied"):
        print(
            f"[DIRECTOR] V1.3 scene_plan layered: "
            f"light='{plan['lighting_preset']}' "
            f"env='{plan['environment_preset']}' "
            f"cam='{plan['camera_preset']}' "
            f"post='{plan.get('post_preset')}' "
            f"recipe='{manifest.get('_template_v2_recipe')}'",
            flush=True,
        )

    return plan
