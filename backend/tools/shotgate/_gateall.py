"""Build the gate jobs, then run the full factory gate against them; then rerun
any failed gate alone once (a full run flakes under load). One detached process.
usage: python -u gateall.py  (log to stdout)"""
import json, os, re, subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
S = os.path.dirname(os.path.abspath(__file__))
BK = r"C:/Users/bgrut/Desktop/FantasyAI/fantasy-studio/backend"
subprocess.run([sys.executable, BK + "/tools/cleantmp.py"])   # stale browser profiles filled the disk once (2026-10-07)
keys = ["moon", "adv", "manor", "g_towerdef", "g_platformer", "g_mystery", "g_citybuild", "g_dungeon"]
if "--ids" in sys.argv:
    _kv = dict(x.split("=") for x in sys.argv[sys.argv.index("--ids") + 1].split(","))
    class _O: stdout = "IDS " + json.dumps({k: int(v) for k, v in _kv.items()}); stderr = ""
    out = _O()
else:
    out = subprocess.run([sys.executable, "-u", os.path.join(S, "buildjobs.py" if os.path.exists(os.path.join(S, "buildjobs.py")) else "_buildjobs.py"), *keys], capture_output=True, text=True, cwd=S)
print(out.stdout[-2000:], out.stderr[-1500:], flush=True)
m = re.search(r"IDS (\{.*\})", out.stdout)
if not m:
    print("NO IDS"); sys.exit(1)
ids = json.loads(m.group(1))
print("IDS", ids, flush=True)
# the planner's model holds the card after the builds; let it go before the gates (never kill Ollama)
try:
    import urllib.request
    ps = json.loads(urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=5).read())
    for m in ps.get("models", []):
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps({"model": m["name"], "keep_alive": 0}).encode(), headers={"Content-Type": "application/json"}), timeout=30).read()
        print("unloaded", m["name"], flush=True)
except Exception as e:
    print("ollama unload skipped:", e, flush=True)
args = [sys.executable, "-u", "tools/factory_check.py", "--job", str(ids["moon"]), "--demo", "http://127.0.0.1:8790/",
        "--adv", str(ids["adv"]), "--bld", str(ids["manor"]), "--td", str(ids["g_towerdef"]), "--pf", str(ids["g_platformer"]),
        "--my", str(ids["g_mystery"]), "--town", str(ids["g_citybuild"]), "--fight", str(ids["g_dungeon"])]
g = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=BK)
print(g.stdout, g.stderr[-1500:], flush=True)
# rerun failures alone, per target
env0 = dict(os.environ, A=str(ids["adv"]), B=str(ids["manor"]), TD=str(ids["g_towerdef"]), PF=str(ids["g_platformer"]),
            MY=str(ids["g_mystery"]), TOWN=str(ids["g_citybuild"]), FIGHT=str(ids["g_dungeon"]))
target = None
for line in g.stdout.splitlines():
    if line.startswith("== studio build"): target = {"J": str(ids["moon"])}
    elif line.startswith("== standalone demo"): target = {"URL": "http://127.0.0.1:8790/"}
    mm = re.match(r"\s+FAIL\s+(\S+\.mjs)", line)
    if mm and target:
        r = subprocess.run(["node", mm.group(1)], cwd=BK + "/tools/shotgate", env=dict(env0, **target),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        print(f"RERUN {mm.group(1)} {list(target)[0]} -> {'PASS' if r.returncode == 0 else 'FAIL'}", flush=True)
        if r.returncode != 0: print((r.stdout + r.stderr)[-2500:], flush=True)
print("GATE DONE", flush=True)
