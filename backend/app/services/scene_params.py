from __future__ import annotations

def _safe_lower(value):
    return str(value or "").strip().lower()


def extract_scene_params(manifest: dict) -> dict:
    subject = str(manifest.get("subject", ""))
    hook = str(manifest.get("hook", ""))
    subtitle = str(manifest.get("subtitle_text", ""))
    palette = manifest.get("palette", {}) or {}

    text_blob = " ".join([
        subject,
        hook,
        subtitle,
        str(manifest.get("audio_hint", "")),
        str(manifest.get("caption_text", "")),
    ]).lower()

    # environment inference
    environment = "city"
    if "studio" in text_blob or "pedestal" in text_blob or "product" in text_blob:
        environment = "studio"
    elif "news" in text_blob or "broadcast" in text_blob:
        environment = "news"

    # tone / lighting preset
    lighting_preset = "cyberpunk_night"
    if "bright" in text_blob or "clean" in text_blob or "commercial" in text_blob:
        lighting_preset = "bright_commercial"
    if "moody" in text_blob or "dark" in text_blob or "noir" in text_blob:
        lighting_preset = "moody_night"

    # camera grammar
    camera_mode = "push_in"
    if "orbit" in text_blob or "showroom" in text_blob:
        camera_mode = "orbit"
    elif "tracking" in text_blob or "drive" in text_blob or "drift" in text_blob:
        camera_mode = "tracking"

    # focal subject
    focal_subject = "car" if "car" in text_blob or "vehicle" in text_blob or "lamborghini" in text_blob else "city"

    return {
        "environment": environment,
        "lighting_preset": lighting_preset,
        "camera_mode": camera_mode,
        "focal_subject": focal_subject,
        "brand_primary": palette.get("primary", "#0EA5E9"),
        "brand_accent": palette.get("accent", "#D946EF"),
    }
