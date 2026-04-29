from __future__ import annotations

VALID_TEMPLATES = {
    "city_scene": "city_loop",
    "product_stage": "product_scene",
    "street_scene": "street_scene",
    "character_stage": "character_stage",
    "ocean_scene": "ocean_scene",
    "scenic_landscape": "scenic_landscape",
    "car_hero": "car_hero",
    "news_broadcast": "neon_news",
}

def resolve_template_name(scene_family: str, fallback: str = "city_loop") -> str:
    return VALID_TEMPLATES.get(scene_family, fallback)
