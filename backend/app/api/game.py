"""Game-mode API (Phase 30): prompt → playable web game, served back to the
frontend. Mirrors the render-jobs UX (submit → poll → play) but games build in
seconds and need NO GPU (library assets), so this works while the video lane's
generation is GPU-blocked.

Jobs are in-memory (games rebuild in ~30s; no DB migration risk). Built games
are served by the /games static mount added in main.py.
"""
from __future__ import annotations

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
                    r"(?:a|an|the|another|some)?\s*(.+)$",
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
                    noun = _re.sub(
                        r"\b(right\s+)?(here|there|at (this|the selected) spot|"
                        r"on (this|the) spot|in this spot)\b",
                        "", rest, flags=_re.IGNORECASE).strip(" .!,\"'")
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
                            items.append(
                                {"kind": kind, "name": noun.lower(),
                                 "x": round(req.at_x, 2), "z": round(req.at_z, 2),
                                 "interact": interact})
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
                spec = patch_game_spec(base_spec, change, verbose=False)
                # STYLE + VIEW ARE SACRED (2026-07-08): the LLM must never
                # drop or drift them during an edit — carry the base game's
                # choices forward; only the explicit-word overrides below may
                # change them
                try:
                    spec.style = base_spec.get("style", spec.style) or spec.style
                    spec.view = base_spec.get("view", spec.view) or spec.view
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
            stage("extracting")
            spec = extract_game_spec(req.prompt, verbose=False)
            job["title"] = spec.title
        # STYLE IS THE USER'S CHOICE (Phase 44): the studio's style chips set
        # it explicitly — the LLM never guesses it, so it's never wrong
        if req.style:
            try:
                spec.style = req.style        # pydantic validates the literal
            except Exception:
                job.setdefault("notes", []).append(
                    f"unknown style '{req.style}' — kept {spec.style}")
        if req.view:
            try:
                spec.view = req.view
            except Exception:
                job.setdefault("notes", []).append(
                    f"unknown view '{req.view}' — kept {spec.view}")
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
        cast = want
        pattern = guess_pattern(want)
        # vehicles DRIVE, flyers FLY, swimmers SWIM — all play as static
        # meshes (no rig); everything else needs the rigged+animated bake
        if pattern in ("vehicle", "flying", "aquatic", "static"):
            player_glb = library.resolve(want)
        else:
            player_glb = ensure_playable(want, verbose=False)
        if not player_glb:
            # THE VISION PATH (primary): unknown hero → SDXL image → 3D mesh →
            # library → playable. This is how the pipeline is MEANT to work and
            # it runs on CPU too (~25-30 min once, then cached forever — the cat
            # and fox were both born this way). We ALWAYS attempt it; a GPU just
            # makes it faster/better. Only a genuine generation FAILURE falls
            # through to the honest same-species stand-in below (never a
            # man-with-a-sword). FS_CPU_CHARGEN=0 disables CPU generation.
            try:
                from app.game_export.generate import ensure_asset
                stage(f"creating '{want}' — image → 3D mesh "
                      f"(first time only; ~25-30 min on CPU, then cached forever)")
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
        if player_glb and pattern == "vehicle":
            spec.player.mode = "drive"
            if abs(spec.player.walk_speed - 2.0) < 1e-6:
                spec.player.walk_speed = 9.0                 # cruise
            if abs(spec.player.run_speed - 5.0) < 1e-6:
                spec.player.run_speed = 19.0                 # boost
        if player_glb and pattern == "flying":
            spec.player.mode = "fly"
            if abs(spec.player.walk_speed - 2.0) < 1e-6:
                spec.player.walk_speed = 6.0                 # glide
            if abs(spec.player.run_speed - 5.0) < 1e-6:
                spec.player.run_speed = 15.0                 # dive/boost
        if player_glb and pattern == "aquatic":
            spec.player.mode = "swim"
            if abs(spec.player.walk_speed - 2.0) < 1e-6:
                spec.player.walk_speed = 6.0                 # cruise (whales MOVE)
            if abs(spec.player.run_speed - 5.0) < 1e-6:
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
        spec.player.asset = player_glb
        spec.player.name = cast
        if abs(spec.player.height_m - 1.75) < 1e-6:      # untouched default -> species height
            spec.player.height_m = library.default_height(cast)
        # CAMERA SCALED TO THE HERO: a 0.6 m fox filmed from person-distance
        # is a speck on screen. Whatever the extractor picked, CLAMP distance
        # and height into a band derived from the cast's actual size — the
        # LLM's choice survives inside the band, absurd framing doesn't.
        h = spec.player.height_m
        spec.camera.distance_m = max(2.0 * h + 0.8,
                                     min(spec.camera.distance_m, 4.2 * h + 2.0))
        spec.camera.height_m = max(0.9 * h,
                                   min(spec.camera.height_m, 2.2 * h + 0.6))
        # per-asset heading facts (play-verified): a generated mesh's nose sign
        # is ambiguous — side-profile refs face either way — so the correction
        # lives as DATA in assets/library_heading.json, never a runtime guess.
        try:
            import json as _json
            _headings = _json.loads((BACKEND_ROOT / "assets" / "library_heading.json")
                                    .read_text(encoding="utf-8"))
            if cast in _headings:
                spec.player.yaw_offset_deg = float(_headings[cast])
        except Exception:
            pass
        job["player"] = cast
        if not spec.world.scatter:
            spec.world.scatter = [ScatterSpec(**s) for s in game_scatter(spec.world.name)]
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
                job.setdefault("notes", []).append(
                    f"the AI imagined '{ekind}' for this world — it's not in "
                    f"your library yet, so it was skipped. Mention '{ekind}' in "
                    f"a prompt or edit to create it once (then it's free forever)")
                continue
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
                ent.asset = glb
                if ent.height_m == 1.0:
                    ent.height_m = library.default_height(ekind)
                    if ent.height_m == 1.0 and guess_pattern(ekind) == "static":
                        ent.height_m = 0.5   # unknown props default small, not person-sized
                kept.append(ent)
            else:
                job.setdefault("notes", []).append(
                    f"entity '{ekind}' not in library yet — skipped")
        spec.entities = kept

        # PLACED ITEMS (Phase 42 Inspector): explicit-coordinate objects from
        # click-to-place edits. Procedural prop kinds render instantly in the
        # runtime; any other noun resolves through the same casting ladder as
        # entities. Placed items are ALWAYS user-invited (they come from an
        # edit, never LLM invention), so unknown nouns may generate.
        _PROC_ALIASES = {"house": "building", "hut": "building", "cabin": "building",
                         "cottage": "building", "shack": "building", "tower": "building",
                         "stone": "rock", "boulder": "rock", "lantern": "beacon",
                         "torch": "campfire", "fire": "campfire", "bonfire": "campfire",
                         "note": "book", "letter": "book", "scroll": "book",
                         "tome": "book", "signpost": "sign", "signboard": "sign",
                         "crate": "chest", "box": "chest", "treasure": "chest",
                         "wall": "fence", "railing": "fence", "barrier": "fence",
                         "hedge": "fence", "gate": "fence", "palisade": "fence"}
        _PROC_PROPS = {"book", "sign", "chest", "building", "rock", "beacon",
                       "campfire", "fence"}
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
        if place:
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
        _water = any(k in _wname for k in ("ocean", "underwater", "lake", "river"))
        if _water:
            amp = max(amp, 3.0)                     # seabed dunes
            spec.world.water_level = 8.0 if "lake" not in _wname else 4.0
        elif spec.player.mode == "swim":
            # aquatic player in a non-water world: give them water anyway
            spec.world.water_level = 8.0
            amp = max(amp, 3.0)
        spec.world.level = build_level(
            spec.seed, spec.world.size_m, n_objectives=n_obj, amplitude_m=amp)
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

        stage("building")
        # RESOLVED spec (absolute asset paths) — lets Game Projects re-export
        # this exact level later without re-running extraction
        job["spec_resolved"] = spec.model_dump()
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
    return {"ok": True, "gpu_free": True, "ollama": ollama, "library_kinds": kinds}
