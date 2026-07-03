"""
Scene-quality middleware — keyword extraction + the pre-render guard.

The orchestrator's LLM is non-deterministic. It might forget to add lighting,
skip materials, or never tag the hero. Our existing template_v2 pipeline
guaranteed these as deterministic steps. We restore that guarantee as a
defensive layer that fires BEFORE every render call.

This module is intentionally NOT hardcoded for any specific prompt. It works
by inspecting scene state via the bridge and filling missing pieces using
defaults derived from the prompt's keywords.

Scalable: works for any prompt the user can imagine. No subject-specific code.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from ..mcp import registry


# ───────────────────────────────────────────────────────────────────────
# Color extraction
# ───────────────────────────────────────────────────────────────────────

# Common color names → linear-space RGB triples (0–1).
# Values picked to look correct under default 3-point lighting.
COLOR_MAP: Dict[str, List[float]] = {
    "red":      [0.85, 0.10, 0.10],
    "scarlet":  [0.90, 0.15, 0.15],
    "crimson":  [0.70, 0.05, 0.10],
    "orange":   [0.95, 0.45, 0.10],
    "amber":    [0.95, 0.65, 0.15],
    "yellow":   [0.95, 0.85, 0.10],
    "gold":     [0.95, 0.75, 0.20],
    "lime":     [0.65, 0.95, 0.20],
    "green":    [0.10, 0.65, 0.20],
    "emerald":  [0.05, 0.70, 0.30],
    "teal":     [0.10, 0.65, 0.65],
    "cyan":     [0.10, 0.85, 0.85],
    "blue":     [0.10, 0.30, 0.85],
    "azure":    [0.20, 0.55, 0.95],
    "navy":     [0.05, 0.15, 0.50],
    "indigo":   [0.30, 0.10, 0.70],
    "purple":   [0.55, 0.15, 0.75],
    "violet":   [0.50, 0.20, 0.80],
    "magenta":  [0.85, 0.10, 0.75],
    "pink":     [0.95, 0.45, 0.65],
    "rose":     [0.95, 0.30, 0.40],
    "white":    [0.92, 0.92, 0.92],
    "ivory":    [0.95, 0.95, 0.88],
    "black":    [0.05, 0.05, 0.05],
    "gray":     [0.50, 0.50, 0.50],
    "grey":     [0.50, 0.50, 0.50],
    "silver":   [0.78, 0.78, 0.82],
    "bronze":   [0.65, 0.40, 0.20],
    "copper":   [0.75, 0.45, 0.20],
    "brown":    [0.45, 0.30, 0.15],
    "tan":      [0.75, 0.60, 0.40],
    "beige":    [0.90, 0.85, 0.70],
    # Skin tones — used for human/character bipeds (auto-selected when prompt
    # mentions person/character and no explicit color was given)
    "skin":         [0.92, 0.78, 0.66],   # default (light-medium)
    "skin_light":   [0.96, 0.85, 0.75],
    "skin_medium":  [0.85, 0.65, 0.50],
    "skin_dark":    [0.50, 0.34, 0.24],
    "skin_deep":    [0.32, 0.20, 0.14],
    "peach":        [0.95, 0.78, 0.68],
}

# Material vibe → adjustments on top of the color.
# Roughness values bumped slightly from physically-accurate values so the BASE COLOR
# reads more clearly. Pure mirror metals reflect their environment so much that the
# color you set barely shows. We sacrifice realism slightly for readability.
MATERIAL_VIBES = {
    "metallic":  {"metallic": 1.0, "roughness": 0.40},
    "metal":     {"metallic": 1.0, "roughness": 0.40},
    "polished":  {"metallic": 1.0, "roughness": 0.20},   # was 0.05 — too mirror-like
    "brushed":   {"metallic": 1.0, "roughness": 0.55},
    "glass":     {"metallic": 0.0, "roughness": 0.10},
    "glossy":    {"metallic": 0.0, "roughness": 0.15},
    "matte":     {"metallic": 0.0, "roughness": 0.85},
    "rough":     {"metallic": 0.0, "roughness": 0.90},
    "ceramic":   {"metallic": 0.0, "roughness": 0.35},
    "plastic":   {"metallic": 0.0, "roughness": 0.45},
    "rubber":    {"metallic": 0.0, "roughness": 0.80},
    "fuzzy":     {"metallic": 0.0, "roughness": 1.00},
    "wood":      {"metallic": 0.0, "roughness": 0.70},
    "stone":     {"metallic": 0.0, "roughness": 0.85},
    "fabric":    {"metallic": 0.0, "roughness": 0.95},
}

EMISSIVE_KEYWORDS = ("glowing", "glow", "neon", "emissive", "luminous", "bright", "radiant")


# Mood / time-of-day → lighting color temperature
LIGHTING_MOOD = {
    # Studio/neutral defaults — bumped from 1500 to 2500 so subjects render bright enough
    # to read their material/color clearly. Previous values left brushed/matte surfaces dim.
    "neutral":     {"color_temp": "neutral", "key_energy": 2500, "fill_energy": 900, "rim_energy": 1200},
    "studio":      {"color_temp": "neutral", "key_energy": 2500, "fill_energy": 900, "rim_energy": 1200},
    # Time-of-day
    "sunset":      {"color_temp": "warm", "key_energy": 2200, "fill_energy": 800, "rim_energy": 1400},
    "sunrise":     {"color_temp": "warm", "key_energy": 2000, "fill_energy": 700, "rim_energy": 1300},
    "golden hour": {"color_temp": "warm", "key_energy": 2400, "fill_energy": 800, "rim_energy": 1400},
    "dawn":        {"color_temp": "warm", "key_energy": 1800, "fill_energy": 700, "rim_energy": 1100},
    "dusk":        {"color_temp": "warm", "key_energy": 1800, "fill_energy": 700, "rim_energy": 1100},
    "noon":        {"color_temp": "neutral", "key_energy": 3200, "fill_energy": 1400, "rim_energy": 900},
    "daylight":    {"color_temp": "neutral", "key_energy": 2800, "fill_energy": 1200, "rim_energy": 1000},
    # Low-light moods — kept dim intentionally, rim light boosted so subject reads against dark BG
    "night":       {"color_temp": "cool", "key_energy": 800,  "fill_energy": 300, "rim_energy": 1400},
    "moonlight":   {"color_temp": "cool", "key_energy": 700,  "fill_energy": 250, "rim_energy": 1300},
    "moody":       {"color_temp": "cool", "key_energy": 1100, "fill_energy": 300, "rim_energy": 1500},
    "dark":        {"color_temp": "cool", "key_energy": 800,  "fill_energy": 250, "rim_energy": 1200},
    # Stylized
    "dramatic":    {"color_temp": "warm", "key_energy": 2800, "fill_energy": 400, "rim_energy": 1800},
    "bright":      {"color_temp": "neutral", "key_energy": 3500, "fill_energy": 1800, "rim_energy": 1200},
}


def _word_in(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def infer_material_from_prompt(prompt: str) -> Dict[str, Any]:
    """Return PrincipledBSDF params derived from the user's prompt.

    First color word matched is used. First material vibe matched is layered on.
    'Glowing' / 'neon' etc trigger an emission color = same as base color.
    """
    p = prompt.lower()

    # Color
    color: Optional[List[float]] = None
    color_name = None
    for name, rgb in COLOR_MAP.items():
        if _word_in(p, name):
            color = rgb
            color_name = name
            break
    if color is None:
        color = [0.65, 0.65, 0.70]  # neutral default
        color_name = "neutral"

    # Vibe
    metallic, roughness = 0.0, 0.55
    vibe_name = None
    for vibe, props in MATERIAL_VIBES.items():
        if _word_in(p, vibe):
            metallic = props.get("metallic", metallic)
            roughness = props.get("roughness", roughness)
            vibe_name = vibe
            break

    # Emission
    emission_strength = 0.0
    emission_color = None
    if any(_word_in(p, kw) for kw in EMISSIVE_KEYWORDS):
        emission_strength = 4.0
        emission_color = color

    return {
        "_meta": {"color_word": color_name, "vibe_word": vibe_name},
        "color": color + [1.0],  # RGBA
        "metallic": metallic,
        "roughness": roughness,
        "emission_color": emission_color,
        "emission_strength": emission_strength,
    }


def infer_lighting_from_prompt(prompt: str) -> Dict[str, Any]:
    """Return apply_three_point_lighting params derived from prompt mood/time keywords."""
    p = prompt.lower()
    for mood, params in LIGHTING_MOOD.items():
        if _word_in(p, mood):
            return {"_meta": {"mood": mood}, **params}
    # Default — neutral studio
    return {
        "_meta": {"mood": "default"},
        "color_temp": "neutral",
        "key_energy": 1500,
        "fill_energy": 500,
        "rim_energy": 800,
    }


# ───────────────────────────────────────────────────────────────────────
# Pre-render guard — the quality floor
# ───────────────────────────────────────────────────────────────────────

def run_pre_render_guard(prompt: str, verbose: bool = True) -> Dict[str, Any]:
    """Inspect the scene and inject defaults for anything the LLM forgot.

    Called by the orchestrator immediately before any render_frame /
    render_animation tool call. Returns a report of what was injected.

    This is the bridge between the LLM's creative freedom and our deterministic
    quality floor. Mirrors the old pipeline's guarantees from cinematic_lighting,
    cinematic_presets, and template_v2 lighting layers.
    """
    report: Dict[str, Any] = {
        "fired": False,
        "actions": [],
        "material_inferred": None,
        "lighting_inferred": None,
    }

    try:
        scene = registry.call("get_scene_info")
        objects = registry.call("list_objects")
    except Exception as e:
        report["error"] = f"scene introspection failed: {e}"
        return report

    if not isinstance(objects, list):
        objects = []

    meshes  = [o for o in objects if o.get("type") == "MESH"]
    lights  = [o for o in objects if o.get("type") == "LIGHT"]
    cameras = [o for o in objects if o.get("type") == "CAMERA"]

    # ── 1. Camera guarantee
    if not scene.get("active_camera"):
        try:
            target = meshes[0]["location"] if meshes else [0, 0, 1]
            registry.call("create_camera", {"name": "AutoCam", "location": [6, -6, 4]})
            registry.call("look_at", {"object": "AutoCam", "target": target})
            report["actions"].append("created AutoCam at [6,-6,4] looking at hero")
            report["fired"] = True
        except Exception as e:
            report["actions"].append(f"camera inject failed: {e}")

    # ── 2. Lighting guarantee
    if len(lights) == 0:
        light_params = infer_lighting_from_prompt(prompt)
        light_meta = light_params.pop("_meta", {})
        # Aim lights at the first mesh's location, fallback to origin
        target = meshes[0]["location"] if meshes else [0, 0, 1]
        try:
            registry.call("apply_three_point_lighting", {"target": target, **light_params})
            report["actions"].append(
                f"applied 3-point lighting at {target} (mood='{light_meta.get('mood')}', "
                f"temp={light_params.get('color_temp')}, key={light_params.get('key_energy')}W)"
            )
            report["lighting_inferred"] = light_meta
            report["fired"] = True
        except Exception as e:
            report["actions"].append(f"lighting inject failed: {e}")

    # ── 3. Material guarantee — apply default to any mesh that has empty slots
    material_params = None
    for mesh in meshes:
        try:
            info = registry.call("get_object_info", {"name": mesh["name"]})
        except Exception:
            continue
        slots = info.get("material_slots", []) or []
        has_material = any(s for s in slots if s)  # None / "" both falsy
        if has_material:
            continue
        # Lazy-compute inferred material once per call
        if material_params is None:
            material_params = infer_material_from_prompt(prompt)
        mp = dict(material_params)
        meta = mp.pop("_meta", {})
        mat_name = f"AutoMat_{mesh['name']}"
        try:
            registry.call("create_material", {"name": mat_name, **mp})
            registry.call("apply_material", {"object": mesh["name"], "material": mat_name})
            report["actions"].append(
                f"applied default material '{mat_name}' to '{mesh['name']}' "
                f"(color='{meta.get('color_word')}', vibe='{meta.get('vibe_word')}')"
            )
            report["material_inferred"] = meta
            report["fired"] = True
        except Exception as e:
            report["actions"].append(f"material inject for '{mesh['name']}' failed: {e}")

    if verbose and report["fired"]:
        print(f"[pre-render guard] fired ({len(report['actions'])} action(s)):")
        for a in report["actions"]:
            print(f"   • {a}")
    elif verbose:
        print("[pre-render guard] scene already complete — no injections needed")

    return report
