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
 "world": {"name": one of "park","garden","forest","meadow","countryside","field","grass","backyard","city","street","plain",
           "mountains","canyon","desert","beach","swamp","volcano","arctic","hills",
           "ocean","lake","river","underwater",
           "mars","moon","castle","jungle","ruins","cave",
           "size_m": float 30..500, "sky": one of "day","sunset","night","overcast","mars","space","dusk", "fog": bool,
           (mars -> sky "mars" + rust ground_color; moon/space -> sky "space" + gray ground),
           "weather": one of "none","rain","snow", "wind": float 0..1,
           "ground_color": [r,g,b] floats 0..1},
 "reward": str or null — what the winner GETS ("winner gets a banana" -> "banana"); null if none stated,
 "intro": 1-2 SHORT atmospheric sentences setting up the quest, written like a real game
          ("The fireflies have scattered across the frozen wood. Find them before dawn."),
 "win_text": one short triumphant victory line ("The meadow glows again."),
 "player": {"name": THE CONTROLLABLE SUBJECT of the prompt as a simple noun ("fox","samurai","man","horse","wizard"...),
            "height_m": float 0.5..3, "walk_speed": float 1..4, "run_speed": float 4..10},
 "camera": {"mode": one of "third_person","first_person","orbit", "distance_m": float 2..12, "fov_deg": float 30..90},
 "player": also may include "attack": one of "none","melee","ranged" ("with a sword/fighting" -> melee,
           "with a gun/bow/blaster" -> ranged),
 "objectives": ORDERED mission steps, each {"kind": one of "collect","defeat","reach","race","survive",
               "label": str, "count": int 1..50} — a mission prompt becomes
               [collect the keys] -> [defeat the guards] -> [reach the tower];
               racing/catching/passing N cars -> {"kind":"race","label":"cars","count":N};
               "survive"/"hold out"/"last N minutes against waves" -> {"kind":"survive",
               "label":"the wolf waves","count": SECONDS 30..300} (needs hostile entities),
 "entities": [{"name": simple noun like "dog","cat","horse","wolf","car", "behavior": one of
               "wander","follow","static","hostile","vehicle" (cars/trucks -> "vehicle"),
               "count": int 1..8, "speed": float 0.5..8}]
}
Map the text's setting to the CLOSEST world.name keyword. entities = OTHER creatures/characters besides
the player (companion pet -> "follow"; enemies/monsters/guards the player fights -> "hostile").
"defeat" objectives need hostile entities. Do not invent fields not in the schema."""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


_PLAYER_KINDS = ("samurai", "wizard", "knight", "viking", "dragon", "eagle",
                 "bird", "fox", "dog", "cat", "horse", "wolf", "bear",
                 "woman", "man")


def _keyword_fallback(text: str) -> dict:
    """No-LLM extraction: setting keywords + sky words. Always succeeds."""
    t = text.lower()
    out: dict = {"title": text.strip()[:60] or "Fantasy Studio Game", "world": {}}
    for k in _PLAYER_KINDS:              # first named subject = the player
        if k in t:
            out["player"] = {"name": k}
            break
    for w in ("city", "street", "downtown", "mountain", "canyon", "desert",
              "underwater", "ocean", "sea", "lake", "river", "reef",
              "beach", "swamp", "volcano", "arctic", "tundra", "hill",
              "mars", "moon", "space", "castle", "jungle", "ruin", "cave",
              "park", "garden", "forest", "meadow",
              "countryside", "field", "backyard", "grass"):
        if w in t:
            out["world"]["name"] = ("city" if w in ("street", "downtown")
                                    else "mountains" if w == "mountain"
                                    else "arctic" if w == "tundra"
                                    else "ocean" if w in ("sea", "reef")
                                    else "moon" if w == "space"
                                    else "ruins" if w == "ruin"
                                    else "hills" if w == "hill" else w)
            break
    if out["world"].get("name") == "mars":
        out["world"]["sky"] = "mars"
        out["world"].setdefault("ground_color", [0.55, 0.30, 0.18])
    elif out["world"].get("name") == "moon":
        out["world"]["sky"] = "space"
        out["world"].setdefault("ground_color", [0.42, 0.42, 0.45])
    if any(w in t for w in ("race", "racing", "catch and pass", "overtake", "finish line")):
        import re as _re
        m = _re.search(r"(\d+)\s+(car|truck|racer|opponent)", t)
        out["objectives"] = [{"kind": "race", "label": "cars",
                              "count": int(m.group(1)) if m else 3}]
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
    # combat verbs
    if any(w in t for w in ("gun", "rifle", "blaster", "bow", "shoot", "sniper")):
        out.setdefault("player", {})["attack"] = "ranged"
    elif any(w in t for w in ("sword", "fight", "battle", "slay", "defeat", "katana")):
        out.setdefault("player", {})["attack"] = "melee"
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


# ── R-ITER: conversational editing of an EXISTING game ──────────────────────
_PATCH_SYSTEM = """You EDIT an existing game. Input: the game's current JSON and a change request.
Output ONLY the complete updated JSON object, no markdown. Rules:
- Same schema as the input. Copy every field you are NOT changing verbatim.
- Do not invent or modify 'asset' fields; when you add a NEW entity, omit 'asset'
  (the pipeline resolves or generates meshes from names).
- If the change replaces the player, update player.name (assets re-resolve).
- objectives kinds: collect, defeat, reach, race. entity behaviors: wander,
  follow, static, hostile, vehicle.
- world.sky one of day,sunset,night,overcast,mars,space,dusk; weather none,rain,snow.
- "reward": what the winner gets, or null.
Apply exactly the requested change — nothing else."""


def patch_game_spec(current: dict, change: str, model: str | None = None,
                    verbose: bool = True) -> GameSpec:
    """Apply a plain-language change to an existing (resolved) spec dict.
    The heavy level blob never goes to the LLM; the seed is preserved so an
    edit keeps the SAME world layout — it's an edit, not a reroll. Raises on
    LLM failure (an edit that silently does nothing is worse than an error)."""
    cur = json.loads(json.dumps(current))          # deep copy
    level = (cur.get("world") or {}).pop("level", None)
    seed = cur.get("seed")
    client = OllamaClient(**({"model": model} if model else {}))
    if not client.is_alive():
        raise RuntimeError("Ollama is offline — game editing needs the local LLM")
    msgs = [{"role": "system", "content": _PATCH_SYSTEM},
            {"role": "user", "content": json.dumps(cur)
             + "\n\nCHANGE REQUEST: " + change[:2000]}]
    last_err: Exception | None = None
    for attempt in (1, 2):
        resp = client.chat(msgs)
        raw = (resp.get("content") or resp.get("message", {}).get("content", "")) \
            if isinstance(resp, dict) else str(resp)
        m = _JSON_RE.search(raw)
        try:
            data = json.loads(m.group(0)) if m else None
            if not isinstance(data, dict):
                raise ValueError("no JSON object in reply")
            data["seed"] = seed                     # same world layout
            spec = spec_from_dict(data)
            if verbose:
                print(f"[game] patched spec: '{spec.title}' <- '{change[:60]}'")
            return spec
        except Exception as e:
            last_err = e
            if attempt == 1:
                msgs.append({"role": "assistant", "content": raw[:2000]})
                msgs.append({"role": "user",
                             "content": f"That was invalid ({e}). Reply with ONLY the corrected JSON object."})
    raise ValueError(f"could not apply the edit: {last_err}")
