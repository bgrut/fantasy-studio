from __future__ import annotations

"""
ai_director.py
==============
The AI cinematic director.

Given a structured scene plan + the available asset capabilities, this
module asks the local LLM to produce a complete directorial manifest:
camera, animation, atmosphere, lighting, composition. The manifest is
pure data — builders read from it instead of falling back to hardcoded
defaults.

If the LLM is unavailable or returns malformed JSON, ``direct_scene()``
returns a hardcoded "sane defaults" manifest derived from the scene
family so the pipeline keeps working.
"""

from typing import Any

from .llm_service import structured_query, is_available


# ═══════════════════════════════════════════════════════════════════════════
# Schema describing the directorial manifest the LLM should produce
# ═══════════════════════════════════════════════════════════════════════════

DIRECTORIAL_SCHEMA: dict = {
    "camera": {
        "style": "tracking|orbit|follow|reveal|handheld|static_low|dolly_in|arc",
        "angle": "low|eye_level|high|birds_eye",
        "focal_length_mm": 35,
        "depth_of_field": True,
        "dof_fstop": 2.8,
        "movement_speed": "slow|moderate|fast",
    },
    "animation": {
        "subject_behavior": "idle|walking|running|driving|drifting|dancing|swimming|floating|turntable",
        "subject_speed": 0.5,
        "secondary_motion": True,
        "motion_style": "smooth|energetic|dramatic|subtle",
    },
    "atmosphere": {
        "fog_density": 0.02,
        "fog_color_warmth": 0.6,
        "volume_scatter": True,
        "bloom_intensity": 0.3,
        "color_temperature": "warm|neutral|cool",
        "contrast": "low|medium|high",
    },
    "lighting": {
        "hdri_search_query": "sunset dramatic sky",
        "key_light_intensity": 1.0,
        "rim_light": True,
        "ambient_intensity": 0.3,
    },
    "composition": {
        "subject_screen_position": "center|left_third|right_third",
        "foreground_elements": True,
        "depth_layers": 3,
        "ground_integration": "contact_shadow|reflection|grounded_plane",
    },
}


_DIRECTOR_SYSTEM = (
    "You are a world-class cinematic director for a 3D animation engine. "
    "You make camera, animation, lighting, and atmosphere decisions like "
    "a film DP would. Decisions must serve the subject and mood. "
    "Pick values that produce visually distinct, premium cinematic shots — "
    "never bland defaults. Return decisions as JSON only."
)


# ═══════════════════════════════════════════════════════════════════════════
# Hardcoded fallback manifests by scene family
# ═══════════════════════════════════════════════════════════════════════════

_FAMILY_DEFAULTS: dict[str, dict] = {
    "car_hero": {
        "camera": {
            "style": "tracking",
            "angle": "low",
            "focal_length_mm": 50,
            "depth_of_field": True,
            "dof_fstop": 2.8,
            "movement_speed": "moderate",
        },
        "animation": {
            "subject_behavior": "driving",
            "subject_speed": 1.0,
            "secondary_motion": True,
            "motion_style": "dramatic",
        },
        "atmosphere": {
            "fog_density": 0.015,
            "fog_color_warmth": 0.5,
            "volume_scatter": True,
            "bloom_intensity": 0.35,
            "color_temperature": "warm",
            "contrast": "high",
        },
        "lighting": {
            "hdri_search_query": "sunset highway dramatic",
            "key_light_intensity": 1.2,
            "rim_light": True,
            "ambient_intensity": 0.25,
        },
        "composition": {
            "subject_screen_position": "center",
            "foreground_elements": True,
            "depth_layers": 4,
            "ground_integration": "reflection",
        },
    },
    "street_scene": {
        "camera": {
            "style": "tracking",
            "angle": "eye_level",
            "focal_length_mm": 40,
            "depth_of_field": True,
            "dof_fstop": 2.0,
            "movement_speed": "moderate",
        },
        "animation": {
            "subject_behavior": "walking",
            "subject_speed": 0.7,
            "secondary_motion": True,
            "motion_style": "smooth",
        },
        "atmosphere": {
            "fog_density": 0.025,
            "fog_color_warmth": 0.4,
            "volume_scatter": True,
            "bloom_intensity": 0.4,
            "color_temperature": "cool",
            "contrast": "high",
        },
        "lighting": {
            "hdri_search_query": "neon city night",
            "key_light_intensity": 1.0,
            "rim_light": True,
            "ambient_intensity": 0.3,
        },
        "composition": {
            "subject_screen_position": "center",
            "foreground_elements": True,
            "depth_layers": 4,
            "ground_integration": "contact_shadow",
        },
    },
    "scenic_landscape": {
        "camera": {
            "style": "reveal",
            "angle": "high",
            "focal_length_mm": 35,
            "depth_of_field": False,
            "dof_fstop": 8.0,
            "movement_speed": "slow",
        },
        "animation": {
            "subject_behavior": "floating",
            "subject_speed": 0.0,
            "secondary_motion": False,
            "motion_style": "smooth",
        },
        "atmosphere": {
            "fog_density": 0.012,
            "fog_color_warmth": 0.7,
            "volume_scatter": True,
            "bloom_intensity": 0.25,
            "color_temperature": "warm",
            "contrast": "medium",
        },
        "lighting": {
            "hdri_search_query": "golden hour mountain sky",
            "key_light_intensity": 1.5,
            "rim_light": True,
            "ambient_intensity": 0.4,
        },
        "composition": {
            "subject_screen_position": "center",
            "foreground_elements": True,
            "depth_layers": 5,
            "ground_integration": "grounded_plane",
        },
    },
    "ocean_scene": {
        "camera": {
            "style": "follow",
            "angle": "eye_level",
            "focal_length_mm": 35,
            "depth_of_field": True,
            "dof_fstop": 4.0,
            "movement_speed": "slow",
        },
        "animation": {
            "subject_behavior": "swimming",
            "subject_speed": 0.6,
            "secondary_motion": True,
            "motion_style": "smooth",
        },
        "atmosphere": {
            "fog_density": 0.020,
            "fog_color_warmth": 0.3,
            "volume_scatter": True,
            "bloom_intensity": 0.35,
            "color_temperature": "cool",
            "contrast": "medium",
        },
        "lighting": {
            "hdri_search_query": "underwater caustics blue",
            "key_light_intensity": 1.1,
            "rim_light": True,
            "ambient_intensity": 0.4,
        },
        "composition": {
            "subject_screen_position": "center",
            "foreground_elements": True,
            "depth_layers": 3,
            "ground_integration": "grounded_plane",
        },
    },
    "character_stage": {
        "camera": {
            "style": "arc",
            "angle": "eye_level",
            "focal_length_mm": 50,
            "depth_of_field": True,
            "dof_fstop": 2.0,
            "movement_speed": "slow",
        },
        "animation": {
            "subject_behavior": "dancing",
            "subject_speed": 1.0,
            "secondary_motion": True,
            "motion_style": "energetic",
        },
        "atmosphere": {
            "fog_density": 0.008,
            "fog_color_warmth": 0.5,
            "volume_scatter": False,
            "bloom_intensity": 0.45,
            "color_temperature": "neutral",
            "contrast": "high",
        },
        "lighting": {
            "hdri_search_query": "studio softbox five point",
            "key_light_intensity": 1.3,
            "rim_light": True,
            "ambient_intensity": 0.2,
        },
        "composition": {
            "subject_screen_position": "center",
            "foreground_elements": False,
            "depth_layers": 2,
            "ground_integration": "reflection",
        },
    },
    "product_scene": {
        "camera": {
            "style": "orbit",
            "angle": "eye_level",
            "focal_length_mm": 85,
            "depth_of_field": True,
            "dof_fstop": 4.0,
            "movement_speed": "slow",
        },
        "animation": {
            "subject_behavior": "turntable",
            "subject_speed": 0.5,
            "secondary_motion": False,
            "motion_style": "smooth",
        },
        "atmosphere": {
            "fog_density": 0.005,
            "fog_color_warmth": 0.5,
            "volume_scatter": False,
            "bloom_intensity": 0.5,
            "color_temperature": "neutral",
            "contrast": "medium",
        },
        "lighting": {
            "hdri_search_query": "studio luxury softbox",
            "key_light_intensity": 1.4,
            "rim_light": True,
            "ambient_intensity": 0.3,
        },
        "composition": {
            "subject_screen_position": "center",
            "foreground_elements": False,
            "depth_layers": 2,
            "ground_integration": "reflection",
        },
    },
}


def _fallback_manifest(scene_plan: dict) -> dict:
    """Return a hardcoded directorial manifest matching the scene family."""
    family = (
        scene_plan.get("template_family")
        or scene_plan.get("scene_family")
        or "scenic_landscape"
    )
    base = _FAMILY_DEFAULTS.get(family) or _FAMILY_DEFAULTS["scenic_landscape"]
    # Deep copy via re-construction so callers can mutate freely
    return {k: dict(v) for k, v in base.items()}


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def direct_scene(scene_plan: dict, asset_capabilities: dict | None = None) -> dict:
    """
    Produce a directorial manifest from a scene plan.

    Parameters
    ----------
    scene_plan : dict
        Output of the scene planner. Should contain at least:
        - subject / focal_subject
        - template_family / scene_family
        - mood / energy_level (optional)
        - environment / time_of_day / weather (optional)
    asset_capabilities : dict, optional
        Information about what motion the resolved asset supports — e.g.
        ``{"has_armature": True, "has_actions": ["walk", "idle"]}``.
        The director uses this so it doesn't request behaviors the asset
        physically can't perform.

    Returns
    -------
    dict
        A complete directorial manifest. Always returns a usable manifest
        — falls back to hardcoded family defaults if the LLM is offline
        or returns invalid JSON.
    """
    if not is_available():
        manifest = _fallback_manifest(scene_plan)
        manifest["_source"] = "fallback_no_llm"
        return manifest

    # Assemble user prompt with all context
    family = scene_plan.get("template_family") or scene_plan.get("scene_family") or ""
    subject = scene_plan.get("subject") or scene_plan.get("focal_subject") or "subject"
    action = scene_plan.get("action") or scene_plan.get("animation_mode") or ""
    environment = scene_plan.get("environment") or ""
    mood = scene_plan.get("mood") or ""
    tod = scene_plan.get("time_of_day") or ""
    weather = scene_plan.get("weather") or ""
    energy = scene_plan.get("energy_level") or ""

    caps_str = ""
    if asset_capabilities:
        caps_str = f"\nAvailable asset capabilities: {asset_capabilities}"

    user_prompt = (
        f"Direct a single 6-second cinematic shot.\n"
        f"Scene family: {family}\n"
        f"Subject: {subject}\n"
        f"Subject action: {action}\n"
        f"Environment: {environment}\n"
        f"Mood: {mood}\n"
        f"Time of day: {tod}\n"
        f"Weather: {weather}\n"
        f"Energy level: {energy}{caps_str}\n\n"
        f"Decide every directorial parameter to produce a premium cinematic shot."
    )

    parsed = structured_query(
        _DIRECTOR_SYSTEM,
        user_prompt,
        schema=DIRECTORIAL_SCHEMA,
    )

    if not parsed:
        manifest = _fallback_manifest(scene_plan)
        manifest["_source"] = "fallback_llm_failed"
        return manifest

    # Merge LLM output into the family default to fill any missing keys
    base = _fallback_manifest(scene_plan)
    for top_key, top_value in parsed.items():
        if isinstance(top_value, dict) and top_key in base:
            base[top_key].update(top_value)
        else:
            base[top_key] = top_value
    base["_source"] = "llm"
    print(
        f"[DIRECTOR] manifest produced for family={family} | "
        f"camera_style={base['camera'].get('style')} | "
        f"behavior={base['animation'].get('subject_behavior')}",
        flush=True,
    )
    return base


# ═══════════════════════════════════════════════════════════════════════════
# Helper: project directorial manifest onto scene_plan controls
# ═══════════════════════════════════════════════════════════════════════════

_BEHAVIOR_TO_MOTION_STYLE = {
    "idle":      "static",
    "walking":   "walking",
    "running":   "walking",
    "driving":   "driving",
    "drifting":  "drifting",
    "dancing":   "dancing",
    "swimming":  "static",
    "floating":  "static",
    "turntable": "static",
}

_DIRECTOR_CAMERA_TO_STYLE = {
    "tracking":   "tracking",
    "follow":     "follow",
    "orbit":      "orbit",
    "reveal":     "reveal",
    "handheld":   "handheld",
    "static_low": "orbit",
    "dolly_in":   "tracking",
    "arc":        "orbit",
}

_MOVEMENT_SPEED_TO_ENERGY = {
    "slow":     "calm",
    "moderate": "cinematic",
    "fast":     "high",
}


def project_to_directorial_controls(manifest: dict) -> dict:
    """
    Convert a directorial manifest (from direct_scene) into the directorial
    controls format the existing scene_director / behavior layer consumes:
        motion_style, camera_style, energy_level, character_behavior
    This is the bridge between the LLM-driven director and the legacy
    builder pipeline.
    """
    cam = manifest.get("camera") or {}
    anim = manifest.get("animation") or {}

    behavior = (anim.get("subject_behavior") or "").lower()
    cam_style = (cam.get("style") or "").lower()
    movement_speed = (cam.get("movement_speed") or "").lower()

    return {
        "motion_style":   _BEHAVIOR_TO_MOTION_STYLE.get(behavior),
        "character_behavior": behavior if behavior in ("idle", "walking", "dancing") else None,
        "camera_style":   _DIRECTOR_CAMERA_TO_STYLE.get(cam_style),
        "energy_level":   _MOVEMENT_SPEED_TO_ENERGY.get(movement_speed, "cinematic"),
    }
