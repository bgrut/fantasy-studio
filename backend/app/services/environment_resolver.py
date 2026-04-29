from __future__ import annotations

"""
environment_resolver.py
=======================
Resolve the correct ground material type and HDRI hints from the scene
plan and prompt text.  This keeps environment decisions in one place
instead of scattered across every template.
"""


# ═══════════════════════════════════════════════════════════════════════════
# Ground type from environment text
# ═══════════════════════════════════════════════════════════════════════════

_GROUND_RULES: list[tuple[list[str], str]] = [
    # (keyword list, ground_type)
    (["highway", "road", "street", "asphalt", "pavement", "freeway",
      "drive", "racing", "track", "lane", "boulevard"], "road_asphalt"),
    (["ocean", "sea", "underwater", "lake", "river", "beach", "coast",
      "reef", "lagoon", "aquatic"], "water_surface"),
    (["park", "forest", "field", "grass", "meadow", "garden", "trail",
      "mountain", "hill", "valley", "jungle", "savanna", "prairie",
      "woodland", "countryside"], "terrain_ground"),
    (["city", "rooftop", "building", "concrete", "sidewalk", "plaza",
      "parking", "urban", "alley", "warehouse"], "concrete"),
    (["studio", "stage", "display", "showroom", "gallery", "pedestal",
      "backdrop"], "studio_cyclorama"),
    (["desert", "sand", "dune", "arid", "wasteland", "sahara"], "desert_sand"),
    (["snow", "winter", "ice", "arctic", "frozen", "tundra", "glacier"], "snow_ground"),
    (["space", "sky", "void", "orbit", "cosmos", "nebula"], "none"),
]


def determine_ground_type(
    environment: str = "",
    scene_family: str = "",
    topic: str = "",
) -> str:
    """
    Return a ground material key based on prompt/environment/family.
    Falls back to 'terrain_ground' which looks decent for most scenes.
    """
    text = f"{environment} {topic}".lower()

    for keywords, ground_type in _GROUND_RULES:
        if any(kw in text for kw in keywords):
            return ground_type

    # Family-based fallback
    family = scene_family.lower()
    family_map = {
        "street_scene": "road_asphalt",
        "car_hero": "road_asphalt",
        "ocean_scene": "water_surface",
        "character_stage": "studio_cyclorama",
        "product_scene": "studio_cyclorama",
        "product_pedestal": "studio_cyclorama",
        "scenic_landscape": "terrain_ground",
        "city_loop": "road_asphalt",
    }
    return family_map.get(family, "terrain_ground")


# ═══════════════════════════════════════════════════════════════════════════
# HDRI search hints from scene plan
# ═══════════════════════════════════════════════════════════════════════════

def build_hdri_search_query(
    environment: str = "",
    time_of_day: str = "",
    mood: str = "",
    scene_family: str = "",
) -> str:
    """
    Build a focused HDRI search string for PolyHaven from scene metadata.
    """
    parts = []
    if environment:
        parts.append(environment)
    if time_of_day:
        parts.append(time_of_day)
    if mood and mood not in ("cinematic", "dramatic"):
        parts.append(mood)

    if parts:
        return " ".join(parts)

    # Family-based fallback
    family_defaults = {
        "street_scene": "neon city night urban",
        "car_hero": "sunset highway dramatic sky",
        "ocean_scene": "underwater blue caustics",
        "character_stage": "studio softbox neutral",
        "product_scene": "studio luxury softbox clean",
        "scenic_landscape": "golden hour mountain sky",
        "city_loop": "city night neon urban",
    }
    return family_defaults.get(scene_family.lower(), "blue sky outdoor")
