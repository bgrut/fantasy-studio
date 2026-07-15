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
           "fog_density": float 0..1 (misty/foggy scene -> 0.7-0.9; default 0.5),
           "health_packs": int 0..12 ("health packs/potions on the ground" -> 4),
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
               "eliminate","score", "label": str, "count": int 1..50} — a mission prompt becomes
               [collect the keys] -> [defeat the guards] -> [reach the tower];
               racing/catching/passing N cars -> {"kind":"race","label":"cars","count":N};
               "survive"/"hold out"/"last N minutes against waves" -> {"kind":"survive",
               "label":"the wolf waves","count": SECONDS 30..300} (needs hostile entities);
               "battle royale"/"last one standing"/"eliminate all N rivals" ->
               {"kind":"eliminate","label":"rivals","count": N rivals 2..12};
               soccer/football/"score N goals" -> {"kind":"score","label":"goals","count": N 1..10};
               "hunt N elk/deer..." -> {"kind":"hunt","label":prey noun,"count": N 1..8}
               (prey = entity behavior "flee" - it runs when it hears the player),
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
    # MISSION GRAMMAR (Phase 47): the fallback speaks EVERY verb — an Ollama
    # hiccup must degrade to a playable mission, not an empty stroll (the
    # cat-with-9-lives prompt once lost all its objectives this way)
    import re as _re
    _stop = r"(?=[,.;!]|\s+(?:then|and|before|while|to|at|in|on)\b|$)"

    def _sing1(w: str) -> str:
        if w.endswith("ves"):
            return w[:-3] + "f"          # wolves -> wolf
        if w.endswith("ies"):
            return w[:-3] + "y"          # ponies -> pony
        return w[:-1] if w.endswith("s") and not w.endswith("ss") else w
    obs = out.get("objectives") or []
    ents = out.get("entities") or []
    m = _re.search(r"\b(?:collect|gather|find|pick up|track(?:ing)?\s+down|"
                   r"hunt(?:ing)?\s+for)\s+(\d+)?\s*((?:[a-z]+\s?){1,3}?)" + _stop, t)
    if m and not any(o.get("kind") == "collect" for o in obs):
        obs.append({"kind": "collect", "count": int(m.group(1) or 5),
                    "label": m.group(2).strip()})
    m = _re.search(r"\b(?:defeat|fight|beat|destroy|slay|kill)\s+(\d+)?\s*"
                   r"(?:the\s+)?(?:hostile\s+)?((?:[a-z]+\s?){1,2}?)" + _stop, t)
    if m and not any(o.get("kind") == "defeat" for o in obs):
        n = int(m.group(1) or 3)
        obs.append({"kind": "defeat", "count": n, "label": m.group(2).strip()})
        ents.append({"name": _sing1(m.group(2).strip()), "behavior": "hostile",
                     "count": max(n, 2), "speed": 2.6})
    m = _re.search(r"\bsurvive\b(?:\s+for)?\s*(\d+)?\s*(minute|min|second|sec)?", t)
    if m and "survive" in t and not any(o.get("kind") == "survive" for o in obs):
        secs = int(m.group(1) or 60) * (60 if (m.group(2) or "").startswith("min") else 1)
        obs.append({"kind": "survive", "count": min(secs, 600),
                    "label": "the onslaught"})
    # battle royale (Phase 61): last-one-standing + shrinking storm zone
    m = _re.search(r"\b(?:battle\s*royale|last\s+(?:one|man|creature)\s+standing|"
                   r"eliminate\s+(?:all\s+)?(\d+)?\s*(?:the\s+)?([a-z]+)?)", t)
    if m and not any(o.get("kind") == "eliminate" for o in obs):
        n = int(m.group(1) or 6)
        obs.append({"kind": "eliminate", "count": max(2, min(n, 12)),
                    "label": _sing1(m.group(2) or "rival") + "s"})
    # hunting (Phase 66): stalk fleeing prey - approach quietly, take the shot
    m = _re.search(r"\bhunt(?:ing)?\s+(?:down\s+)?(\d+)?\s*(?:the\s+)?((?:[a-z]+\s?){1,2}?)" + _stop, t)
    if m and m.group(2) and m.group(2).strip() not in ("for", "down")             and not any(o.get("kind") == "hunt" for o in obs):
        n = int(m.group(1) or 3)
        prey = _sing1(m.group(2).strip())
        obs.append({"kind": "hunt", "count": max(1, min(n, 8)), "label": prey})
        ents.append({"name": prey, "behavior": "flee", "count": max(n, 2), "speed": 2.4})
    # sports (Phase 61): score N goals -> ball + goal + counter
    m = _re.search(r"\bscore\s+(\d+)?\s*goals?\b|\b(?:soccer|football)\b", t)
    if m and not any(o.get("kind") == "score" for o in obs):
        obs.append({"kind": "score", "count": max(1, min(int(m.group(1) or 3), 10)),
                    "label": "goals"})
    m = _re.search(r"\b(?:reach|get to|arrive at|escape to|make it to|return to)\s+"
                   r"(?:the\s+)?((?:[a-z]+\s?){1,4}?)" + _stop, t)
    if m and not any(o.get("kind") in ("reach", "race") for o in obs):
        obs.append({"kind": "reach", "label": m.group(1).strip(), "count": 1})
    # hostiles named without a defeat verb ("avoid the hostile wolves")
    m = _re.search(r"\b(?:hostile|avoid(?:ing)?\s+the|chased by|fleeing)\s+"
                   r"(?:hostile\s+)?([a-z]+)", t)
    if m and not any(e.get("behavior") == "hostile" for e in ents):
        ents.append({"name": _sing1(m.group(1)), "behavior": "hostile",
                     "count": 3, "speed": 2.6})
    if obs:
        out["objectives"] = obs
    if ents:
        out["entities"] = ents
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
- Entity "name" must be the CONCRETE creature noun from the request ("wolf",
  "bear", "knight") — NEVER a generic word like "entity" or "creature".
  EXAMPLE: request "add 2 wolves as enemies" -> append to "entities":
  {"name": "wolf", "behavior": "hostile", "count": 2, "speed": 3.0}
- If the change replaces the player, update player.name (assets re-resolve).
- objectives kinds: collect, defeat, reach, race, survive. entity behaviors:
  wander, follow, static, hostile, vehicle.
- world.sky one of day,sunset,night,overcast,mars,space,dusk; weather none,rain,snow.
- "fog_density" 0..1 in world: misty/foggy -> 0.7-0.9, clear air -> 0.2.
- "health_packs" int in world: "add health packs/potions" -> 4-6.
- DIFFICULTY: "make it harder" -> raise hostile entities' speed/count/hp and/or
  lower player.hp; "make it easier" -> the inverse (and/or add health_packs).
- "reward": what the winner gets, or null.
- world.placed_items: objects at EXPLICIT coordinates (the request context
  supplies x/z when the user clicked a spot). Each item:
  {"kind": "book"|"sign"|"chest"|"building"|"rock"|"beacon"|"campfire"|<any noun>,
   "name": "label", "x": <number>, "z": <number>, "interact": "text or null"}.
  "place/put a X here" -> APPEND one item (copy existing items verbatim).
  A book/sign/note that should say something -> its text goes in "interact"
  (the player walks up and presses E to read it). Omit "asset".
Apply exactly the requested change — nothing else."""

_GENERIC_ENTITY_NAMES = {"entity", "entities", "creature", "creatures",
                         "character", "characters", "being", "animal",
                         "animals", "thing", "unit"}


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
            # SAFETY NET: the LLM sometimes names an added entity "entity".
            # Recover the real noun from the change text (library kinds win),
            # else drop it — a junk-named entity resolves to nothing anyway.
            fixed_ents = []
            for e in (data.get("entities") or []):
                nm = str(e.get("name", "")).lower().strip() if isinstance(e, dict) else ""
                if nm in _GENERIC_ENTITY_NAMES:
                    from app.game_export import library as _lib
                    words = [w.strip(".,!?").rstrip("s") for w in change.lower().split()]
                    hit = next((w for w in words if w and _lib.resolve(w)), None)
                    if hit:
                        e["name"] = hit
                        if verbose:
                            print(f"[game] patch: renamed generic entity -> '{hit}'")
                    else:
                        continue                       # unrecoverable — drop
                fixed_ents.append(e)
            data["entities"] = fixed_ents
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
