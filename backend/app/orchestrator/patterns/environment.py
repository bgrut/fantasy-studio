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
