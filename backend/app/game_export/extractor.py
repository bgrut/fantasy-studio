"""Phase 26.5 — prompt/PRD → GameSpec (the Fable-style front-end).

Reuses the SAME OllamaClient as the video slot extractor (one LLM edge, two
backends). The model only fills SEMANTIC fields (title, world, speeds,
camera, objectives) — asset paths and structure stay deterministic. Failure
ladder: one corrective re-ask → keyword fallback → pure defaults. A weak
extraction degrades to a working default game, never a broken one.
"""
from __future__ import annotations

import json
import re

from app.orchestrator.llm import OllamaClient

from .spec import GameSpec, spec_from_dict

_SYSTEM = """You turn a game idea (a short prompt OR a long PRD document) into ONE JSON object.
Output ONLY the JSON object, no markdown, no commentary. Schema (all fields optional — omit anything the text doesn't justify):
{
 "title": str,
 "world": {"name": one of "park","garden","forest","meadow","countryside","field","grass","backyard","plain",
           "size_m": float 30..500, "sky": one of "day","sunset","night","overcast", "fog": bool,
           "weather": one of "none","rain","snow", "wind": float 0..1,
           "ground_color": [r,g,b] floats 0..1},
 "player": {"name": str, "height_m": float 0.5..3, "walk_speed": float 1..4, "run_speed": float 4..10},
 "camera": {"mode": one of "third_person","first_person","orbit", "distance_m": float 2..12, "fov_deg": float 30..90},
 "objectives": [{"kind":"collect","label":str,"count":int 1..50}],
 "entities": [{"name": simple noun like "dog","cat","horse", "behavior": one of "wander","follow","static",
               "count": int 1..8, "speed": float 0.5..8}]
}
Map the text's setting to the CLOSEST world.name keyword. entities = OTHER creatures/characters in the
scene besides the player (a companion pet -> behavior "follow"). Do not invent fields not in the schema."""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _keyword_fallback(text: str) -> dict:
    """No-LLM extraction: setting keywords + sky words. Always succeeds."""
    t = text.lower()
    out: dict = {"title": text.strip()[:60] or "Fantasy Studio Game", "world": {}}
    for w in ("park", "garden", "forest", "meadow", "countryside", "field", "backyard", "grass"):
        if w in t:
            out["world"]["name"] = w
            break
    for sky, words in (("night", ("night", "moon", "dark")), ("sunset", ("sunset", "dusk", "golden")),
                       ("overcast", ("overcast", "cloudy", "foggy", "gloomy"))):
        if any(w in t for w in words):
            out["world"]["sky"] = sky
            break
    if "fog" in t or "mist" in t:
        out["world"]["fog"] = True
    if any(w in t for w in ("rain", "storm", "drizzl", "downpour")):
        out["world"]["weather"] = "rain"
    elif any(w in t for w in ("snow", "blizzard", "wintry", "winter")):
        out["world"]["weather"] = "snow"
    if any(w in t for w in ("windy", "gale", "breez", "storm")):
        out["world"]["wind"] = 0.9
    return out


def _merge(base: dict, over: dict) -> dict:
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def extract_game_spec(text: str, model: str | None = None, verbose: bool = True) -> GameSpec:
    """Text (prompt or PRD) → validated GameSpec. Never raises."""
    base = GameSpec().model_dump()
    llm_out: dict | None = None
    try:
        client = OllamaClient(**({"model": model} if model else {}))
        if client.is_alive():
            msgs = [{"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": text[:12000]}]
            for attempt in (1, 2):
                resp = client.chat(msgs)
                # OllamaClient.chat returns the message dict itself: {'role','content'}
                raw = (resp.get("content") or resp.get("message", {}).get("content", "")) \
                    if isinstance(resp, dict) else str(resp)
                m = _JSON_RE.search(raw)
                try:
                    cand = json.loads(m.group(0)) if m else None
                    if isinstance(cand, dict):
                        spec_from_dict(_merge(json.loads(json.dumps(base)), cand))  # validate merged
                        llm_out = cand
                        break
                except Exception as e:
                    if attempt == 1:
                        msgs.append({"role": "assistant", "content": raw[:2000]})
                        msgs.append({"role": "user",
                                     "content": f"That was invalid ({e}). Reply with ONLY the corrected JSON object."})
        elif verbose:
            print("[game] extractor: Ollama not reachable — keyword fallback")
    except Exception as e:
        if verbose:
            print(f"[game] extractor: LLM path failed ({type(e).__name__}: {e}) — keyword fallback")

    over = llm_out if llm_out is not None else _keyword_fallback(text)
    spec = spec_from_dict(_merge(base, over))
    if verbose:
        src = "ollama" if llm_out is not None else "keywords"
        print(f"[game] spec via {src}: '{spec.title}' — world={spec.world.name}, "
              f"sky={spec.world.sky}, cam={spec.camera.mode}, objectives={len(spec.objectives)}")
    return spec
