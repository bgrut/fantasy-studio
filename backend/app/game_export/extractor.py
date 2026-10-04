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
           "ground_color": [r,g,b] floats 0..1 — the COLOUR OF THE GROUND
           MATERIAL ITSELF, as if you picked it up in your hand: grass is
           green, soil brown, rock grey, sand pale gold, snow white. It is
           NOT the lighting, the time of day or the mood. A "sunny meadow"
           has GREEN ground and warm LIGHT — put the sunlight in "palette",
           never in the ground, because a pale-yellow ground renders the
           meadow as bleached sand. Keep it SATURATED and MID-DARK: real
           ground sits around 0.2-0.55 per channel, and anything above 0.75
           on every channel is snow or nothing. Grass [0.30,0.48,0.22],
           forest floor [0.22,0.30,0.16], soil [0.34,0.24,0.15], red rock
           [0.46,0.24,0.16], sand [0.72,0.62,0.40], snow [0.90,0.92,0.95]},
 "world" may also include "archetype": THE LANDFORM, and the structural twin of
 "style" — one of "plain" (gentle rolling ground, the default), "canyon" (high
 tableland split by a deep winding gorge), "mesa" (stepped flat-topped plateaus
 with cliff edges), "dunes" (long parallel desert ridges), "basin" (a sheltered
 bowl inside a raised rim), "peaks" (alpine, sharp summits and deep valleys),
 "archipelago" (open sea with islands rising out of it), "volcano" (a lava
 field on a volcano's flank, lava channels to cross, the smoking cone ahead),
 "cave" (underground: a tunnel through rock opening into chambers, under a roof).
 Pick the one the text
 describes or implies: sailing/diving/island-hopping -> archipelago; desert or
 sand -> dunes; a gorge, ravine or river-cut -> canyon; badlands or a
 southwestern butte country -> mesa; a crater, valley floor or sheltered
 hollow -> basin; mountains, climbing or snowy summits -> peaks; a volcano,
 lava, magma or an eruption -> volcano; a cave, cavern, grotto, mine tunnel or
 anything underground -> cave. Use "plain"
 for ordinary fields, forests, towns and city streets.
 ANY world set ON or UNDER water — sailing, a boat or ship, the sea, the ocean,
 diving, reefs, islands, pirates — MUST use "archetype":"archipelago" and set
 "sky" to a real daylight or night sky (never "space"). archipelago is the only
 landform that puts a sea in the world, so without it a sailing game is dry
 lumpy ground and the boat sits on dirt.
 "genre": "adventure" or "factory", TOP-LEVEL. Use "factory" when the text
 describes BUILDING A PRODUCTION SYSTEM rather than a quest — automation,
 conveyor belts, mining and refining, a factory, a base you expand, "automate",
 "production line", "assembly", "logistics", "idle/incremental". A factory game
 has no hero and no combat: the player is a builder placing machines, so do not
 invent objectives like "defeat" or "collect 5 X" for one. Everything else is
 "adventure".
 "theme": TOP-LEVEL, ONLY for genre "factory", and only when the prompt's world
 is not literally mining and smelting. It names the game's things in the
 prompt's own fiction so the screen reads in that world. An object with these
 keys, each a short lowercase noun (singular): "resource" (what is gathered:
 "grain", "kelp", "scrap"), "deposit" (where it grows or lies: "field",
 "bed", "heap"), "ores" (a list of exactly three kinds of the resource:
 ["wheat","barley","rye"]), "refined" (one step processed: "flour"),
 "combined" (two kinds combined: "dough"), "product" (the finished thing:
 "loaf"), "currency" (what it sells for: "coins"), "extractor" (the machine
 that gathers: "harvester"), "refiner" ("mill"), "combiner" ("kneader"),
 "assembler" ("oven"), "outlet" (where things are sold: "stall"), "carrier"
 (what moves things: "cart"). Give a plural after a slash when it is not the
 singular plus s: "flour/flour", "dough/dough", "loaf/loaves", "grain/grain".
 EVERY WORD NAMES A DIFFERENT THING: never reuse the resource as "refined",
 "combined" or "product". A turnip farm is turnip -> washed turnip -> turnip
 crate -> turnip stew, never turnip -> turnip -> turnip.
 A rusted mining outpost needs no theme: omit it.
 A HAUNTING HAS GHOSTS: a prompt about a haunting, a curse, spirits or the
 undead casts its hostiles as "ghost" (or "spirit", "wraith", "phantom"), never as
 wolves or bears, and gives them "spectral": true and a speed under 1.2.
 "style": A TOP-LEVEL FIELD, a sibling of "world" and "player" — NOT a key
 inside "world". Put it at the root of the object: {"title":..., "style":"pixel",
 "world":{...}}. It is THE ART DIRECTION, and the single biggest lever on
 whether two games look like different products. Pick from: "default" (photoreal — natural light
 and texture), "cartoon" (flat cel fills, thick ink outlines, saturated),
 "sketch" (hand-drawn linework), "anime" (soft cel banding, bright), "horror"
 (desaturated, crushed blacks, heavy grain), "pixel" (low-res nearest-neighbour,
 retro), "lowpoly" (flat-shaded facets, clean palettes), and the ILLUSTRATION looks,
 which are whole art directions rather than filters — each commits a palette,
 an atmosphere and a surface treatment together: "illustrated" (warm flat
 colour fields separated by haze, like a painted poster; forests, lookouts,
 wilderness), "dunescape" (sand and low golden sun, soft distance, vast and
 quiet; deserts, dunes, pilgrimage), "watercolor" (pale washes, soft light,
 storybook; fairy tales, gentle worlds), "claymation" (simple rounded forms
 under real light, toy-like and tactile), "noir" (near-monochrome silhouettes
 in grey haze, grain, dread; horror, mystery, the unsettling), "storybook"
 (inked linework over muted paper, spindly and hand-drawn; gothic whimsy,
 survival, the eerie). USE "default" (photoreal) UNLESS THE PROMPT ASKS FOR
 A LOOK in its own words: a shark-hunting sailboat adventure is "default"; a
 haunted asylum reads "horror"; a retro 8-bit arcade racer reads "pixel"; a
 Ghibli-ish forest walk reads "anime"; a gritty city heist, a wildlife documentary, or a NIGHT STREET RACE
 under neon reads "default" (neon is light, not resolution: it wants real
 reflections and a night palette with a hot accent, not a low-res filter).
 THE ILLUSTRATION LOOKS OWN THEIR SKY: "illustrated", "storybook",
 "watercolor", "dunescape" and "papercraft" paint a paper daylight over the
 world, so a prompt whose whole point is night light (moonlit, fireflies,
 lanterns, candles, stars, dawn, dusk, aurora, bioluminescent) MUST be
 "default" or "anime" with a night "sky" in "world"; a paper look on a night
 prompt is WRONG and will be overridden.
 ALWAYS EMIT "style". Every prompt carries a genre and every genre implies a
 look, so "default" is a CHOICE meaning "photoreal", never a way to skip the
 question. A prompt naming retro, 8-bit, 16-bit, pixel art or "arcade cabinet"
 MUST be "pixel"; neon, synthwave, cyberpunk and night-city prompts are
 "default" with a palette (dark sky, coloured fog, one hot accent), never
 "pixel"; naming haunted, cursed, undead, asylum or nightmare MUST be
 "horror"; naming cute, cartoon, toy or kid-friendly MUST be "cartoon". If two
 prompts on the same subject would look identical coming out of this field,
 you have not used it.
 "world" may also include "palette": a COLOR SCRIPT when the text implies a mood —
 {"sky":"#rrggbb","fog":"#rrggbb","sun_color":"#rrggbb","accent":"#rrggbb",
  "sun_azimuth_deg":0-360,"sun_elevation_deg":4-88,"sun_intensity":0.2-4.5,
  "ambient":0.1-1.0,"exposure":0.4-1.3}. COMMIT to 2-4 hues like a film still —
 sky and fog in the same family, one warm or neon accent. Examples:
 The "sky" you give MUST BE A REAL SKY COLOUR with real saturation — daylight
 is a deep blue near #6ba3e8, overcast a grey-blue near #9aa8b4, sunset orange,
 night near-black blue. NEVER a pale near-white wash: a sky lighter than about
 #c8dce8 renders as fog, drains the whole frame and makes a sunny world look
 washed out and flat. If you are not confident, OMIT "palette" and let the
 preset sky do its job — it is already correct for day/sunset/night.
 neon/synthwave/cyberpunk night -> {"sky":"#0a0618","fog":"#1a0f2e",
 "sun_color":"#b0c8ff","accent":"#ff2fa0","sun_elevation_deg":18,"exposure":0.85};
 golden/peach sunset -> {"sky":"#e8996a","fog":"#e5b48a","sun_color":"#ffcf9a",
 "accent":"#ff8a4a","sun_elevation_deg":10,"sun_azimuth_deg":255,"exposure":0.75};
 violet starlit night -> {"sky":"#0d0a24","fog":"#241a44","sun_color":"#9a8ce8",
 "accent":"#ffb060","ambient":0.42}. Omit "palette" entirely for neutral scenes.
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
               TOWER DEFENCE ("build towers/turrets", "defend the castle/base/village from
               waves", "tower defense") -> {"kind":"defend","label": what is defended
               ("castle","village","base"),"count": WAVES 3..8} AND the attackers as ONE
               hostile entity {"name": creature noun,"behavior":"hostile","count": 6..12}.
               The PLAYER is the DEFENDER ("archer","knight","ranger"), never the attacker;
               "battle royale"/"last one standing"/"eliminate all N rivals" ->
               {"kind":"eliminate","label":"rivals","count": N rivals 2..12};
               soccer/football/"score N goals" -> {"kind":"score","label":"goals","count": N 1..10};
               MYSTERY / WHODUNIT ("question the suspects", "name the killer", "solve the
               murder") -> [{"kind":"collect","label":"clues","count":3,"asset":"clue"},
               {"kind":"accuse","label":"the killer","count":1}] AND 3-5 people with
               "behavior":"suspect", each {"name": a human body ("man","scientist"),
               "role": who they are in the story ("the butler","the gardener")};
               "hunt N elk/deer..." -> {"kind":"hunt","label":prey noun,"count": N 1..8}
               (prey = entity behavior "flee" - it runs when it hears the player);
               "escort/protect/lead/guide NAME to PLACE" -> {"kind":"escort",
               "label": NAME} AND one entity {"name": NAME, "behavior":"escort",
               "count":1} — the escortee walks to the goal by itself and DIES if
               unprotected, so escort games also need hostile entities to defend
               against (an escort without threats is a walk),
 "entities": [{"name": simple noun like "dog","cat","horse","wolf","car", "behavior": one of
               "wander","follow","static","hostile","vehicle" (cars/trucks -> "vehicle"),
               "guard" (patrolling sentries with VISION CONES for stealth/heist games —
               they only attack when they SEE the player; sneak past by crouching),
               "guide" (a friendly mentor/informant/professor who greets the player and
               explains each objective — add ONE to any game with a story or a
               tutorial feel; never hostile),
               "escort" (the person/creature the player must protect on the road —
               use with an "escort" objective; never also mark them "guide"),
               "count": int 1..8, "speed": float 0.5..8}]
}
Map the text's setting to the CLOSEST world.name keyword. entities = OTHER creatures/characters besides
the player (companion pet -> "follow"; enemies/monsters the player fights -> "hostile";
guards/security/police in a heist or stealth game -> "guard").
HEIST/BURGLAR/STEAL games: objectives = steal the goods ({"kind":"collect",
"label":"jewels"|"paintings"|...}) then escape ({"kind":"reach","label":"the getaway car"});
entities = 2-4 "guard".
"defeat" objectives need hostile entities.
"events": OPTIONAL story beats — scripted reversals that fire DURING play. Each is
{"when": condition, "then": [actions]}. Conditions (exact grammar):
"collected>=N" (N items taken so far) | "kills>=N" | "time>N" (seconds since start) |
"hp<=N" (player hearts) | "alert" (a guard has spotted the player).
Actions (exact grammar): "popup:TEXT" (dramatic one-liner shown to the player) |
"spawn:NAME xN" (N more of an entity ALREADY in this game's entities list appear near
the player) | "alertguards" (every guard converges) | "timer:SECONDS:LABEL:lose"
(countdown; reaching zero loses with LABEL) | "win:TEXT" | "lose:TEXT".
Use 1-3 events when the text implies drama — an alarm tripped halfway through a
heist, reinforcements at the second relic, a collapse timer once the vault is
opened. Example: {"when":"collected>=2","then":["popup:The alarm is tripped!",
"spawn:guard x2","alertguards"]}. Only reference entity names that exist in
"entities". Omit "events" entirely for calm games.
Do not invent fields not in the schema."""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


_PLAYER_KINDS = ("samurai", "wizard", "knight", "viking", "dragon", "eagle",
                 "bird", "fox", "dog", "cat", "horse", "wolf", "bear",
                 "woman", "man")


# PLATFORMER (2026-09-27). Named outright, or described by its verb: jumping
# between, across or onto ledges, islands, platforms or rooftops.
PLATFORMER_WORDS = (r"\bplatform(?:er|ing)\b|\bside[\s-]?scroll(?:er|ing)?\b|\bjump\s*(?:'n'|n|and)\s*run\b"
                    r"|\bjump(?:s|ing)?\s+(?:\w+\s+){0,3}(?:between|across|from|onto|over|up)\s+(?:\w+\s+){0,3}"
                    r"(?:platforms?|islands?|ledges?|rooftops?|clouds?|pillars?|blocks?|rocks?|stones?)\b")

# FLYING A CRAFT (2026-09-27). "Fly a fighter through an asteroid field" names
# the player by its verb: the thing flown is the player, and it flies. Read
# before the sailing rule, so "pilot a space ship" is a flight, not a voyage.
FLY_WORDS = (r"\b(?:fly|flies|flying|pilot|pilots|piloting)\s+(?:a|an|the|my|your|his|her|their)?\s*"
             r"((?:[a-z-]+\s+){0,2}(?:fighter|jet|plane|airplane|spaceship|starship|spacecraft|starfighter|"
             r"x-wing|helicopter|glider|rocket|gunship|biplane|airship|shuttle|drone|ship|craft))\b")

# SAILING (2026-09-27). "Sail a pirate ship across the ocean" cast a pirate
# on foot: the verb says the player IS the vessel. The captured group is the
# vessel as the sentence names it ("pirate ship"), which is what gets built.
SAIL_WORDS = (r"\b(?:sail|sails|sailing|captain|captains|steer|steers|pilot|pilots|row|rows|rowing|paddle|paddles)"
              r"\s+(?:a|an|the|my|your|his|her|their)?\s*((?:[a-z]+\s+){0,2}"
              r"(?:ship|boat|sailboat|galleon|schooner|yacht|raft|canoe|kayak|frigate|dinghy|ferry|longboat|junk|"
              r"gondola|trawler|warship|catamaran|clipper))\b")

# TOWER DEFENCE (2026-09-27). The genre is named by its build verb: towers or
# turrets raised against waves, or a place defended from them. Shared with the
# export pipeline so the extractor and the studio's hold rule agree.
TD_WORDS = (r"\btower[\s-]?defen[cs]e\b"
            r"|\b(?:build|builds|building|place|places|placing|raise|raises|raising|put|set\s+up)\s+"
            r"(?:\w+\s+){0,2}(?:towers?|turrets?|cannons?|ballistas?|defen[cs]es)\b"
            r"|\bdefend\s+(?:the|our|my|a|your)\s+(?:\w+\s+)?(?:base|castle|keep|village|fort|fortress|gate|walls?|"
            r"kingdom|town|tower|outpost|camp|citadel|farm|city)\b")
# MYSTERY (2026-09-29). A whodunit names itself by its deduction: suspects to
# question, a culprit to name, a murder to solve. A killer whale or a mysterious
# forest is not one; "suspects", "who killed", "name the killer" are.
MYSTERY_WORDS = (r"\bwhodunn?it\b|\bmurder\s+myster(?:y|ies)\b|\bsuspects\b|\bculprit\b|\baccus(?:e|es|ing|ation)\b"
                 r"|\b(?:question|questions|questioning|interrogate|interrogating|interview|interviewing)\s+(?:the\s+|a\s+|each\s+|every\s+)?(?:\w+\s+)?suspects?\b"
                 r"|\bwho\s+(?:killed|murdered|poisoned|stabbed|shot|did\s+it|done\s+it)\b"
                 r"|\b(?:find|name|catch|unmask|identify|expose|figure\s+out)\s+(?:the\s+|who\s+the\s+)?(?:killer|murderer|thief|culprit|poisoner)\b"
                 r"|\bsolve\s+(?:the|a|this)\s+(?:\w+\s+)?(?:murder|crime|case|mystery|killing|theft)\b")
# CITY BUILDER (2026-09-29). Named outright, or by its verbs: zoning, growing a
# population, laying out a town. A city street to race down is not one.
CITY_WORDS = (r"\bcity[\s-]?build(?:er|ing)\b|\btown[\s-]?build(?:er|ing)\b|\bsim[\s-]?city\b"
              r"|\bzon(?:e|es|ed|ing)\s+(?:\w+\s+)?(?:houses|homes|residential|commercial|industrial|shops|districts?)\b"
              r"|\b(?:residential|commercial|industrial)\s+(?:zones?|zoning|districts?)\b"
              r"|\b(?:grow|grows|growing)\s+(?:the\s+|a\s+|my\s+|your\s+)?(?:population|city|town|village)\b"
              r"|\b(?:build|builds|building|found|plan|lay\s+out)\s+(?:a|my|the|your)\s+(?:own\s+)?(?:city|town|village|metropolis)\b"
              r"|\bpopulation\s+(?:of|to)\s+\d+")
_DEFENDED = ("castle", "keep", "village", "base", "fort", "fortress", "citadel", "town",
             "kingdom", "outpost", "camp", "farm", "gate", "city", "tower")


_GROUND_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "on", "at", "for", "from", "with",
                "his", "her", "their", "your", "my", "our", "its", "all", "some", "any", "lost",
                "old", "hidden", "ancient", "secret", "missing", "golden", "magic", "item", "items",
                "thing", "things", "object", "objects", "enemies", "enemy", "foes", "foe", "stuff",
                "beacon", "exit", "goal", "finish", "end", "safety", "escape", "home"}


def _stem(w: str) -> str:
    w = w.lower().strip()
    if w.endswith("'s"):
        w = w[:-2]
    w = w.strip("'")
    if len(w) > 4 and w.endswith("ves"):
        return w[:-3] + "f"                   # wolves, wolf; leaves, leaf
    for suf in ("ies", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


_NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12}


def sought_object(prompt: str):
    """What the sentence is looking for, as (label, count), or None (2026-09-30).

    "a detective searching a rainy city for a stolen painting" was planned as
    collect three clues, a step it never named; the sentence names its own
    object. Read from the verbs of seeking: find, search for, look for,
    recover, retrieve, steal, rescue, track down."""
    import re as _r
    t = (prompt or "").lower()
    m = _r.search(r"\b(?:find|finds|finding|search(?:es|ing)?(?:\s+\w+){0,3}?\s+for|look(?:s|ing)?\s+for|"
                  r"recover(?:s|ing)?|retriev(?:e|es|ing)|steal(?:s|ing)?|rescu(?:e|es|ing)|"
                  r"track(?:s|ing)?\s+down|hunt(?:s|ing)?\s+for|collect(?:s|ing)?|gather(?:s|ing)?)\s+"
                  r"(?:(the|a|an|his|her|their|my|your)\s+)?(?:(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+)?"
                  r"((?:[a-z'-]+\s+){0,2}?[a-z'-]+?)(?=\s+(?:in|on|at|from|before|while|and|to|with|across|inside|through|of|near|under|that|which|who)\b|[,.;:!?]|$)", t)
    if not m:
        return None
    label = m.group(3).strip()
    if not label or label in ("it", "them", "him", "her", "out", "way", "home"):
        return None
    art = (m.group(1) or "").strip()
    plural = label.endswith("s") and not label.endswith("ss")
    if m.group(2):
        n = int(m.group(2)) if m.group(2).isdigit() else _NUMS.get(m.group(2), 1)
    elif art in ("a", "an"):
        n = 1
    else:
        n = 3 if plural else 1
    return label, max(1, min(n, 50))


def label_grounded(label: str, prompt: str) -> bool:
    """A step's label is the prompt's when one of its words is a word of the
    prompt (plurals and the first five letters forgiven)."""
    import re as _r
    words = {_stem(w) for w in _r.findall(r"[a-z']+", (prompt or "").lower()) if len(w) > 2}
    heads = {w[:5] for w in words if len(w) >= 5}
    toks = [_stem(t) for t in _r.findall(r"[a-z']+", (label or "").lower())]
    toks = [t for t in toks if len(t) > 2 and t not in _GROUND_STOP]
    if not toks:
        return True                           # a label with no words of its own names nothing new
    return any(t in words or (len(t) >= 5 and t[:5] in heads) for t in toks)


def ground_objectives(objectives: list, prompt: str) -> tuple[list, list]:
    """Keep the collect and defeat steps the sentence asked for (2026-09-29).

    "A horror game in a graveyard at night, find the three lanterns" came out
    with a first step nobody asked for: collect the abandoned camp's supplies.
    A collect, defeat or reach step is the prompt's when a word of its label is a word
    of the prompt (plurals and the first five letters forgiven: lantern and
    lanterns, skeleton and skeletons, wolf and wolves); a step the model made
    up from nothing is dropped. Other kinds are verbs the prompt said out loud
    (race, survive, hunt...) or the ending, and are left alone. If dropping
    would leave no step to play, nothing is dropped: a paraphrase ("treasure"
    as "gold coins") is better than an empty game.
    Returns (kept, dropped)."""
    def grounded(label: str) -> bool:
        return label_grounded(label, prompt)

    kept, dropped = [], []
    for o in objectives:
        kind = getattr(o, "kind", None) or (o.get("kind") if isinstance(o, dict) else None)
        label = getattr(o, "label", None) if not isinstance(o, dict) else o.get("label")
        if kind in ("collect", "defeat", "reach") and not grounded(label or ""):
            dropped.append(o)
        else:
            kept.append(o)
    playable = [o for o in kept if (getattr(o, "kind", None) or (o.get("kind") if isinstance(o, dict) else None)) != "reach"]
    if dropped and not playable:
        return list(objectives), []
    return kept, dropped


def defended_noun(text: str) -> str:
    """What a tower defence protects, from its own words; a castle when unsaid."""
    import re as _re
    t = (text or "").lower()
    m = _re.search(r"\b(?:defend|protect|guard|hold|save)\s+(?:the|our|my|a|your)\s+(?:\w+\s+)?("
                   + "|".join(_DEFENDED) + r")\b", t)
    if m:
        return m.group(1)
    for w in _DEFENDED:
        if _re.search(r"\b" + w + r"\b", t) and w != "tower":
            return w
    return "castle"


def distinct_theme(theme: dict) -> dict:
    """A factory's chain must name a different thing at every stage.

    "A cozy farming game" came back as turnip -> turnip -> turnip -> turnip:
    resource, refined, combined and product all one word, so the panel read
    "14 turnip, 0 turnip, 0 turnip" and a player could not tell a raw crop
    from the thing it became. Each stage that repeats an earlier one is named
    as that stage of the earlier thing; the singular/plural pair the runtime
    reads ("loaf/loaves") is respected on both sides.
    """
    if not isinstance(theme, dict):
        return theme
    t = dict(theme)

    def base(v):
        return str(v or "").split("/")[0].strip().lower()

    seen = set()
    r = base(t.get("resource"))
    if r:
        seen.add(r)
    for key, make in (("refined", lambda w: "washed " + w),
                      ("combined", lambda w: w + " bundle"),
                      ("product", lambda w: w + " crate")):
        v = base(t.get(key))
        if not v:
            continue
        if v in seen:
            root = r or v
            t[key] = make(root)
            v = base(t[key])
        seen.add(v)
    return t


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
                   r"hunt(?:s|ed|ing)?\s+for)\s+(\d+)?\s*((?:[a-z]+\s?){1,3}?)" + _stop, t)
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
    # tower defence (2026-09-27): the build verb, not a timer
    if _re.search(TD_WORDS, t) and not any(o.get("kind") == "defend" for o in obs):
        mw = _re.search(r"\b(\d+)\s+waves?\b", t)
        obs.append({"kind": "defend", "count": max(3, min(int(mw.group(1)) if mw else 5, 8)),
                    "label": defended_noun(t)})
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
    # hunt(s|ed|ing) — "a wolf HUNTS 3 elk" is the common phrasing
    m = _re.search(r"\bhunt(?:s|ed|ing)?\s+(?:down\s+)?(\d+)?\s*(?:the\s+)?((?:[a-z]+\s?){1,2}?)" + _stop, t)
    if m and m.group(2) and m.group(2).strip() not in ("for", "down")             and not any(o.get("kind") == "hunt" for o in obs):
        n = int(m.group(1) or 3)
        prey = _sing1(m.group(2).strip())
        obs.append({"kind": "hunt", "count": max(1, min(n, 8)), "label": prey})
        ents.append({"name": prey, "behavior": "flee", "count": max(n, 2), "speed": 2.4})
    # capture/hold (Phase 72): stand in glowing zones to take them
    m = _re.search(r"\b(?:capture|hold|control|claim)\s+(?:the\s+)?(\d+)?\s*"
                   r"(?:zones?|points?|areas?|territor(?:y|ies)|flags?|hills?)", t)
    if m and not any(o.get("kind") == "capture" for o in obs):
        n = int(m.group(1) or 3)
        obs.append({"kind": "capture", "count": max(1, min(n, 5)), "label": "zones"})
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
    # STYLE ARRIVES NESTED (2026-09-03). "style" is a top-level GameSpec field
    # but it is DESCRIBED in the middle of the world section, and the model
    # duly emitted it inside "world" — where the schema silently dropped it.
    # Measured: a neon arcade racer and a haunted asylum both came back
    # style="default" while archetype and ground_color were picked correctly,
    # so the art direction the user asked for never reached the renderer and
    # every game looked the same. The prompt now says where it goes; this
    # catches the model when it puts it somewhere else anyway.
    if isinstance(over, dict):
        _w = over.get("world")
        if isinstance(_w, dict) and "style" in _w and "style" not in over:
            over["style"] = _w.pop("style")
    spec = spec_from_dict(_merge(base, over))
    if getattr(spec, "theme", None):
        spec.theme = distinct_theme(spec.theme)
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
- objectives kinds: collect, defeat, reach, race, survive, defend (tower
  defence: count = waves), accuse (a mystery's last step: name the killer
  among the "suspect" entities). entity behaviors: suspect (a mystery's
  person of interest, with "role" saying who they are),
  wander, follow, static, hostile, vehicle, guard (patrolling vision-cone
  sentry for stealth/heist — attacks only when it sees the player).
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
