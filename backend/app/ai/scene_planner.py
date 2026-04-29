import json
import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "deepseek-r1"


def _safe_json_extract(text: str) -> dict:
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    if "```json" in text:
        try:
            chunk = text.split("```json", 1)[1].split("```", 1)[0].strip()
            return json.loads(chunk)
        except Exception:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass

    raise ValueError("Model did not return valid JSON")


def generate_scene_plan(prompt: str, model: str = DEFAULT_MODEL) -> dict:
    system = """
You are a world-class short-form 3D scene planner for Blender animation.

Convert the user's creative prompt into a strict JSON scene plan.

Return ONLY JSON.

Schema:
{
  "environment": "",
  "lighting": "",
  "assets": [],
  "camera_style": "",
  "mood": "",
  "motion": "",
  "materials": [],
  "effects": [],
  "duration_seconds": 12,
  "aspect_ratio": "9:16",
  "fps": 24,
  "template_hint": "",
  "title_text": "",
  "subtitle_text": "",
  "caption_text": "",
  "quality_tier": "high",
  "shot_design": {
    "opening": "",
    "mid": "",
    "ending": ""
  }
}

Rules:
- Optimize for vertical short-form content.
- Prefer visually strong, practical, renderable ideas.
- Keep duration 8 to 60 seconds.
- Use cinematic but concise field values.
- For cyberpunk/city prompts, favor city_loop.
- For luxury products, favor product_pedestal.
- For text-led informational scenes, favor neon_news.
- No explanations outside JSON.
"""

    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": system + "\n\nUSER PROMPT:\n" + prompt,
            "stream": False,
        },
        timeout=180,
    )
    resp.raise_for_status()
    raw = resp.json()["response"]
    plan = _safe_json_extract(raw)

    plan.setdefault("environment", "studio")
    plan.setdefault("lighting", "clean_studio")
    plan.setdefault("assets", [])
    plan.setdefault("camera_style", "slow_push")
    plan.setdefault("mood", "cinematic")
    plan.setdefault("motion", "subtle")
    plan.setdefault("materials", [])
    plan.setdefault("effects", [])
    plan.setdefault("duration_seconds", 12)
    plan.setdefault("aspect_ratio", "9:16")
    plan.setdefault("fps", 24)
    plan.setdefault("template_hint", "")
    plan.setdefault("title_text", prompt[:42])
    plan.setdefault("subtitle_text", "BLENDER LANE")
    plan.setdefault("caption_text", prompt[:120])
    plan.setdefault("quality_tier", "high")
    plan.setdefault("shot_design", {
        "opening": "strong opening frame",
        "mid": "camera progression",
        "ending": "resolved hero frame"
    })

    return plan
