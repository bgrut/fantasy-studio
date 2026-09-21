"""Prompt fidelity: ten sentences, ten games, each scored against its sentence.

    python backend/tools/prompt_check.py            # builds the ten, scores them, writes PROMPT_FIDELITY.md
    python backend/tools/prompt_check.py --reuse    # scores the newest finished job with each sentence instead of rebuilding

The gates prove the machinery works. This proves the promise: that the game
the studio builds is the game the sentence asked for. Each sentence carries
the things a careful reader would expect from it (the genre, the time of
day, the hero, the building, who is hostile, what is collected and how
many, the mood of a factory) and the build is scored on how many of them
it delivered, from the resolved spec the studio wrote. The studio's own
off-brief notes (brief_check) ride along. The pass line is a mean of 0.85
with no genre missed; the table is written for reading either way.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
import urllib.request

API = "http://127.0.0.1:8789"
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "tools" / "PROMPT_FIDELITY.md"

# the runtime's own mood words, so a factory is scored the way it will look
MOODS = {
    "warm": r"\b(red|rust|rusted|ember|cinder|lava|magma|volcan|scorch|burn|fire|ash|crimson|copper|desert|sun-?baked|inferno|forge)\w*",
    "cold": r"\b(ice|icy|frost|frozen|snow|glacier|arctic|tundra|winter|polar|blizzard|cryo|white)\w*",
    "green": r"\b(jungle|forest|moss|verdant|overgrown|swamp|fungal|spore|garden|bloom|vine|toxic|acid)\w*",
}

PROMPTS = [
    {"prompt": "a haunted manor on a windswept moor, find the three relics before the bell tolls",
     "want": {"genre": "adventure", "sky": "night", "style": "horror", "landmark": "manor", "spectral": True,
              "collect": ("relic", 3), "reach": "bell"}},
    {"prompt": "a tokyo drift racing game through neon streets at night",
     "want": {"genre": "adventure", "sky": "night", "mode": "drive", "objective": "race", "city": True}},
    {"prompt": "a rusted mining outpost on a dead red moon",
     "want": {"genre": "factory", "mood": "warm"}},
    {"prompt": "an ice refinery on a frozen moon",
     "want": {"genre": "factory", "mood": "cold"}},
    {"prompt": "a knight defending a stone keep from wolves at dusk",
     "want": {"genre": "adventure", "hero": "knight", "landmark": "keep", "hostile": "wolf", "sky": "dusk"}},
    {"prompt": "a samurai crossing a bamboo forest to reach a mountain temple",
     "want": {"genre": "adventure", "hero": "samurai", "objective": "reach", "landmark": "temple"}},
    {"prompt": "a detective searching a rainy city for a stolen painting",
     "want": {"genre": "adventure", "hero": "detective", "weather": "rain", "collect": ("painting", 1), "city": True}},
    {"prompt": "a scientist collecting samples in a toxic swamp full of crocodiles",
     "want": {"genre": "adventure", "hero": "scientist", "collect": ("sample", None), "hostile": "crocodile"}},
    {"prompt": "a moonlit forest walk to gather lost fireflies before dawn",
     "want": {"genre": "adventure", "sky": "night", "collect": ("firefl", None)}},
    {"prompt": "a bakery on a floating island where grain is milled into flour and baked into loaves",
     "want": {"genre": "factory", "theme": ["flour", "loaf", "loaves", "grain", "dough", "bread"]}},
]


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(path):
    return json.loads(urllib.request.urlopen(API + path, timeout=60).read())


def build(prompt: str) -> dict:
    r = post("/api/game/export", {"prompt": prompt})
    jid = r.get("job_id") or r.get("id")
    t0 = time.time()
    while True:
        time.sleep(3)
        j = get(f"/api/game/jobs/{jid}").get("job", {})
        if j.get("status") in ("complete", "failed", "error", "cancelled") or time.time() - t0 > 900:
            return j


def newest_with(prompt: str) -> dict | None:
    jobs = get("/api/game/jobs").get("jobs", [])
    for j in jobs:                                   # newest first
        if j.get("prompt") == prompt and j.get("status") == "complete":
            return get(f"/api/game/jobs/{j['id']}").get("job", {})
    return None


def score(job: dict, want: dict) -> tuple[list[str], list[str]]:
    """Return (hits, misses), each a list of readable lines."""
    sp = job.get("spec_resolved") or {}
    world = sp.get("world") or {}
    level = world.get("level") or {}
    player = sp.get("player") or {}
    ents = sp.get("entities") or []
    objs = sp.get("objectives") or []
    hits, misses = [], []

    def mark(ok: bool, label: str, got: str):
        (hits if ok else misses).append(f"{label}: {got}")

    for key, exp in want.items():
        if key == "genre":
            got = job.get("genre") or sp.get("genre")
            mark(got == exp, f"genre {exp}", str(got))
        elif key == "sky":
            got = world.get("sky")
            mark(got == exp, f"sky {exp}", str(got))
        elif key == "style":
            got = sp.get("style")
            mark(got == exp, f"style {exp}", str(got))
        elif key == "weather":
            got = str(world.get("weather") or "")
            mark(exp in got, f"weather {exp}", got or "none")
        elif key == "mode":
            got = player.get("mode")
            mark(got == exp, f"player mode {exp}", str(got))
        elif key == "hero":
            got = str(player.get("name") or "")
            mark(exp in got.lower(), f"hero {exp}", got or "none")
        elif key == "landmark":
            ent = level.get("enterable") or {}
            got = str(ent.get("label") or "") if isinstance(ent, dict) else ""
            mark(exp in got.lower(), f"enterable {exp}", got or "none")
        elif key == "spectral":
            got = sum(1 for e in ents if e.get("spectral"))
            mark(got >= 1, "ghosts", f"{got} spectral")
        elif key == "hostile":
            names = [str(e.get("name") or "") for e in ents if e.get("behavior") == "hostile"]
            mark(any(exp in n.lower() for n in names), f"hostile {exp}", ", ".join(names) or "none")
        elif key == "collect":
            word, count = exp
            found = [o for o in objs if o.get("kind") == "collect" and word in str(o.get("label") or "").lower()]
            ok = bool(found) and (count is None or any(int(o.get("count") or 0) == count for o in found))
            mark(ok, f"collect {word}" + (f" x{count}" if count else ""),
                 ", ".join(f"{o.get('label')} x{o.get('count')}" for o in objs if o.get("kind") == "collect") or "none")
        elif key == "reach":
            found = [o for o in objs if o.get("kind") == "reach" and exp in str(o.get("label") or "").lower()]
            mark(bool(found), f"reach {exp}", ", ".join(str(o.get("label")) for o in objs if o.get("kind") == "reach") or "none")
        elif key == "objective":
            kinds = [o.get("kind") for o in objs]
            mark(exp in kinds, f"objective {exp}", ", ".join(map(str, kinds)) or "none")
        elif key == "city":
            got = bool(level.get("osm"))
            mark(got, "a city district", "built" if got else "none")
        elif key == "mood":
            text = " ".join(str(x or "") for x in (sp.get("title"), world.get("name"), world.get("description"), world.get("setting")))
            fam = next((m for m, rx in MOODS.items() if re.search(rx, text, re.I)), "void")
            mark(fam == exp, f"mood {exp}", f"{fam} from {sp.get('title')!r}")
        elif key == "theme":
            theme = json.dumps(sp.get("theme") or {}).lower() + " " + str(sp.get("title") or "").lower()
            got = [w for w in exp if w in theme]
            mark(bool(got), "theme words", ", ".join(got) or f"none of {exp} in the theme or title")
    return hits, misses


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reuse", action="store_true", help="score the newest finished job for each sentence instead of building")
    ap.add_argument("--only", type=int, default=None, help="only the first N sentences")
    args = ap.parse_args()
    rows = []
    for item in PROMPTS[: args.only or len(PROMPTS)]:
        prompt, want = item["prompt"], item["want"]
        job = newest_with(prompt) if args.reuse else None
        secs = 0
        if job is None and not args.reuse:
            t0 = time.time()
            job = build(prompt)
            secs = int(time.time() - t0)
        if job is None:                                # --reuse and nothing finished with this sentence: a miss, never a rebuild
            job = {"status": "unfinished", "error": "no finished build with this sentence"}
        if job.get("status") != "complete":
            rows.append({"prompt": prompt, "job": job.get("id"), "title": None, "genre": None, "hits": [], "misses": [f"build {job.get('status')}: {job.get('error') or ''}"], "brief": [], "standins": [], "secs": secs})
            print(f"  {prompt[:60]:60} -> FAILED {job.get('status')}", flush=True)
            continue
        hits, misses = score(job, want)
        brief = list(job.get("brief_errors") or [])
        standins = [n.split(" for now")[0] for n in (job.get("notes") or []) if "is played by" in n]   # the studio's own stand-in notes
        rows.append({"prompt": prompt, "job": job.get("id"), "title": (job.get("spec_resolved") or {}).get("title"), "genre": job.get("genre"),
                     "hits": hits, "misses": misses, "brief": brief, "standins": standins, "secs": secs})
        n, t = len(hits), len(hits) + len(misses)
        print(f"  {prompt[:60]:60} -> job {job.get('id')} {n}/{t}" + (" | " + "; ".join(misses) if misses else "") + (f" | off-brief: {'; '.join(brief)}" if brief else ""), flush=True)

    scored = [r for r in rows if r["hits"] or r["misses"]]
    total_hits = sum(len(r["hits"]) for r in scored)
    total = sum(len(r["hits"]) + len(r["misses"]) for r in scored)
    mean = total_hits / total if total else 0.0
    genre_miss = any(m.startswith("genre ") for r in rows for m in r["misses"])
    unfinished = [r for r in rows if r["title"] is None]
    ok = mean >= 0.85 and not genre_miss and not unfinished     # a build that did not finish is a miss, not a gap in the table

    md = ["# Prompt fidelity", "",
          f"Scored on {time.strftime('%Y-%m-%d')} by `backend/tools/prompt_check.py`: each sentence carries what a careful reader would expect from it, and the build is scored on how many of those it delivered, read from the resolved spec the studio wrote. The studio's own off-brief notes ride along.", "",
          f"**{total_hits} of {total} expectations met ({mean:.0%}).** " + ("Pass." if ok else "Below the line (0.85, no genre missed, every build finished).") + (f" {len(unfinished)} build(s) did not finish." if unfinished else ""), "",
          "| the sentence | title | genre | score | missed | stand-ins | off-brief |", "|---|---|---|---:|---|---|---|"]
    for r in rows:
        n, t = len(r["hits"]), len(r["hits"]) + len(r["misses"])
        md.append(f"| {r['prompt']} | {r['title'] or ''} | {r['genre'] or ''} | {n}/{t} | {'; '.join(r['misses']) or ''} | {'; '.join(r['standins']) or ''} | {'; '.join(r['brief']) or ''} |")
    md += ["", "## What each sentence is held to", ""]
    for item in PROMPTS:
        md.append(f"- {item['prompt']}: " + ", ".join(f"{k} {v}" if not isinstance(v, bool) else k for k, v in item["want"].items()))
    md.append("")
    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"\n{total_hits}/{total} met ({mean:.0%}) | genre missed: {genre_miss} | {'PASS' if ok else 'FAIL'} | written {OUT.relative_to(ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
