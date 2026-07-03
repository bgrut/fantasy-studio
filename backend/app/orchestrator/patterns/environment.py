"""
Environment pattern — sky color + ground material + atmospheric tone.

Not a "subject" pattern. The composer calls this in PARALLEL with the subject
pattern to populate the world around the hero. Returns a dict of environment
settings (sky color, ground material params, mood mods) that the composer
applies via set_world_background / create_material / apply_material.

Why a pattern, not just a hardcoded function:
    Same architecture as subject patterns — adding a new mood (jungle, space,
    underwater) is a new entry in MOOD_ENV_PRESETS. Scales without code changes
    in composer.
"""

from typing import Any, Dict


# Each mood → world background color + ground material + atmospheric tweaks
MOOD_ENV_PRESETS: Dict[str, Dict[str, Any]] = {
    "neutral": {
        "sky_color":     [0.05, 0.05, 0.07, 1.0],
        "sky_strength":  1.0,
        "ground_color":  [0.20, 0.20, 0.22, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.85,
    },
    "sunset": {
        "sky_color":     [0.55, 0.25, 0.15, 1.0],   # warm orange horizon
        "sky_strength":  1.5,
        "ground_color":  [0.40, 0.25, 0.15, 1.0],   # warm earth
        "ground_metallic": 0.0,
        "ground_roughness": 0.85,
    },
    "sunrise": {
        "sky_color":     [0.60, 0.40, 0.30, 1.0],
        "sky_strength":  1.3,
        "ground_color":  [0.30, 0.25, 0.22, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.85,
    },
    "golden hour": {
        "sky_color":     [0.55, 0.35, 0.20, 1.0],
        "sky_strength":  1.6,
        "ground_color":  [0.40, 0.30, 0.18, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.80,
    },
    "dawn": {
        "sky_color":     [0.35, 0.30, 0.40, 1.0],
        "sky_strength":  0.9,
        "ground_color":  [0.20, 0.18, 0.22, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.85,
    },
    "dusk": {
        "sky_color":     [0.35, 0.25, 0.40, 1.0],
        "sky_strength":  0.9,
        "ground_color":  [0.20, 0.18, 0.22, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.85,
    },
    "noon": {
        "sky_color":     [0.45, 0.65, 0.95, 1.0],   # bright blue sky
        "sky_strength":  2.0,
        "ground_color":  [0.45, 0.50, 0.30, 1.0],   # grass-ish green
        "ground_metallic": 0.0,
        "ground_roughness": 0.80,
    },
    "daylight": {
        "sky_color":     [0.40, 0.60, 0.90, 1.0],
        "sky_strength":  1.8,
        "ground_color":  [0.40, 0.45, 0.28, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.80,
    },
    "night": {
        "sky_color":     [0.02, 0.03, 0.06, 1.0],
        "sky_strength":  0.3,
        "ground_color":  [0.05, 0.05, 0.08, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.90,
    },
    "moonlight": {
        "sky_color":     [0.05, 0.07, 0.15, 1.0],
        "sky_strength":  0.4,
        "ground_color":  [0.10, 0.10, 0.14, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.85,
    },
    "moody": {
        "sky_color":     [0.04, 0.04, 0.08, 1.0],
        "sky_strength":  0.5,
        "ground_color":  [0.08, 0.08, 0.10, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.85,
    },
    "dramatic": {
        "sky_color":     [0.15, 0.08, 0.10, 1.0],
        "sky_strength":  0.8,
        "ground_color":  [0.15, 0.10, 0.10, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.85,
    },
    "dark": {
        "sky_color":     [0.03, 0.03, 0.05, 1.0],
        "sky_strength":  0.4,
        "ground_color":  [0.06, 0.06, 0.08, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.90,
    },
    "bright": {
        "sky_color":     [0.65, 0.78, 0.95, 1.0],
        "sky_strength":  2.5,
        "ground_color":  [0.65, 0.65, 0.60, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.75,
    },
    "studio": {
        "sky_color":     [0.08, 0.08, 0.10, 1.0],
        "sky_strength":  1.2,
        "ground_color":  [0.15, 0.15, 0.18, 1.0],
        "ground_metallic": 0.0,
        "ground_roughness": 0.50,
    },
}


def env_for_mood(mood: str) -> Dict[str, Any]:
    """Return environment params for a mood. Falls back to neutral."""
    return dict(MOOD_ENV_PRESETS.get(mood, MOOD_ENV_PRESETS["neutral"]))


# Mood → HDRI filename mapping. The composer looks for these files in
# backend/assets/hdri/. If a file is missing, we fall back to the flat
# sky color from MOOD_ENV_PRESETS. Files can be added incrementally —
# the system never breaks if they're absent.
#
# Recommended free HDRIs (Poly Haven, CC0):
#   sunset:    venice_sunset.hdr
#   noon:      kloppenheim_06.hdr
#   night:     moonlit_golf.hdr
#   studio:    studio_small_09.hdr
#   golden hour: golden_gate_hills.hdr
#   moonlight: moonlit_golf.hdr
MOOD_HDRI_MAP = {
    "sunset":      "venice_sunset.hdr",
    "sunrise":     "venice_sunset.hdr",
    "golden hour": "golden_gate_hills.hdr",
    "dusk":        "venice_sunset.hdr",
    "dawn":        "kloppenheim_06.hdr",
    "noon":        "kloppenheim_06.hdr",
    "daylight":    "kloppenheim_06.hdr",
    "night":       "moonlit_golf.hdr",
    "moonlight":   "moonlit_golf.hdr",
    "studio":      "studio_small_09.hdr",
    "bright":      "kloppenheim_06.hdr",
    "moody":       "moonlit_golf.hdr",
}


# ════════════════════════════════════════════════════════════════════════
# Phase 19 — SETTING-driven cinematic environments
#
# A "setting" is WHERE the scene is (place), distinct from "mood" (light/time).
# Each setting is a full bundle the composer realizes via execute_python:
#   ground : a procedural material kind + base color + roughness
#   sky    : vertical gradient (zenith→horizon) + strength
#   sun    : a directional sun light (elevation, azimuth, color, energy)
#   fog    : volumetric world mist density + color (cinematic depth)
#
# `ground.kind` values map to procedural node setups in the composer builder:
#   smooth | grass | sand | concrete | wood | snow | rock | water | void | tiles
# ════════════════════════════════════════════════════════════════════════

ENVIRONMENT_SPECS: Dict[str, Dict[str, Any]] = {
    "studio": {
        "ground": {"kind": "smooth", "color": [0.20, 0.20, 0.22], "roughness": 0.45},
        "sky":    {"zenith": [0.05, 0.05, 0.06], "horizon": [0.14, 0.14, 0.16], "strength": 1.0},
        "sun":    {"elevation": 55, "azimuth": 35, "color": [1.0, 0.98, 0.95], "energy": 3.0},
        "fog":    {"density": 0.0, "color": [0.1, 0.1, 0.12]},
        "hdri_mood_ok": True,   # studio HDRI looks great here
    },
    "grassland": {
        "ground": {"kind": "grass", "color": [0.17, 0.32, 0.10], "roughness": 0.95},
        "sky":    {"zenith": [0.18, 0.40, 0.78], "horizon": [0.72, 0.82, 0.93], "strength": 1.7},
        "sun":    {"elevation": 50, "azimuth": 40, "color": [1.0, 0.97, 0.88], "energy": 4.5},
        "fog":    {"density": 0.004, "color": [0.75, 0.83, 0.92]},
    },
    "forest": {
        "ground": {"kind": "grass", "color": [0.12, 0.20, 0.08], "roughness": 0.95},
        "sky":    {"zenith": [0.10, 0.22, 0.30], "horizon": [0.35, 0.45, 0.40], "strength": 1.1},
        "sun":    {"elevation": 62, "azimuth": 25, "color": [0.95, 1.0, 0.85], "energy": 3.5},
        "fog":    {"density": 0.012, "color": [0.55, 0.65, 0.55]},
    },
    "beach": {
        "ground": {"kind": "sand", "color": [0.78, 0.70, 0.52], "roughness": 0.9},
        "sky":    {"zenith": [0.25, 0.50, 0.85], "horizon": [0.85, 0.88, 0.90], "strength": 2.0},
        "sun":    {"elevation": 45, "azimuth": 50, "color": [1.0, 0.96, 0.85], "energy": 5.0},
        "fog":    {"density": 0.006, "color": [0.85, 0.88, 0.92]},
    },
    "desert": {
        "ground": {"kind": "sand", "color": [0.80, 0.62, 0.38], "roughness": 0.92},
        "sky":    {"zenith": [0.30, 0.50, 0.80], "horizon": [0.92, 0.82, 0.65], "strength": 2.2},
        "sun":    {"elevation": 60, "azimuth": 30, "color": [1.0, 0.93, 0.78], "energy": 5.5},
        "fog":    {"density": 0.003, "color": [0.9, 0.82, 0.68]},
    },
    "snow": {
        "ground": {"kind": "snow", "color": [0.90, 0.93, 0.98], "roughness": 0.6},
        "sky":    {"zenith": [0.55, 0.62, 0.75], "horizon": [0.85, 0.88, 0.93], "strength": 1.8},
        "sun":    {"elevation": 35, "azimuth": 45, "color": [0.92, 0.95, 1.0], "energy": 4.0},
        "fog":    {"density": 0.010, "color": [0.88, 0.92, 0.97]},
    },
    "street": {
        "ground": {"kind": "concrete", "color": [0.16, 0.16, 0.17], "roughness": 0.7},
        "sky":    {"zenith": [0.20, 0.30, 0.45], "horizon": [0.55, 0.58, 0.62], "strength": 1.3},
        "sun":    {"elevation": 48, "azimuth": 60, "color": [1.0, 0.97, 0.92], "energy": 3.8},
        "fog":    {"density": 0.006, "color": [0.6, 0.62, 0.68]},
    },
    "interior": {
        "ground": {"kind": "wood", "color": [0.32, 0.20, 0.11], "roughness": 0.4},
        "sky":    {"zenith": [0.10, 0.10, 0.12], "horizon": [0.22, 0.20, 0.18], "strength": 0.8},
        "sun":    {"elevation": 40, "azimuth": 20, "color": [1.0, 0.92, 0.80], "energy": 2.5},
        "fog":    {"density": 0.0, "color": [0.1, 0.1, 0.1]},
    },
    "mountain": {
        "ground": {"kind": "rock", "color": [0.28, 0.27, 0.26], "roughness": 0.9},
        "sky":    {"zenith": [0.15, 0.35, 0.70], "horizon": [0.70, 0.78, 0.88], "strength": 1.9},
        "sun":    {"elevation": 42, "azimuth": 35, "color": [1.0, 0.97, 0.9], "energy": 4.8},
        "fog":    {"density": 0.014, "color": [0.7, 0.76, 0.85]},
    },
    "space": {
        "ground": {"kind": "void", "color": [0.02, 0.02, 0.03], "roughness": 1.0},
        "sky":    {"zenith": [0.00, 0.00, 0.01], "horizon": [0.02, 0.02, 0.05], "strength": 0.4},
        "sun":    {"elevation": 30, "azimuth": 60, "color": [1.0, 1.0, 1.0], "energy": 6.0},
        "fog":    {"density": 0.0, "color": [0.0, 0.0, 0.0]},
        "starfield": True,
    },
    "underwater": {
        "ground": {"kind": "sand", "color": [0.20, 0.35, 0.38], "roughness": 0.9},
        "sky":    {"zenith": [0.02, 0.18, 0.28], "horizon": [0.05, 0.30, 0.40], "strength": 0.9},
        "sun":    {"elevation": 70, "azimuth": 20, "color": [0.6, 0.85, 0.95], "energy": 2.5},
        "fog":    {"density": 0.06, "color": [0.10, 0.35, 0.45]},   # heavy blue murk
    },
    "night_city": {
        "ground": {"kind": "concrete", "color": [0.08, 0.08, 0.10], "roughness": 0.45},  # wet asphalt sheen
        "sky":    {"zenith": [0.02, 0.02, 0.06], "horizon": [0.12, 0.08, 0.18], "strength": 0.6},
        "sun":    {"elevation": 25, "azimuth": 50, "color": [0.5, 0.55, 0.9], "energy": 1.2},
        "fog":    {"density": 0.02, "color": [0.15, 0.12, 0.25]},
        "neon": True,
    },
}


# Mood → how to nudge the sun + sky of any setting (time-of-day on top of place).
# Multipliers/offsets applied to the setting's base sun/sky.
MOOD_MODIFIERS: Dict[str, Dict[str, Any]] = {
    "neutral":     {"sun_energy": 1.0, "sun_warm": 0.0,  "sun_elev": 0,   "sky_strength": 1.0, "exposure": 0.0},
    "noon":        {"sun_energy": 1.2, "sun_warm": -0.05, "sun_elev": +20, "sky_strength": 1.15, "exposure": 0.1},
    "daylight":    {"sun_energy": 1.1, "sun_warm": 0.0,  "sun_elev": +10, "sky_strength": 1.1, "exposure": 0.05},
    "golden hour": {"sun_energy": 0.9, "sun_warm": 0.25, "sun_elev": -30, "sky_strength": 1.0, "exposure": 0.05},
    "sunset":      {"sun_energy": 0.8, "sun_warm": 0.35, "sun_elev": -38, "sky_strength": 0.9, "exposure": 0.0},
    "sunrise":     {"sun_energy": 0.8, "sun_warm": 0.25, "sun_elev": -35, "sky_strength": 0.9, "exposure": 0.0},
    "dawn":        {"sun_energy": 0.5, "sun_warm": 0.10, "sun_elev": -40, "sky_strength": 0.6, "exposure": -0.1},
    "dusk":        {"sun_energy": 0.4, "sun_warm": 0.15, "sun_elev": -42, "sky_strength": 0.6, "exposure": -0.15},
    "night":       {"sun_energy": 0.15, "sun_warm": -0.2, "sun_elev": -10, "sky_strength": 0.25, "exposure": -0.3},
    "moonlight":   {"sun_energy": 0.2, "sun_warm": -0.25, "sun_elev": +5,  "sky_strength": 0.3, "exposure": -0.25},
    "studio":      {"sun_energy": 1.0, "sun_warm": 0.0,  "sun_elev": 0,   "sky_strength": 1.0, "exposure": 0.0},
    "dramatic":    {"sun_energy": 1.1, "sun_warm": 0.1,  "sun_elev": -20, "sky_strength": 0.7, "exposure": -0.05},
    "moody":       {"sun_energy": 0.6, "sun_warm": -0.1, "sun_elev": -10, "sky_strength": 0.6, "exposure": -0.15},
    "dark":        {"sun_energy": 0.3, "sun_warm": -0.1, "sun_elev": 0,   "sky_strength": 0.4, "exposure": -0.25},
    "bright":      {"sun_energy": 1.3, "sun_warm": 0.0,  "sun_elev": +10, "sky_strength": 1.3, "exposure": 0.15},
}


def resolve_environment(setting: str, mood: str, style: str = "photoreal") -> Dict[str, Any]:
    """Combine a setting + mood + style into a single concrete environment spec.

    Returns a flat dict the composer's execute_python builder consumes:
      ground{kind,color,roughness}, sky{zenith,horizon,strength},
      sun{elevation,azimuth,color,energy}, fog{density,color},
      extras{starfield,neon}, post{exposure,saturation,contrast}
    """
    import copy
    spec = copy.deepcopy(ENVIRONMENT_SPECS.get(setting, ENVIRONMENT_SPECS["studio"]))
    mod = MOOD_MODIFIERS.get(mood, MOOD_MODIFIERS["neutral"])

    # Apply mood to sun
    sun = spec["sun"]
    sun["energy"] = round(sun["energy"] * mod["sun_energy"], 2)
    sun["elevation"] = max(5, min(85, sun["elevation"] + mod["sun_elev"]))
    warm = mod["sun_warm"]
    if warm:  # shift color temperature: +warm = more orange, -warm = more blue
        r, g, b = sun["color"]
        sun["color"] = [min(1.0, r + warm), g, max(0.0, b - warm)]
    spec["sky"]["strength"] = round(spec["sky"]["strength"] * mod["sky_strength"], 2)

    # Style: stylized = more saturated, flatter, less fog, punchier sky.
    stylized = style in ("cartoon", "anime", "claymation", "painting")
    if stylized:
        spec["fog"]["density"] = round(spec["fog"]["density"] * 0.4, 4)
        # boost ground + sky saturation by pushing toward primary
        spec["post"] = {"exposure": mod["exposure"] + 0.05, "saturation": 1.35, "contrast": 1.1}
        spec["ground"]["roughness"] = min(1.0, spec["ground"]["roughness"] + 0.1)
    else:
        spec["post"] = {"exposure": mod["exposure"], "saturation": 1.05, "contrast": 1.02}

    spec["_setting"] = setting
    spec["_mood"] = mood
    spec["_style"] = style
    return spec


def hdri_for_mood(mood: str, hdri_dir):
    """Return absolute HDRI path if file exists, else None.

    Args:
        mood: scene mood
        hdri_dir: Path to backend/assets/hdri/

    Returns: Path or None
    """
    from pathlib import Path
    filename = MOOD_HDRI_MAP.get(mood)
    if not filename:
        return None
    path = Path(hdri_dir) / filename
    return path if path.exists() else None
