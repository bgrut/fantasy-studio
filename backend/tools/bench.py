"""THE BENCHMARK (2026-10-20): how close are we, as a number.

"How close are we to every output feeling like a handmade indie game?" was
answered by eye, five prompts a round. This builds N prompts drawn from a
wide pool (heroes, verbs, places, hours and weathers; the same set for a
given date and seed), plays each one, asks a local vision model to judge
it against its sentence, and measures how DIFFERENT the games are from
each other, since sameness is the complaint.

    python tools/bench.py --n 30 [--seed 2026] [--keep] [--no-judge]

A game passes when it built, threw no page errors, its hero moves, its
frame is neither black nor washed out, it runs at 30 fps or better, and the
judge rates it 3 or more of 5 for matching its sentence and for looking
good. Variety is the share of distinct makers, faces, layouts and
mechanics across the batch. Writes renders/bench/<date>/report.json and
report.html, and appends a line to renders/bench/history.jsonl.

Jobs are deleted afterwards unless --keep (they are this tool's own).
"""
from __future__ import annotations

import argparse, base64, collections, datetime as dt, html, json, os, random, shutil, subprocess, sys, time, urllib.request

BK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "http://127.0.0.1:8789"
OLLAMA = "http://127.0.0.1:11434"
JUDGE = "gemma3:12b"

HEROES = ["a fox", "an old lighthouse keeper", "a young witch", "a courier", "a knight", "a beekeeper", "a deep-sea diver", "a ranger",
          "a baker", "a samurai", "a cat burglar", "a botanist", "a retired astronaut", "a shepherd", "a street racer", "a monk",
          "a firefighter", "a postwoman", "a robot gardener", "a pirate captain", "a snowboarder", "a detective", "a scout",
          "a blacksmith", "a mountaineer", "a florist", "a nomad", "a ghost", "a kid on a bike", "a paleontologist"]
DOINGS = ["searches for {n} lost {t}", "delivers {t} around {p}", "climbs to the top of {p}", "explores {p} to find {a} {t1}",
          "escapes from {p}", "repairs {n} broken {t}", "patrols {p}", "races across {p}", "gathers {n} {t}", "crosses {p} to reach {g}",
          "tracks {a} {beast} through {p}", "lights the {n} lamps of {p}", "defends {g} from {foes}", "follows the river through {p}"]
THINGS = ["lanterns", "letters", "seeds", "relics", "maps", "eggs", "crystals", "pages", "bells", "keys", "honey jars", "fossils", "radios"]
PLACES = ["a misty pine forest", "a sunken city", "a desert canyon", "a Scottish island", "a neon city", "a bamboo valley", "a frozen lake",
          "an autumn village", "a volcanic ridge", "a flower meadow", "a haunted moor", "a mountain monastery", "a coral reef", "a salt marsh",
          "an abandoned railway", "a cliffside harbour", "a lavender farm", "a redwood forest", "a moon base", "an old castle",
          "the savanna", "a rainy city", "a jungle temple", "a snowy peak", "a fishing village", "the badlands"]
GOALS = ["the old stone bridge", "the watchtower", "the ruined chapel", "the hidden shrine", "the summit cairn", "the lighthouse", "the station"]
FOES = ["goblins", "wolves", "raiders", "drones", "skeletons", "crows"]
BEASTS = ["stag", "wolf", "snow leopard", "wild boar", "fox"]
HOURS = ["at dawn", "at dusk", "at night", "in a storm", "in the fog", "at midday", "in the rain", "under falling snow", ""]


# each verb with things and places it makes sense with: the bench measures the
# studio on sentences a person would write, not on word salad
VERBS = [
    ("searches {p} for {n} lost {t}", ["lanterns", "letters", "relics", "maps", "keys", "pages", "bells"], PLACES),
    ("delivers {t} around {p}", ["letters", "bread", "honey jars", "flowers", "medicine", "newspapers"],
     ["an autumn village", "a fishing village", "a cliffside harbour", "a rainy city", "a Scottish island", "a lavender farm"]),
    ("climbs to the top of {p}", [""], ["a snowy peak", "a volcanic ridge", "an old castle", "a mountain monastery", "the badlands mesa", "a sea stack"]),
    ("explores {p} to find a hidden {t1}", ["shrine", "door", "garden", "spring", "observatory", "tomb"], PLACES),
    ("escapes from {p}", [""], ["an old castle", "a haunted moor", "a moon base", "a sunken city", "a jungle temple", "an abandoned railway"]),
    ("repairs {n} broken {t} in {p}", ["lanterns", "radios", "water pumps", "fences", "signal towers", "bridges"], PLACES),
    ("patrols {p}", [""], ["a misty pine forest", "a neon city", "a salt marsh", "the savanna", "a frozen lake shore", "a cliffside harbour"]),
    ("races across {p}", [""], ["a desert canyon", "a neon city", "the savanna", "a frozen lake", "the badlands"]),
    ("gathers {n} {t} in {p}", ["seeds", "eggs", "fossils", "crystals", "mushrooms", "shells"], PLACES),
    ("crosses {p} to reach {g}", [""], PLACES),
    ("tracks a {beast} through {p}", [""], ["a redwood forest", "a misty pine forest", "a snowy peak", "the savanna", "a bamboo valley"]),
    ("lights the {n} lamps of {p}", [""], ["a fishing village", "an old castle", "a mountain monastery", "an abandoned railway", "a haunted moor"]),
    ("defends {g} from {foes}", [""], PLACES),
    ("follows the river through {p}", [""], ["a misty pine forest", "a jungle", "a bamboo valley", "a desert canyon", "an autumn valley"]),
]


def prompts(n: int, seed: int) -> list[str]:
    r = random.Random(seed)
    out = set()
    while len(out) < n:
        d, things, places = r.choice(VERBS)
        t = r.choice(things)
        s = d.format(n=r.choice(["three", "four", "five"]), t=t, t1=t, p=r.choice(places),
                     g=r.choice(GOALS), foes=r.choice(FOES), beast=r.choice(BEASTS))
        out.add(f"{r.choice(HEROES)} {s} {r.choice(HOURS)}".strip())
    return sorted(out, key=lambda x: r.random())


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(path):
    return json.loads(urllib.request.urlopen(API + path, timeout=60).read())


def build(prompt: str) -> tuple[int | None, str, float]:
    t0 = time.time()
    # the same sentence builds the same world on every run (its seed is its own text), so
    # two runs differ by what changed in the studio, not by the dice (run 3 -> 4 swung 15% -> 5%)
    import zlib
    r = post("/api/game/export", {"prompt": prompt, "seed": zlib.crc32(prompt.encode()) % 999_983 + 1})
    jid = r.get("job_id") or r.get("id")
    st = "?"
    while time.time() - t0 < 1500:
        time.sleep(3)
        j = get(f"/api/game/jobs/{jid}"); j = j.get("job", j)
        st = j.get("status")
        if st in ("complete", "failed", "error", "cancelled"):
            break
    return jid, st, time.time() - t0


def free_gpu():
    """every resident model out of video memory: the game is measured, not the judge"""
    try:
        for m in json.loads(urllib.request.urlopen(OLLAMA + "/api/ps", timeout=5).read()).get("models", []):
            req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps({"model": m["name"], "keep_alive": 0}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=30).read()
    except Exception:  # noqa: BLE001
        pass


def probe(jid: int, out_prefix: str) -> dict:
    free_gpu()
    r = subprocess.run(["node", "_benchprobe.mjs"], cwd=os.path.join(BK, "tools", "shotgate"), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300, env=dict(os.environ, J=f"job_{jid}", OUT=out_prefix))
    for line in reversed((r.stdout or "").splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return {"crash": (r.stderr or r.stdout)[-300:]}


def judge(prompt: str, shots: list[str]) -> dict:
    imgs = [base64.b64encode(open(s, "rb").read()).decode() for s in shots if os.path.exists(s)]
    if not imgs:
        return {"match": 0, "quality": 0, "defects": ["no screenshots"]}
    q = ("These are screenshots of one video game (the hero's view, the same place from above, and the place the sentence is about) made from this sentence: \"" + prompt + "\".\n"
         "Score like a games art director, with this scale for both scores: 1 = broken or empty, 2 = placeholder or wrong, "
         "3 = a coherent, competent indie game, 4 = polished, with a clear art direction, 5 = standout, award-worthy.\n"
         "match: does the world show what the sentence asks for: the place, the time of day, the weather, the hero, the named things.\n"
         "quality: lighting, detail, composition, believable materials, no visual glitches.\n"
         "defects: only problems you can actually see in THESE images, each naming the thing and where (not generic advice).\n"
         'Reply with JSON only: {"match": n, "quality": n, "defects": ["..."]}')
    body = {"model": JUDGE, "prompt": q, "images": imgs, "stream": False, "format": "json", "options": {"temperature": 0, "seed": 7}}   # the same pictures, the same verdict
    err = None
    for _attempt in range(2):                  # Ollama answers 500 now and then under load
        try:
            req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            res = json.loads(urllib.request.urlopen(req, timeout=300).read())
            v = json.loads(res.get("response") or "{}")
            return {"match": int(v.get("match", 0)), "quality": int(v.get("quality", 0)), "defects": [str(x)[:120] for x in (v.get("defects") or [])][:6]}
        except Exception as e:  # noqa: BLE001
            err = e; time.sleep(5)
    return {"match": 0, "quality": 0, "defects": [f"judge failed: {err}"[:120]]}


def shot_light(path: str) -> dict | None:
    """the frame's light, read from the screenshot (a WebGL canvas reads back blank
    once its frame is presented, so the page cannot measure itself)"""
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((96, 54))
        px = [v / 255 for v in im.getdata()]
        m = sum(px) / len(px)
        return {"mean": round(m, 3), "sd": round((sum((v - m) ** 2 for v in px) / len(px)) ** 0.5, 3)}
    except Exception:  # noqa: BLE001
        return None


def unload():
    try:
        post_o = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps({"model": JUDGE, "keep_alive": 0}).encode(),
                                        headers={"Content-Type": "application/json"})
        urllib.request.urlopen(post_o, timeout=60).read()
    except Exception:  # noqa: BLE001
        pass


def check(row: dict, judged: bool) -> dict:
    L = row.get("light") or {}
    J = row.get("judge") or {}
    return {
        "built": row.get("status") == "complete",
        "no_errors": not row.get("errors") and not row.get("crash"),
        "moves": (row.get("moved") or 0) > 1.0 or row.get("mode") in ("drive", "fly", "swim", "sail"),
        # not black, not blown out, and not one flat tone; a moonlit frame is dark and
        # low in spread, so the spread is judged against its own brightness
        "light": bool(L) and 0.04 < L.get("mean", 0) < 0.86 and (L.get("sd", 0) > 0.035 or L.get("sd", 0) / max(0.01, L.get("mean", 0)) > 0.3),
        "fps": (row.get("fps") or 0) >= 30,
        "judged": (not judged) or (J.get("match", 0) >= 3 and J.get("quality", 0) >= 3),
    }


def finish(OUT: str, rows: list, day: str, seed: int, n: int, history: bool = True):
    # variety: how many different things the batch chose
    def share(key):
        vals = [key(r) for r in rows if r.get("status") == "complete"]
        vals = [v for v in vals if v]
        if not vals:
            return {"distinct": 0, "top_share": 0}
        c = collections.Counter(vals)
        return {"distinct": len(c), "top": c.most_common(1)[0][0], "top_share": round(c.most_common(1)[0][1] / len(vals), 2)}
    variety = {
        "maker": share(lambda r: (r.get("vibe") or {}).get("maker")),
        "head_face": share(lambda r: (r.get("vibe") or {}).get("head")),
        "layout": share(lambda r: (r.get("design") or {}).get("layout")),
        "mechanic": share(lambda r: (r.get("design") or {}).get("mechanic")),
    }
    done = [r for r in rows if r.get("status") == "complete"]
    J = [r["judge"] for r in done if r.get("judge")]
    summary = {"date": day, "seed": seed, "n": n, "pass_rate": round(sum(r["pass"] for r in rows) / max(1, len(rows)), 3),
               "built": len(done), "match_avg": round(sum(j["match"] for j in J) / max(1, len(J)), 2),
               "quality_avg": round(sum(j["quality"] for j in J) / max(1, len(J)), 2),
               "fails_by_check": dict(collections.Counter(c for r in rows for c, v in r["checks"].items() if not v)), "variety": variety}
    json.dump({"summary": summary, "rows": rows}, open(os.path.join(OUT, "report.json"), "w", encoding="utf-8"), indent=1)
    if history:
        with open(os.path.join(BK, "renders", "bench", "history.jsonl"), "a", encoding="utf-8") as h:
            h.write(json.dumps(summary) + "\n")
    cards = []
    for r in rows:
        j = r.get("judge") or {}
        imgs = "".join(f'<img src="{s}" loading="lazy">' for s in r.get("shots", [])[1:])
        cards.append(f'<div class="c {"ok" if r["pass"] else "no"}"><div class="p">{html.escape(r["prompt"])}</div>{imgs}'
                     f'<div class="m">match {j.get("match", "-")} · quality {j.get("quality", "-")} · {html.escape(str((r.get("vibe") or {}).get("maker", "")))} · '
                     f'{html.escape(str((r.get("design") or {}).get("layout", "")))} / {html.escape(str((r.get("design") or {}).get("mechanic", "")))} · {r.get("fps", "-")} fps</div>'
                     f'<div class="d">{html.escape("; ".join(j.get("defects", [])))}</div>'
                     f'<div class="f">{html.escape(" ".join(c for c, v in r["checks"].items() if not v))}</div></div>')
    page = (f'<!doctype html><meta charset="utf-8"><title>Benchmark {day}</title><style>body{{font:14px system-ui;background:#111;color:#ddd;margin:20px}}'
            f'.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:14px}}.c{{background:#1b1b1b;border-radius:8px;padding:10px;border-left:4px solid #3a3}}'
            f'.c.no{{border-left-color:#c44}}.c img{{width:49%;margin-right:1%;border-radius:4px}}.p{{font-weight:600;margin-bottom:6px}}.m,.d,.f{{font-size:12px;color:#aaa;margin-top:4px}}.f{{color:#e77}}</style>'
            f'<h1>Benchmark {day}</h1><pre>{html.escape(json.dumps(summary, indent=1))}</pre><div class="g">{"".join(cards)}</div>')
    open(os.path.join(OUT, "report.html"), "w", encoding="utf-8").write(page)
    print("SUMMARY", json.dumps(summary))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=int(dt.date.today().strftime("%Y%m%d")))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--rescore", help="a past run's date: re-read its screenshots and re-apply the checks, building nothing")
    a = ap.parse_args()
    if a.rescore:
        OUT = os.path.join(BK, "renders", "bench", a.rescore)
        rep = json.load(open(os.path.join(OUT, "report.json"), encoding="utf-8"))
        rows = rep["rows"]
        for r in rows:
            if r.get("status") == "complete":
                r["light"] = shot_light(os.path.join(OUT, f"g{r['k']:03d}_eye.jpg")) or r.get("light")
            r["checks"] = check(r, judged=any(x.get("judge") for x in rows))
            r["pass"] = all(r["checks"].values())
        finish(OUT, rows, rep["summary"]["date"], rep["summary"]["seed"], rep["summary"]["n"], history=True)
        return
    day = dt.date.today().isoformat()
    OUT = os.path.join(BK, "renders", "bench", day)
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for k, pr in enumerate(prompts(a.n, a.seed)):
        jid, st, secs = build(pr)
        row = {"k": k, "prompt": pr, "job": jid, "status": st, "build_s": round(secs)}
        if st == "complete":
            pre = os.path.join(OUT, f"g{k:03d}")
            row.update(probe(jid, pre))
            row["shots"] = [os.path.basename(pre + s) for s in ("_open.jpg", "_eye.jpg", "_high.jpg", "_goal.jpg")]
            row["light"] = shot_light(pre + "_eye.jpg") or row.get("light")
            if not a.no_judge:
                row["judge"] = judge(pr, [pre + "_eye.jpg", pre + "_high.jpg", pre + "_goal.jpg"])
        row["checks"] = check(row, judged=not a.no_judge)
        row["pass"] = all(row["checks"].values())
        rows.append(row)
        print(f"[{k + 1}/{a.n}] {'PASS' if row['pass'] else 'FAIL'} job {jid} {pr[:70]} | "
              + " ".join(c for c, v in row["checks"].items() if not v), flush=True)
        if not a.keep and jid:
            shutil.rmtree(os.path.join(BK, "renders", "game_jobs", f"job_{jid}"), ignore_errors=True)
    unload()
    finish(OUT, rows, day, a.seed, a.n)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
