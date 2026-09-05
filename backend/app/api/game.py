"""Game-mode API (Phase 30): prompt → playable web game, served back to the
frontend. Mirrors the render-jobs UX (submit → poll → play) but games build in
seconds and need NO GPU (library assets), so this works while the video lane's
generation is GPU-blocked.

Jobs are in-memory (games rebuild in ~30s; no DB migration risk). Built games
are served by the /games static mount added in main.py.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

BACKEND_ROOT = Path(__file__).resolve().parents[2]
GAME_JOBS_DIR = BACKEND_ROOT / "renders" / "game_jobs"

_jobs: dict[int, dict] = {}
_next_id = 1
_lock = threading.Lock()


def _record_start(prompt: str) -> int | None:
    """Insert a render_jobs row so game builds show up LIVE in the pipeline
    bar and land in Gallery/Insights like every video run. Never raises."""
    try:
        from app.db import get_conn
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO render_jobs(project_name, topic, template_name, status, provider_name) "
                "VALUES ('game', ?, '__game__', 'rendering', 'GameExport')",
                (prompt,))
            return cur.lastrowid
    except Exception:
        return None


def _record_finish(row_id: int | None, ok: bool, play_url: str | None,
                   error: str | None) -> None:
    if row_id is None:
        return
    try:
        from app.db import get_conn
        with get_conn() as conn:
            conn.execute(
                "UPDATE render_jobs SET status=?, output_url=?, error_text=?, "
                "updated_at=datetime('now') WHERE id=?",
                ("complete" if ok else "failed", play_url, error, row_id))
    except Exception:
        pass


class GameExportRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    player: str | None = None    # override; None = cast from the prompt (extractor)
    godot: bool = False          # also emit a Godot 4 project
    seed: int | None = None      # world-layout seed; None = fresh random level
    base_job_id: int | None = None   # R-ITER: edit THIS game instead of generating anew
    # Phase 42 Inspector: the point (and thing) the user clicked in the game —
    # "place a book here" gets real coordinates instead of guessing
    at_x: float | None = None
    at_z: float | None = None
    at_target: str | None = None     # what was clicked: "ground", "wolf", ...
    # Phase 44: LINE TOOL second point — "place a fence here" tiles segments
    # from (at_x, at_z) to (at_x2, at_z2)
    at_x2: float | None = None
    at_z2: float | None = None
    # Phase 44: STYLE PRESET — user-selected in the studio, never LLM-guessed
    style: str | None = None
    # Phase 45: VIEW PRESET — 3d / topdown (2D Zelda) / side (side-scroller)
    view: str | None = None
    # Phase 44: RULE CHIP toggle — deterministic edit on one placed item
    rule_index: int | None = None
    rule_name: str | None = None
    rule_on: bool | None = None
    # Phase 136: dist-relative or assets/splats path of a Gaussian-splat world
    splat: str | None = None
    pano: str | None = None          # Phase 140: scene-image panorama world
    procedural: bool = False         # build vehicles in code (crisp) vs generated mesh
    # Pivot Move 1: LOCKED LAYERS — sections the user approved; edits carry
    # them forward verbatim ("player" | "world" | "objectives" | "entities" |
    # "entities:<name>"). None = keep the base game's locks.
    locked: list[str] | None = None
    # Pivot Move 5: QUALITY PACK — none/cinematic/noir/golden/retro
    grade: str | None = None


def _expand_design_doc(prompt: str) -> str | None:
    """DESIGN-DOC-ALWAYS (2026-07-29): every build thinks like a game
    designer first — the local LLM expands the one-liner into a compact
    implementation doc (world, hero+abilities, mission beats, enemies,
    special rules), and EXTRACTION consumes the doc. This is the Claude-Code
    pattern: write the plan, then implement it. The user's literal words
    stay authoritative — the doc may only ADD detail, never contradict.
    Returns None (build from the raw prompt, exactly as before) when the
    prompt is already doc-sized or the LLM is unavailable."""
    if len(prompt) > 400:
        return None                      # user already wrote a design doc
    try:
        from app.orchestrator.llm import OllamaClient
        msg = OllamaClient().chat(
            [{"role": "system", "content":
              "You are a AAA game designer. Expand the player's one-line "
              "game idea into a compact implementation doc, max 180 words, "
              "with exactly these sections:\n"
              "WORLD: setting, time of day, weather, mood.\n"
              "HERO: who they are, how they move, signature ability/element "
              "(only if the concept implies one).\n"
              "MISSION: 2-4 concrete objective steps with counts.\n"
              "ENEMIES: kinds, counts, behavior.\n"
              "FEEL: one line on pacing and atmosphere.\n"
              "HARD RULES: never contradict or drop anything the player "
              "stated — every noun, number, and place they wrote must appear "
              "unchanged. Add vivid, specific detail only where they were "
              "silent. Plain text, no markdown headers beyond the section "
              "names."},
             {"role": "user", "content": prompt}],
            temperature=0.6, max_tokens=340)
        doc = (msg or {}).get("content") or ""
        return doc.strip() if len(doc.strip()) > 80 else None
    except Exception:  # noqa: BLE001 — LLM down: raw prompt path unchanged
        return None


_CAR_CLASSES = {
    # class -> parametric silhouette (metres + ratios). Hand-tuned so each
    # reads instantly from a distance: a coupe is long/low, a truck is tall
    # with a short cabin pushed forward.
    "sports":   {"length": 4.35, "width": 1.90, "bodyH": 0.50, "bodyY": 0.44,
                 "cabinLen": 0.40, "cabinH": 0.40, "cabinX": -0.06,
                 "wheelR": 0.33, "wheelBase": 0.32},
    "sedan":    {"length": 4.70, "width": 1.83, "bodyH": 0.62, "bodyY": 0.52,
                 "cabinLen": 0.46, "cabinH": 0.52, "cabinX": -0.03,
                 "wheelR": 0.34, "wheelBase": 0.31},
    "suv":      {"length": 4.75, "width": 1.95, "bodyH": 0.80, "bodyY": 0.66,
                 "cabinLen": 0.52, "cabinH": 0.62, "cabinX": -0.02,
                 "wheelR": 0.40, "wheelBase": 0.30},
    "truck":    {"length": 5.40, "width": 2.02, "bodyH": 0.84, "bodyY": 0.72,
                 "cabinLen": 0.36, "cabinH": 0.66, "cabinX": 0.10,
                 "wheelR": 0.44, "wheelBase": 0.31},
    "van":      {"length": 5.10, "width": 1.98, "bodyH": 0.96, "bodyY": 0.70,
                 "cabinLen": 0.66, "cabinH": 0.70, "cabinX": -0.04,
                 "wheelR": 0.38, "wheelBase": 0.32},
    "taxi":     {"length": 4.72, "width": 1.86, "bodyH": 0.66, "bodyY": 0.54,
                 "cabinLen": 0.48, "cabinH": 0.56, "cabinX": -0.02,
                 "wheelR": 0.35, "wheelBase": 0.31},
}
_CAR_PAINT = {
    "red": 0xb5202a, "blue": 0x1e4f9c, "black": 0x14161a, "white": 0xdfe3e8,
    "silver": 0xa9b0b8, "grey": 0x6d737a, "gray": 0x6d737a, "green": 0x1f6b3a,
    "yellow": 0xd9a410, "orange": 0xcf5a12, "purple": 0x5b2c86,
    "gold": 0xc8a13a, "pink": 0xcf5f8f,
}


def classify_hot_edit(prompt: str) -> dict | None:
    """HOT EDITS (2026-08-05, the studio unlock): an edit that only moves
    runtime dials should never rebuild the world. Rebuilding two minutes to
    change one number is what makes iteration — and therefore quality —
    not happen. Returns a patch the running game applies in a frame, or
    None when the edit needs real geometry (COLD: new terrain, new cast,
    new city, weather, time of day).

    Deterministic on purpose: the LLM is not consulted, so a hot edit can
    never silently re-roll the world the user already approved."""
    import re as _re
    p = (prompt or "").lower().strip()
    if not p:
        return None
    # any word implying new geometry/content forces the cold path
    if _re.search(r"\b(add|place|put|spawn|remove|delete|build|make it a|"
                  r"turn it into|new |another |city|forest|desert|island|"
                  r"night|day|dusk|dawn|sunset|rain|snow|storm|weather|"
                  r"terrain|mountain|river|road|building|house|tree)\b", p):
        return None
    patch: dict = {}

    def _num(default=None):
        m = _re.search(r"(\d+(?:\.\d+)?)", p)
        return float(m.group(1)) if m else default

    more = bool(_re.search(r"\b(more|faster|higher|increase|up|stronger|"
                           r"brighter|tougher|thicker|heavier|denser|"
                           r"harder|bigger)\b", p))
    less = bool(_re.search(r"\b(less|slower|lower|decrease|down|weaker|"
                           r"darker|easier|thinner|lighter|clearer|"
                           r"softer|smaller)\b", p))
    if not (more or less or _re.search(r"\bset\b", p)):
        return None
    k = 1.35 if more else 0.72

    if _re.search(r"\b(fog|haze|mist)\b", p):
        patch["fog_density"] = round(_num(6.0) if _re.search(r"\bset\b", p)
                                     else 6.0 * k, 2)
    if _re.search(r"\b(sun|light|lighting|bright)\b", p):
        patch["sun_intensity"] = round(2.2 * k, 2)
    if _re.search(r"\b(exposure|contrast|dark|bright)\b", p) and "sun" not in p:
        patch["exposure"] = round(1.0 * k, 2)
    if _re.search(r"\b(enemy|enemies|wolves|wolf|hostile|guard|rival)\b", p):
        if _re.search(r"\b(hp|health|tough|strong)\b", p):
            patch["enemy_hp"] = int(max(1, round(3 * k)))
        else:
            patch["enemy_speed"] = round(2.6 * k, 2)
    elif _re.search(r"\b(hp|health|lives|tough)\b", p):
        patch["player_hp"] = int(max(1, round(_num(5) if _re.search(r"\bset\b", p)
                                              else 5 * k)))
    elif _re.search(r"\b(speed|run|walk|move|fast|slow)\b", p):
        patch["walk_speed"] = round(2.0 * k, 2)
        patch["run_speed"] = round(5.0 * k, 2)
    return patch or None


def _infer_car_params(prompt: str, cast: str) -> dict | None:
    """Parametric-car params from the user's words (2026-08-04). Research
    verdict: cars are hard-surface parametric objects — image-to-3D melts
    rooflines and smears wheels on every single one. Built-in-code cars are
    crisp by construction; the prompt picks class + paint."""
    import re as _re
    t = (prompt + " " + (cast or "")).lower()
    if not _re.search(r"\b(car|truck|van|taxi|cab|suv|jeep|sedan|coupe|"
                      r"pickup|lorry|ferrari|lamborghini|porsche|mustang|"
                      r"corvette|f150|f-150|racer|racecar|race car)\b", t):
        return None
    if _re.search(r"\b(truck|pickup|f150|f-150|lorry)\b", t):
        cls = "truck"
    elif _re.search(r"\b(van|minivan|bus)\b", t):
        cls = "van"
    elif _re.search(r"\b(suv|jeep|4x4|crossover)\b", t):
        cls = "suv"
    elif _re.search(r"\b(taxi|cab)\b", t):
        cls = "taxi"
    elif _re.search(r"\b(sports?|ferrari|lamborghini|porsche|mustang|"
                    r"corvette|coupe|racer|racecar|race car|supercar)\b", t):
        cls = "sports"
    else:
        cls = "sedan"
    p = dict(_CAR_CLASSES[cls])
    paint = 0xf2c200 if cls == "taxi" else _CAR_CLASSES and 0xb5202a
    for name, hexv in _CAR_PAINT.items():
        if _re.search(rf"\b{name}\b", t):
            paint = hexv
            break
    p["paint"] = paint
    p["_class"] = cls
    return p


def _infer_vfx(prompt: str) -> str | None:
    """Ability-VFX element from the game's THEME. Two-gate design: the text
    must signal a magical/elemental concept (bender, mage, dragon, wraith…)
    AND name an element. Word-boundary regexes kill false positives —
    'fireflies' must never set a fox on fire."""
    import re as _re
    p = prompt.lower()

    def has(w: str) -> bool:
        return _re.search(rf"\b{w}", p) is not None

    magical = any(has(w) for w in (
        "bender", "bending", "mage", "wizard", "sorcer", "witch", "warlock",
        "elemental", "magic", "summon", "avatar", "spell", "druid",
        "necromancer", "enchant", "mystic", "shaman"))
    creature = any(has(w) for w in (
        "dragon", "phoenix", "wraith", "golem", "demon", "spirit", "ghost",
        "genie", "djinn", "yeti"))
    if not (magical or creature):
        return None
    if any(has(w) for w in ("water", "tide", "wave", "aqua", "ocean")):
        return "water"
    if _re.search(r"\bfire(?!fl)", p) or any(has(w) for w in
            ("flame", "ember", "lava", "inferno", "phoenix")):
        return "fire"
    if any(has(w) for w in ("frost", "ice ", "icy", "snow", "blizzard", "glacier", "yeti")):
        return "frost"
    if any(has(w) for w in ("lightning", "thunder", "electric", "storm")):
        return "electric"
    if any(has(w) for w in ("shadow", "dark", "void", "necromancer", "wraith", "ghost", "demon")):
        return "shadow"
    if any(has(w) for w in ("nature", "druid", "forest spirit", "vine", "leaf", "bloom")):
        return "nature"
    if _re.search(r"\bwind\b", p) or any(has(w) for w in
            ("air bend", "airbend", "gale", "tempest", "sky spirit")):
        return "wind"
    if magical:
        return "arcane"        # a wizard with no named element still glows
    return "fire" if has("dragon") else None


def _run_job(job_id: int, req: GameExportRequest) -> None:
    job = _jobs[job_id]
    row_id = _record_start(req.prompt)     # metrics: live row in the pipeline bar

    def stage(s: str) -> None:
        job["stage"] = s
        job["updated_at"] = time.time()

    try:
        from app.game_export import library
        from app.game_export.extractor import extract_game_spec
        from app.game_export.dressing import game_scatter
        from app.game_export.spec import ScatterSpec
        from app.game_export.verify_game import verify_dist
        from app.game_export.web_exporter import export_web_game

        # R-ITER: a base_job_id means EDIT that game — patch its saved spec
        # with the change request instead of extracting from scratch. Same
        # seed = same world; cached assets = the edit lands in seconds.
        base_spec = None
        if req.base_job_id is not None:
            import json as _json
            base_spec = (_jobs.get(req.base_job_id) or {}).get("spec_resolved")
            if base_spec is None:
                p = GAME_JOBS_DIR / f"job_{req.base_job_id}" / "spec_full.json"
                if p.exists():
                    base_spec = _json.loads(p.read_text(encoding="utf-8"))
            if base_spec is None:
                raise RuntimeError(
                    f"game #{req.base_job_id} has no saved spec to edit — rebuild it once first")

        if base_spec is not None:
            stage("applying your edit")
            from app.game_export.spec import spec_from_dict as _sfd
            spec = None
            # RULE CHIP toggle (Phase 44): fully deterministic — flip one rule
            # on one placed item, re-export. No LLM anywhere near it.
            if (req.rule_index is not None and req.rule_name
                    and req.rule_on is not None):
                import copy as _copy
                cur = _copy.deepcopy(base_spec)
                items = (cur.get("world") or {}).get("placed_items") or []
                if not (0 <= req.rule_index < len(items)):
                    raise RuntimeError("rule toggle: placed item index out of range")
                it = items[req.rule_index]
                rl = [r for r in (it.get("rules") or []) if r != req.rule_name]
                if req.rule_on:
                    rl.append(req.rule_name)
                it["rules"] = rl
                spec = _sfd(cur)
                job.setdefault("notes", []).append(
                    f"rule '{req.rule_name}' {'ON' if req.rule_on else 'OFF'} "
                    f"for '{it.get('name') or it.get('kind')}'")
            # INSPECTOR FAST PATH: "place a book here" with clicked coordinates
            # is fully deterministic — no LLM round-trip, the edit lands in the
            # time it takes to re-export. Longer sentences still go to the LLM.
            if req.at_x is not None and req.at_z is not None:
                import copy as _copy
                import re as _re
                m = _re.match(
                    r"^\s*(?:please\s+)?(?:place|put|add|drop|spawn)\s+"
                    r"(?:an|a|the|another|some)?\b\s*(.+)$",
                    req.prompt.strip(), _re.IGNORECASE)
                if m:
                    rest = m.group(1)
                    interact = None
                    low = rest.lower()
                    for sep in (" that says ", " which says ", " saying ",
                                " that reads ", " with hint ", " with the hint ",
                                " with text ", " that tells "):
                        if sep in low:
                            i = low.index(sep)
                            interact = rest[i + len(sep):].strip().strip("\"'“”‘’.") or None
                            rest = rest[:i]
                            break
                    # LOCATIVE STRIPPING (2026-08-06). This was five literal
                    # phrases, so "add storefront at the point i picked" left a
                    # six-word noun, missed the <=3 word gate below, and fell
                    # through to the LLM — which regenerates the spec and threw
                    # an entire OSM city away to add one shop. A surgical
                    # append must not depend on the user phrasing "here"
                    # exactly: the coordinates are already attached, so the
                    # locative carries no information and is pure noise.
                    for _pat in (
                        r"\bwhere\s+i\s+(clicked|picked|selected|pointed).*$",
                        r"\b(at|on|in|to)\s+(this|that|the|my)?\s*"
                        r"(selected|clicked|picked|chosen|marked)?\s*"
                        r"(point|spot|place|location|marker|pin|position|pick)\b.*$",
                        r"\b(right\s+)?(here|there)\b",
                    ):
                        rest = _re.sub(_pat, "", rest, flags=_re.IGNORECASE)
                    noun = rest.strip(" .!,\"'")
                    # strip PURPOSE clauses — "a fence to block the dogs" is
                    # still just a fence (the blocking comes free: colliders)
                    for cut in (" to ", " so ", " for ", " between ",
                                " from ", " because "):
                        if cut in noun.lower():
                            noun = noun[:noun.lower().index(cut)]
                    noun = noun.strip(" .!,\"'")
                    if noun and len(noun.split()) <= 3:
                        w = noun.split()[-1].lower()
                        kind = (w[:-3] + "y") if w.endswith("ies") else \
                               (w[:-1] if w.endswith("s") and not w.endswith("ss") else w)
                        cur = _copy.deepcopy(base_spec)
                        items = cur.setdefault("world", {}).setdefault("placed_items", [])
                        if req.at_x2 is not None and req.at_z2 is not None:
                            # LINE TOOL: tile segments from A to B ("place a
                            # fence here" spans the two clicked points)
                            import math as _m
                            dx = req.at_x2 - req.at_x
                            dz = req.at_z2 - req.at_z
                            dist = _m.hypot(dx, dz)
                            seg = 2.0
                            # floor keeps spacing >= seg so the de-overlap
                            # nudge never scatters a deliberate line run
                            n = max(1, min(48, int(dist / seg)))
                            yaw = _m.degrees(_m.atan2(-dz, dx))
                            for i in range(n):
                                t = (i + 0.5) / n
                                items.append({
                                    "kind": kind, "name": noun.lower(),
                                    "x": round(req.at_x + dx * t, 2),
                                    "z": round(req.at_z + dz * t, 2),
                                    "yaw_deg": round(yaw, 1),
                                    "interact": interact if i == n // 2 else None})
                            job.setdefault("notes", []).append(
                                f"placed {n} × '{noun}' along your line ({dist:.0f} m)")
                        else:
                            # FACE THE STREET (2026-08-06): a shopfront dropped
                            # at the right spot but at an arbitrary angle still
                            # reads as a mistake — real buildings front onto the
                            # road. Structures snap parallel to the nearest kerb;
                            # loose props (books, chests) keep their free angle,
                            # because a crate askew in an alley is correct.
                            _drop = {"kind": kind, "name": noun.lower(),
                                     "x": round(req.at_x, 2),
                                     "z": round(req.at_z, 2),
                                     "interact": interact}
                            _STRUCT = ("building", "shop", "store", "storefront",
                                       "shopfront", "cafe", "restaurant", "bar",
                                       "office", "tower", "house", "hut", "stall",
                                       "kiosk", "wall", "fence", "sign", "billboard")
                            if any(w in (kind + " " + noun).lower() for w in _STRUCT):
                                _roads = ((cur.get("world") or {}).get("level")
                                          or {}).get("osm", {}).get("roads")
                                if _roads:
                                    from app.game_export.level import nearest_road_yaw
                                    _ry = nearest_road_yaw(_roads, req.at_x, req.at_z)
                                    if _ry is not None:
                                        _drop["yaw_deg"] = _ry
                                        job.setdefault("notes", []).append(
                                            f"'{noun}' aligned to the street ({_ry:.0f}°)")
                            items.append(_drop)
                            job.setdefault("notes", []).append(
                                f"placed '{noun}' at ({req.at_x:.1f}, {req.at_z:.1f})"
                                + (" with a readable hint" if interact else ""))
                        spec = _sfd(cur)
            if spec is None:
                from app.game_export.extractor import patch_game_spec
                change = req.prompt
                if req.at_x is not None and req.at_z is not None:
                    tgt = f" on the {req.at_target}" if req.at_target else ""
                    change += (
                        f"\n\nCONTEXT: the user clicked world position "
                        f"x={req.at_x:.1f}, z={req.at_z:.1f}{tgt}. Words like "
                        f"'here'/'this spot'/'this one' refer to that selection; "
                        f"use these exact coordinates for any placed_items you add.")
                elif req.at_target:
                    change += (f"\n\nCONTEXT: the user clicked the {req.at_target} — "
                               f"'this'/'it' refers to that.")
                # Pivot Move 1 — LOCKED LAYERS: tell the LLM what is frozen…
                _locked = list(req.locked if req.locked is not None
                               else (base_spec.get("locked") or []))
                if _locked:
                    change += ("\n\nLOCKED (approved by the user — copy these "
                               "sections from the base spec VERBATIM, never "
                               "modify them): " + ", ".join(_locked))
                spec = patch_game_spec(base_spec, change, verbose=False)
                # …and then ENFORCE it deterministically: whatever the LLM
                # did, locked sections are restored from the base game. A
                # lock is a promise, not a suggestion.
                try:
                    from ..game_export.spec import (PlayerSpec as _PS,
                                                    WorldSpec as _WS,
                                                    EntitySpec as _ES,
                                                    ObjectiveSpec as _OS)
                    for _sec in _locked:
                        if _sec == "player" and base_spec.get("player"):
                            spec.player = _PS(**base_spec["player"])
                        elif _sec == "world" and base_spec.get("world"):
                            spec.world = _WS(**base_spec["world"])
                        elif _sec == "objectives" and base_spec.get("objectives") is not None:
                            spec.objectives = [_OS(**o) for o in base_spec["objectives"]]
                        elif _sec == "entities" and base_spec.get("entities") is not None:
                            spec.entities = [_ES(**e) for e in base_spec["entities"]]
                        elif _sec.startswith("entities:"):
                            _nm = _sec.split(":", 1)[1].strip().lower()
                            _base_e = next((e for e in (base_spec.get("entities") or [])
                                            if str(e.get("name", "")).lower() == _nm), None)
                            if _base_e:
                                _kept = [e for e in spec.entities
                                         if e.name.lower() != _nm]
                                spec.entities = _kept + [_ES(**_base_e)]
                    spec.locked = _locked
                except Exception:
                    pass
                # STYLE + VIEW ARE SACRED (2026-07-08): the LLM must never
                # drop or drift them during an edit — carry the base game's
                # choices forward; only the explicit-word overrides below may
                # change them
                try:
                    spec.style = base_spec.get("style", spec.style) or spec.style
                    spec.view = base_spec.get("view", spec.view) or spec.view
                    spec.grade = base_spec.get("grade", spec.grade) or spec.grade
                except Exception:
                    pass
                # THE WORLD IS SACRED TOO (2026-07-28): "give the knight 3
                # more hp" once moved the fight OUTSIDE the castle — the LLM
                # re-imagined the scenery during an unrelated edit. Unless the
                # edit explicitly talks about the world, every world field and
                # the SEED carry forward from the base game; only placed_items
                # (LLM may add) and the deterministic sky/weather/style word
                # overrides below may differ.
                _wl = req.prompt.lower()
                _world_words = (
                    "world", "setting", "scene", "scenery", "environment",
                    "map", "terrain", "ground", "move to", "teleport",
                    "city", "forest", "desert", "ocean", "island", "castle",
                    "dungeon", "mansion", "arena", "stadium", "village",
                    "mountain", "cave", "indoor", "outdoor", "outside",
                    "inside", "interior", "sky", "weather", "night", "day",
                    "sunset", "snow", "rain", "storm", "fog")
                if not any(w in _wl for w in _world_words):
                    _keep_items = spec.world.placed_items
                    for k, v in (base_spec.get("world") or {}).items():
                        if k == "placed_items":
                            continue
                        try:
                            setattr(spec.world, k, _copy.deepcopy(v))
                        except Exception:
                            pass
                    spec.world.placed_items = _keep_items
                try:
                    spec.seed = base_spec.get("seed", spec.seed) or spec.seed
                except Exception:
                    pass
                # THE USER'S EXPLICIT WORDS WIN (2026-07-08): when an edit
                # literally names a sky or weather, that beats whatever the
                # LLM picked — "make it a starry night" once came back as
                # sky="space" (washed-out airless glare, not night).
                import re as _re
                _cl = req.prompt.lower()
                for w, sky in (("starry", "night"), ("night", "night"),
                               ("midnight", "night"), ("sunrise", "sunset"),
                               ("dawn", "sunset"), ("sunset", "sunset"),
                               ("dusk", "dusk"), ("twilight", "dusk"),
                               ("noon", "day"), ("daytime", "day"), ("day", "day"),
                               ("overcast", "overcast"), ("cloudy", "overcast"),
                               ("mars", "mars"), ("outer space", "space")):
                    if _re.search(rf"\b{_re.escape(w)}\b", _cl):
                        if spec.world.sky != sky:
                            job.setdefault("notes", []).append(
                                f"sky set to {sky} (your words beat the AI's pick)")
                        spec.world.sky = sky
                        break
                for w, wx in (("blizzard", "snow"), ("snowstorm", "snow"),
                              ("snow", "snow"), ("rain", "rain"),
                              ("drizzle", "rain"), ("storm", "rain"),
                              ("clear sky", "none"), ("clear skies", "none")):
                    if _re.search(rf"\b{_re.escape(w)}\b", _cl):
                        spec.world.weather = wx
                        break
                # style words in edits are deterministic too ("make it horror")
                for w, st in (("horror", "horror"), ("scary", "horror"),
                              ("spooky", "horror"), ("anime", "anime"),
                              ("cartoon", "cartoon"), ("toon", "cartoon"),
                              ("cel-shaded", "cartoon"), ("pixel", "pixel"),
                              ("retro", "pixel"), ("8-bit", "pixel"),
                              ("low-poly", "lowpoly"), ("low poly", "lowpoly"),
                              ("photoreal", "default"), ("realistic", "default")):
                    if _re.search(rf"\b{_re.escape(w)}\b", _cl):
                        spec.style = st
                        job.setdefault("notes", []).append(f"style set to {st}")
                        break
                # view words in edits are deterministic too ("make it top-down")
                for w, vw in (("top-down", "topdown"), ("top down", "topdown"),
                              ("topdown", "topdown"), ("overhead", "topdown"),
                              ("side-scroller", "side"), ("side scroller", "side"),
                              ("sidescroller", "side"), ("platformer", "side"),
                              ("side view", "side"), ("2d", "topdown"),
                              ("3d", "3d"), ("third person", "3d")):
                    if _re.search(rf"\b{_re.escape(w)}\b", _cl):
                        spec.view = vw
                        job.setdefault("notes", []).append(f"view set to {vw}")
                        break
                # SAFETY NET: LLM-added placed items sometimes forget the
                # coordinates from context — new items land where you clicked
                if req.at_x is not None and req.at_z is not None:
                    base_n = len(((base_spec.get("world") or {})
                                  .get("placed_items")) or [])
                    for it in spec.world.placed_items[base_n:]:
                        if abs(it.x) < 1e-6 and abs(it.z) < 1e-6:
                            it.x, it.z = round(req.at_x, 2), round(req.at_z, 2)
            job["title"] = spec.title
            job["edited_from"] = req.base_job_id
        else:
            stage("designing")
            # DESIGN-DOC-ALWAYS: think like a designer, then build. The doc
            # rides ABOVE the user's prompt so their words stay the contract.
            _doc = _expand_design_doc(req.prompt)
            if _doc:
                job.setdefault("notes", []).append("design doc written")
                job["design_doc"] = _doc
            stage("extracting")
            # DETERMINISM FIX (2026-07-29): extraction reads ONLY the user's
            # raw prompt — feeding the doc in let it invent creatures (a
            # 'snow warbler' with unverified orientation) and fragment
            # objectives. The doc now enriches FLAVOR ONLY below: narrative
            # intro + title. Casting, objectives, and world verbs stay a
            # pure function of the user's words.
            spec = extract_game_spec(req.prompt, verbose=False)
            if _doc:
                try:
                    import re as _re2
                    # narrative intro: WORLD flavor + FEEL line from the doc
                    mW = _re2.search(r"WORLD:\s*(.+?)(?:\n[A-Z]{2,}|$)", _doc, _re2.S)
                    mF = _re2.search(r"FEEL:\s*(.+?)(?:\n[A-Z]{2,}|$)", _doc, _re2.S)
                    intro = " ".join(s.strip().replace("\n", " ")
                                     for s in ((mW.group(1) if mW else ""),
                                               (mF.group(1) if mF else "")) if s.strip())
                    if intro and not getattr(spec, "intro", None):
                        spec.intro = intro[:280]
                except Exception:
                    pass
        # ── ABILITY VFX (2026-07-29): element aura inferred from the THEME —
        # deterministic keywords, and gated so it only fires when the
        # character concept is actually magical/elemental (a waterbender, a
        # fire dragon, a storm mage) — never bolted onto a plain knight.
        try:
            spec.player.vfx = _infer_vfx(
                (getattr(spec, "prompt", "") or "") + " " + req.prompt)
        except Exception:
            pass
        # SWIM-MODE GUARD (2026-07-29): 'water bender' made the LLM cast
        # mode=swim — a no-collision hover that walks through mountains.
        # Swim is only legal when the prompt actually puts us IN water.
        try:
            _pl = req.prompt.lower()
            if spec.player.mode == "swim" and not any(
                    w in _pl for w in ("ocean", "underwater", "sea", "dive",
                                       "reef", "lake", "swim", "whale",
                                       "fish", "dolphin", "shark")):
                spec.player.mode = "walk"
        except Exception:
            pass
            job["title"] = spec.title
        # STYLE IS THE USER'S CHOICE (Phase 44): the studio's style chips set
        # it explicitly — the LLM never guesses it, so it's never wrong
        # ART DIRECTION IS NOW PROMPT-DRIVEN (2026-08-30). Style used to come
        # only from the studio dropdown, which defaults to Photoreal — so every
        # game built without touching that control shipped identical art
        # direction, and "they all look the same" was structurally true. The
        # extractor now picks one; an explicit user choice below still wins.
        if not req.style and spec.style and spec.style != "default":
            job.setdefault("notes", []).append(
                f"art direction: {spec.style} (chosen from your prompt — "
                f"pick a style in the studio to override)")
        if req.style:
            try:
                spec.style = req.style        # pydantic validates the literal
            except Exception:
                job.setdefault("notes", []).append(
                    f"unknown style '{req.style}' — kept {spec.style}")
        # A STYLE IS A GAME, NOT A COAT OF PAINT (2026-09-05). Every world we
        # made was a heightfield seen from a third-person follow camera, so
        # seventeen styles were seventeen paint jobs on ONE game — "always on
        # the same plane", exactly as the user put it. The games these looks
        # are named after are not all third-person: Limbo is a side-scroller,
        # Alto's Odyssey is a side-scroller, Tengami is a side-on pop-up book,
        # Monument Valley and the 2D-Zelda pixel lineage are overhead. Binding
        # a default CAMERA to the look changes what the game IS, not merely
        # how it is lit, and it costs nothing because the view presets have
        # existed all along and no style ever reached for one.
        #
        # Only a default: an explicit pick from the studio still wins below.
        _STYLE_VIEW = {
            "noir": "side",        # Limbo
            "comic": "side",       # panels read across
            "papercraft": "side",  # Tengami's folding pages
            "dunescape": "side",   # Alto's Odyssey
            "pixel": "topdown",    # the 2D Zelda lineage
            "storybook": "topdown",
        }
        _sv = _STYLE_VIEW.get(spec.style or "default")
        if _sv and not req.view:
            spec.view = _sv
            job.setdefault("notes", []).append(
                f"{spec.style} plays as a {_sv} game — this look's camera is "
                f"part of it (pick a view in the studio to override)")
        if req.view:
            try:
                spec.view = req.view
            except Exception:
                job.setdefault("notes", []).append(
                    f"unknown view '{req.view}' — kept {spec.view}")
        if req.grade:
            try:
                spec.grade = req.grade        # pydantic validates the literal
            except Exception:
                job.setdefault("notes", []).append(
                    f"unknown grade '{req.grade}' — kept {spec.grade}")
        if req.locked is not None and base_spec is None:
            spec.locked = req.locked          # fresh build with locks pre-set
        # "a cat with 9 lives" → 9 HP: numbers the user wrote are game facts
        import re as _re9
        _m9 = _re9.search(r"(\d+)\s*lives\b", req.prompt.lower())
        if _m9:
            spec.player.hp = max(1, min(20, int(_m9.group(1))))
            job.setdefault("notes", []).append(
                f"{_m9.group(1)} lives → {spec.player.hp} HP")
        # SNOW IS BRIGHT: snowy scenes must have snow-colored ground — that's
        # what reflects the moonlight and makes winter nights luminous. The
        # LLM often picks a dark ground for "snowy night" and the whole scene
        # drowns (the too-dark Foxfire Quest, 2026-07-07).
        _snowy = (spec.world.weather == "snow"
                  or any(w in (spec.world.name or "").lower()
                         for w in ("arctic", "snow", "tundra", "winter")))
        if _snowy:
            g = spec.world.ground_color
            spec.world.ground_color = [g[0] + (0.78 - g[0]) * 0.8,
                                       g[1] + (0.80 - g[1]) * 0.8,
                                       g[2] + (0.86 - g[2]) * 0.8]
        # READABILITY FLOOR: no edit or extraction may produce a near-black
        # ground — "make it darker" should darken the MOOD (sky palette does
        # that), never drown the world. Applies to fresh builds AND edits.
        g = spec.world.ground_color
        _lum = 0.299 * g[0] + 0.587 * g[1] + 0.114 * g[2]
        if _lum < 0.14:
            k = 0.14 / max(_lum, 1e-3)
            spec.world.ground_color = [min(c * k, 1.0) for c in g]

            # LEVEL VARIETY: every FRESH build gets a new world layout (edits
            # keep their world). Pass an explicit seed to reproduce a level.
            import random as _random
            spec.seed = req.seed if req.seed is not None else _random.randint(1, 999_999)
        job["seed"] = spec.seed

        stage("resolving assets")
        # SUBJECT IS THE HERO (2026-07-08): the prompt's own words outrank
        # the LLM's cast — "a wolf roaming the mountains" once played as a
        # FOX with a wandering wolf NPC. If the extracted player noun never
        # appears in the prompt, promote the first prompt noun that resolves
        # in the library (and drop its duplicate non-hostile entity).
        if base_spec is None and req.player is None and spec.player.name:
            _pl = spec.player.name.lower()
            _ptext = req.prompt.lower()
            if _pl not in _ptext:
                _skip = {"firefly", "fireflies", "snowflake", "snowflakes",
                         "beacon", "beacons", "star", "stars"}
                cand = None
                for wd in _ptext.replace(",", " ").replace(".", " ").split():
                    w = (wd[:-3] + "y") if wd.endswith("ies") else \
                        (wd[:-1] if wd.endswith("s") and not wd.endswith("ss") else wd)
                    if w in _skip or len(w) < 3:
                        continue
                    if library.resolve(w):
                        cand = w
                        break
                if cand and cand != _pl:
                    job.setdefault("notes", []).append(
                        f"hero cast corrected: '{cand}' is your prompt's subject "
                        f"(the AI said '{_pl}')")
                    spec.player.name = cand
                    spec.entities = [e for e in spec.entities
                                     if not (e.name.lower() == cand
                                             and e.behavior in ("wander", "follow"))]
        # PLAYER CASTING (accuracy-first, like the video hero): explicit
        # override > the prompt's extracted subject > man. Falls through the
        # ladder with a visible note whenever the cast changes.
        want = (req.player or spec.player.name or "man").strip().lower()
        from app.game_export.bake import ensure_playable
        from app.game_export.generate import guess_pattern
        # THE CAST HAS TO MATCH THE ART DIRECTION (2026-09-05). A photoreal
        # scanned human standing in a flat illustrated world is the same clash
        # that put low-poly trees in a photoreal one, and no material trick
        # fixes a silhouette. For the FLAT looks, a generic human is recast
        # from the blocky roster, which is drawn in the same language as the
        # scenery.
        #
        # Deliberately narrow. Only bare, interchangeable nouns are recast: a
        # "wizard", "samurai" or "detective" is a specific character the user
        # asked for by name and keeps its own mesh, because losing that
        # identity would be a worse bug than the style clash. Photoreal styles
        # are never touched.
        _FLAT_LOOKS = {"cartoon", "illustrated", "watercolor", "storybook",
                       "kawaii", "comic", "papercraft", "lowpoly"}
        _GENERIC_HUMAN = {"man", "woman", "person", "human", "guy", "girl",
                          "boy", "villager", "farmer", "traveller", "traveler",
                          "adventurer", "hiker", "settler", "trader", "guard",
                          "scout", "worker", "miner", "sailor", "wanderer",
                          "climber", "camper", "kid", "child"}
        _BLOCKY = ["blocky villager", "blocky adventurer", "blocky traveller",
                   "blocky farmer", "blocky scout", "blocky settler",
                   "blocky trader", "blocky worker", "blocky hiker"]
        try:
            if (spec.style in _FLAT_LOOKS
                    and (want or "").strip().lower() in _GENERIC_HUMAN):
                _pick = _BLOCKY[int(spec.seed or 0) % len(_BLOCKY)]
                if library.resolve(_pick):
                    want = _pick
                    spec.player.anims = {
                        "idle": "idle", "walk": "walk", "run": "sprint",
                        "attack": "attack-melee-right", "die": "die",
                    }
                    job.setdefault("notes", []).append(
                        f"cast recast to the blocky {spec.style} look — a "
                        f"scanned human in a flat world is a style clash "
                        f"(name a specific character to keep a detailed one)")
        except Exception:  # noqa: BLE001
            pass
        cast = want
        pattern = guess_pattern(want)
        # vehicles DRIVE, flyers FLY, swimmers SWIM — all play as static
        # meshes (no rig); everything else needs the rigged+animated bake
        if pattern in ("vehicle", "flying", "aquatic", "static"):
            player_glb = library.resolve(want)
        else:
            # proc modules are code, not meshes — no rig bake to run
            _pre = library.resolve(want)
            player_glb = _pre if (_pre or "").startswith("proc:") \
                else ensure_playable(want, verbose=False)
        if (player_glb or "").startswith("proc:"):
            # sculpted module: authored in metres with named drive pivots.
            # The roadster is 1.135m tall; the camera band derives from this.
            spec.player.asset = player_glb
            spec.player.height_m = 1.15
            spec.player.mode = spec.player.mode or "drive"
            job.setdefault("notes", []).append(
                f"hero is a sculpted proc module ({player_glb}) — wheels steer "
                "and spin on real pivots (img2threejs lane)")
        if not player_glb:
            # THE VISION PATH (primary): unknown hero → SDXL image → 3D mesh →
            # library → playable. This is how the pipeline is MEANT to work and
            # it runs on CPU too (~25-30 min once, then cached forever — the cat
            # and fox were both born this way). We ALWAYS attempt it; a GPU just
            # makes it faster/better. Only a genuine generation FAILURE falls
            # through to the honest same-species stand-in below (never a
            # man-with-a-sword). FS_CPU_CHARGEN=0 disables CPU generation.
            try:
                from app.game_export.generate import ensure_asset, gpu_available
                _eta = ("~6 min on your GPU" if gpu_available()
                        else "~25-30 min on CPU")
                stage(f"creating '{want}' — image → 3D mesh "
                      f"(first time only; {_eta}, then cached forever)")
                ensure_asset(want, verbose=False)
                player_glb = (library.resolve(want)
                              if pattern in ("vehicle", "flying", "aquatic", "static")
                              else ensure_playable(want, verbose=False))
                if player_glb:
                    job.setdefault("notes", []).append(
                        f"'{want}' was CREATED for this game and saved to your library")
            except Exception as ge:
                job.setdefault("notes", []).append(
                    f"player '{want}' generation failed ({type(ge).__name__}) — "
                    f"using a stand-in for now; re-run to try again")
        # A RACE PUTS YOU IN A CAR (2026-08-25): "a courier races 5 rivals"
        # cast a human, so the player stood at the start line on foot while
        # the rivals drove past (user report: "i wasnt even in the car??").
        # A race objective implies a seat: a walk-mode hero in a racing game
        # is promoted to pattern "vehicle" so the whole hardened branch below
        # (drive mode, speed floors, parametric car, metric height) applies
        # unchanged. The hero's NAME survives for the HUD and intro.
        _race_seated = False
        if (any(o.kind == "race" for o in spec.objectives)
                and pattern != "vehicle"
                and (spec.player.mode or "walk") == "walk"
                and player_glb):
            pattern = "vehicle"
            _race_seated = True
            job.setdefault("notes", []).append(
                f"'{spec.player.name}' races on wheels — a race objective "
                "implies a driver's seat, so the hero starts in a car")
        if player_glb and pattern == "vehicle":
            spec.player.mode = "drive"
            # A DRIVE-MODE CAR'S NO-SHIFT TOP SPEED *IS* walk_speed
            # (2026-08-06). These tests used to fire only when the model had
            # left the schema default untouched, so an unlucky roll of
            # walk_speed 0.1 shipped a racing demo you could outwalk — same
            # prompt, same code, dead car, and nothing in the job notes to say
            # why. Below a jogging pace is not a car, so the floor is enforced
            # whatever the model asked for.
            if spec.player.walk_speed < 7.0:
                spec.player.walk_speed = 9.0                 # cruise
            if spec.player.run_speed < 14.0:
                spec.player.run_speed = 19.0                 # boost
            # PARAMETRIC CARS (2026-08-04): a car is a HARD-SURFACE
            # parametric object — image-to-3D melts rooflines and smears
            # wheels on every single one. Vehicles are now BUILT IN CODE
            # (research: this is what the good three.js GTA demos do);
            # the prompt picks class + paint. Animals keep the mesh path.
            try:
                # a promoted racer HAS no vehicle mesh — without the
                # parametric car he would drive his own body laid on its
                # side, so the seat promotion overrides the procedural opt-in
                _cp = _infer_car_params(req.prompt, spec.player.name or "") \
                    if (req.procedural or _race_seated) else None
                # The fallback fires for BOTH failure paths: the promoted
                # racer (human hero, race objective) AND the misclassified
                # one — 'courier' classifies as a vehicle (courier van), takes
                # this branch naturally, and would drive his own body laid on
                # its side. If there is a race and the subject's NAME carries
                # no car word, he gets the sedan's full geometry — the height
                # line below reads bodyY/bodyH, so a partial dict would throw.
                if not _cp and (
                        _race_seated
                        or (any(o.kind == "race" for o in spec.objectives)
                            and _infer_car_params(spec.player.name or "", "")
                            is None)):
                    _cp = _infer_car_params("car", "car")
                if _cp:
                    _cls = _cp.pop("_class", "sedan")
                    spec.player.car_params = _cp
                    spec.player.yaw_offset_deg = 0.0   # built nose +X
                    # TRUE SCALE: the runtime scales any model to height_m,
                    # so a 1.5m default inflated the metric-built car (it
                    # towered over the rivals, verified). Height comes from
                    # the params themselves now — real car proportions.
                    spec.player.height_m = round(
                        _cp["bodyY"] + _cp["bodyH"] * 0.75 + _cp["cabinH"], 2)
                    job.setdefault("notes", []).append(
                        f"parametric {_cls} built in code — crisp panels, "
                        f"round wheels, real glass (no mesh generation)")
            except Exception:
                pass
        # KIT CHARACTERS NAME THEIR CLIPS THEIR OWN WAY (2026-09-04). The
        # Kenney blocky cast ships 27 authored animations per character, but
        # calls the run "sprint" and the swing "attack-melee-right". The
        # runtime resolves clips through player.anims, so the mapping is all
        # that is needed — without it a blocky hero would sprint by playing
        # whatever clip happened to be first in the file.
        try:
            if player_glb and "kc_" in str(player_glb).replace("\\", "/"):
                spec.player.anims = {
                    "idle": "idle", "walk": "walk", "run": "sprint",
                    "attack": "attack-melee-right", "die": "die",
                }
                job.setdefault("notes", []).append(
                    "blocky cast: 27 authored clips, style-matched to the "
                    "low-poly scenery")
        except Exception:  # noqa: BLE001
            pass
        if player_glb and spec.player.mode == "walk":
            # BIPED SPEED CEILING (2026-08-30), the sibling of the drive/fly
            # floors below. Nothing bounded a WALKING hero, so the model was
            # free to roll walk_speed 2.5 m/s — jog pace — for a character
            # whose walk clip depicts 0.40, and the legs could never catch up.
            # The bound scales with leg length (height is the proxy we have),
            # because a 1.2m fox and a 2.4m ogre do not walk at one speed.
            _h = max(0.4, float(spec.player.height_m or 1.8))
            _k = _h / 1.8
            _wmax, _rmax = round(2.4 * _k, 2), round(7.0 * _k, 2)
            if spec.player.walk_speed > _wmax:
                job.setdefault("notes", []).append(
                    f"walk speed {spec.player.walk_speed:.1f} -> {_wmax:.1f} m/s "
                    f"(anatomical ceiling for a {_h:.1f}m cast; the legs have to "
                    f"keep up)")
                spec.player.walk_speed = _wmax
            if spec.player.run_speed > _rmax:
                spec.player.run_speed = _rmax
        if player_glb and pattern == "flying":
            spec.player.mode = "fly"
            if spec.player.walk_speed < 4.5:                 # floor, see 'drive'
                spec.player.walk_speed = 6.0                 # glide
            if spec.player.run_speed < 11.0:
                spec.player.run_speed = 15.0                 # dive/boost
        if player_glb and pattern == "aquatic":
            spec.player.mode = "swim"
            if spec.player.walk_speed < 4.5:                 # floor, see 'drive'
                spec.player.walk_speed = 6.0                 # cruise (whales MOVE)
            if spec.player.run_speed < 10.0:
                spec.player.run_speed = 14.0                 # burst
        if not player_glb:
            # HONEST STAND-IN — never cross species. A hero we can't build yet
            # degrades to the CLOSEST asset of the SAME kind: a polar bear plays
            # as a wolf, NEVER a man-with-a-sword. Loud, self-healing note.
            stand_in = library.nearest(want, pattern)
            if stand_in != want:
                job.setdefault("notes", []).append(
                    f"Couldn't build '{want}' yet — brand-new characters need a GPU "
                    f"(coming soon). Cast the closest match, '{stand_in}', as a "
                    f"stand-in so your game plays now; re-run this prompt once your "
                    f"GPU is in to get the real '{want}'.")
            player_glb = library.resolve(stand_in)
            cast = stand_in
        if not player_glb:
            raise RuntimeError("no player asset in library (assets/library.json)")
        # PNG-EMBEDDED CHARACTERS RENDER UNTEXTURED (2026-08-07). detective_anim
        # and man_anim embed PNG and both showed up as white/grey mannequins;
        # walker.glb embeds JPEG and was always fine — same loader, same rig,
        # same clips, the codec is the only difference. scripts/_bake_hero.py
        # re-encodes to JPEG keeping full geometry and 2048px maps, so the hero
        # loses no detail. Applied at the ONE point the asset is finally set:
        # player_glb is assigned down several branches and patching them
        # individually already missed one.
        if player_glb and str(player_glb).endswith("_anim.glb"):
            _hero = Path(str(player_glb)[:-len("_anim.glb")] + "_hero.glb")
            if _hero.exists():
                player_glb = str(_hero)
                job.setdefault("notes", []).append(
                    f"hero uses the JPEG bake ({_hero.name}) — PNG-embedded "
                    f"characters render untextured in the web runtime")
        spec.player.asset = player_glb
        spec.player.name = cast
        if abs(spec.player.height_m - 1.75) < 1e-6:      # untouched default -> species height
            spec.player.height_m = library.default_height(cast)
        else:
            # THE MESH DECIDES SCALE, NOT THE NOUN PHRASE (2026-08-05):
            # "a cat burglar" made the LLM read a person and set 1.7 m, so
            # the game rendered a house-cat scaled to human height. The cast
            # resolved to a CAT mesh, and a cat is 0.6 m whatever the job
            # title says. Deliberate variation still survives (a "giant
            # wolf" at 1.5x reads as intended); only physically absurd
            # values — past 1.8x or under 0.55x the species — snap back.
            _sp_h = library.default_height(cast)
            if _sp_h > 0 and not (_sp_h * 0.55 <= spec.player.height_m <= _sp_h * 1.8):
                job.setdefault("notes", []).append(
                    f"{cast} height {spec.player.height_m:.2f}m → {_sp_h:.2f}m "
                    f"(species scale; the mesh decides, not the name)")
                spec.player.height_m = _sp_h
        # CAMERA SCALED TO THE HERO: a 0.6 m fox filmed from person-distance
        # is a speck on screen. Whatever the extractor picked, CLAMP distance
        # and height into a band derived from the cast's actual size — the
        # LLM's choice survives inside the band, absurd framing doesn't.
        h = spec.player.height_m
        spec.camera.distance_m = max(2.0 * h + 0.8,
                                     min(spec.camera.distance_m, 4.2 * h + 2.0))
        spec.camera.height_m = max(0.9 * h,
                                   min(spec.camera.height_m, 2.2 * h + 0.6))
        # FOG SANITY (2026-07-15): the LLM loves dramatic fog — unless the
        # prompt actually says fog/mist/haze, cap density so photoreal scenes
        # stay crisp (words-beat-AI, same rule as sky/hunt).
        try:
            if not any(w in req.prompt.lower() for w in ("fog", "mist", "haze", "smoke")):
                if spec.world.fog_density is None or spec.world.fog_density > 0.35:
                    spec.world.fog_density = 0.3
        except Exception:
            pass
        # CITY GROUND SANITY (2026-07-27 London was PURPLE): the LLM picks
        # mood colors; real streets are asphalt. Any OSM-city world gets a
        # neutral urban gray — the painted road/crosswalk layer stays on top.
        try:
            from app.game_export.level import detect_place as _dp
            if _dp(req.prompt):
                spec.world.ground_color = [0.40, 0.40, 0.43]
                spec.world.grass = False
        except Exception:
            pass
        # per-asset heading facts (play-verified): a generated mesh's nose sign
        # is ambiguous — side-profile refs face either way — so the correction
        # lives as DATA in assets/library_heading.json, never a runtime guess.
        try:
            import json as _json
            _headings = _json.loads((BACKEND_ROOT / "assets" / "library_heading.json")
                                    .read_text(encoding="utf-8"))
            # FACING REGRESSION FIX (2026-08-04): the lookup was EXACT-match
            # only, so a cast of 'red fox' or 'the knight' silently missed a
            # 'fox'/'knight' override and the character walked backwards
            # again. Match on the resolved ASSET FILE too (the ground truth
            # that heading data is really keyed to), then on word overlap.
            _ck = (cast or "").strip().lower()
            _hit = _headings.get(_ck)
            if _hit is None:
                _stem = Path(spec.player.asset or "").stem.lower() \
                    .replace("_anim", "").replace("_", " ")
                _hit = _headings.get(_stem)
            if _hit is None:
                _words = set(_ck.split()) | set(
                    Path(spec.player.asset or "").stem.lower()
                    .replace("_anim", "").split("_"))
                for _k, _v in _headings.items():
                    if set(_k.split()) & _words:
                        _hit = _v
                        break
            if _hit is not None:
                spec.player.yaw_offset_deg = float(_hit)
                job.setdefault("notes", []).append(
                    f"heading data applied: {_hit:+.0f}deg")
        except Exception:
            pass
        if req.pano:
            spec.world.pano = req.pano
            job.setdefault("notes", []).append("scene-image panorama world attached")
            # RULES-CONTAMINATION FIX (2026-08-04): the caption used to join
            # the extraction prompt — and the LLM derived OBJECTIVES from
            # scenery words ('woodcutter's stash' on a beach, playtest). The
            # caption now patches APPEARANCE fields only, deterministically:
            # sky + weather word tables, nothing else. Objectives, entities
            # and rules come from the user's words alone; terrain color and
            # horizon come from the photo itself (ground bake + pano).
            try:
                _cap_p = (BACKEND_ROOT / req.pano).with_suffix(".txt")
                _cap = _cap_p.read_text(encoding="utf-8").lower() if _cap_p.exists() else ""
                import re as _re3
                for w, sky in (("sunset", "sunset"), ("dusk", "dusk"),
                               ("twilight", "dusk"), ("dawn", "sunset"),
                               ("night", "night"), ("overcast", "overcast"),
                               ("cloudy", "overcast"), ("noon", "day"),
                               ("midday", "day"), ("daytime", "day")):
                    if _re3.search(rf"\b{w}\b", _cap):
                        spec.world.sky = sky
                        break
                for w, wx in (("snow", "snow"), ("blizzard", "snow"),
                              ("rain", "rain"), ("storm", "rain")):
                    if _re3.search(rf"\b{w}\b", _cap):
                        spec.world.weather = wx
                        break
            except Exception:
                pass
        if req.splat:
            spec.world.splat = req.splat
            job.setdefault("notes", []).append(
                "Gaussian-splat world attached — the splat is the scenery, "
                "the mesh terrain stays as the physics floor")
        job["player"] = cast
        if not spec.world.scatter:
            spec.world.scatter = [ScatterSpec(**s) for s in game_scatter(
                spec.world.name, getattr(spec.world, 'archetype', 'plain'),
                int(spec.seed or 0), spec.style)]
        # REAL-CITY DE-CLUTTER (Phase 126): OSM already builds the actual
        # blocks — the boxy prop buildings clash beside them. Trees/bushes
        # stay (parks); prop buildings + duplicate lamps go.
        try:
            from app.game_export.level import detect_place as _dp2
            if _dp2(req.prompt):
                spec.world.scatter = [sc for sc in spec.world.scatter
                                      if 'building' not in sc.asset and 'lamp' not in sc.asset]
        except Exception:
            pass
        # generic-human aliases resolve to the man rig instead of generating
        # a new "npc" species from scratch
        _HUMAN_ALIASES = {"npc", "npcs", "guy", "person", "people", "villager",
                          "enemy", "soldier", "guard", "human"}
        # ambient phenomena are ATMOSPHERE, not assets — weather/sky systems
        # already render them; generating a "snowflake" mesh is 30 wasted
        # CPU-minutes (caught live 2026-07-07 on the snowy-fox prompt)
        _AMBIENT = {"snow", "snowflake", "snowflakes", "rain", "raindrop",
                    "raindrops", "wind", "fog", "mist", "cloud", "clouds",
                    "star", "stars", "sunlight", "moonlight", "sky", "dawn",
                    "dusk", "sunset", "sunrise", "shadow", "shadows"}
        # EVERY GAME EXPLAINS ITSELF (2026-08-05): a game should tell you what
        # to do through a PERSON standing in the world, the way Pokémon does,
        # not a HUD line nobody reads. Asking the LLM for an "informant" was
        # unreliable — it wrote the intro text and skipped the character. So
        # a guide is added deterministically whenever a game has a mission and
        # nobody to explain it. The LLM may still name one; this only fills a
        # gap it left. Locked entities and pano worlds are left alone.
        if (spec.objectives and not spec.world.pano
                and "entities" not in (spec.locked or [])
                and not any(e.behavior == "guide" for e in spec.entities)
                and len(spec.entities) < 8):
            from app.game_export.spec import EntitySpec as _GES
            _gname = ("man" if any(e.behavior == "guard" for e in spec.entities)
                      else "woman")
            spec.entities.append(_GES(
                name=_gname, behavior="guide", count=1, speed=0.0,
                height_m=library.default_height(_gname), hp=3))
            job.setdefault("notes", []).append(
                "a guide was added — they greet you and explain each objective")

        # A HEIST WITH NO GUARDS IS AN EMPTY BLOCK (2026-08-06).
        # Casting is LLM-luck: one build cast a noun that was neither in the
        # library nor named in the prompt, so every guard was dropped by the
        # invited-nouns rule and the level shipped with nothing to sneak past —
        # a silent, total loss of the game's premise. Behaviours the DESIGN
        # depends on now fall back to a library humanoid instead of vanishing.
        # Ambience entities keep the old behaviour: they are meant to be
        # skippable, and substituting for them is how you get a crowd of
        # identical men standing in for birds.
        _STRUCTURAL = {"guard", "guide", "hostile", "vehicle"}

        def _understudy(behavior: str):
            """(kind, glb) for a structural role whose own noun could not be
            cast, or (None, None) if even the fallbacks are missing."""
            if behavior not in _STRUCTURAL:
                return None, None
            ladder = (("car", "van", "truck") if behavior == "vehicle"
                      else ("man", "soldier", "thug", "knight", "detective", "woman"))
            for cand in ladder:
                glb2 = ensure_playable(cand, verbose=False) or library.resolve(cand)
                if glb2:
                    return cand, glb2
            return None, None

        kept = []
        for ent in spec.entities:
            if ent.name.lower().strip() in _AMBIENT:
                job.setdefault("notes", []).append(
                    f"'{ent.name}' is atmosphere — rendered by the weather/sky system")
                continue
            ekind = "man" if ent.name.lower() in _HUMAN_ALIASES else ent.name
            # prefer the ANIMATED variant (real gait — no gliding); static fallback
            glb = ensure_playable(ekind, verbose=False) or library.resolve(ekind)
            if not glb and not any(w in req.prompt.lower()
                                   for w in ekind.lower().split()):
                # INVITED NOUNS ONLY (2026-07-07): the LLM sometimes invents
                # ambience entities (an owl for a night forest). Lovely when
                # cached, but an uninvited noun must never cost 35 CPU-minutes
                # of generation. Skip with a note; prompt-named nouns still
                # generate like always.
                sub, glb = _understudy(ent.behavior)
                if not glb:
                    job.setdefault("notes", []).append(
                        f"the AI imagined '{ekind}' for this world — it's not in "
                        f"your library yet, so it was skipped. Mention '{ekind}' in "
                        f"a prompt or edit to create it once (then it's free forever)")
                    continue
                job.setdefault("notes", []).append(
                    f"'{ekind}' isn't in your library, so the {ent.behavior} is "
                    f"played by '{sub}' — the level keeps its {ent.behavior}s")
                ekind = sub
            if not glb:
                # THE SAME PIPELINE FOR EVERY NOUN (2026-07-06): entities and
                # props generate exactly like the player does — a missing
                # monkey or bottle is created once, cached in the library
                # forever. This is what makes "anything at scale" true.
                try:
                    from app.game_export.generate import ensure_asset
                    stage(f"creating '{ekind}' — image → 3D mesh "
                          f"(first time only; slow without a GPU)")
                    ensure_asset(ekind, verbose=True)
                    glb = ensure_playable(ekind, verbose=False) or library.resolve(ekind)
                    if glb:
                        job.setdefault("notes", []).append(
                            f"'{ekind}' was CREATED for this game and saved to your library")
                except Exception as ge:
                    job.setdefault("notes", []).append(
                        f"entity '{ekind}' generation failed ({type(ge).__name__}) — skipped")
            if glb:
                ent.name = ekind
                # NPCs GET THE LIGHT BAKE (2026-08-07). man_anim.glb is 49MB:
                # 478,407 triangles and 4K textures. As a background NPC its
                # texture never finished landing, so the informant and the
                # guards rendered as untextured grey mannequins while the
                # crowd — which already uses the light bake — looked right.
                # walker.glb is that same rig decimated with 512px maps and
                # the identical idle/walk/run/attack clip set, which is
                # exactly what scripts/_bake_walker.py exists to produce. The
                # PLAYER keeps the full-resolution asset; it is the one
                # character the camera ever gets close to.
                _light = BACKEND_ROOT / "assets" / "library" / "walker.glb"
                if str(glb).endswith("man_anim.glb") and _light.exists():
                    glb = str(_light)
                    job.setdefault("notes", []).append(
                        f"{ent.behavior} uses the light walker bake "
                        f"(man_anim is 49MB — too heavy for a background NPC)")
                ent.asset = glb
                if ent.height_m == 1.0:
                    ent.height_m = library.default_height(ekind)
                    if ent.height_m == 1.0 and guess_pattern(ekind) == "static":
                        ent.height_m = 0.5   # unknown props default small, not person-sized
                kept.append(ent)
            else:
                sub, glb2 = _understudy(ent.behavior)
                if glb2:
                    ent.name = sub
                    ent.asset = glb2
                    if ent.height_m == 1.0:
                        ent.height_m = library.default_height(sub)
                    kept.append(ent)
                    job.setdefault("notes", []).append(
                        f"'{ekind}' could not be cast, so the {ent.behavior} is "
                        f"played by '{sub}' — the level keeps its {ent.behavior}s")
                else:
                    job.setdefault("notes", []).append(
                        f"entity '{ekind}' not in library yet — skipped")
        spec.entities = kept

        # PLACED ITEMS (Phase 42 Inspector): explicit-coordinate objects from
        # click-to-place edits. Procedural prop kinds render instantly in the
        # runtime; any other noun resolves through the same casting ladder as
        # entities. Placed items are ALWAYS user-invited (they come from an
        # edit, never LLM invention), so unknown nouns may generate.
        # NYC KIT (2026-08-06): the city's facade families, droppable one at a
        # time. These are not library GLBs — there is no such asset — they are
        # the SAME generator the block is built from, called for one footprint.
        # Dropping a "brownstone" therefore gets real punched windows, not a
        # box wearing a photograph of some.
        _PROC_ALIASES = {"house": "brownstone", "hut": "building", "cabin": "building",
                         "cottage": "brownstone", "shack": "building",
                         "tower": "skyscraper", "highrise": "skyscraper",
                         "high-rise": "skyscraper", "office": "skyscraper",
                         "office tower": "skyscraper", "glass tower": "skyscraper",
                         "walkup": "brownstone", "walk-up": "brownstone",
                         "apartment": "brownstone", "tenement": "brownstone",
                         "townhouse": "brownstone", "row house": "brownstone",
                         "loft": "warehouse", "factory": "warehouse",
                         "warehouse building": "warehouse",
                         "bodega": "storefront", "shop": "storefront",
                         "store": "storefront", "deli": "storefront",
                         "cafe": "storefront", "restaurant": "storefront",
                         "bank": "limestone", "courthouse": "limestone",
                         "library building": "limestone",
                         "stone": "rock", "boulder": "rock", "lantern": "beacon",
                         "torch": "campfire", "fire": "campfire", "bonfire": "campfire",
                         "note": "book", "letter": "book", "scroll": "book",
                         "tome": "book", "signpost": "sign", "signboard": "sign",
                         "crate": "chest", "box": "chest", "treasure": "chest",
                         "wall": "fence", "railing": "fence", "barrier": "fence",
                         "hedge": "fence", "gate": "fence", "palisade": "fence"}
        _PROC_PROPS = {"book", "sign", "chest", "building", "rock", "beacon",
                       "campfire", "fence",
                       # facade families — see procProp/buildFacadeBox
                       "brownstone", "skyscraper", "warehouse", "storefront",
                       "limestone"}
        kept_items = []
        for it in spec.world.placed_items:
            k = _PROC_ALIASES.get((it.kind or "").lower().strip(),
                                  (it.kind or "").lower().strip())
            it.kind = k
            if k in _PROC_PROPS:
                kept_items.append(it)
                continue
            if it.asset:                       # re-export of a resolved spec
                kept_items.append(it)
                continue
            # LIVING PLACEMENTS: prefer the already-baked ANIMATED variant so
            # a placed cat breathes its idle instead of freezing in bind pose
            # (never triggers a bake — only uses what's cached)
            _anim_glb = BACKEND_ROOT / "assets" / "library" / f"{k}_anim.glb"
            glb = (str(_anim_glb) if _anim_glb.exists() else None) \
                or library.resolve(k)
            if not glb:
                try:
                    from app.game_export.generate import ensure_asset
                    stage(f"creating '{k}' — image → 3D mesh "
                          f"(first time only; slow without a GPU)")
                    ensure_asset(k, verbose=True)
                    glb = library.resolve(k) or ensure_playable(k, verbose=False)
                    if glb:
                        job.setdefault("notes", []).append(
                            f"'{k}' was CREATED for this game and saved to your library")
                except Exception as ge:
                    job.setdefault("notes", []).append(
                        f"placed '{k}' generation failed ({type(ge).__name__}) — skipped")
            if glb:
                it.asset = glb
                if not it.height_m:
                    it.height_m = library.default_height(k)
                kept_items.append(it)
            else:
                job.setdefault("notes", []).append(
                    f"placed item '{k}' could not be resolved — skipped")
        # DEFAULT RULES (Phase 44): props ship with their honest behaviors on —
        # firelight repels hostiles, solid things block them. Chips can toggle.
        for it in kept_items:
            if it.kind in ("campfire", "beacon") and "safe_zone" not in it.rules:
                it.rules.append("safe_zone")
            if it.collide and "blocks_enemies" not in it.rules:
                it.rules.append("blocks_enemies")
        # PLACEMENTS NEVER STACK (2026-07-08): a new item that lands on an
        # earlier one (LLM echoing existing coordinates) gets nudged aside —
        # the sign must stand BESIDE the campfire, not inside it.
        import math as _math
        for _i, it in enumerate(kept_items):
            for prev in kept_items[:_i]:
                dx, dz = it.x - prev.x, it.z - prev.z
                d = _math.hypot(dx, dz)
                if d < 1.6:
                    ang = _math.atan2(dz, dx) if d > 1e-6 else 0.8
                    it.x = round(prev.x + _math.cos(ang) * 1.9, 2)
                    it.z = round(prev.z + _math.sin(ang) * 1.9, 2)
        spec.world.placed_items = kept_items

        # COLLECTIBLES LOOK LIKE THE PROMPT'S NOUN: when an entity matches a
        # collect label ("fire flame" ↔ "fire flames"), its generated mesh
        # BECOMES the collectible instead of the generic orb — the 30 CPU
        # minutes spent creating it are finally visible in-game. The entity
        # stops being an NPC.
        def _words(s: str) -> set:
            return {w.rstrip("s") for w in (s or "").lower().split() if w}
        def _singular(s: str) -> str:
            out = []
            for w in (s or "").lower().split():
                out.append(w[:-3] + "y" if w.endswith("ies") else w.rstrip("s"))
            return " ".join(out)
        for ob in spec.objectives:
            if ob.kind != "collect":
                continue
            for ent in list(spec.entities):
                if ent.asset and _words(ent.name) & _words(ob.label):
                    ob.asset = ent.asset
                    spec.entities.remove(ent)
                    break
        # COLLECTIBLE LABELS GENERATE TOO: "collect 6 fireflies" must produce
        # firefly meshes even when the extractor casts no matching entity —
        # the label is a noun like any other (fireflies-stayed-orbs fix).
        # GENERIC collectible labels ("food", "supplies", "treasures") never
        # deserve a 35-minute mesh generation — they render as the glowing
        # pickups, with a note pointing at the specific-noun path instead
        _GENERIC_COLLECT = {"food", "meal", "supply", "supplies", "item",
                            "thing", "treasure", "star", "coin", "point",
                            "orb", "token", "collectible", "pickup", "loot",
                            "resource", "goodie", "snack"}
        for ob in spec.objectives:
            if ob.kind != "collect" or ob.asset:
                continue
            sing = _singular(ob.label)
            if not sing or sing in _AMBIENT:
                continue
            if sing.split()[-1] in _GENERIC_COLLECT:
                job.setdefault("notes", []).append(
                    f"'{ob.label}' renders as glowing pickups — name a specific "
                    f"thing ('fish', 'bones', 'apples') to generate a real mesh for it")
                continue
            glb = library.resolve(sing)
            if not glb:
                try:
                    from app.game_export.generate import ensure_asset
                    stage(f"creating '{sing}' — image → 3D mesh "
                          f"(first time only; slow without a GPU)")
                    ensure_asset(sing, verbose=True)
                    glb = library.resolve(sing)
                    if glb:
                        job.setdefault("notes", []).append(
                            f"'{sing}' was CREATED for this game and saved to your library")
                except Exception as ge:
                    job.setdefault("notes", []).append(
                        f"collectible '{sing}' generation failed "
                        f"({type(ge).__name__}) — glowing orbs used")
            if glb:
                ob.asset = glb

        # RACE SANITY: a race needs rivals — and rivals are the PLAYER'S OWN
        # KIND, whatever that is (foxes race foxes, whales race whales). A
        # "race" verb in the prompt must never conjure phantom cars.
        from app.game_export.spec import EntitySpec
        for ob in spec.objectives:
            if ob.kind == "race" and not any(e.behavior == "vehicle" for e in spec.entities):
                okind = cast
                # ensure_playable = the RIGGED variant (legs actually move);
                # "{kind}_anim" was never a registry key, so rivals silently
                # got the static mesh (the gliding fox of 2026-07-07)
                oglb = ensure_playable(okind, verbose=False) or library.resolve(okind)
                rival_speed = (6.5 if guess_pattern(okind) == "vehicle"
                               else max(spec.player.walk_speed * 0.85, 2.5))
                if oglb:
                    spec.entities.append(EntitySpec(
                        name=okind, asset=oglb, behavior="vehicle",
                        count=min(ob.count, 8), speed=rival_speed,
                        height_m=library.default_height(okind)))

        # HUNT OVERRIDE (Phase 68): explicit hunt words in the PROMPT beat the
        # LLM's verb pick — "hunt 3 elk" once extracted as COLLECT 3 elk, so
        # the elk neither fled nor could be killed. Same words-beat-AI rule as
        # sky/weather. Converts the mis-verbed step, ensures fleeing prey, and
        # ARMS the hunter (claws for beasts, a ranged shot for people).
        import re as _re2
        # hunt(s|ed|ing) — "a wolf HUNTS 3 elk" must match, not just "hunt"
        _hm = _re2.search(r"\bhunt(?:s|ed|ing)?\s+(?:down\s+)?(\d+)?\s*(?:the\s+)?"
                          r"([a-z]+)", req.prompt.lower())
        if _hm and _hm.group(2) not in ("for", "down"):
            from app.game_export.spec import ObjectiveSpec
            prey = _hm.group(2)
            prey = (prey[:-3] + "f") if prey.endswith("ves") else                    (prey[:-3] + "y") if prey.endswith("ies") else                    (prey[:-1] if prey.endswith("s") and not prey.endswith("ss") else prey)
            n_prey = int(_hm.group(1) or 3)
            converted = False
            for ob in spec.objectives:
                if ob.kind == "hunt":
                    converted = True
                    break
                if ob.kind in ("collect", "defeat") and prey in ob.label.lower():
                    ob.kind = "hunt"
                    ob.count = min(ob.count, 8)
                    converted = True
                    job.setdefault("notes", []).append(
                        f"'{prey}' is HUNTED, not collected — your words beat the AI's pick")
                    break
            if not converted:
                spec.objectives.insert(0, ObjectiveSpec(
                    kind="hunt", label=prey, count=max(1, min(n_prey, 8))))
            # prey must exist and FLEE (drop any duplicate wander/collect cast)
            spec.entities = [e for e in spec.entities
                             if not (e.name.lower() == prey and e.behavior in ("wander", "follow"))]
            if not any(e.behavior == "flee" for e in spec.entities):
                pglb = (ensure_playable(prey, verbose=False) or library.resolve(prey))
                if pglb:
                    spec.entities.append(EntitySpec(
                        name=prey, asset=pglb, behavior="flee",
                        count=max(n_prey, 2), speed=2.4,
                        height_m=library.default_height(prey), hp=2))
            # a hunter without a weapon is a spectator
            if spec.player.attack == "none":
                spec.player.attack = ("ranged" if guess_pattern(cast) == "biped"
                                      else "melee")
                job.setdefault("notes", []).append(
                    f"hunter armed: {spec.player.attack} "
                    f"({'rifle shot - F to shoot' if spec.player.attack == 'ranged' else 'claws/bite - F to attack'})")

        # CAPTURE OVERRIDE (Phase 72): same words-beat-AI rule as hunt — the
        # player said capture/hold/control zones, so a capture step LEADS the
        # quest whatever ladder the LLM invented.
        _cm = _re2.search(r"\b(?:capture|hold|control|claim)\s+(?:the\s+)?(\d+)?\s*"
                          r"(?:zones?|points?|areas?|territor(?:y|ies)|flags?|hills?)",
                          req.prompt.lower())
        if _cm and not any(ob.kind == "capture" for ob in spec.objectives):
            from app.game_export.spec import ObjectiveSpec
            _nz = int(_cm.group(1) or 3)
            spec.objectives.insert(0, ObjectiveSpec(
                kind="capture", label="zones", count=max(1, min(_nz, 5))))
            job.setdefault("notes", []).append(
                "capture-the-zone mode added — your words beat the AI's pick")

        # BATTLE ROYALE SANITY (Phase 61): an 'eliminate' step is last-one-
        # standing — the rivals are HOSTILE copies of the player's own kind
        # (foxes fight foxes) unless the prompt already cast hostiles. The
        # runtime adds the shrinking storm zone.
        for ob in spec.objectives:
            if ob.kind == "eliminate" and not any(
                    e.behavior == "hostile" for e in spec.entities):
                okind = ob.label.strip().lower() if ob.label else cast
                rglb = (ensure_playable(okind, verbose=False)
                        or library.resolve(okind)
                        or ensure_playable(cast, verbose=False)
                        or library.resolve(cast))
                if rglb:
                    if not (library.resolve(okind)):
                        okind = cast
                    spec.entities.append(EntitySpec(
                        name=okind, asset=rglb, behavior="hostile",
                        count=min(max(ob.count, 2), 12),
                        speed=max(spec.player.walk_speed * 0.8, 2.2),
                        height_m=library.default_height(okind), hp=3))
                    ob.label = okind + "s" if not ob.label else ob.label

        # grass: off for cities and snow (quality-pack gate)
        from app.game_export.dressing import wants_grass
        spec.world.grass = wants_grass(spec.world.name, spec.world.weather)

        # MISSION SANITY: defeat steps need hostiles that actually resolved.
        # Clamp counts to what exists; drop unwinnable steps with a note.
        total_hostiles = sum(e.count for e in spec.entities if e.behavior == "hostile")
        sane = []
        for ob in spec.objectives:
            if ob.kind in ("defeat", "eliminate"):
                if total_hostiles <= 0:
                    job.setdefault("notes", []).append(
                        f"'defeat {ob.label}' dropped — no enemies could be cast")
                    continue
                ob.count = min(ob.count, total_hostiles)
            if ob.kind == "hunt":
                total_prey = sum(e.count for e in spec.entities if e.behavior == "flee")
                if total_prey <= 0:
                    job.setdefault("notes", []).append(
                        f"'hunt {ob.label}' dropped — no prey could be cast")
                    continue
                ob.count = min(ob.count, total_prey)
            if ob.kind == "survive" and total_hostiles <= 0:
                job.setdefault("notes", []).append(
                    f"'survive {ob.label}' dropped — waves need at least one hostile")
                continue
            sane.append(ob)
        spec.objectives = sane

        stage("designing level")
        from app.game_export.level import build_level, build_osm_city, detect_place
        n_obj = sum(o.count for o in spec.objectives if o.kind == "collect")
        is_city = any(k in (spec.world.name or "").lower() for k in ("city", "street", "town"))
        # REAL CITIES (shared with video's OSM system): a named place in the
        # prompt swaps procedural building scatter for actual OSM footprints.
        # Real blocks are ~100-250m — the world grows to hold a real district.
        place = detect_place(req.prompt) if is_city else None
        # FLORA OBEYS THE PROMPT (2026-08-25): the silhouette pack rolls a
        # tree archetype from the seed, and its first field test planted dead
        # snags in a prompt that said "a pine forest". An explicit tree word
        # outranks the dice; the seed only decides when the user didn't.
        import re as _flre
        _flm = _flre.search(
            r"\b(pine|fir|spruce|conifer|birch|oak|willow|maple|palm|cypress|"
            r"dead tree|cactus|jungle)\b", req.prompt.lower())
        if _flm:
            spec.world.flora = _flm.group(1)
        # EDITS MUST NOT BULLDOZE THE CITY (2026-08-06). Place detection reads
        # the PROMPT, and an edit's prompt is "add a storefront here" — there is
        # no city name in it, because the setting was decided two builds ago. So
        # a real-map game quietly rebuilt itself as procedural scatter and 46
        # OSM footprints became 0: the user added one shop and lost Manhattan.
        # A scan the base already paid for IS the world; carry it rather than
        # re-derive it from a sentence that was never about the setting.
        _base_level = ((base_spec or {}).get("world") or {}).get("level") or {}
        _keep_city = (not place) and bool(_base_level.get("osm"))
        if place or _keep_city:
            spec.world.size_m = max(spec.world.size_m, 360.0)
        # SETTING-DRIVEN TERRAIN (2026-07-05): "mountains" means PEAKS, not a
        # flat plane — amplitude scales with the world class, scalably.
        _TERRAIN_AMP = {"mountain": 16.0, "alpine": 16.0, "volcano": 14.0,
                        "canyon": 11.0, "cliff": 11.0, "hill": 6.5,
                        "desert": 3.4, "dune": 3.4, "arctic": 4.5,
                        "swamp": 0.9, "beach": 1.4, "plain": 1.5,
                        "mars": 8.0, "moon": 5.0, "cave": 7.0,
                        "castle": 1.2, "ruins": 2.6, "jungle": 3.5}
        _wname = (spec.world.name or "").lower()
        amp = next((v for k, v in _TERRAIN_AMP.items() if k in _wname), 2.4)
        if is_city:
            amp = 0.35                              # cities are near-flat
        if spec.player.mode == "fly":
            amp = max(amp, 8.0)                     # flyers deserve relief to soar over
        # WATER WORLDS: rolling seabed + a water plane the runtime renders;
        # swimmers stay beneath it, everything gets underwater fog below it
        # ── SEMANTIC LAYOUT (2026-08-25, phase 2): spatial language becomes
        # regions. Parsed from the prompt; an EDIT with no spatial language
        # inherits the base game's layout — same contract as the city carry:
        # an edit must never re-derive the world.
        from app.game_export.level import parse_regions
        _regions = parse_regions(req.prompt)
        if not _regions and base_spec is not None:
            _regions = ((((base_spec.get("world") or {}).get("level") or {})
                         .get("regions_src")) or [])
        _regional_water = any(r.get("kind") == "water" for r in _regions)
        _water = any(k in _wname for k in ("ocean", "underwater", "lake", "river"))
        # a REGIONAL lake must not trigger the whole-world flood: "a lake in
        # the north" used to fill the entire map to +4m because the world got
        # named after its lake. Oceans stay global; lakes become terrain.
        if _regional_water and not any(k in _wname for k in ("ocean", "underwater")):
            _water = False
        # FROZEN water is ICE (2026-07-23: 'frozen lake' floated the polar
        # bear belly-up like a whale) — solid, walkable, snowy; no water
        # plane, no swim handling.
        if _water and any(k in req.prompt.lower() for k in ("frozen", "ice", "icy")):
            _water = False
        if _water:
            amp = max(amp, 3.0)                     # seabed dunes
            spec.world.water_level = 8.0 if "lake" not in _wname else 4.0
        elif spec.player.mode == "swim":
            # aquatic player in a non-water world: give them water anyway
            spec.world.water_level = 8.0
            amp = max(amp, 3.0)
        # ARCHETYPE (2026-08-30): the landform the prompt asked for. Applied
        # before regions and before the corridor, so it changes the SHAPE of
        # the world rather than its dressing — and the corridor still flattens
        # the mission path, so a canyon floor stays walkable.
        # SURFACE VESSELS FLOAT (2026-09-03). The model picks mode="swim"
        # for anything that belongs on water, which is right for a shark and
        # wrong for a boat — one swims through it, the other sits on top of
        # it. Decided here rather than asked of the LLM: the vocabulary for
        # "thing that floats" is small and closed, and a wrong guess puts the
        # player underwater with no way to tell why.
        if spec.player.mode == "swim":
            _hay = " ".join(str(x).lower() for x in (
                spec.player.asset, getattr(spec.player, "species", "") or "",
                spec.world.name or "", spec.title or ""))
            if any(w in _hay for w in ("boat", "ship", "sail", "raft", "canoe",
                                       "kayak", "yacht", "ferry", "schooner",
                                       "galleon", "dinghy", "trawler", "cutter")):
                spec.player.buoyant = True
                job.setdefault("notes", []).append(
                    "surface vessel: rides the waterline (boats float, they "
                    "don't dive)")
        _arch = getattr(spec.world, "archetype", "plain") or "plain"
        # TERRAIN RESOLUTION SCALES WITH THE WORLD (2026-09-04). grid_n was a
        # flat 48 whatever the world's size, so a 150m map had 3.1m polygons
        # and a 350m map 7.3m ones. At that size a hillside is a handful of
        # facets and every landform reads as folded card — the single biggest
        # thing standing between us and anything that looks photographed.
        # Targeting ~1.6m per cell instead, capped so the trimesh collider and
        # the level payload stay sane (128 -> 16k heights, ~120KB of JSON,
        # against 2.3k and 17KB before).
        _gn = int(max(64, min(128, round(float(spec.world.size_m) / 1.6))))
        spec.world.level = build_level(
            spec.seed, spec.world.size_m, n_objectives=n_obj, amplitude_m=amp,
            grid_n=_gn, regions=_regions, archetype=_arch)
        job.setdefault("notes", []).append(
            f"terrain {_gn}x{_gn} "
            f"({float(spec.world.size_m) / _gn:.1f}m per polygon, was "
            f"{float(spec.world.size_m) / 48:.1f}m)")
        # GROUND FOLLOWS THE LANDFORM (2026-08-30). The first built canyon was
        # a red-rock gorge carpeted in meadow grass, which throws away most of
        # what the archetype just bought: shape read as canyon, surface read as
        # valley. The runtime picks its detail texture (grass / soil / stone /
        # sand / snow) from the ground COLOUR, so tinting the ground per
        # landform swings the material with it for free. Only applied when the
        # model left the default green — an explicit colour still wins.
        # A PALE SKY FOGS THE WHOLE FRAME (2026-09-04). world.palette.sky
        # overrides the preset, and the model keeps authoring near-white
        # washes for bright scenes — #bfe0d4 for a sunny meadow, then #c2d8f0
        # after the prompt was tightened. A sky lighter than the ground drains
        # every other colour and is a large part of the "papery" read, so this
        # is clamped here rather than asked for again: telling the model twice
        # and getting it twice is the signal to make it deterministic.
        try:
            # palette is a PaletteSpec MODEL, not a dict — the first version of
            # this guarded on isinstance(dict) and so never ran at all, and the
            # sky it was written to catch (#c2d4ff, lightness 0.88) sailed
            # straight through. Handle both shapes.
            _pal = getattr(spec.world, "palette", None)
            if isinstance(_pal, dict):
                _sky_hex = _pal.get("sky")
            else:
                _sky_hex = getattr(_pal, "sky", None) if _pal is not None else None
            if _sky_hex and str(_sky_hex).startswith("#") and len(str(_sky_hex)) == 7:
                import colorsys
                _r = int(_sky_hex[1:3], 16) / 255
                _g = int(_sky_hex[3:5], 16) / 255
                _b = int(_sky_hex[5:7], 16) / 255
                _h, _l, _sat = colorsys.rgb_to_hls(_r, _g, _b)
                # night skies are meant to be dark; only bright ones can wash
                if _l > 0.78 or (_l > 0.62 and _sat < 0.30):
                    _l2, _s2 = min(_l, 0.68), max(_sat, 0.45)
                    _r2, _g2, _b2 = colorsys.hls_to_rgb(_h, _l2, _s2)
                    _new = "#%02x%02x%02x" % (int(_r2 * 255), int(_g2 * 255),
                                              int(_b2 * 255))
                    if isinstance(_pal, dict):
                        _pal["sky"] = _new
                    else:
                        _pal.sky = _new
                    spec.world.palette = _pal
                    job.setdefault("notes", []).append(
                        f"sky deepened {_sky_hex} -> {_new} (a near-white sky "
                        f"fogs the whole frame)")
        except Exception:  # noqa: BLE001
            pass
        _ARCH_GROUND = {
            "canyon": [0.46, 0.26, 0.17],      # red rock
            "mesa":   [0.52, 0.34, 0.22],      # dusty butte
            "dunes":  [0.72, 0.62, 0.40],      # sand
            "peaks":  [0.62, 0.64, 0.66],      # bare stone above the treeline
            "basin":  [0.40, 0.42, 0.28],      # dry scrub
        }
        if (_arch in _ARCH_GROUND
                and list(spec.world.ground_color) == [0.35, 0.52, 0.28]):
            spec.world.ground_color = _ARCH_GROUND[_arch]
        if _arch != "plain":
            job.setdefault("notes", []).append(
                f"landform: {_arch} (from your prompt — the ground itself, "
                f"not just its colour)")
        if _arch == "archipelago" and spec.world.water_level is None:
            # an archipelago without a sea is just lumpy ground: this landform
            # puts most of the map below zero on purpose, so the water plane
            # IS the world and has to exist
            spec.world.water_level = 0.0
        if (spec.world.water_level is None
                and spec.world.level.get("water_suggest") is not None):
            spec.world.water_level = spec.world.level["water_suggest"]
        if _regions:
            _dirname = {(0, -1): "north", (0, 1): "south",
                        (1, 0): "east", (-1, 0): "west", (0, 0): "center"}
            job.setdefault("notes", []).append(
                "semantic layout: " + ", ".join(
                    r["name"] + " in the " + _dirname.get(tuple(r["dir"]), "map")
                    for r in _regions))
        if _keep_city:
            # everything the city scan produced: footprints, the road route the
            # mission path follows, the goal pin, and any doors already planned
            for _ck in ("osm", "path", "goal", "enterable", "enterables",
                        "landmarks", "spawn"):
                if _ck in _base_level:
                    spec.world.level[_ck] = _base_level[_ck]
            job.setdefault("notes", []).append(
                "kept the base game's real-city map (%d buildings) — an edit "
                "does not re-scan" % len((_base_level.get("osm") or {}).get("buildings", [])))
        # INTERIOR LEVELS (Phase 95): 'inside a castle/house/dungeon' builds
        # ROOMS — walls with colliders, doorways, furniture, torchlight. The
        # words must say inside/interior/indoor; 'defends the castle' stays an
        # exterior castle world.
        _pl = req.prompt.lower()
        if base_spec is not None:
            # EDITS NEVER RE-DERIVE THE WORLD, part 2 (2026-07-28): every
            # world-shape heuristic below (interior, enterable buildings,
            # quest chains) reads the PROMPT — and an edit's prompt is just
            # "give the knight 3 more hp", so the castle hall vanished on
            # rebuild. Heuristics on an edit read the ORIGINAL prompt plus
            # the edit text, so the world keeps its shape and explicit
            # world words in the edit still work.
            _base_prompt = (
                base_spec.get("prompt")
                or (_jobs.get(req.base_job_id) or {}).get("prompt")
                # legacy games saved before prompts rode along: the title +
                # intro + world name usually carry the setting words
                or " ".join(str(x) for x in (
                    base_spec.get("title"), base_spec.get("intro"),
                    (base_spec.get("world") or {}).get("name")) if x))
            _pl = (str(_base_prompt) + " " + req.prompt).lower()
        import re as _re3
        _im = _re3.search(
            r"\b(?:inside|interior of|indoors?|within the walls of)\s+"
            r"(?:a\s+|an\s+|the\s+)?(castle|house|mansion|dungeon|temple|"
            r"tavern|cottage|fortress|palace|room|home)?", _pl)
        # THE GENRE IMPLIES THE WORLD SHAPE (2026-08-05): a burglar game is
        # ALWAYS indoors — you cannot infiltrate a meadow. "A cat burglar
        # infiltrates a moonlit mansion" built an open grass field because
        # the prompt never said the literal word "inside". Heist words plus
        # a building noun are as strong a signal as "inside" ever was.
        _heist = _re3.search(r"\b(?:heist|burglar|burgle|burgl\w+|infiltrat\w+|"
                             r"steal|stole|stealing|rob|robbing|robbery|loot\w*|"
                             r"thief|thieve\w*|sneak\w*|stealth)\b", _pl)
        _bld = _re3.search(r"\b(mansion|museum|vault|bank|gallery|manor|estate|"
                           r"penthouse|villa|castle|house|palace|temple|"
                           r"fortress|tower|warehouse)\b", _pl)
        # A CITY HEIST IS NOT ONE ROOM (2026-08-05): in a named real city the
        # genre-implies-interior shortcut would throw the whole street grid
        # away and drop the player in a single hall. There the heist is the
        # BLOCK — see the multi-building pass after the OSM fetch. An explicit
        # "inside the vault" still wins; only the implied case defers.
        _city_heist = bool(_heist and is_city and place)
        # ...and a BARE "inside" defers too. The interior regex matches the
        # word alone with no building noun, so "4 guards patrol inside them"
        # in a Manhattan heist collapsed the whole street grid into one
        # nameless dungeon. Only a named venue ("inside the vault") outranks
        # the block.
        if ((_im and (_im.group(1) or not _city_heist))
                or " dungeon" in _pl or (_heist and _bld and not _city_heist)):
            from app.game_export.level import build_interior
            _ik_raw = (_im.group(1) if _im else None) \
                or (_bld.group(1) if (_heist and _bld) else None) or "dungeon"
            _ik = {"mansion": "house", "cottage": "house", "home": "house",
                   "room": "house", "tavern": "house", "temple": "castle",
                   "fortress": "castle", "palace": "castle",
                   # heist venues: grand halls read as castle, homes as house
                   "museum": "castle", "gallery": "castle", "manor": "house",
                   "estate": "house", "villa": "house", "penthouse": "house",
                   "vault": "dungeon", "bank": "castle", "warehouse": "dungeon",
                   "tower": "castle"}.get(_ik_raw, _ik_raw)
            interior = build_interior(spec.seed, _ik)
            # flat floor, no outdoor dressing, world sized to the room plan
            spec.world.level["heights"] = [0.0] * (
                spec.world.level["grid_n"] ** 2)
            spec.world.level["interior"] = interior
            spec.world.size_m = max(interior["bounds"][0], interior["bounds"][1]) + 8
            spec.world.scatter = []
            spec.world.grass = False
            spec.world.weather = "none"
            # OBJECTIVES LIVE IN THE ROOMS (2026-07-23 test: clues + beacon
            # spawned outside the walls — they still used the OUTDOOR path).
            # Goal -> far room; collectibles spread across rooms; the mission
            # path runs down the hall so zones/waypoints stay indoors too.
            _rooms = interior["rooms"]
            import random as _rnd
            _rr = _rnd.Random(spec.seed + 9)
            _far = max(_rooms, key=lambda r: r[0] * r[0] + r[1] * r[1])
            spec.world.level["goal"] = [_far[0], _far[1]]
            _pts = []
            for _k in range(max(n_obj, 1)):
                _cx, _cz, _rw, _rd = _rooms[_k % len(_rooms)]
                _pts.append([round(_cx + _rr.uniform(-_rw / 2 + 1.0, _rw / 2 - 1.0), 2),
                             round(_cz + _rr.uniform(-_rd / 2 + 1.0, _rd / 2 - 1.0), 2)])
            spec.world.level["collect_points"] = _pts
            _hall = _rooms[0]
            spec.world.level["path"] = [
                [0.0, round(-_hall[3] / 2 + 2.0, 2)], [0.0, 0.0],
                [_far[0], _far[1]]]
            spec.world.level["landmarks"] = []
            job.setdefault("notes", []).append(
                f"interior level: {_ik} — rooms, doorways, torchlight")
        # QUEST CHAINS (moon plan 3.1): a single-objective prompt becomes a
        # 3-step story — scout a Point of Interest, do the deed, reach the
        # beacon. The scout step is a collect(1) staged AT the POI (collect
        # steps consume level.collect_points in order, so prepending the POI
        # position stages it there deterministically).
        _pois2 = spec.world.level.get("pois") or []
        _gameplay = [o for o in spec.objectives if o.kind != "reach"]
        # INTENT GATE (2026-07-28): the scout step leaked into EVERY
        # single-objective game — a soccer match got "collect the abandoned
        # camp's supplies". Quest chains now require the prompt to actually
        # sound like a quest/adventure; sports, brawls, and races get
        # exactly the objectives the user asked for.
        _questy = _re3.search(
            r"\b(quest|explor\w*|adventur\w*|journey|wander|trek|search|"
            r"find|discover|scout|lost|hidden|treasure|relic|ruin\w*|"
            r"myster\w*|collect)\b", _pl)
        # PANO GATE (2026-08-04): image worlds skip quest-chain injection —
        # 'the woodcutter's stash' materializing on a user's beach photo
        # reads as rules-gone-wrong; their prompt is the whole contract.
        if (_pois2 and _questy and len(_gameplay) == 1
                and spec.player.mode == "walk"
                and not spec.world.pano
                and "interior" not in spec.world.level):
            from app.game_export.spec import ObjectiveSpec as _OS
            _poi0 = _pois2[0]
            _scout_names = {"ruin": "the old watchtower cache",
                            "camp": "the abandoned camp's supplies",
                            "shrine": "the shrine offering",
                            "circle": "the relic at the standing stones",
                            "lumber": "the woodcutter's stash"}
            spec.objectives.insert(0, _OS(
                kind="collect", count=1,
                label=_scout_names.get(_poi0["kind"], "the lost supplies")))
            spec.world.level.setdefault("collect_points", []).insert(
                0, [_poi0["x"], _poi0["z"]])
            job.setdefault("notes", []).append(
                "quest chain: scout the " + _poi0["kind"] + " first, then "
                + (_gameplay[0].label or _gameplay[0].kind))
        # ENTERABLE BUILDING (moon plan 2.2): an EXTERIOR world that mentions
        # a structure gets a real door — outside stays the level, the door
        # teleports into a generated interior past the map edge and back.
        if "interior" not in spec.world.level and not is_city:
            _sm = _re3.search(
                r"\b(castle|fortress|palace|mansion|house|cottage|tavern|"
                r"temple|cabin|dungeon)\b", _pl)
            if _sm:
                from app.game_export.level import build_interior
                _ek_raw = _sm.group(1)
                _ek = {"mansion": "house", "cottage": "house", "cabin": "house",
                       "tavern": "house", "temple": "castle",
                       "fortress": "castle", "palace": "castle"}.get(_ek_raw, _ek_raw)
                _eplan = build_interior(spec.seed + 7, _ek)
                import random as _rnd2
                _er = _rnd2.Random(spec.seed + 13)
                _lm = spec.world.level.get("landmarks") or []
                if _lm:
                    _door = [_lm[0][0], _lm[0][1]]
                else:
                    _half2 = spec.world.size_m / 2
                    _door = [round(_half2 * 0.5, 2), round(_half2 * _er.uniform(-0.3, 0.3), 2)]
                spec.world.level["enterable"] = {"plan": _eplan, "door": _door}
                job.setdefault("notes", []).append(
                    f"the {_ek_raw} has a real door — step through the glow to go inside")
        if place:
            stage(f"fetching {place} map (OpenStreetMap)")
            osm = build_osm_city(place, spec.world.size_m)
            if osm:
                spec.world.level["osm"] = osm
                # streets are the level: the mission path FOLLOWS the road
                # route (race rivals, collectibles and the goal pin to it) and
                # the ground is dead flat so nothing pokes through the asphalt
                route = osm.get("route")
                if route:
                    spec.world.level["path"] = route
                    spec.world.level["goal"] = list(route[-1])
                    n = len(route)
                    spec.world.level["collect_points"] = [
                        list(route[int((k + 1) / (n_obj + 1) * (n - 1))])
                        for k in range(n_obj)]
                    g = spec.world.level["grid_n"]
                    spec.world.level["heights"] = [0.0] * (g * g)
                spec.world.scatter = [s for s in spec.world.scatter
                                      if "building" not in Path(s.asset).name]
                job.setdefault("notes", []).append(
                    f"real-city map: {place} ({len(osm['buildings'])} buildings, "
                    f"{len(osm['roads'])} roads, route={'yes' if route else 'no'}, "
                    f"© OpenStreetMap contributors)")
            else:
                job.setdefault("notes", []).append(
                    f"OSM fetch for '{place}' unavailable — procedural city used")

        # ── MULTI-BUILDING CITY HEIST (2026-08-05) ──────────────────────────
        # The flagship shape: a burglar working a real block. Several OSM
        # footprints each get their own interior parked past the map edge and
        # a glowing door on their street face; the loot spreads ACROSS them,
        # so finishing the job means four break-ins, not one room sweep. Runs
        # after the OSM fetch because it needs the real footprints and the
        # road route (the door faces the nearest street).
        if _city_heist and spec.world.level.get("osm"):
            from app.game_export.level import plan_enterables, spread_loot
            _want = 4
            _nm = _re3.search(r"\b(\d+)\s+(?:buildings?|houses?|homes?|shops?|"
                              r"stores?|apartments?|places?)\b", _pl)
            if _nm:
                _want = max(2, min(5, int(_nm.group(1))))
            _ents = plan_enterables(spec.world.level["osm"], spec.world.level,
                                    spec.seed, spec.world.size_m, want=_want)
            if _ents:
                spec.world.level["enterables"] = _ents
                if n_obj:
                    spec.world.level["collect_points"] = spread_loot(
                        _ents, n_obj, spec.seed)
                # ONE SENTRY PER VENUE minimum: with 4 doors and 2 guards two
                # buildings were free money, and the stealth loop only exists
                # where somebody is watching.
                _gs = [e for e in spec.entities if e.behavior == "guard"]
                if _gs:
                    _have = sum(e.count for e in _gs)
                    if _have < len(_ents):
                        _gs[0].count += len(_ents) - _have
                job.setdefault("notes", []).append(
                    "city heist: " + str(len(_ents)) + " enterable buildings ("
                    + ", ".join(e["label"] for e in _ents)
                    + ") — walk to a glowing door to go inside")
            else:
                job.setdefault("notes", []).append(
                    "no footprint suited an enterable door — street-level heist")

        stage("building")
        # RESOLVED spec (absolute asset paths) — lets Game Projects re-export
        # this exact level later without re-running extraction
        job["spec_resolved"] = spec.model_dump()
        # the ORIGINAL prompt rides along (2026-07-28): edits re-run the
        # world-shape heuristics, which must read what the user first asked
        # for — an edit chain keeps the earliest real prompt
        job["spec_resolved"]["prompt"] = (
            base_spec.get("prompt") if base_spec else None) or req.prompt
        out_dir = GAME_JOBS_DIR / f"job_{job_id}"
        dist = export_web_game(spec, out_dir, verbose=False)
        # persist the full spec so this game stays EDITABLE across restarts
        import json as _json
        (out_dir / "spec_full.json").write_text(
            _json.dumps(job["spec_resolved"]), encoding="utf-8")

        stage("verifying")
        v = verify_dist(dist)
        if not v["ok"]:
            raise RuntimeError(f"verify failed: {v['errors']}")

        if req.godot:
            stage("emitting godot project")
            from app.game_export.godot_exporter import export_godot_game
            export_godot_game(spec, out_dir, verbose=False)
            job["godot_path"] = str(out_dir / "godot")

        job["status"] = "complete"
        job["play_url"] = f"/games/job_{job_id}/dist/"
        job["checks"] = len(v["checks"])
        # SHOTGATE (2026-07-29): give the build EYES — load the exported game
        # in headless Chrome, press START, run, screenshot, surface errors.
        # Best-effort: node/chrome absent or timeout never fails the build.
        try:
            stage("visual gate")
            import subprocess as _sp
            shot = out_dir / "dist" / "_shot.png"
            r = _sp.run(
                ["node", str(BACKEND_ROOT / "tools" / "shotgate" / "shot.mjs"),
                 f"http://127.0.0.1:8789/games/job_{job_id}/dist/index.html",
                 str(shot)],
                capture_output=True, text=True, timeout=90,
                cwd=str(BACKEND_ROOT / "tools" / "shotgate"))
            # DOES IT MATCH THE BRIEF (2026-09-03). "Rendered clean" was
            # true of every bug in the 2026-09-03 pass: the green canyon,
            # the sunken sailboat and the photoreal neon racer all passed
            # this gate. The running game now reports what it actually
            # built and we hold that against the spec that asked for it.
            _facts = {}
            for _ln in (r.stdout or "").splitlines():
                if _ln.startswith("SHOTGATE-FACTS "):
                    try:
                        _facts = json.loads(_ln[len("SHOTGATE-FACTS "):])
                    except Exception:  # noqa: BLE001
                        _facts = {}
            if _facts:
                from ..game_export.brief_check import check_brief
                _miss = check_brief(spec, _facts)
                job["facts"] = _facts
                for _m in _miss:
                    job.setdefault("notes", []).append(f"⚠ off-brief — {_m}")
                if _miss:
                    job["brief_errors"] = _miss
            if r.returncode == 0 and shot.exists():
                job["shot"] = f"/games/job_{job_id}/dist/_shot.png"
                job.setdefault("notes", []).append(
                    "visual gate: rendered clean, no runtime errors"
                    + ("" if not _facts else
                       " — and matches the brief" if not job.get("brief_errors")
                       else f" — but {len(job['brief_errors'])} thing(s) off-brief"))
                job["checks"] = job.get("checks", 0) + 1
            elif r.returncode == 2:
                # LOUD, NOT BURIED (2026-08-05): a shader link failure
                # ("VALIDATE_STATUS false") renders a BLACK ROOM, yet the
                # build still said complete because runtime errors were
                # appended as one note among many and nothing surfaced them.
                # Broken output must never read as a clean build.
                _det = (r.stderr or "").replace("SHOTGATE-ERRORS", "").strip()
                job["visual_errors"] = _det[:400]
                _fatal = ("VALIDATE_STATUS" in _det or "Shader Error" in _det
                          or "is not a function" in _det
                          or "before initialization" in _det)
                job.setdefault("notes", []).append(
                    ("⚠ VISUAL GATE FAILED — the game renders broken: "
                     if _fatal else "⚠ visual gate: runtime errors — ")
                    + _det[:220])
                if shot.exists():
                    job["shot"] = f"/games/job_{job_id}/dist/_shot.png"
        except Exception as _ge:  # noqa: BLE001
            # BEST-EFFORT MUST NOT MEAN SILENT (2026-09-03). This handler
            # swallowed a NameError for a whole release: json was never
            # imported here, so the gate raised on its first line and every
            # build reported no screenshot, no facts and no complaint. A gate
            # that can disable itself without saying so is not a gate.
            job.setdefault("notes", []).append(
                f"⚠ visual gate did not run ({type(_ge).__name__}: {_ge})"[:200])
        # ── SCENE AUDIT (2026-08-25, critique-loop phase 1) ─────────────
        # The shot gate above answers "does it render without errors". This
        # answers "is what it rendered PLAUSIBLE": the game audits its own
        # scene graph headless — floating, buried, inside-a-wall — and the
        # corrections are written next to the build, where the runtime
        # applies them at every boot. One confirm pass proves they landed.
        # Best-effort like the shot gate: no chrome, no audit, no failure.
        try:
            stage("scene audit")
            import subprocess as _sp3
            import json as _json3
            _aurl = f"http://127.0.0.1:8789/games/job_{job_id}/dist/index.html"

            def _run_audit():
                r3 = _sp3.run(
                    ["node", str(BACKEND_ROOT / "tools" / "shotgate" / "audit.mjs"),
                     _aurl],
                    capture_output=True, text=True, timeout=150,
                    cwd=str(BACKEND_ROOT / "tools" / "shotgate"))
                for ln in (r3.stdout or "").splitlines():
                    if ln.startswith("AUDIT-JSON "):
                        return _json3.loads(ln[len("AUDIT-JSON "):])
                return None

            _rep = _run_audit()
            if _rep is not None:
                _dfx = [d for d in _rep.get("defects", []) if d.get("fix")]
                if _dfx:
                    (out_dir / "dist" / "audit_fixes.json").write_text(
                        _json3.dumps({"fixes": [{"id": d["id"], "fix": d["fix"]}
                                                for d in _dfx]}),
                        encoding="utf-8")
                    _rep2 = _run_audit()
                    _left = (len(_rep2.get("defects", []))
                             if _rep2 is not None else None)
                    _kinds = {}
                    for d in _dfx:
                        _kinds[d["type"]] = _kinds.get(d["type"], 0) + 1
                    job["audit"] = {"checked": _rep.get("checked"),
                                    "found": len(_rep["defects"]),
                                    "fixed": len(_dfx), "remaining": _left}
                    job.setdefault("notes", []).append(
                        "scene audit: fixed "
                        + ", ".join(f"{v} {k}" for k, v in _kinds.items())
                        + (f" — {_left} remaining after apply"
                           if _left is not None else ""))
                    if _left == 0:
                        job["checks"] = job.get("checks", 0) + 1
                else:
                    job["audit"] = {"checked": _rep.get("checked"),
                                    "found": 0, "fixed": 0}
                    job.setdefault("notes", []).append(
                        f"scene audit: {_rep.get('checked', 0)} objects checked"
                        " — nothing floating, buried or inside a wall")
                    job["checks"] = job.get("checks", 0) + 1
        except Exception:  # noqa: BLE001
            pass
        stage("done")
        _record_finish(row_id, True, job["play_url"], None)
    except Exception as e:
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {e}"
        job["trace"] = traceback.format_exc()[-1500:]
        stage("failed")
        _record_finish(row_id, False, None, job["error"])


def open_spec_as_job(spec_dict: dict, title: str = "", prompt: str = "",
                     player: str | None = None) -> int:
    """Phase 43: open a SAVED level spec as a live job — exact deterministic
    re-export (no LLM, no re-casting), so project levels are playable,
    Inspectable and editable again in seconds. The job carries spec_resolved,
    which is what the edit bar and 'save back to level' need."""
    global _next_id
    with _lock:
        job_id = _next_id
        _next_id += 1
        _jobs[job_id] = {
            "id": job_id, "prompt": prompt, "status": "running",
            "stage": "queued", "title": title,
            "created_at": time.time(), "updated_at": time.time(),
        }

    def _run() -> None:
        job = _jobs[job_id]
        try:
            import json as _json
            from app.game_export.spec import spec_from_dict
            from app.game_export.verify_game import verify_dist
            from app.game_export.web_exporter import export_web_game
            job["stage"] = "building"
            spec = spec_from_dict(spec_dict)
            job["title"] = spec.title or title
            job["seed"] = spec.seed
            job["player"] = player or spec.player.name
            out_dir = GAME_JOBS_DIR / f"job_{job_id}"
            dist = export_web_game(spec, out_dir, verbose=False)
            job["spec_resolved"] = spec.model_dump()
            (out_dir / "spec_full.json").write_text(
                _json.dumps(job["spec_resolved"]), encoding="utf-8")
            job["stage"] = "verifying"
            v = verify_dist(dist)
            if not v["ok"]:
                raise RuntimeError(f"verify failed: {v['errors']}")
            job["status"] = "complete"
            job["play_url"] = f"/games/job_{job_id}/dist/"
            job["checks"] = len(v["checks"])
            job["stage"] = "done"
        except Exception as e:
            job["status"] = "failed"
            job["error"] = f"{type(e).__name__}: {e}"
            job["trace"] = traceback.format_exc()[-1500:]
            job["stage"] = "failed"
        job["updated_at"] = time.time()

    threading.Thread(target=_run, daemon=True).start()
    return job_id


@router.post("/api/game/export")
def export_game(req: GameExportRequest):
    global _next_id
    # HOT EDIT SHORT-CIRCUIT (2026-08-05): when an edit only moves runtime
    # dials, return the patch immediately — no job, no rebuild, no re-roll
    # of a world the user already approved. The studio applies it to the
    # running game in a frame. This is the single biggest felt change:
    # iteration stops costing two minutes.
    if req.base_job_id is not None:
        _hot = classify_hot_edit(req.prompt)
        if _hot:
            _bj = _jobs.get(req.base_job_id)
            if _bj:
                _bj.setdefault("notes", []).append(
                    "live edit (no rebuild): "
                    + ", ".join(f"{k}={v}" for k, v in _hot.items()))
            return {"ok": True, "hot": True, "patch": _hot,
                    "job_id": req.base_job_id}
    with _lock:
        job_id = _next_id
        _next_id += 1
        _jobs[job_id] = {
            "id": job_id, "prompt": req.prompt, "status": "running",
            "stage": "queued", "created_at": time.time(), "updated_at": time.time(),
        }
    t = threading.Thread(target=_run_job, args=(job_id, req), daemon=True)
    t.start()
    return {"ok": True, "job_id": job_id}


@router.get("/api/game/jobs/{job_id}")
def get_game_job(job_id: int):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="game job not found")
    return {"ok": True, "job": {k: v for k, v in job.items() if k != "trace"},
            "trace": job.get("trace")}


@router.get("/api/game/jobs")
def list_game_jobs():
    return {"ok": True, "jobs": sorted(_jobs.values(), key=lambda j: -j["id"])[:50]}


@router.get("/api/game/library")
def get_library():
    """The generated-asset catalog (the user's creations ARE the marketplace).
    Raw entries are generations awaiting first-use optimization."""
    import json as _json
    from app.game_export import library as lib
    out = []
    try:
        data = _json.loads(lib.LIBRARY_JSON.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    import hashlib as _hl
    # NEWEST FIRST: library.json preserves insertion order — reverse it so
    # freshly created characters top the Assets page
    for kind, entry in list(data.items())[::-1]:
        rel = entry if isinstance(entry, str) else entry.get("raw", "")
        p = lib.BACKEND_ROOT / rel
        key = _hl.md5(kind.lower().encode("utf-8")).hexdigest()[:12]
        has_thumb = (BACKEND_ROOT / "renders" / "_actor_cache" / f"{key}_ref.png").exists()
        out.append({
            "kind": kind,
            "ready": isinstance(entry, str),
            "path": rel,
            "size_mb": round(p.stat().st_size / 1e6, 1) if p.exists() else None,
            "source": "generated",
            "thumb": f"/api/game/library/thumb/{kind}" if has_thumb else None,
        })
    return {"ok": True, "assets": out, "count": len(out)}


@router.get("/api/game/library/thumb/{kind}")
def library_thumb(kind: str):
    """Character thumbnail = its SDXL reference image (the exact picture the
    3D mesh was built from — the most honest preview possible)."""
    import hashlib as _hl
    from fastapi.responses import FileResponse
    key = _hl.md5(kind.lower().encode("utf-8")).hexdigest()[:12]
    p = BACKEND_ROOT / "renders" / "_actor_cache" / f"{key}_ref.png"
    if not p.exists():
        raise HTTPException(status_code=404, detail="no thumbnail for this character")
    return FileResponse(str(p), media_type="image/png")


class RerollAssetRequest(BaseModel):
    kind: str = Field(min_length=2, max_length=60)


@router.post("/api/game/reroll_asset")
def reroll_asset(req: RerollAssetRequest):
    """HERO REROLL (Phase 108): purge every cache for `kind` and regenerate
    with a random seed offset — a different take on the same character.
    Blocking (~6 min GPU); the frontend shows progress and then rebuilds
    the game so the new hero ships."""
    import hashlib as _hl
    import os as _os
    import random as _rd
    from pathlib import Path as _Pth
    from app.game_export import library as _lib
    from app.game_export.generate import ensure_asset, guess_pattern
    from app.game_export.bake import ensure_playable
    kind = req.kind.strip().lower()
    h = _hl.md5(kind.encode()).hexdigest()[:12]
    for f in _Pth(BACKEND_ROOT / "renders" / "_actor_cache").glob(h + "*"):
        f.unlink(missing_ok=True)
    safe = kind.replace(" ", "_")
    for pat in (safe + ".glb", safe + "_anim.glb", safe + "_atlas.png"):
        (_Pth(BACKEND_ROOT / "assets" / "library") / pat).unlink(missing_ok=True)
    try:
        import json as _j
        _lj = _j.loads(_lib.LIBRARY_JSON.read_text(encoding="utf-8"))
        _lj.pop(kind, None)
        _lib.LIBRARY_JSON.write_text(_j.dumps(_lj, indent=2), encoding="utf-8")
    except Exception:
        pass
    _os.environ["FS_REF_SEED"] = str(_rd.randint(1000, 999999))
    try:
        ensure_asset(kind, verbose=False)
        if guess_pattern(kind) in ("vehicle", "flying", "aquatic", "static"):
            ok = bool(_lib.resolve(kind))
        else:
            ok = bool(ensure_playable(kind, verbose=False))
    finally:
        _os.environ.pop("FS_REF_SEED", None)
    if not ok:
        raise HTTPException(500, f"reroll failed for '{kind}' — the previous "
                                 "hero was purged; generate any game with it to retry")
    return {"ok": True, "kind": kind}


@router.post("/api/game/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    """Phase 125: cancel a running build. Kills any generation subprocess
    (TRELLIS/TripoSG/TripoSR inference) and marks the job failed; the
    worker thread then errors out at its next subprocess call. The purged
    character re-generates cleanly on the next prompt that needs it."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.get("status") != "running":
        return {"ok": True, "already": job.get("status")}
    killed = 0
    try:
        import subprocess as _sp
        out = _sp.run(["wmic", "process", "where",
                       "name like '%python%'", "get", "ProcessId,CommandLine"],
                      capture_output=True, text=True, timeout=10).stdout
        import re as _re
        for line in out.splitlines():
            if _re.search(r"trellis|triposg|inference_", line, _re.I):
                m = _re.search(r"(\d+)\s*$", line.strip())
                if m:
                    _sp.run(["taskkill", "/PID", m.group(1), "/F"],
                            capture_output=True, timeout=5)
                    killed += 1
    except Exception:
        pass
    job["status"] = "failed"
    job["error"] = "cancelled by user"
    job["stage"] = "cancelled"
    job["updated_at"] = time.time()
    return {"ok": True, "killed_processes": killed}


@router.post("/api/game/upload_splat")
async def upload_splat(request: __import__("fastapi").Request):
    """Phase 136: accept a .ply/.splat/.ksplat upload (raw body, filename in
    X-Filename header) into assets/splats/. Returns the backend-relative
    path to pass as the export request's `splat` field."""
    name = request.headers.get("x-filename", "world.ply")
    import re as _re
    name = _re.sub(r"[^A-Za-z0-9._-]", "_", name)[-80:]
    if not name.lower().endswith((".ply", ".splat", ".ksplat")):
        raise HTTPException(400, "expected a .ply / .splat / .ksplat file")
    dest = BACKEND_ROOT / "assets" / "splats" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = await request.body()
    if len(body) > 800 * 1024 * 1024:
        raise HTTPException(413, "splat too large (800MB cap)")
    dest.write_bytes(body)
    return {"ok": True, "path": f"assets/splats/{name}", "mb": round(len(body) / 1e6, 1)}


@router.get("/api/game/splats")
def list_splats():
    """Phase 137: splat worlds available on disk (uploads + trained + samples)."""
    d = BACKEND_ROOT / "assets" / "splats"
    items = []
    if d.exists():
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in (".ply", ".splat", ".ksplat") and f.is_file():
                items.append({"name": f.name, "path": f"assets/splats/{f.name}",
                              "mb": round(f.stat().st_size / 1e6, 1)})
    return {"ok": True, "splats": items}


_splat_jobs: dict[int, dict] = {}
_splat_seq = {"n": 0}


@router.post("/api/game/train_splat")
async def train_splat(request: __import__("fastapi").Request):
    """Phase 137 Tier 2: upload a walkthrough VIDEO (raw body, X-Filename),
    train a Gaussian-splat world from it (ffmpeg -> COLMAP -> Brush).
    Long-running (20-60 min) — returns a job id to poll."""
    import re as _re
    name = _re.sub(r"[^A-Za-z0-9._-]", "_",
                   request.headers.get("x-filename", "capture.mp4"))[-80:]
    if not name.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
        raise HTTPException(400, "expected a video file (.mp4/.mov/.mkv/.webm)")
    body = await request.body()
    if len(body) > 2000 * 1024 * 1024:
        raise HTTPException(413, "video too large (2GB cap)")
    vdir = BACKEND_ROOT / "assets" / "splats" / "_train"
    vdir.mkdir(parents=True, exist_ok=True)
    vid = vdir / name
    vid.write_bytes(body)
    out = BACKEND_ROOT / "assets" / "splats" / (Path(name).stem + ".ply")

    with _lock:
        _splat_seq["n"] += 1
        job_id = _splat_seq["n"]
        _splat_jobs[job_id] = {"id": job_id, "status": "running",
                               "stage": "queued", "splat": None, "error": None}

    def _train() -> None:
        job = _splat_jobs[job_id]
        try:
            import subprocess
            p = subprocess.Popen(
                [sys.executable, str(BACKEND_ROOT / "scripts" / "train_splat.py"),
                 str(vid), str(out)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                cwd=str(BACKEND_ROOT))
            tail: list[str] = []
            for line in p.stdout or []:
                line = line.strip()
                if line:
                    tail.append(line)
                    tail[:] = tail[-30:]
                if line.startswith("STAGE:"):
                    job["stage"] = line.split(":", 1)[1]
            p.wait()
            if p.returncode == 0 and out.exists():
                # up-axis sidecar for export auto-fit (COLMAP frames are y-down)
                import json as _json
                Path(str(out) + ".meta.json").write_text(
                    _json.dumps({"source": "brush", "up": "y_down"}), encoding="utf-8")
                job["status"] = "complete"
                job["stage"] = "done"
                job["splat"] = f"assets/splats/{out.name}"
            else:
                job["status"] = "failed"
                job["error"] = "\n".join(tail[-6:]) or f"exit {p.returncode}"
        except Exception as e:  # noqa: BLE001
            job["status"] = "failed"
            job["error"] = str(e)

    threading.Thread(target=_train, daemon=True).start()
    return {"ok": True, "job_id": job_id}


class ImagineSplatRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=300)


@router.post("/api/game/imagine_splat")
def imagine_splat(req: ImagineSplatRequest):
    """Phase 137 Tier 3: text -> Gaussian splat. SDXL paints the reference,
    original TRELLIS (MIT) decodes it as 3D Gaussians and saves a .ply.
    GPU job (~5-10 min after first-run model downloads)."""
    import re as _re
    slug = _re.sub(r"[^a-z0-9]+", "_", req.prompt.lower()).strip("_")[:48] or "splat"
    out = BACKEND_ROOT / "assets" / "splats" / f"{slug}.ply"

    with _lock:
        _splat_seq["n"] += 1
        job_id = _splat_seq["n"]
        _splat_jobs[job_id] = {"id": job_id, "status": "running",
                               "stage": "reference", "splat": None, "error": None}

    def _imagine() -> None:
        job = _splat_jobs[job_id]
        try:
            import subprocess
            from app.asset_gen.reference import generate_reference, unload_reference_pipeline
            from app.game_export.generate import _minimal_slots
            ref = BACKEND_ROOT / "assets" / "splats" / "_train" / f"{slug}_ref.png"
            ref.parent.mkdir(parents=True, exist_ok=True)
            slots = _minimal_slots(req.prompt, "structure")
            generate_reference(slots, output_path=ref, style="photoreal", seed=42)
            unload_reference_pipeline()
            job["stage"] = "gaussians"
            vpy = BACKEND_ROOT / "venv_trellis" / "Scripts" / "python.exe"
            r = subprocess.run(
                [str(vpy), str(BACKEND_ROOT / "scripts" / "text_to_splat.py"),
                 str(ref), str(out)],
                capture_output=True, text=True, cwd=str(BACKEND_ROOT),
                timeout=3600)
            if r.returncode == 0 and out.exists():
                # up-axis sidecar for export auto-fit (TRELLIS gaussians are z-up)
                import json as _json
                Path(str(out) + ".meta.json").write_text(
                    _json.dumps({"source": "trellis", "up": "z"}), encoding="utf-8")
                job["status"] = "complete"
                job["stage"] = "done"
                job["splat"] = f"assets/splats/{out.name}"
            else:
                tail = ((r.stdout or "") + "\n" + (r.stderr or "")).strip().splitlines()
                job["status"] = "failed"
                job["error"] = "\n".join(tail[-6:]) or f"exit {r.returncode}"
        except Exception as e:  # noqa: BLE001
            job["status"] = "failed"
            job["error"] = str(e)

    threading.Thread(target=_imagine, daemon=True).start()
    return {"ok": True, "job_id": job_id}


@router.post("/api/game/upload_scene")
async def upload_scene(request: __import__("fastapi").Request):
    """Phase 140 (the mint.gg pattern, local): drop a SCENE IMAGE and it
    becomes the world — gemma3-vision describes it, SDXL img2img expands it
    into a seamless 360 equirect panorama, and the runtime uses it as the
    visible world backdrop AND the light source (IBL), so meshes match the
    backdrop (the coherence mint's splat worlds lack). Returns a job id
    (same poll endpoint as splat jobs)."""
    import re as _re
    name = _re.sub(r"[^A-Za-z0-9._-]", "_",
                   request.headers.get("x-filename", "scene.png"))[-80:]
    if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        raise HTTPException(400, "expected an image (.png/.jpg/.webp)")
    pdir = BACKEND_ROOT / "assets" / "panos"
    (pdir / "_src").mkdir(parents=True, exist_ok=True)
    # MULTI-PHOTO (Arc H1): multipart posts carry 2-8 views of the SAME place
    # (what mint asks for, and the only honest way to get real coverage).
    # A raw body is still the single-photo path, unchanged.
    srcs: list[Path] = []
    _ctype = (request.headers.get("content-type") or "").lower()
    if _ctype.startswith("multipart/form-data"):
        form = await request.form()
        for _k, _v in form.multi_items():
            fn = getattr(_v, "filename", None)
            if not fn or not fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            fn = _re.sub(r"[^A-Za-z0-9._-]", "_", fn)[-80:]
            data = await _v.read()
            if not data or len(data) > 40 * 1024 * 1024:
                continue
            p = pdir / "_src" / fn
            p.write_bytes(data)
            srcs.append(p)
            if len(srcs) >= 8:
                break
        if not srcs:
            raise HTTPException(400, "no usable images in the upload")
        name = srcs[0].name
    else:
        body = await request.body()
        if len(body) > 40 * 1024 * 1024:
            raise HTTPException(413, "image too large (40MB cap)")
        p = pdir / "_src" / name
        p.write_bytes(body)
        srcs = [p]
    src = srcs[0]
    slug = _re.sub(r"[^a-z0-9]+", "_", Path(name).stem.lower()).strip("_")[:48] or "scene"
    out = pdir / f"{slug}.jpg"

    with _lock:
        _splat_seq["n"] += 1
        job_id = _splat_seq["n"]
        _splat_jobs[job_id] = {"id": job_id, "status": "running",
                               "stage": "reading image", "splat": None,
                               "pano": None, "hint": None, "error": None}

    def _pano() -> None:
        job = _splat_jobs[job_id]
        try:
            import base64
            import json as _json
            import urllib.request as _ur
            # 1 — the local vision LLM describes the scene (drives both the
            # panorama prompt and the world mood)
            caption = ""
            try:
                b64 = base64.b64encode(src.read_bytes()).decode()
                req2 = _ur.Request(
                    "http://127.0.0.1:11434/api/chat",
                    data=_json.dumps({
                        "model": "gemma3:12b", "stream": False,
                        "messages": [{"role": "user", "content":
                            "Describe this scene for a 360 panorama prompt in "
                            "one line: setting, time of day, weather, mood, "
                            "key colors. No preamble.",
                            "images": [b64]}]}).encode(),
                    headers={"Content-Type": "application/json"})
                caption = _json.load(_ur.urlopen(req2, timeout=180))["message"]["content"].strip()[:300]
            except Exception:  # noqa: BLE001 — caption is enrichment
                caption = "an atmospheric outdoor scene"
            job["hint"] = caption
            # persist the caption — at BUILD time it steers the whole world
            # (terrain palette, trees, sky) to MATCH the image, so the level
            # belongs inside the panorama instead of clashing with it
            (pdir / f"{slug}.txt").write_text(caption, encoding="utf-8")
            job["stage"] = "painting panorama"
            # 2 — THE 'WALK INTO THE IMAGE' REBUILD (2026-08-04): the photo
            # survives VERBATIM at its natural field of view (~62 deg) —
            # SDXL only INPAINTS the world around it, and the original is
            # composited back pixel-perfect afterward. The old path
            # stretched the photo to 180 deg and repainted ALL of it at
            # strength 0.52, so the user's own image never survived into
            # the game. This is the property the reference splat demos
            # have: the image IS the view you walk into, untouched.
            from PIL import Image
            from PIL import ImageDraw as _ID
            from PIL import ImageFilter as _IF
            import numpy as np
            im = Image.open(src).convert("RGB")
            W, H = 2560, 1280
            iw, ih = im.size
            # ══ THE ROOT-CAUSE FIX (2026-08-05) ═══════════════════════════
            # Every 'it looks stretched' report traces to ONE geometric bug:
            # we pasted a PERSPECTIVE photo straight into an EQUIRECTANGULAR
            # panorama. Those are different projections — like pasting a flat
            # map onto a globe. The horizon bent, verticals sheared, and the
            # ground smeared into a funnel when reprojected down.
            #
            # Correct operation: treat the photo as what it is — a pinhole
            # camera view with a focal length — and RAY-TRACE it into equirect.
            # For each panorama pixel we build its 3D ray, intersect it with
            # the photo's image plane, and sample. Straight lines stay
            # straight, the horizon lands exactly at latitude 0, and the
            # ground below the horizon maps to real distances on the floor.
            HFOV = 88.0                     # phone-ish wide; honest footprint
            uu, vv = np.meshgrid((np.arange(W) + 0.5) / W,
                                 (np.arange(H) + 0.5) / H)
            lon_e = (uu - 0.5) * 2.0 * np.pi
            lat_e = (0.5 - vv) * np.pi

            def _warp_one(pim, yaw_deg):
                """Ray-trace ONE pinhole photo into the equirect at a given
                yaw. Multi-photo worlds (Arc H1) call this per photo — real
                coverage from real views beats inventing 300 degrees of
                scenery, which is the whole reason mint asks for 2-8 images."""
                pw, ph = pim.size
                fpx = (pw / 2.0) / np.tan(np.radians(HFOV / 2.0))
                lo = lon_e - np.radians(yaw_deg)          # rotate into its sector
                dx = np.cos(lat_e) * np.sin(lo)
                dy = np.sin(lat_e)
                dz = -np.cos(lat_e) * np.cos(lo)          # camera looks down -Z
                fw = dz < -1e-6
                with np.errstate(divide="ignore", invalid="ignore"):
                    px = np.where(fw, fpx * dx / (-dz) + pw / 2.0, -1e9)
                    py = np.where(fw, -fpx * dy / (-dz) + ph / 2.0, -1e9)
                ins = fw & (px >= 0) & (px <= pw - 1.001) \
                    & (py >= 0) & (py <= ph - 1.001)
                pa = np.asarray(pim, dtype=np.float32)
                xj = np.clip(px, 0, pw - 1.001); yj = np.clip(py, 0, ph - 1.001)
                x0j = xj.astype(np.int32); y0j = yj.astype(np.int32)
                fxj = (xj - x0j)[..., None]; fyj = (yj - y0j)[..., None]
                wv = (pa[y0j, x0j] * (1 - fxj) * (1 - fyj)
                      + pa[y0j, x0j + 1] * fxj * (1 - fyj)
                      + pa[y0j + 1, x0j] * (1 - fxj) * fyj
                      + pa[y0j + 1, x0j + 1] * fxj * fyj)
                return wv, ins

            # MULTI-PHOTO (Arc H1): every extra photo is real information the
            # diffuser no longer has to hallucinate. Photos are spread evenly
            # around the compass; photo 0 stays at yaw 0 so the player still
            # spawns facing the primary view.
            _ims = []
            for _sp in srcs:
                try:
                    _ims.append(Image.open(_sp).convert("RGB"))
                except Exception:
                    pass
            if not _ims:
                _ims = [im]
            _n_ph = len(_ims)
            warped = np.zeros((H, W, 3), dtype=np.float32)
            inside = np.zeros((H, W), dtype=bool)
            inside0 = None
            for _i, _pim in enumerate(_ims):
                _yaw = (360.0 / _n_ph) * _i if _n_ph > 1 else 0.0
                _wv, _ins = _warp_one(_pim, _yaw)
                _fresh = _ins & ~inside          # first photo wins overlaps
                warped[_fresh] = _wv[_fresh]
                inside |= _ins
                if inside0 is None:
                    inside0 = _ins.copy()        # tile prior uses photo 0 ONLY
            if _n_ph > 1:
                job["stage"] = f"placing {_n_ph} photos around the compass"
            photo_eq = Image.fromarray(warped.astype(np.uint8))
            photo_mask = Image.fromarray((inside * 255).astype(np.uint8))
            # bounding box of the photo's true angular footprint
            # MULTI-PHOTO FIX (2026-08-05): the bbox must come from ONE
            # photo's footprint. With photos spread around the compass the
            # merged bbox spans the whole frame INCLUDING the unfilled gaps,
            # so the tile prior tiled black and img2img (not mask-aware)
            # preserved it — verified: black wedges between every view.
            _bb = inside0 if inside0 is not None else inside
            _cols = np.where(_bb.any(axis=0))[0]
            _rows = np.where(_bb.any(axis=1))[0]
            sx0, src_w2 = int(_cols[0]), int(_cols[-1] - _cols[0] + 1)
            sy0, src_h = int(_rows[0]), int(_rows[-1] - _rows[0] + 1)
            srcp = photo_eq.crop((sx0, sy0, sx0 + src_w2, sy0 + src_h))
            canvas = Image.new("RGB", (W, H))
            # r2 PRIOR: the blurred full-stretch let the model invent a
            # different valley at a different scale. Instead, EDGE-EXTEND
            # the photo outward (columns/rows continue their own content),
            # then blur lightly — the surround is forced to continue THIS
            # scene's horizon, palette and structure.
            # r6 (kept): the prior must carry real TEXTURE — a blurred palette
            # field gives the diffuser nothing to denoise into and it returns
            # the blur (4 verified failed runs, inpaint AND img2img alike).
            # Alternating mirrored tiles of the warped photo supply structure;
            # img2img reinterprets them into fresh matching scenery.
            # The tiles are now EQUIRECT-WARPED, so the invented surround
            # shares the photo's projection instead of fighting it.
            tile_src = srcp.resize((src_w2, H), Image.LANCZOS)
            tile_flip = tile_src.transpose(Image.FLIP_LEFT_RIGHT)
            for tx in range(0, W, src_w2):
                canvas.paste(tile_flip if (tx // src_w2) % 2 else tile_src, (tx, 0))
            # composite the ray-traced photo through its TRUE footprint mask
            # (the footprint is a barrel-shaped region, not a rectangle —
            # that curvature IS the correct equirect geometry)
            canvas.paste(photo_eq, (0, 0), photo_mask)
            mask = Image.fromarray(
                (255 - np.asarray(photo_mask.filter(_IF.MaxFilter(9)))).astype(np.uint8))
            mask = mask.filter(_IF.GaussianBlur(6))
            from app.asset_gen.reference import _load_t2i_pipeline, unload_reference_pipeline
            from diffusers import StableDiffusionXLImg2ImgPipeline
            t2i = _load_t2i_pipeline()
            # r5: the INPAINT pipeline returned unpainted color fields at
            # every strength/tiling combination tried (3 verified runs).
            # img2img is the path already proven in character generation:
            # repaint the whole tile from the palette prior, then composite
            # the untouched photo back on top.
            i2i = StableDiffusionXLImg2ImgPipeline(**t2i.components)
            # r4 TILED OUTPAINT (verified fix): inpainting the whole 2:1
            # equirect in one pass returned empty color fields at ANY
            # strength — SDXL is trained on ~1:1 and collapses on a 1792x896
            # canvas. Instead the world grows outward in 1024x1024 SQUARE
            # steps the model handles natively: each pass sees a strip of
            # already-real pixels on one side and paints the rest, so the
            # panorama continues the photo instead of inventing a new scene.
            pw = 1024
            pano_prompt = ("360 degree panorama continuing outward from the "
                           "scene, " + caption
                           + ", photorealistic, consistent horizon line, "
                             "matching light and colors, no seams")
            neg = "text, watermark, people, frame, border, blurry, distorted"
            res = canvas
            for direction in ("right", "left"):
                # walk outward from the photo in half-tile steps
                steps = int(np.ceil(((W - src_w2) / 2) / (pw // 2)))
                for si in range(steps):
                    if direction == "right":
                        x_end = min(W, sx0 + src_w2 + (si + 1) * (pw // 2))
                        x_start = max(0, x_end - pw)
                    else:
                        x_start = max(0, sx0 - (si + 1) * (pw // 2))
                        x_end = min(W, x_start + pw)
                    if x_end - x_start < 64:
                        continue
                    tile = res.crop((x_start, 0, x_end, H)).resize((pw, pw), Image.LANCZOS)
                    tmask = mask.crop((x_start, 0, x_end, H)).resize((pw, pw), Image.LANCZOS)
                    if np.asarray(tmask).mean() < 4:
                        continue                       # nothing left to paint
                    # NOTE: never name this 'out' — that's the pano's output
                    # PATH in the enclosing scope (cost one failed run)
                    # 0.85: high enough to break the repeated-photo pattern
                    # into new scenery, low enough to keep its structure
                    tile_out = i2i(prompt=pano_prompt, negative_prompt=neg,
                                   image=tile, strength=0.85,
                                   guidance_scale=6.5,
                                   num_inference_steps=28).images[0]
                    painted = tile_out.resize((x_end - x_start, H), Image.LANCZOS)
                    # keep whatever was already REAL in this strip (the photo
                    # and previously-painted pixels) — mask decides per pixel
                    keep = tmask.resize((x_end - x_start, H), Image.LANCZOS)
                    res.paste(painted, (x_start, 0), keep)
                    # painted pixels are now REAL: they anchor the next step
                    md = _ID.Draw(mask)
                    md.rectangle([x_start, 0, x_end, H], fill=0)
                    md.rectangle([sx0 - 2, sy0 - 2, sx0 + src_w2 + 2, sy0 + src_h + 2], fill=0)
            # the ray-traced photo goes back through its true footprint —
            # geometrically exact, and it always wins over generated pixels
            res.paste(photo_eq, (0, 0), photo_mask)
            arr = np.asarray(res).astype(np.float32)
            # 2b — POLE REPAIR (2026-08-05): SDXL has no concept of equirect
            # projection, so in the top/bottom bands it paints BUILDINGS —
            # verified: upside-down towers overhead and aerial streets
            # underfoot. Geometry knows better: above the scene there is
            # sky, below it there is ground. Both poles are rebuilt by
            # vertically extending the nearest valid row and easing into a
            # single averaged colour at the pole itself, so the dome closes
            # cleanly instead of pinwheeling invented architecture.
            _pol = np.radians(38.0)
            _lat_col = (0.5 - (np.arange(H) + 0.5) / H) * np.pi
            _top_i = int(np.argmax(_lat_col < _pol))          # first row below +38
            _bot_i = int(np.argmax(_lat_col < -_pol))         # first row below -38
            if 0 < _top_i < _bot_i < H:
                _sky = arr[_top_i:_top_i + 12].mean(axis=(0, 1))
                _gnd = arr[max(0, _bot_i - 12):_bot_i].mean(axis=(0, 1))
                for _y in range(_top_i):
                    t = 1.0 - (_y / max(_top_i - 1, 1))       # 1 at pole
                    arr[_y] = arr[_top_i] * (1 - t) + _sky * t
                for _y in range(_bot_i, H):
                    t = (_y - _bot_i) / max(H - _bot_i - 1, 1)
                    arr[_y] = arr[_bot_i - 1] * (1 - t) + _gnd * t
            # 3 — horizontal wrap-seam blend so the pano tiles at 0/360
            blend = 96
            for x in range(blend):
                a = x / blend
                arr[:, x] = arr[:, x] * a + arr[:, -blend + x] * (1 - a)
            # EXPOSURE NORMALISATION (2026-08-05): a blanket runtime lift
            # blew out bright source photos and still left dark ones murky
            # (verified: a sunset test photo rendered as white haze).
            # Normalise HERE instead — every panorama lands on the same
            # mid-tone, so ONE neutral runtime exposure serves all images.
            # Gentle (sqrt, clamped) so contrast and mood survive.
            _luma = float((arr * np.array([0.299, 0.587, 0.114])).sum(-1).mean())
            if 4.0 < _luma < 250.0:
                arr = np.clip(arr * float(np.clip(np.sqrt(112.0 / _luma),
                                                  0.72, 1.5)), 0, 255)
            Image.fromarray(arr.astype(np.uint8)).save(out, "JPEG", quality=90)
            try:
                unload_reference_pipeline()
            except Exception:
                pass
            # PHASE B — depth lift: Depth-Anything-V2-Small (Apache-2.0)
            # estimates per-pixel depth on the panorama; the runtime
            # displaces a dome with it so the world has REAL PARALLAX as
            # the player moves (the walkable-splat feel, no splats needed).
            job["stage"] = "measuring depth"
            try:
                from transformers import pipeline as _tfpipe
                # DPT-MiDaS (MIT/Apache): the installed transformers predates
                # the 'depth_anything' model type — DPT is the supported
                # classic and plenty for dome displacement
                dp = _tfpipe("depth-estimation",
                             model="Intel/dpt-hybrid-midas", device=0)
                dres = dp(Image.fromarray(arr.astype(np.uint8)))
                dm = np.asarray(dres["depth"], dtype=np.float32)
                dm = (dm - dm.min()) / max(float(dm.max() - dm.min()), 1e-6)
                Image.fromarray((dm * 255).astype(np.uint8)) \
                    .resize((768, 384)).save(pdir / f"{slug}_d.png")
                del dp
                import torch as _t2
                if _t2.cuda.is_available():
                    _t2.cuda.empty_cache()
                # ── SPLAT LIFT (2026-08-04, the mint answer): synthesize a
                # REAL gaussian-splat world from the image — every pixel
                # above the horizon band becomes a 3D gaussian at its
                # measured depth (our terrain owns the floor). No models,
                # pure numpy; renders through the existing splat pipeline.
                job["stage"] = "lifting to gaussian splats"
                sw, sh = 896, 448
                pano_s = np.asarray(Image.fromarray(arr.astype(np.uint8))
                                    .resize((sw, sh)), dtype=np.float32) / 255.0
                dm_s = np.asarray(Image.fromarray((dm * 255).astype(np.uint8))
                                  .resize((sw, sh)), dtype=np.float32) / 255.0
                us, vs = np.meshgrid((np.arange(sw) + 0.5) / sw,
                                     (np.arange(sh) + 0.5) / sh)
                lon = (us - 0.5) * 2.0 * np.pi
                lat = (0.5 - vs) * np.pi
                # lift ONLY near/mid scenery (disparity >= 0.2 ≈ within
                # ~225m) — sky and far haze stay on the background pano;
                # lifting them wrapped the camera in an opaque white shell
                # METRIC CALIBRATION (research: THE 'being there' fix — DPT
                # is relative disparity, so without this the scene has no
                # true scale). Assume the pano camera stands 1.6m above a
                # flat floor: a ground-band pixel at latitude L has true
                # range 1.6/sin(-L). Fit r = k/d on that band (median) so
                # the WHOLE lift shares one metric scale.
                lat_f = lat.ravel()
                d_f = dm_s.ravel()
                gb = (lat_f < np.radians(-25.0)) & (d_f > 0.05)
                if int(gb.sum()) > 500:
                    k = float(np.median((1.6 / np.sin(-lat_f[gb])) * d_f[gb]))
                    k = float(np.clip(k, 6.0, 120.0))
                else:
                    k = 45.0
                # THE WALL FIX (2026-08-04 — research verdict, verbatim:
                # "the 45m inner radius. Delete it. That single number is
                # what makes it a wall."). Standing scenery off at 55m is
                # exactly why the photo read as a billboard in front of the
                # player instead of a place around them. Two changes:
                #  1. NO minimum radius — near scenery comes all the way in.
                #  2. GROUND SUBSTITUTION below the horizon: predicted depth
                #     is DISCARDED and replaced with the exact plane
                #     solution r = h / sin(-lat), h = 1.6m eye height (the
                #     same math three.js GroundedSkybox uses). A relative
                #     depth model can never hold a floor flat; geometry can.
                # Result: ONE CONTINUOUS SHEET from underfoot to horizon —
                # the seam only existed because we had a shell with a hole.
                r_depth = k / np.maximum(d_f, 0.14)
                lat_g2 = np.minimum(lat_f, np.radians(-2.5))
                r_ground = 1.6 / np.maximum(np.sin(-lat_g2), 1e-3)
                below = lat_f < np.radians(-2.5)
                rr_all = np.where(below, np.minimum(r_ground, 400.0), r_depth)
                keep = (d_f >= 0.10) & (lat_f < np.radians(58.0))  # sky stays on the pano
                rr = np.clip(rr_all, 0.7, 400.0)[keep]
                # depth-edge shrink: splats straddling discontinuities smear
                # the moment the player translates — shrink them hard
                gy2, gx2 = np.gradient(np.log(np.maximum(dm_s, 0.05)))
                shrink = (1.0 / (1.0 + 10.0 * np.hypot(gx2, gy2))).ravel()[keep]
                lonk, latk = lon.ravel()[keep], lat.ravel()[keep]
                n = int(rr.size)
                # 17 floats/vertex: xyz + normals + f_dc + opacity + 3 scale
                # + 4 rot — writing 18 once misaligned every vertex (giant
                # garbage blobs); the header's property count is the law
                d18 = np.zeros((n, 17), dtype="<f4")
                d18[:, 0] = np.cos(latk) * np.sin(lonk) * rr
                d18[:, 1] = np.sin(latk) * rr + 1.6
                d18[:, 2] = -np.cos(latk) * np.cos(lonk) * rr
                d18[:, 6:9] = (pano_s.reshape(-1, 3)[keep] - 0.5) / 0.28209479177
                d18[:, 9] = 6.0                          # ~opaque after sigmoid
                d18[:, 10:13] = np.log(np.maximum(
                    rr * (2.0 * np.pi / sw) * 1.15 * shrink, 1e-3))[:, None]
                d18[:, 13] = 1.0                          # identity rotation
                sp_out = pdir / f"{slug}_splat.ply"
                hdr = ("ply\nformat binary_little_endian 1.0\n"
                       f"element vertex {n}\n"
                       + "".join(f"property float {p}\n" for p in
                                 ("x", "y", "z", "nx", "ny", "nz",
                                  "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
                                  "scale_0", "scale_1", "scale_2",
                                  "rot_0", "rot_1", "rot_2", "rot_3"))
                       + "end_header\n")
                with open(sp_out, "wb") as fh:
                    fh.write(hdr.encode("ascii"))
                    d18.tofile(fh)
                print(f"[pano] splat lift: {n} gaussians -> {sp_out.name}", flush=True)
                # GROUND PROJECTION (the user-named gap: 'you don't make it
                # the ground'): reproject the pano's below-horizon pixels
                # onto the y=0 floor (camera 1.6m) — the sand you walk on IS
                # the photo's sand, continuous into the horizon.
                job["stage"] = "projecting ground"
                # r2 CRISPNESS (2026-08-04): 1024px over 300m = 30cm/px mush
                # underfoot. 2048px over 240m = 12cm/px, BILINEAR sampled +
                # unsharp — the far field belongs to the splats/pano anyway.
                G, half = 2048, 120.0
                xs2 = np.linspace(-half, half, G)
                gx3, gz3 = np.meshgrid(xs2, xs2)
                dist3 = np.hypot(gx3, gz3)
                lat_g = -np.arctan2(1.6, np.maximum(dist3, 0.35))
                lon_g = np.arctan2(gx3, -gz3)
                Hp, Wp = arr.shape[0], arr.shape[1]
                uf = (lon_g / (2 * np.pi) + 0.5) * (Wp - 1)
                vf = (0.5 - lat_g / np.pi) * (Hp - 1)
                x0 = np.clip(np.floor(uf).astype(int), 0, Wp - 2)
                y0 = np.clip(np.floor(vf).astype(int), 0, Hp - 2)
                fx3 = np.clip(uf - x0, 0, 1)[..., None]
                fy3 = np.clip(vf - y0, 0, 1)[..., None]
                ground = (arr[y0, x0] * (1 - fx3) * (1 - fy3)
                          + arr[y0, x0 + 1] * fx3 * (1 - fy3)
                          + arr[y0 + 1, x0] * (1 - fx3) * fy3
                          + arr[y0 + 1, x0 + 1] * fx3 * fy3)
                # PLAYABILITY LIFT: dark source photos (dusk forest) bake a
                # near-black floor — gamma-normalize so mean luminance lands
                # ~0.34 while keeping the photo's identity
                gl = ground.mean() / 255.0
                if gl < 0.30:
                    gamma = np.log(0.34) / np.log(max(gl, 0.02))
                    ground = np.power(ground / 255.0, gamma) * 255.0
                from PIL import ImageFilter
                # RING FIX (2026-08-04 playtest): pure reprojection fans the
                # floor into concentric rings — a photo has almost no pixels
                # for the ground BENEATH the camera (it never sees there), so
                # each distance ring samples one image row. Standard fix:
                # the projection keeps large-scale colour + lighting (blurred),
                # and a TILED CROP of the photo's real visible ground supplies
                # the high-frequency grain. Rings vanish, material is honest.
                gimg = Image.fromarray(ground.astype(np.uint8))
                low = np.asarray(gimg.filter(ImageFilter.GaussianBlur(14)),
                                 dtype=np.float32)
                # crop the photo's own near-ground band (bottom centre)
                cw = max(64, min(iw, ih) // 3)
                cx1 = max(0, iw // 2 - cw // 2)
                cy1 = max(0, ih - int(ih * 0.30) - cw // 2)
                patch = np.asarray(im.crop((cx1, cy1, cx1 + cw, cy1 + cw))
                                   .resize((512, 512), Image.LANCZOS),
                                   dtype=np.float32)
                # mirror-tile so edges meet, then normalise to a detail mask
                tile = np.concatenate([patch, patch[:, ::-1]], axis=1)
                tile = np.concatenate([tile, tile[::-1]], axis=0)   # 1024^2
                reps = int(np.ceil(G / tile.shape[0]))
                det = np.tile(tile, (reps, reps, 1))[:G, :G]
                det = det / np.maximum(det.mean(axis=(0, 1), keepdims=True), 1e-3)
                final = np.clip(low * (0.62 + 0.38 * det), 0, 255)
                Image.fromarray(final.astype(np.uint8)) \
                    .filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2)) \
                    .save(pdir / f"{slug}_ground.jpg", quality=92)
            except Exception as e:  # noqa: BLE001 — dome falls back to flat pano
                print(f"[pano] depth lift skipped: {e}", flush=True)
            job["status"] = "complete"
            job["stage"] = "done"
            job["pano"] = f"assets/panos/{out.name}"
        except Exception as e:  # noqa: BLE001
            job["status"] = "failed"
            job["error"] = str(e)[:300]

    threading.Thread(target=_pano, daemon=True).start()
    return {"ok": True, "job_id": job_id}


@router.get("/api/game/splat_jobs/{job_id}")
def get_splat_job(job_id: int):
    job = _splat_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such splat job")
    return {"ok": True, "job": job}


@router.get("/api/game/health")
def game_health():
    """Game mode works without a GPU — report what's available."""
    from app.game_export import library as lib
    kinds = []
    try:
        import json as _json
        kinds = list(_json.loads(lib.LIBRARY_JSON.read_text(encoding="utf-8")).keys())
    except Exception:
        pass
    ollama = False
    try:
        from app.orchestrator.llm import OllamaClient
        ollama = OllamaClient().is_alive()
    except Exception:
        pass
    gpu_name = None
    try:
        from app.game_export.generate import gpu_available
        if gpu_available():
            import torch
            gpu_name = torch.cuda.get_device_name(0)
    except Exception:
        pass
    return {"ok": True, "gpu_free": True, "gpu": gpu_name, "ollama": ollama,
            "library_kinds": kinds}
