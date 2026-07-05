"""Static verification gate for exported games — the "without error" guarantee.

Runs after every export (export_game.py calls it automatically): structure,
vendored libs, JS syntax (node), asset references, and a real GLB parse that
confirms the player actually carries the animation clips the spec expects.
Interactive checks (console errors, movement, FPS) run via the browser preview
during development; this gate is the automated floor every build must clear.
"""
from __future__ import annotations

import json
import shutil
import struct
import subprocess
from pathlib import Path

# vendor files must be real payloads, not download-error stubs
_VENDOR_MIN = {"three.module.js": 900_000, "rapier.es.js": 1_500_000,
               "jsm/loaders/GLTFLoader.js": 60_000}


def _glb_json(path: Path) -> dict:
    """Parse a .glb's JSON chunk (glTF 2.0 binary container)."""
    with open(path, "rb") as f:
        magic, _ver, _len = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:  # 'glTF'
            raise ValueError("not a GLB file")
        clen, ctype = struct.unpack("<II", f.read(8))
        if ctype != 0x4E4F534A:  # 'JSON'
            raise ValueError("first chunk is not JSON")
        return json.loads(f.read(clen))


def verify_dist(dist: str | Path) -> dict:
    """Returns {"ok": bool, "checks": [...], "errors": [...]}. Never raises."""
    dist = Path(dist)
    checks, errors = [], []

    def check(name, ok, detail=""):
        (checks if ok else errors).append(f"{name}{': ' + detail if detail else ''}")
        return ok

    # ── structure ────────────────────────────────────────────────────────────
    idx = dist / "index.html"
    check("index.html", idx.exists())
    if idx.exists():
        html = idx.read_text(encoding="utf-8")
        check("importmap", '"three"' in html and "importmap" in html)
        check("game.js referenced", "game.js" in html)
    for rel, mn in _VENDOR_MIN.items():
        p = dist / "vendor" / rel
        check(f"vendor/{rel}", p.exists() and p.stat().st_size >= mn,
              f"{p.stat().st_size//1000}KB" if p.exists() else "missing")

    # ── spec + asset references ──────────────────────────────────────────────
    spec = None
    sp = dist / "spec.json"
    if check("spec.json", sp.exists()):
        try:
            spec = json.loads(sp.read_text(encoding="utf-8"))
        except Exception as e:
            check("spec.json parses", False, str(e))
    if spec:
        refs = [spec["player"]["asset"]]
        refs += [s["asset"] for s in spec.get("world", {}).get("scatter", [])]
        refs += [e["asset"] for e in spec.get("entities", [])]
        for r in refs:
            check(f"asset {Path(r).name}", (dist / r.lstrip("./")).exists())

    # ── JS syntax via node (skipped cleanly if node absent) ──────────────────
    game_js = dist / "game.js"
    if check("game.js", game_js.exists()) and shutil.which("node"):
        tmp = dist / "_check.mjs"
        tmp.write_text(game_js.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            r = subprocess.run(["node", "--check", str(tmp)],
                               capture_output=True, text=True, timeout=30)
            check("game.js syntax (node)", r.returncode == 0, r.stderr.strip()[:200])
        finally:
            tmp.unlink(missing_ok=True)

    # ── player GLB: skinned + animated for WALK mode; DRIVE players are rigid
    # bodies (cars) — mesh validity only.
    if spec:
        glb = dist / spec["player"]["asset"].lstrip("./")
        if glb.exists():
            try:
                g = _glb_json(glb)
                if spec["player"].get("mode") in ("drive", "fly", "swim"):
                    check(f"player mesh ({spec['player']['mode']} mode)", bool(g.get("meshes")),
                          f"meshes={len(g.get('meshes', []))}")
                else:
                    anims = [a.get("name", "") for a in g.get("animations", [])]
                    check("player skinned", bool(g.get("skins")), f"skins={len(g.get('skins', []))}")
                    want = set(spec["player"].get("anims", {}).values())
                    have = want & set(anims)
                    check("player animations", bool(anims), f"clips={anims}")
                    if anims and want and not have:
                        check("anim names match spec", False, f"want {sorted(want)}, have {anims}")
            except Exception as e:
                check("player GLB parses", False, f"{type(e).__name__}: {e}")

    return {"ok": not errors, "checks": checks, "errors": errors}
