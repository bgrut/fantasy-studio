"""THE DESIGNER (2026-10-20).

Every game was laid out by one template: spawn in the middle, the goal at a
far edge, a path with two wobbles, the things to find strung along it. The
skins differed and the game did not ("different characters, same game").
A made game has a designer: someone who decided how its space unfolds, the
one thing about it that plays differently, and the moment it turns.

design_of() reads the sentence (and the seed, where the sentence is silent)
and returns that decision:

  layout    how the space unfolds
            route    a journey out to somewhere (the old shape)
            loop     out around the land and home again
            hub      a home base with spokes to the places you go
            scatter  things hidden about the map, found by looking
            ascent   the land climbs to the goal on switchbacks
  mechanic  the one system this game has that others do not
            tracks     prints in the ground lead to what you seek
            freshness  what you carry cools; home refills it
            lantern    your light is what you have; lamps you light stay lit
            gusts      the wind shoves you; shelter is behind things
            cold       warmth drains away from a fire
            none
  moment    where the game turns, at about half way
            storm      the weather breaks
            nightfall  the light goes
            fog        a bank of fog rolls in
            none

It never overrides a shape another system owns: races, arenas, tower
defence, platformers, city builders, factories, interiors, cities, seas,
fjords, coasts, slot canyons and rivers keep the route they were built for.
"""
from __future__ import annotations

import random
import re

_OWNED = re.compile(
    r"\b(race|races|racing|racer|drift\w*|rally|karts?|grand prix|tower defen[cs]e|platformer|side-?scroll\w*|"
    r"city builder|build a city|zone|factory|assembly|conveyor|arena|colosseum|gladiators?|joust\w*|"
    r"soccer|football|stadium|heist|museum|mall|supermarket|hospital|prison|interior|inside|indoors|"
    r"spaceship|space station|orbit\w*|asteroids?|underwater|reef|submarine|scuba|ocean floor|"
    r"sail\w*|naval|fleet|pirate ship|galleon|"
    # a mystery has its own shape (suspects, clues, a casebook); a dungeon is built as rooms
    r"mystery|whodunit|murder|suspects?|casebook|interrogat\w*|dungeon crawler|dungeons?)\b")


def design_of(prompt: str, seed: int, *, owned: bool = False, night: bool = False,
              weather: str | None = None, objectives: list | None = None) -> dict:
    p = (prompt or "").lower()
    r = random.Random((seed or 1) * 2654435761 % (2 ** 32))
    has = lambda pat: bool(re.search(pat, p))
    kinds = [getattr(o, "kind", None) or (o.get("kind") if isinstance(o, dict) else None) for o in (objectives or [])]
    why = []

    # ── the layout ───────────────────────────────────────────────────────────
    if owned or _OWNED.search(p):
        layout = "route"; why.append("the shape belongs to another system")
    elif has(r"\b(climb\w*|summit|ascend\w*|ascent|peak|top of|scal(e|es|ing) the|mountaintop|clifftop|up the mountain)\b"):
        layout = "ascent"; why.append("the sentence climbs")
    elif has(r"\b(deliver\w*|rounds?|visit\w*|every (house|home|door|cottage|stall)|each (house|home|door)|around (the|a) (village|town|island|farm|market)|errands?|postman|mail ?route|paper ?round)\b"):
        layout = "hub"; why.append("rounds from a home base")
    elif has(r"\b(search\w*|explor\w*|scattered|hidden|lost|find (?:all|the|her|his|their|every)|discover\w*|forage\w*|gather\w*|hunt for|look(?:s|ing)? for|track\w*)\b"):
        layout = "scatter"; why.append("finding is looking")
    elif has(r"\b(patrol\w*|circuit|tour|loop|walk the bounds|round the|survey\w*|check(?:s|ing)? (?:the|on))\b"):
        layout = "loop"; why.append("a round that comes home")
    elif has(r"\b(journey|travel\w*|cross\w*|to reach|reach the|rides?|riding|march\w*|quest|lair|to slay|to rescue|to save|to defeat|to stop|"
             r"head\w* to|make (?:his|her|their|the|a) way|escape\w* to|flee\w*|return\w* to|pilgrim\w*|voyage)\b"):
        layout = "route"; why.append("a journey out")
    else:
        layout = r.choice(["route", "loop", "scatter", "hub", "scatter", "loop"])
        why.append("the sentence was silent: the seed chose")

    # ── the mechanic ─────────────────────────────────────────────────────────
    mech = "none"
    if has(r"\b(deliver\w*|bread|pizza|pies?|soup|meals?|hot|warm|fresh|baker\w*|cocoa|coffee|tea|medicine)\b") and has(r"\b(deliver\w*|bring\w*|carr(y|ies|ying)|take\w*|rounds?)\b"):
        mech = "freshness"
    elif has(r"\b(track\w*|trail\w*|footprints?|follow\w* the|hunt\w*|lost (cubs?|dog|cat|sheep|lamb|child|kitten|puppy|fox|horse|calf)|missing|find (?:her|his|their) (?:lost|missing)?\s*\w+|cubs?|kits|pups?)\b") \
            and not has(r"\b(city|street|downtown)\b"):
        mech = "tracks"
    elif (night or has(r"\b(night|midnight|dark\w*|cave\w*|catacomb\w*|mine\b|mines\b|tunnels?|crypt\w*|lantern\w*|lamps?|torch\w*|candle\w*)\b")) \
            and has(r"\b(lantern\w*|lamps?|torch\w*|light\w*|dark\w*|candle\w*|beacon\w*|relight\w*|caves?|catacomb\w*|mines?|tunnels?)\b"):
        mech = "lantern"
    elif has(r"\b(snow\w*|blizzard\w*|winter|frozen|freez\w*|arctic|tundra|glacier\w*|cold|frost\w*|icy)\b") and not has(r"\b(cozy|cosy|christmas|holiday|festive)\b"):
        mech = "cold"
    elif (weather in ("storm", "thunder", "wind")) or has(r"\b(storm\w*|gales?|windswept|wind\w*|hurricanes?|blustery|squalls?|tempest\w*)\b"):
        mech = "gusts"
    if mech != "none":
        why.append("mechanic: " + mech)

    # ── the moment ───────────────────────────────────────────────────────────
    if has(r"\b(storm\w*|before the (rain|storm)|gathering clouds|thunder\w*)\b") and weather not in ("storm", "thunder"):
        moment = "storm"
    elif has(r"\b(before (night|nightfall|dark|sunset|dusk)|at dusk|sunset|as the sun sets|nightfall|the light fades|before the light)\b") and not night:
        moment = "nightfall"
    elif has(r"\b(mist\w*|fog\w*|haze)\b"):
        moment = "fog"
    elif layout in ("scatter", "loop", "ascent") and not night and weather in (None, "", "none", "clear"):
        moment = r.choice(["storm", "fog", "none", "nightfall"])
    else:
        moment = "none"
    if owned:
        mech = "none" if mech in ("gusts", "cold") else mech
    return {"layout": layout, "mechanic": mech, "moment": moment, "why": why}
