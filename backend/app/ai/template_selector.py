def _flatten_assets_for_matching(assets) -> str:
    parts = []

    if not isinstance(assets, list):
        return ""

    for item in assets:
        if isinstance(item, str):
            parts.append(item.lower())
        elif isinstance(item, dict):
            for v in item.values():
                if isinstance(v, str):
                    parts.append(v.lower())
                elif isinstance(v, list):
                    for subv in v:
                        if isinstance(subv, str):
                            parts.append(subv.lower())

    return " ".join(parts)


def _score_city(text: str) -> int:
    keys = [
        "city", "cyberpunk", "urban", "street", "road", "skyscraper",
        "billboard", "neon", "rain", "wet asphalt", "wet street",
        "fog", "holographic", "traffic", "downtown"
    ]
    return sum(1 for k in keys if k in text)


def _score_product(text: str) -> int:
    keys = [
        "product", "bottle", "watch", "perfume", "commercial",
        "pedestal", "hero object", "studio product", "luxury product"
    ]
    return sum(1 for k in keys if k in text)


def _score_news(text: str) -> int:
    keys = [
        "news", "broadcast", "studio anchor", "breaking news",
        "headline", "ticker", "screen wall"
    ]
    return sum(1 for k in keys if k in text)


def select_template(scene_plan: dict) -> str:
    env = str(scene_plan.get("environment", "")).lower()
    hint = str(scene_plan.get("template_hint", "")).lower()
    mood = str(scene_plan.get("mood", "")).lower()
    subject = str(scene_plan.get("subject", "" ) or scene_plan.get("caption_text", "")).lower()
    camera = str(scene_plan.get("camera_style", "")).lower()
    motion = str(scene_plan.get("motion", "")).lower()
    assets = _flatten_assets_for_matching(scene_plan.get("assets", []))

    blob = " ".join([env, hint, mood, subject, camera, motion, assets])

    city_score = _score_city(blob)
    product_score = _score_product(blob)
    news_score = _score_news(blob)

    # Strong routing rules
    if city_score >= max(product_score, news_score) and city_score >= 2:
        return "city_loop"

    if product_score >= max(city_score, news_score) and product_score >= 2:
        return "product_pedestal"

    if news_score >= max(city_score, product_score) and news_score >= 1:
        return "neon_news"

    # fallback heuristics
    if "city" in blob or "cyberpunk" in blob:
        return "city_loop"
    if "product" in blob or "pedestal" in blob:
        return "product_pedestal"
    if "news" in blob or "broadcast" in blob:
        return "neon_news"

    return "city_loop"
