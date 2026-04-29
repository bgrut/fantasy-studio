"""
Prompt Intelligence — maps natural language to structured scene parameters.
This enriches the scene plan (produced by the LLM / legacy planner) with
specific technical parameters: canonical subject types, search queries,
animation hints, camera style, environment family, weather modifiers,
and a canonical time-of-day.

Design rules:
  - Never OVERRIDE an existing scene_plan value. Only fill missing or
    empty keys.
  - Works on a dict (not the ScenePlan dataclass) so it stays portable.
    Callers convert to/from dataclass at the integration site.
  - No side effects. Pure in → pure out.
"""
from __future__ import annotations

from typing import Any


# === SUBJECT SYNONYMS ===
# Maps user words to canonical asset types and search terms.
SUBJECT_MAP: dict[str, dict[str, Any]] = {
    # Vehicles
    "car": {"type": "vehicle", "search": ["car", "automobile", "sedan"], "animation": "driving"},
    "sports car": {"type": "vehicle", "search": ["sports car", "supercar"], "animation": "driving_fast"},
    "ferrari": {"type": "vehicle", "search": ["Ferrari", "sports car"], "animation": "driving_fast"},
    "lamborghini": {"type": "vehicle", "search": ["Lamborghini", "supercar"], "animation": "driving_fast"},
    "truck": {"type": "vehicle", "search": ["truck", "pickup"], "animation": "driving"},
    "motorcycle": {"type": "vehicle", "search": ["motorcycle", "bike"], "animation": "driving_fast"},
    "race car": {"type": "vehicle", "search": ["race car", "F1", "racing"], "animation": "driving_fast"},
    "bus": {"type": "vehicle", "search": ["bus", "coach"], "animation": "driving"},
    "airplane": {"type": "vehicle", "search": ["airplane", "aircraft", "jet"], "animation": "flying"},
    "helicopter": {"type": "vehicle", "search": ["helicopter", "chopper"], "animation": "flying"},
    "boat": {"type": "vehicle", "search": ["boat", "ship", "yacht"], "animation": "sailing"},

    # Animals
    "dog": {"type": "animal", "search": ["dog", "canine", "puppy"], "animation": "walking"},
    "cat": {"type": "animal", "search": ["cat", "feline", "kitten"], "animation": "walking"},
    "horse": {"type": "animal", "search": ["horse", "stallion", "mare"], "animation": "galloping"},
    "tiger": {"type": "animal", "search": ["tiger", "big cat"], "animation": "walking"},
    "lion": {"type": "animal", "search": ["lion", "big cat"], "animation": "walking"},
    "eagle": {"type": "animal", "search": ["eagle", "bird of prey"], "animation": "flying"},
    "dolphin": {"type": "animal", "search": ["dolphin", "porpoise"], "animation": "swimming"},
    "whale": {"type": "animal", "search": ["whale", "humpback"], "animation": "swimming"},
    "shark": {"type": "animal", "search": ["shark", "great white"], "animation": "swimming"},
    "butterfly": {"type": "animal", "search": ["butterfly", "moth"], "animation": "flying"},
    "snake": {"type": "animal", "search": ["snake", "serpent"], "animation": "slithering"},
    "lizard": {"type": "animal", "search": ["lizard", "gecko", "reptile"], "animation": "crawling"},
    "fish": {"type": "animal", "search": ["fish", "tropical fish"], "animation": "swimming"},
    "bird": {"type": "animal", "search": ["bird", "songbird"], "animation": "flying"},
    "bear": {"type": "animal", "search": ["bear", "grizzly"], "animation": "walking"},
    "wolf": {"type": "animal", "search": ["wolf", "canine"], "animation": "running"},
    "deer": {"type": "animal", "search": ["deer", "stag", "elk"], "animation": "walking"},
    "rabbit": {"type": "animal", "search": ["rabbit", "bunny", "hare"], "animation": "hopping"},
    "frog": {"type": "animal", "search": ["frog", "toad"], "animation": "hopping"},
    "dinosaur": {"type": "animal", "search": ["dinosaur", "T-Rex", "raptor"], "animation": "walking"},
    "dragon": {"type": "animal", "search": ["dragon", "wyvern"], "animation": "flying"},

    # Characters
    "robot": {"type": "character", "search": ["robot", "mech", "droid"], "animation": "walking"},
    "person": {"type": "character", "search": ["human", "person", "character"], "animation": "walking"},
    "man": {"type": "character", "search": ["male character", "man"], "animation": "walking"},
    "woman": {"type": "character", "search": ["female character", "woman"], "animation": "walking"},
    "warrior": {"type": "character", "search": ["warrior", "knight", "soldier"], "animation": "walking"},
    "dancer": {"type": "character", "search": ["dancer", "character"], "animation": "dancing"},
    "astronaut": {"type": "character", "search": ["astronaut", "spaceman"], "animation": "walking"},
    "zombie": {"type": "character", "search": ["zombie", "undead"], "animation": "walking"},
    "ninja": {"type": "character", "search": ["ninja", "martial artist"], "animation": "fighting"},
    "superhero": {"type": "character", "search": ["superhero", "hero"], "animation": "flying"},
    "chef": {"type": "character", "search": ["chef", "cook", "character"], "animation": "idle"},
}

# === ACTION SYNONYMS ===
# Maps user action words to animation types and camera styles.
ACTION_MAP: dict[str, dict[str, Any]] = {
    # Movement
    "running": {"animation": "running", "speed": 0.15, "camera": "tracking"},
    "walking": {"animation": "walking", "speed": 0.06, "camera": "tracking"},
    "sprinting": {"animation": "running", "speed": 0.2, "camera": "tracking"},
    "jogging": {"animation": "walking", "speed": 0.1, "camera": "tracking"},
    "driving": {"animation": "driving", "speed": 0.3, "camera": "tracking"},
    "racing": {"animation": "driving_fast", "speed": 0.5, "camera": "tracking"},
    "speeding": {"animation": "driving_fast", "speed": 0.5, "camera": "tracking"},
    "flying": {"animation": "flying", "speed": 0.2, "camera": "follow"},
    "swimming": {"animation": "swimming", "speed": 0.08, "camera": "follow"},
    "galloping": {"animation": "galloping", "speed": 0.2, "camera": "tracking"},
    "climbing": {"animation": "climbing", "speed": 0.03, "camera": "orbit"},
    "crawling": {"animation": "crawling", "speed": 0.02, "camera": "orbit"},

    # Performance
    "dancing": {"animation": "dancing", "speed": 0.0, "camera": "orbit"},
    "singing": {"animation": "idle", "speed": 0.0, "camera": "dolly_in"},
    "posing": {"animation": "idle", "speed": 0.0, "camera": "orbit"},
    "fighting": {"animation": "fighting", "speed": 0.05, "camera": "orbit"},
    "cooking": {"animation": "idle", "speed": 0.0, "camera": "orbit"},

    # Static
    "sitting": {"animation": "idle", "speed": 0.0, "camera": "orbit"},
    "standing": {"animation": "idle", "speed": 0.0, "camera": "orbit"},
    "sleeping": {"animation": "idle", "speed": 0.0, "camera": "dolly_in"},
    "resting": {"animation": "idle", "speed": 0.0, "camera": "orbit"},
}

# === ENVIRONMENT SYNONYMS ===
# Maps user environment words to scene parameters.
ENVIRONMENT_MAP: dict[str, dict[str, Any]] = {
    # Urban
    "city":     {"family": "street_scene", "ground": "asphalt", "hdri_keywords": ["city", "urban"]},
    "street":   {"family": "street_scene", "ground": "asphalt", "hdri_keywords": ["street", "urban"]},
    "downtown": {"family": "street_scene", "ground": "concrete", "hdri_keywords": ["city", "downtown"]},
    "alley":    {"family": "street_scene", "ground": "concrete", "hdri_keywords": ["city", "dark"]},
    "rooftop":  {"family": "street_scene", "ground": "concrete", "hdri_keywords": ["city", "sky"]},

    # Roads
    "highway":   {"family": "car_hero", "ground": "asphalt", "hdri_keywords": ["road", "landscape"]},
    "road":      {"family": "car_hero", "ground": "asphalt", "hdri_keywords": ["road"]},
    "racetrack": {"family": "car_hero", "ground": "asphalt", "hdri_keywords": ["outdoor"]},

    # Nature
    "park":     {"family": "scenic_landscape", "ground": "grass",   "hdri_keywords": ["sunny", "green", "park"]},
    "forest":   {"family": "scenic_landscape", "ground": "terrain", "hdri_keywords": ["forest", "trees"]},
    "jungle":   {"family": "scenic_landscape", "ground": "terrain", "hdri_keywords": ["tropical", "green"]},
    "mountain": {"family": "scenic_landscape", "ground": "terrain", "hdri_keywords": ["mountain", "landscape"]},
    "field":    {"family": "scenic_landscape", "ground": "grass",   "hdri_keywords": ["open", "field"]},
    "garden":   {"family": "scenic_landscape", "ground": "grass",   "hdri_keywords": ["garden", "sunny"]},
    "desert":   {"family": "scenic_landscape", "ground": "sand",    "hdri_keywords": ["desert", "sand"]},
    "beach":    {"family": "scenic_landscape", "ground": "sand",    "hdri_keywords": ["beach", "ocean"]},
    "snow":     {"family": "scenic_landscape", "ground": "snow",    "hdri_keywords": ["winter", "snow"]},

    # Water
    "ocean":      {"family": "ocean_scene",      "ground": "water",   "hdri_keywords": ["ocean", "water"]},
    "underwater": {"family": "ocean_scene",      "ground": "water",   "hdri_keywords": ["underwater"]},
    "lake":       {"family": "scenic_landscape", "ground": "water",   "hdri_keywords": ["lake"]},
    "river":      {"family": "scenic_landscape", "ground": "terrain", "hdri_keywords": ["river"]},

    # Indoor
    "stage":      {"family": "character_stage", "ground": "studio", "hdri_keywords": ["studio"]},
    "studio":     {"family": "character_stage", "ground": "studio", "hdri_keywords": ["studio"]},
    "restaurant": {"family": "character_stage", "ground": "wood",   "hdri_keywords": ["indoor", "warm"]},
    "kitchen":    {"family": "character_stage", "ground": "tile",   "hdri_keywords": ["indoor"]},
    "room":       {"family": "character_stage", "ground": "wood",   "hdri_keywords": ["indoor"]},

    # Special
    "space": {"family": "scenic_landscape", "ground": "none", "hdri_keywords": ["space", "stars"]},
    "sky":   {"family": "scenic_landscape", "ground": "none", "hdri_keywords": ["sky", "clouds"]},
}

# === WEATHER / MOOD MODIFIERS ===
WEATHER_MAP: dict[str, dict[str, Any]] = {
    "rain":   {"atmosphere_density": 0.015, "ground_wet": True,  "hdri_keywords": ["overcast", "storm"]},
    "rainy":  {"atmosphere_density": 0.015, "ground_wet": True,  "hdri_keywords": ["overcast", "storm"]},
    "fog":    {"atmosphere_density": 0.025, "ground_wet": False, "hdri_keywords": ["fog", "mist"]},
    "foggy":  {"atmosphere_density": 0.025, "ground_wet": False, "hdri_keywords": ["fog", "mist"]},
    "snow":   {"atmosphere_density": 0.008, "ground_wet": False, "hdri_keywords": ["winter", "overcast"]},
    "storm":  {"atmosphere_density": 0.02,  "ground_wet": True,  "hdri_keywords": ["storm", "dark"]},
    "clear":  {"atmosphere_density": 0.002, "ground_wet": False, "hdri_keywords": ["clear", "blue"]},
    "sunny":  {"atmosphere_density": 0.002, "ground_wet": False, "hdri_keywords": ["sunny", "bright"]},
}

TIME_MAP: dict[str, str] = {
    "sunrise":      "dawn",
    "dawn":         "dawn",
    "morning":      "morning",
    "noon":         "midday",
    "midday":       "midday",
    "afternoon":    "midday",
    "golden hour":  "golden_hour",
    "sunset":       "sunset",
    "dusk":         "dusk",
    "evening":      "dusk",
    "twilight":     "dusk",
    "night":        "night",
    "midnight":     "night",
    "dark":         "night",
}


def enrich_scene_plan(prompt: str, scene_plan: dict | None) -> dict:
    """
    Enrich a scene plan dict with word intelligence.

    Adds precise technical parameters based on prompt words.
    Does NOT override existing scene_plan values — only ADDS missing ones.
    Multi-word phrases (e.g. "sports car", "golden hour") are checked before
    single words so the longest match wins.

    Returns the same (now-enriched) dict.
    """
    if scene_plan is None:
        scene_plan = {}

    prompt_lower = (prompt or "").lower()
    words = prompt_lower.split()

    enrichments: dict[str, Any] = {}

    # --- Subject: prefer multi-word phrases first (longest match wins) ---
    for phrase in sorted(SUBJECT_MAP.keys(), key=len, reverse=True):
        if phrase in prompt_lower:
            data = SUBJECT_MAP[phrase]
            if not scene_plan.get("subject_type"):
                enrichments["subject_type"] = data["type"]
            enrichments.setdefault("search_queries", list(data["search"]))
            enrichments.setdefault("default_animation", data["animation"])
            break

    # --- Action: first matching single word wins ---
    for word in words:
        if word in ACTION_MAP:
            data = ACTION_MAP[word]
            enrichments["animation"] = data["animation"]
            enrichments["animation_speed"] = data["speed"]
            enrichments["suggested_camera"] = data["camera"]
            break

    # --- Environment: longest phrase wins ---
    for phrase in sorted(ENVIRONMENT_MAP.keys(), key=len, reverse=True):
        if phrase in prompt_lower:
            data = ENVIRONMENT_MAP[phrase]
            enrichments["environment_type"] = phrase
            enrichments["suggested_ground"] = data["ground"]
            enrichments["hdri_keywords"] = list(data.get("hdri_keywords", []))
            if not scene_plan.get("template_family"):
                enrichments["template_family"] = data["family"]
            break

    # --- Weather ---
    for word in words:
        if word in WEATHER_MAP:
            enrichments["weather"] = word
            for k, v in WEATHER_MAP[word].items():
                # Weather 'hdri_keywords' should merge with environment ones,
                # not clobber them.
                if k == "hdri_keywords":
                    existing = enrichments.get("hdri_keywords") or []
                    enrichments["hdri_keywords"] = list(dict.fromkeys(existing + list(v)))
                else:
                    enrichments[k] = v
            break

    # --- Time of day: longest phrase first so "golden hour" beats "hour" ---
    for phrase in sorted(TIME_MAP.keys(), key=len, reverse=True):
        if phrase in prompt_lower:
            enrichments["time_of_day"] = TIME_MAP[phrase]
            break

    # --- Merge: only set keys that are missing or falsy ---
    for key, value in enrichments.items():
        if key not in scene_plan or not scene_plan[key]:
            scene_plan[key] = value

    return scene_plan
