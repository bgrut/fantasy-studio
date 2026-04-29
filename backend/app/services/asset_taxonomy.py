from __future__ import annotations


ASSET_ALIASES = {
    "building": {"building", "skyscraper", "tower", "highrise", "architecture"},
    "car": {"car", "vehicle", "automobile", "futuristic_car"},
    "sign": {"sign", "billboard", "neon_sign", "ad_panel"},
    "product": {"product", "bottle", "perfume", "watch", "hero_object"},
    "wet_asphalt": {"wet_asphalt", "wet_road", "asphalt", "street", "road"},
    "city_hdri": {"city_hdri", "night_hdri", "urban_hdri", "cyberpunk_hdri"},
    "studio_hdri": {"studio_hdri", "studio_light", "clean_hdri", "product_hdri"},
}


def normalize_need(label: str) -> str:
    value = (label or "").strip().lower()
    for canonical, aliases in ASSET_ALIASES.items():
        if value == canonical or value in aliases:
            return canonical
    return value