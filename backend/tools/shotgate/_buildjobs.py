"""Build the jobs this round needs, one after another, and print their ids.
usage: python buildjobs.py moon adv manor g_towerdef ...   (any subset, in order)
       python buildjobs.py "p:a prompt of your own"        (a prompt given inline)
(rebuilt 2026-10-25 from the session transcripts after the file vanished; a copy
 lives at backend/tools/shotgate/_buildjobs.py)"""
import json, sys, time, urllib.request

PROMPTS = {
    "moon": "a rusted mining outpost on a dead red moon",
    "frost": "an ice refinery on a frozen moon",
    "bakery": "a bakery on a floating island where grain is milled into flour and baked into loaves",
    "adv": "a tokyo drift racing game through neon streets at night",
    "manor": "a haunted manor on a windswept moor, find the three relics before the bell tolls",
    "g_towerdef": "a tower defense game where goblins march down a road and I build archer towers to stop them",
    "g_platformer": "a 2D platformer where a fox jumps between floating islands collecting gems",
    "g_mystery": "a detective mystery in a foggy victorian manor, find three clues and name the killer",
    "g_citybuild": "a city builder where I lay roads, zone houses and grow the population to 500",
    "g_dungeon": "a dungeon crawler, a knight fights skeletons to find the golden key",
    "g_cartoonfox": "a cartoon village where a fox collects five stars",
    "g_graveyard": "a horror game in a graveyard at night, find the three lanterns",
}
API = "http://127.0.0.1:8789"

def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def get(path):
    return json.loads(urllib.request.urlopen(API + path, timeout=60).read())

out = {}
for key in sys.argv[1:]:
    t0 = time.time()
    r = post("/api/game/export", {"prompt": key[2:] if key.startswith("p:") else PROMPTS[key]})
    jid = r.get("job_id") or r.get("id")
    j = {}
    while True:
        time.sleep(3)
        j = get(f"/api/game/jobs/{jid}")
        j = j.get("job", j)
        st = j.get("status")
        if st in ("complete", "failed", "error", "cancelled"):
            break
        if time.time() - t0 > 1500:
            st = "timeout"; break
    print(f"{key.upper()} JOB {jid} {st} | genre {j.get('genre')} | {int(time.time()-t0)}s | {j.get('stage')} | {j.get('error') or ''}", flush=True)
    out[key] = jid
print("IDS", json.dumps(out))
