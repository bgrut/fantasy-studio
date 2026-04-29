"""
Scene Recipe Builder — decomposes any prompt into a structured recipe of
assets, environment layers, and composition instructions.

Pure data. NO Blender imports. NO asset pipeline modification.

The recipe produced here is attached to the manifest as
`manifest["scene_recipe"]` in render_from_manifest.py. Downstream,
`app.scene.world_builder` reads the recipe to make smarter decisions
about HDRI keywords, ground material, atmosphere density, lighting
style, camera behavior, and compositor settings — without ever
overriding what the template already set.

Every helper is tolerant of missing / empty input so a half-built
scene_plan can't crash the recipe builder.
"""
from __future__ import annotations

from typing import Any


# --- Primary entry point ----------------------------------------------------

def build_scene_recipe(
    prompt: str,
    scene_plan: dict | None,
    manifest: dict | None = None,
) -> dict:
    """
    Build a complete scene recipe from the prompt + scene_plan.

    `scene_plan` is a dict (see _scene_plan_to_dict() in the integration
    layer if you're passing a ScenePlan dataclass). Any field may be
    missing; the recipe fills sensible defaults.
    """
    scene_plan = scene_plan or {}
    manifest = manifest or {}
    prompt_text = (prompt or "").lower()

    subject = str(scene_plan.get("subject") or scene_plan.get("focal_subject") or "")
    environment = str(scene_plan.get("environment") or "outdoor")
    action = str(scene_plan.get("action") or scene_plan.get("animation_mode") or "idle")
    time_of_day = str(scene_plan.get("time_of_day") or "golden_hour")
    mood = str(scene_plan.get("mood") or "cinematic")

    # Fallback: if the scene_plan didn't specify a recognized environment,
    # scan the raw prompt for complex-environment / ground-map keywords.
    # This is what lets "monkey in a baseball stadium" pick up the stadium
    # complex preset even when upstream enrichment didn't flag it.
    env_for_lookup = environment
    if env_for_lookup in ("", "outdoor"):
        for kw in list(_COMPLEX_ENVIRONMENTS.keys()) + list(_GROUND_MAP.keys()):
            if kw and kw in prompt_text:
                env_for_lookup = kw
                break

    recipe = {
        "hero":        build_hero_recipe(subject, action, scene_plan),
        "environment": build_environment_recipe(env_for_lookup, time_of_day),
        "ground":      build_ground_recipe(env_for_lookup),
        "sky":         build_sky_recipe(time_of_day, env_for_lookup, mood),
        "atmosphere":  build_atmosphere_recipe(time_of_day, mood, env_for_lookup),
        "lighting":    build_lighting_recipe(time_of_day, mood, env_for_lookup),
        "camera":      build_camera_recipe(action, mood, scene_plan),
        "props":       build_prop_recipe(subject, env_for_lookup, action),
        "compositor":  build_compositor_recipe(time_of_day, mood),
        # Useful for traceability / frontend breakdown panel.
        "summary": {
            "subject":     subject,
            "environment": env_for_lookup or environment,
            "action":      action,
            "time_of_day": time_of_day,
            "mood":        mood,
        },
    }
    return recipe


# --- Hero --------------------------------------------------------------------

def build_hero_recipe(subject: str, action: str, scene_plan: dict) -> dict:
    static_actions = {"idle", "sitting", "standing", "sleeping", "resting", "posing"}
    return {
        "query":            subject,
        "action":           action,
        "animation_speed":  get_animation_speed(action),
        "placement":        "center_ground",
        "needs_animation":  action.lower() not in static_actions,
        "scale_preference": "realistic",
    }


# --- Environment (simple vs complex) ----------------------------------------

_COMPLEX_ENVIRONMENTS: dict[str, dict[str, Any]] = {
    "stadium": {
        "primary":         "stadium grandstand",
        "secondary":       ["stadium lights", "scoreboard"],
        "ground_override": "grass",
    },
    "restaurant": {
        "primary":         "restaurant interior",
        "secondary":       ["dining table", "chair"],
        "ground_override": "wood_floor",
    },
    "kitchen": {
        "primary":         "kitchen interior",
        "secondary":       ["kitchen counter", "cooking pot"],
        "ground_override": "tile_floor",
    },
    "classroom": {
        "primary":         "classroom interior",
        "secondary":       ["desk", "chalkboard"],
        "ground_override": "wood_floor",
    },
    "space station": {
        "primary":         "space station interior",
        "secondary":       ["control panel"],
        "ground_override": "metal_floor",
    },
    "castle": {
        "primary":         "castle wall",
        "secondary":       ["torch", "banner"],
        "ground_override": "stone_floor",
    },
}


def build_environment_recipe(environment: str, time_of_day: str) -> dict:
    env_lower = (environment or "").lower()
    for key, config in _COMPLEX_ENVIRONMENTS.items():
        if key in env_lower:
            return {
                "type":              "complex",
                "primary_query":     config["primary"],
                "secondary_queries": list(config["secondary"]),
                "ground_override":   config["ground_override"],
                "searchable":        True,
            }
    return {
        "type":       "simple",
        "searchable": False,
        "style":      categorize_environment(environment),
    }


# --- Ground ------------------------------------------------------------------

_GROUND_MAP: dict[str, dict[str, str]] = {
    "city":       {"material": "asphalt",     "detail": "road_markings"},
    "street":     {"material": "asphalt",     "detail": "road_markings"},
    "park":       {"material": "grass",       "detail": "dirt_patches"},
    "forest":     {"material": "terrain",     "detail": "roots_leaves"},
    "jungle":     {"material": "terrain",     "detail": "moss_vines"},
    "mountain":   {"material": "terrain",     "detail": "rocky"},
    "desert":     {"material": "sand",        "detail": "dunes"},
    "beach":      {"material": "sand",        "detail": "water_edge"},
    "ocean":      {"material": "water",       "detail": "caustics"},
    "stadium":    {"material": "grass",       "detail": "sport_lines"},
    "restaurant": {"material": "wood_floor",  "detail": "planks"},
    "kitchen":    {"material": "tile",        "detail": "grout"},
    "stage":      {"material": "dark_glossy", "detail": "reflective"},
    "highway":    {"material": "asphalt",     "detail": "lane_lines"},
    "snow":       {"material": "snow",        "detail": "footprints"},
    "space":      {"material": "metal",       "detail": "panels"},
}


def build_ground_recipe(environment: str) -> dict:
    env_lower = (environment or "").lower()
    for key, config in _GROUND_MAP.items():
        if key in env_lower:
            return dict(config)
    return {"material": "terrain", "detail": "generic"}


# --- Sky / HDRI keywords -----------------------------------------------------

_TIME_SKY_KEYWORDS: dict[str, list[str]] = {
    "dawn":        ["sunrise", "dawn", "pink", "warm"],
    "morning":     ["morning", "bright", "clear"],
    "midday":      ["noon", "blue", "sunny", "bright"],
    "golden_hour": ["golden", "sunset", "warm", "dramatic"],
    "sunset":      ["sunset", "orange", "dramatic"],
    "dusk":        ["twilight", "purple", "blue_hour"],
    "night":       ["night", "dark", "stars", "moon"],
}


def build_sky_recipe(time_of_day: str, environment: str, mood: str) -> dict:
    keywords: list[str] = []
    keywords.extend(_TIME_SKY_KEYWORDS.get(time_of_day, ["blue", "sky"]))

    env_lower = (environment or "").lower()
    if "ocean" in env_lower or "beach" in env_lower:
        keywords.extend(["ocean", "tropical", "water"])
    elif "city" in env_lower or "urban" in env_lower:
        keywords.extend(["city", "urban", "buildings"])
    elif "forest" in env_lower or "jungle" in env_lower:
        keywords.extend(["forest", "canopy", "green"])
    elif "mountain" in env_lower:
        keywords.extend(["mountain", "alpine", "landscape"])
    elif "desert" in env_lower:
        keywords.extend(["desert", "arid", "hot"])
    elif "indoor" in env_lower or "studio" in env_lower:
        keywords.extend(["studio", "neutral", "soft"])

    # De-dup while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            deduped.append(kw)
    return {"hdri_keywords": deduped}


# --- Atmosphere -------------------------------------------------------------

_TIME_ATMOSPHERE_DENSITY: dict[str, float] = {
    "dawn":        0.008,
    "golden_hour": 0.006,
    "sunset":      0.008,
    "dusk":        0.010,
    "night":       0.012,
    "midday":      0.002,
    "morning":     0.003,
}


def build_atmosphere_recipe(
    time_of_day: str,
    mood: str,
    environment: str,
) -> dict:
    env_lower = (environment or "").lower()
    if "ocean" in env_lower or "underwater" in env_lower:
        return {
            "type":    "underwater",
            "density": 0.02,
            "color":   (0.1, 0.3, 0.5),
        }

    density = _TIME_ATMOSPHERE_DENSITY.get(time_of_day, 0.004)
    mood_lower = (mood or "").lower()
    if mood_lower in ("dramatic", "moody", "dark"):
        density *= 1.5
    elif mood_lower in ("foggy", "misty"):
        density *= 3.0
    elif mood_lower in ("clear", "bright"):
        density *= 0.5

    return {"type": "atmospheric", "density": density}


# --- Lighting ----------------------------------------------------------------

_INDOOR_ENV_WORDS = ("restaurant", "kitchen", "studio", "stage", "room", "indoor")


def build_lighting_recipe(time_of_day: str, mood: str, environment: str) -> dict:
    env_lower = (environment or "").lower()
    is_indoor = any(w in env_lower for w in _INDOOR_ENV_WORDS)

    if is_indoor:
        return {
            "style":            "interior",
            "key_energy":       150,
            "color_temp":       "warm",
            "practical_lights": True,
        }

    warm_times = ("golden_hour", "sunset", "dawn")
    if time_of_day == "night":
        color_temp = "cool"
    elif time_of_day in warm_times:
        color_temp = "warm"
    else:
        color_temp = "neutral"
    return {
        "style":      "exterior",
        "key_energy": 80 if time_of_day == "night" else 250,
        "color_temp": color_temp,
        "rim_light":  True,
    }


# --- Camera ------------------------------------------------------------------

_ACTION_CAMERAS: dict[str, dict[str, Any]] = {
    "driving":      {"style": "tracking",   "speed": "fast",      "angle": "low",          "lens": 35},
    "driving_fast": {"style": "tracking",   "speed": "fast",      "angle": "very_low",     "lens": 28},
    "running":      {"style": "tracking",   "speed": "moderate",  "angle": "eye_level",    "lens": 50},
    "walking":      {"style": "slow_orbit", "speed": "slow",      "angle": "eye_level",    "lens": 50},
    "dancing":      {"style": "orbit",      "speed": "moderate",  "angle": "slightly_low", "lens": 40},
    "flying":       {"style": "follow",     "speed": "fast",      "angle": "below",        "lens": 28},
    "swimming":     {"style": "follow",     "speed": "slow",      "angle": "eye_level",    "lens": 35},
    "idle":         {"style": "slow_orbit", "speed": "slow",      "angle": "eye_level",    "lens": 50},
    "sitting":      {"style": "dolly_in",   "speed": "very_slow", "angle": "eye_level",    "lens": 65},
}


def build_camera_recipe(action: str, mood: str, scene_plan: dict) -> dict:
    action_key = str(
        scene_plan.get("action")
        or scene_plan.get("animation_mode")
        or action
        or "idle"
    ).lower()
    base = _ACTION_CAMERAS.get(action_key) or _ACTION_CAMERAS["idle"]
    camera = dict(base)  # copy so we don't mutate the module-level map

    mood_lower = (mood or "").lower()
    if mood_lower in ("dramatic", "epic", "intense"):
        camera["angle"] = "low"
        camera["lens"] = min(camera["lens"], 35)
    elif mood_lower in ("intimate", "peaceful", "calm"):
        camera["style"] = "dolly_in"
        camera["speed"] = "very_slow"

    camera["dof"] = True
    camera["dof_fstop"] = 2.8 if mood_lower in ("dramatic", "cinematic") else 4.0
    return camera


# --- Contextual props -------------------------------------------------------

_ENV_PROPS: dict[str, list[str]] = {
    "park":       ["park bench", "tree"],
    "city":       ["street lamp", "trash can"],
    "forest":     ["fallen log", "mushroom", "fern"],
    "beach":      ["palm tree", "beach umbrella"],
    "stadium":    ["baseball bat", "sports equipment"],
    "restaurant": ["dining table set", "wine bottle"],
    "kitchen":    ["cooking pot", "cutting board"],
    "highway":    ["road barrier", "highway sign"],
    "desert":     ["cactus", "desert rock"],
    "mountain":   ["pine tree", "boulder"],
}


def build_prop_recipe(subject: str, environment: str, action: str) -> list[dict]:
    env_lower = (environment or "").lower()
    props: list[dict] = []
    for key, prop_list in _ENV_PROPS.items():
        if key in env_lower:
            for p in prop_list[:2]:  # Max 2 props per scene
                props.append({
                    "query":         p,
                    "placement":     "background",
                    "optional":      True,
                    "max_instances": 1,
                })
            break
    return props


# --- Compositor -------------------------------------------------------------

def build_compositor_recipe(time_of_day: str, mood: str) -> dict:
    mood_lower = (mood or "").lower()
    warm_times = ("golden_hour", "sunset", "dawn")
    cool_times = ("night", "dusk")
    return {
        "bloom": True,
        "bloom_threshold": 0.7 if time_of_day in cool_times else 0.85,
        "color_grade": {
            "shadows":    "cool"    if time_of_day in cool_times else "neutral",
            "highlights": "warm"    if time_of_day in warm_times else "neutral",
        },
        "vignette":        mood_lower in ("dramatic", "cinematic", "moody", "dark"),
        "lens_distortion": 0.02,
    }


# --- Utility ----------------------------------------------------------------

_ANIMATION_SPEEDS: dict[str, float] = {
    "running":      0.15,
    "walking":      0.06,
    "driving":      0.30,
    "driving_fast": 0.50,
    "galloping":    0.20,
    "flying":       0.20,
    "swimming":     0.08,
    "dancing":      0.00,
    "idle":         0.00,
    "climbing":     0.03,
    "crawling":     0.02,
}


def get_animation_speed(action: str) -> float:
    return _ANIMATION_SPEEDS.get((action or "").lower(), 0.05)


def categorize_environment(env: str) -> str:
    env_lower = (env or "").lower()
    if any(w in env_lower for w in ("city", "urban", "street", "downtown")):
        return "urban"
    if any(w in env_lower for w in ("forest", "jungle", "woods")):
        return "forest"
    if any(w in env_lower for w in ("ocean", "sea", "underwater")):
        return "ocean"
    if any(w in env_lower for w in ("mountain", "alpine", "peak")):
        return "mountain"
    if any(w in env_lower for w in ("desert", "sand")):
        return "desert"
    if any(w in env_lower for w in ("studio", "stage", "indoor")):
        return "indoor"
    return "outdoor"
