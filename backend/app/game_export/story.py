"""THE STORY LAYER (2026-10-12).

Every game opened on the same card: "the guide . 1 / 5 . Look around . Drag
with the mouse to look", in the same gold, over every world from a lighthouse
in a storm to a bakery on a floating island. The owner: "not all the games can
start with Look around; most games have a creative in-depth story line to
start and guide".

A game's story is written here, once per fresh build, by the local model: who
tells it, a chapter heading, a tagline for the title, a prologue of concrete
sentences, one in-world line per objective (what to do, said by someone who is
there), the line that gets the player moving, and an epilogue. The runtime sets
the opening card, the objective lines and the win screen from it.

A fixed list of stock phrases is refused (they are what makes a line read as
generated), there are no em dashes in anything the player reads, and when the
model is down the fallback composes the same shape from the spec itself.
"""
from __future__ import annotations

import json
import random
import re

from app.orchestrator.llm import OllamaClient

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# words and turns that mark a line as boilerplate
_STOCK = re.compile(
    r"\b(embark\w*|journey awaits|adventure awaits|awaits you|beckons?|the fate of|"
    r"ancient evil|look around|mysterious|unravel|delve|tapestry|realm of|"
    r"little did|in a world where|brave hero|epic quest|your quest begins|"
    r"only you can|destiny|testament|a prayer|whispers?|echoes of)\b", re.I)

_SYSTEM = """You write the opening of a video game from a one-sentence idea.
Write like a novelist, not a marketer: concrete names, a place, a time of day
or year, weather, objects you could touch, one human detail. Every game is its
own story: invent a specific person or document that tells it.

Reply with ONLY a JSON object:
{
 "narrator": who tells it, a person or a document inside the world, 2-8 words, in the form you are given,
 "chapter": a specific chapter heading, 2-5 words, never "Chapter One" or the game title,
 "tagline": one line under the title, 4-10 words, specific to this game,
 "prologue": [3 or 4 items, each ONE short sentence, setting the scene and the stakes in the narrator's voice],
 "first_move": one short in-world line that gets the player moving, naming a real place or thing,
 "beats": [one short in-world line per objective, in order, saying what to do and naming the thing],
 "epilogue": 1-2 sentences for the end
}
Rules: no em dashes; no exclamation marks except in a shout someone actually gives;
never write the words: embark, journey, adventure awaits, beckons, the fate of,
ancient evil, look around, mysterious, unravel, delve, destiny, only you can.
Do not explain controls. Do not address the reader as "hero" or "player"."""


def _clean(s, limit=260):
    s = str(s or "").strip().strip('"').strip()
    # the model writes U+FFFD where an apostrophe belongs, and curly quotes
    s = s.replace("�", "'").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    # (2026-10-21) and a spaced hyphen, which reads as the dash it stands in for
    s = s.replace("—", ", ").replace("–", "-").replace(" -- ", ", ").replace(" - ", ", ")
    # (2026-10-23) and markdown: a ship's name came to the card as "*Sea Serpent*"
    s = re.sub(r"(?<!\w)(\*\*|__|\*|_)(\S(?:.*?\S)?)\1(?!\w)", r"\2", s).replace("*", "")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r",\s*,", ",", s)
    if len(s) <= limit:
        return s
    # a line ends on a whole sentence, never mid-word ("he only alluded t")
    cut = max(s.rfind(". ", 0, limit), s.rfind("? ", 0, limit), s.rfind("! ", 0, limit))
    if cut > limit * 0.4:
        return s[:cut + 1]
    return s[:s.rfind(" ", 0, limit)].rstrip(",;: ") + "."


def _ok(s):
    return bool(s) and not _STOCK.search(s)


_SMALL = {"the", "a", "an", "of", "at", "to", "in", "on", "and", "for", "from", "with", "by", "his", "her", "their", "my", "your"}


def _names(line, label):
    """the line mentions the label's own words (any one that is not filler, singular or plural)"""
    words = [w for w in re.findall(r"[a-z]+", str(label or "").lower()) if w not in _SMALL and len(w) > 2]
    low = str(line or "").lower()
    return not words or any(re.search(r"\b" + re.escape(w.rstrip("s")) + r"(e?s)?\b", low) for w in words)


# (2026-10-20) a delivery runs on the repair objective (a pad, hold E), and the
# HUD calls it "Deliver 4 packages"; the story was told "repair" and wrote
# "Repair the package labeled 'Fragile'". It is told what the player is told.
_PARCEL = re.compile(r"package|parcel|deliver|letter|mail|pizza|crate|box|supplies|medicine|food|meal|bread|loa(?:f|ves)|pies?|cakes?|buns|hot ?dogs?|hotdogs?|sandwich\w*|burgers?|tacos?|noodles?|dumplings?|kebabs?|pretzels?|pastr|cookies|groceries|flowers|bouquets?|milk|newspapers?|papers|presents|gifts|cheese|eggs|soup|cocoa|coffee|potions?|scrolls?", re.I)


def _shown_kind(o):
    k = getattr(o, "kind", "") or ""
    if k != "repair":
        return k
    lab = str(getattr(o, "label", "") or "")
    # (2026-10-24) the same for the other jobs the repair objective runs: a beekeeper's
    # "Check 4 hives" was told "repair" and the story wrote "Repair the northwest hive"
    if _PARCEL.search(lab):
        return "deliver"
    if lab.lower().startswith("buried "):        # (2026-10-26) an archaeologist's dig: one find, its sand brushed off
        return "uncover"
    if lab.lower().endswith(" on the wheel"):    # (2026-10-26) a potter's job: a pot thrown on each wheel
        return "throw"
    if re.search(r"\b(?:bee)?hives?\b", lab, re.I):
        return "check"
    if re.search(r"\b(thirsty|wilting|dry)\b", lab, re.I):
        return "water"
    if re.search(r"\b(crowds?|audiences?|listeners?|passers-?by)\b", lab, re.I):
        return "play for"
    if re.search(r"\b(trees?|pines?|oaks?|birch(?:es)?|spruces?|logs?|timber)\b", lab, re.I):
        return "fell"
    if re.search(r"\b(lost|missing|stranded|hikers?|climbers?|skiers?|campers?|survivors?)\b", lab, re.I):
        return "find"
    if re.search(r"fire|flame|blaze|burn", lab, re.I):
        return "put out"
    return k


def _fallback(spec, prompt):
    rng = random.Random((getattr(spec, "seed", 0) or 0) * 31 + len(prompt or ""))
    who = str(getattr(spec.player, "name", "") or "traveller")
    obs = list(getattr(spec, "objectives", []) or [])
    verbs = {"collect": "Gather", "reach": "Get to", "defeat": "Put down", "race": "Beat",
             "survive": "Hold out against", "eliminate": "Clear out", "score": "Score",
             "deliver": "Carry", "serve": "Serve", "repair": "Mend", "photograph": "Photograph",
             "check": "Check", "fell": "Fell", "find": "Find", "put out": "Put out", "water": "Water", "play for": "Play for", "uncover": "Uncover", "throw": "Throw"}
    beats = []
    for o in obs:
        lab = str(getattr(o, "label", "") or "it")
        n = int(getattr(o, "count", 1) or 1)
        if _shown_kind(o) == "uncover":
            n = 1                                         # four mounds, one statue
        # "Put down dragon." wants its article
        if n == 1 and not re.match(r"(the|a|an|my|your|his|her|their)\b", lab, re.I) and not lab[:1].isupper():
            lab = "the " + lab
        beats.append(_clean(f"{verbs.get(_shown_kind(o), 'Find')} {str(n) + ' ' if n > 1 else ''}{lab}."))
    intro = _clean(getattr(spec, "intro", "") or "")
    pro = [s for s in re.split(r"(?<=[.?])\s+", intro) if s] or [_clean(prompt).capitalize() + "."]
    heads = ["Before First Light", "The Long Way In", "What the Weather Brought", "One Last Errand",
             "The Hour Before", "Where the Road Ends", "The Turning Tide", "Out Past the Lamps"]
    # (2026-10-13) the fallback had "The man" for a narrator and the win line
    # ("The gold is yours!") for a tagline; it takes a name and a form from the
    # seed like the model's story does, and the tagline is never the ending
    seed = getattr(spec, "seed", 0) or 0
    forms = ["field notes", "logbook", "last letter", "account", "journal", "notebook", "testimony", "diary"]
    name = random.Random(seed * 7 + 1).choice(_NAMES)
    narrator = f"{name}'s {random.Random(seed * 13 + 5).choice(forms)}"
    tag = rng.choice(["Nobody else is coming.", "It has to be tonight.", "Further than it looks.", "Everyone else turned back.",
                      "Not everyone comes back.", "There is still time, just.", "Someone has to go.", "It was never on any map."])
    return {"narrator": narrator, "chapter": rng.choice(heads),
            "tagline": tag,
            "prologue": pro[:4], "first_move": beats[0] if beats else "Go.",
            "beats": beats, "epilogue": _clean(getattr(spec, "win_text", "") or "")}


# the model reaches for the same narrator ("Silas's testament") every time;
# the seed hands it a form and a name to start from instead
_FORMS = ["a ship's or station log", "a letter never sent", "a radio transcript", "a child's diary",
          "field notes in a notebook", "a voicemail", "a guidebook's margin notes", "an apprentice's journal",
          "a police or incident report", "the back of a recipe card", "a postcard", "a work order",
          "an old woman telling it to her grandchild", "a rival who wants you to fail", "a dispatcher on the radio",
          "the place itself", "a song a local sings", "a museum placard", "a captain's orders", "a text thread"]
# a knight's tale is not a dispatch log: a world before radio gets forms of its own
_OLD = re.compile(r"\b(medieval|castles?|knights?|kingdom|dragons?|wizards?|vikings?|samurai|shogun|ninjas?|pharaohs?|egypt\w*|roman|gladiators?|pirates?|"
                  r"victorian|western|cowboys?|monaster\w*|temples?|ruins?|tombs?|lighthouse|blacksmith|smithy|princess|sword|ancient)\b", re.I)
_FORMS_OLD = ["a chronicle kept by a monk", "a letter never sent", "a ballad a minstrel sings", "an apprentice's journal",
              "a ship's log", "a ledger's margin notes", "an old woman telling it to her grandchild", "a rival who wants you to fail",
              "a herald's proclamation", "the place itself", "a confession", "a captain's orders", "a map's annotations", "a wanted poster"]
_NAMES = ["Ines", "Tomasz", "Adaeze", "Ruairi", "Mei", "Kofi", "Sigrun", "Teodor", "Priya", "Mateo", "Ilse", "Yusuf",
          "Noor", "Haruto", "Bronagh", "Amara", "Lev", "Catalina", "Oskar", "Femi", "Wren", "Dasha", "Emeka", "Rosalind",
          "Kai", "Marisol", "Anselm", "Tove", "Ravi", "Odile", "Bram", "Esme", "Joaquin", "Hana", "Cormac", "Zainab"]


def write_story(spec, prompt: str, verbose: bool = True) -> dict:
    """The story for a fresh build. Never raises; falls back to a composed one."""
    obs = [{"kind": _shown_kind(o), "label": getattr(o, "label", ""), "count": getattr(o, "count", 1)}
           for o in (getattr(spec, "objectives", []) or [])]
    seed = getattr(spec, "seed", 0) or 0
    # (2026-10-21) the story is set in the world that was built: "a blacksmith delivers
    # medicine around a rainy city" was told as "The Ledger of Deliveries, 1888" over glass
    # towers and taxis. A built city that is not a cosy town is the present day
    _lvl = getattr(spec.world, "level", None) or {}
    _osm = _lvl.get("osm") if isinstance(_lvl, dict) else None
    modern = bool(_osm) and not (isinstance(_osm, dict) and _osm.get("town"))
    era = ("Era: the present day. The world is a modern city of glass and concrete towers, cars and traffic "
           "lights; set the story now, with no year from the past and nothing a modern city would not have.\n") if modern else ""
    user = (f"Game idea: {prompt}\nTitle: {getattr(spec, 'title', '')}\n"
            f"The player is: {getattr(spec.player, 'name', '')}\n"
            f"Objectives in order: {json.dumps(obs)}\n"
            f"Setting notes: sky {getattr(spec.world, 'sky', '')}, weather {getattr(spec.world, 'weather', '')}, "
            f"world {getattr(spec.world, 'name', '')}\n"
            f"{era}"
            f"Tell it as {random.Random(seed).choice(_FORMS_OLD if _OLD.search(prompt or '') and not modern else _FORMS)}; the first person named in it is "
            f"{random.Random(seed * 7 + 1).choice(_NAMES)} (other names for anyone else).\n"
            "Each beat must be about ITS objective exactly, the same verb and the same thing named, in-world. "
            "first_move must point toward the first objective. Never invent a task, an item to collect or a step "
            "that the objectives do not have.")
    try:
        client = OllamaClient()
        if not client.is_alive():
            raise RuntimeError("ollama down")
        msgs = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
        for attempt in (1, 2):
            resp = client.chat(msgs, temperature=0.95)
            raw = (resp.get("content") or "") if isinstance(resp, dict) else str(resp)
            m = _JSON_RE.search(raw)
            try:
                d = json.loads(m.group(0), strict=False) if m else None   # a raw newline inside a line is fine
            except ValueError:
                d = None
            if not isinstance(d, dict):
                continue
            out = {
                "narrator": _clean(d.get("narrator"), 60),
                "chapter": _clean(d.get("chapter"), 48),
                "tagline": _clean(d.get("tagline"), 90),
                "prologue": [_clean(x, 220) for x in (d.get("prologue") or []) if _clean(x)][:4],
                "first_move": _clean(d.get("first_move"), 140),
                "beats": [_clean(x, 160) for x in (d.get("beats") or []) if _clean(x)][:len(obs) or 1],
                "epilogue": _clean(d.get("epilogue"), 240),
            }
            # a stock sentence is dropped, not the whole story; the short
            # fields are asked for again once, then patched from the fallback
            def _scrub(t):
                return " ".join(x for x in re.split(r"(?<=[.?!])\s+", t or "") if x and _ok(x)).strip()
            out["prologue"] = [y for y in (_scrub(x) for x in out["prologue"]) if y]
            out["epilogue"] = _scrub(out["epilogue"])
            out["tagline"] = out["tagline"] if _ok(out["tagline"]) else ""
            out["beats"] = [b if _ok(b) else "" for b in out["beats"]]
            bad = [k for k in ("narrator", "chapter", "first_move") if not _ok(out[k])]
            # a narrator is a who, not a sentence: "The sandstone remembers everything." (2026-10-13)
            if out["narrator"] and (out["narrator"].rstrip().endswith((".", "!", "?")) or len(out["narrator"].split()) > 8):
                bad.append("narrator")
            bad += ["prologue"] if len(out["prologue"]) < 2 else []
            if not bad or attempt == 2:
                fb = _fallback(spec, prompt)
                if len(out["prologue"]) < 2:
                    if attempt == 2 and not out["prologue"]:
                        break
                for k2 in ("narrator", "chapter", "first_move", "tagline", "epilogue"):
                    if not out[k2] or not _ok(out[k2]):
                        out[k2] = fb[k2]
                out["beats"] = [b or fb["beats"][i] for i, b in enumerate(out["beats"][:len(fb["beats"])])]
                while len(out["beats"]) < len(obs):
                    out["beats"].append(fb["beats"][len(out["beats"])])
                # a beat names the thing its objective is about, or it is the
                # objective plainly said: "gather the kindling" for "reach the
                # lamp" sent players looking for kindling that is not there
                for i, o in enumerate(obs):
                    if not _names(out["beats"][i], o.get("label")):
                        out["beats"][i] = fb["beats"][i]
                if obs and not _names(out["first_move"], obs[0].get("label")):
                    out["first_move"] = out["beats"][0]
                out["prologue"] = out["prologue"][:4]
                return out
            if attempt == 1:
                msgs.append({"role": "assistant", "content": raw[:2000]})
                msgs.append({"role": "user", "content": f"Rewrite {', '.join(bad)}: they are generic or missing. "
                             "Be specific to this game. Reply with ONLY the JSON object."})
    except Exception as e:
        if verbose:
            print(f"[game] story: model path failed ({type(e).__name__}: {e}) - composed fallback")
    return _fallback(spec, prompt)
