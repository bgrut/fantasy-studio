from ..ai.template_selector import select_template


def _normalize_assets(assets):
    normalized = []

    if not isinstance(assets, list):
        return normalized

    for item in assets:
        if isinstance(item, str):
            normalized.append(item)
        elif isinstance(item, dict):
            label = (
                item.get("name")
                or item.get("type")
                or item.get("asset")
                or item.get("category")
            )
            if isinstance(label, str) and label.strip():
                normalized.append(label.strip())

    return normalized


def build_manifest(prompt: str, scene_plan: dict) -> dict:
    scene_plan_for_select = dict(scene_plan)
    scene_plan_for_select["subject"] = prompt

    template_name = select_template(scene_plan_for_select)

    duration = int(scene_plan.get("duration_seconds", 12))
    fps = int(scene_plan.get("fps", 24))
    aspect_ratio = scene_plan.get("aspect_ratio", "9:16")

    if aspect_ratio == "16:9":
        width, height = 1920, 1080
    elif aspect_ratio == "1:1":
        width, height = 1080, 1080
    else:
        width, height = 1080, 1920

    return {
        "template_name": template_name,
        "title_text": scene_plan.get("title_text") or prompt[:48],
        "subtitle_text": scene_plan.get("subtitle_text") or "AI GENERATED PRODUCTION",
        "subject": prompt,
        "hook": scene_plan.get("caption_text") or prompt,
        "environment": scene_plan.get("environment", "studio"),
        "lighting": scene_plan.get("lighting", "clean_studio"),
        "assets": _normalize_assets(scene_plan.get("assets", [])),
        "camera_style": scene_plan.get("camera_style", "slow_push"),
        "mood": scene_plan.get("mood", "cinematic"),
        "motion": scene_plan.get("motion", "subtle"),
        "materials": scene_plan.get("materials", []),
        "effects": scene_plan.get("effects", []),
        "audio_hint": scene_plan.get("mood", "cinematic"),
        "caption_text": scene_plan.get("caption_text", prompt[:120]),
        "duration_seconds": duration,
        "aspect_ratio": aspect_ratio,
        "fps": fps,
        "output_resolution": {
            "width": width,
            "height": height
        },
        "quality_tier": scene_plan.get("quality_tier", "high"),
        "shot_design": scene_plan.get("shot_design", {})
    }
