def select_template(scene_plan: dict) -> str:
    env = str(scene_plan.get("environment", "")).lower()
    hint = str(scene_plan.get("template_hint", "")).lower()
    assets = " ".join(scene_plan.get("assets", [])).lower()
    mood = str(scene_plan.get("mood", "")).lower()

    if any(x in hint for x in ["product", "pedestal", "luxury"]):
        return "product_pedestal"

    if any(x in env for x in ["city", "cyberpunk", "street", "urban"]) or any(x in assets for x in ["building", "car", "road", "neon"]):
        return "city_loop"

    if any(x in hint for x in ["news", "broadcast"]) or "news" in mood:
        return "neon_news"

    return "neon_news"
