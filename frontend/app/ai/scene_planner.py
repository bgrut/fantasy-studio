import json
import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "deepseek-r1"


def _safe_json_extract(text: str) -> dict:
    text = text.strip()

    # try raw json
    try:
        return json.loads(text)
    except Exception:
        pass

    # try fenced block
    if "```json" in text:
        try:
            chunk = text.split("```json", 1)[1].split("```", 1)[0].strip()
            return json.loads(chunk)
        except Exception:
            pass

    # try first {...} block
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
You are a 3D scene planner for Blender.

Convert the user's prompt into a structured JSON scene plan.
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
  "duration_seconds": 12,
  "aspect_ratio": "9:16",
  "fps": 24,
  "template_hint": "",
  "title_text": "",
  "subtitle_text": "",
  "caption_text": ""
}

Rules:
- Keep assets practical and renderable.
- Prefer short-form vertical video.
- Keep duration between 8 and 60 seconds.
- Use concise strings.
- Do not include any explanation outside JSON.
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

    # normalize defaults
    plan.setdefault("environment", "studio")
    plan.setdefault("lighting", "clean_studio")
    plan.setdefault("assets", [])
    plan.setdefault("camera_style", "slow_push")
    plan.setdefault("mood", "cinematic")
    plan.setdefault("motion", "subtle")
    plan.setdefault("materials", [])
    plan.setdefault("duration_seconds", 12)
    plan.setdefault("aspect_ratio", "9:16")
    plan.setdefault("fps", 24)
    plan.setdefault("template_hint", "")
    plan.setdefault("title_text", "AI GENERATED PRODUCTION")
    plan.setdefault("subtitle_text", "BLENDER LANE")
    plan.setdefault("caption_text", prompt[:120])

    return plan
