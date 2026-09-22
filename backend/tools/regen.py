"""Regenerate the library's poor models, with the judge in the loop.

    python backend/tools/regen.py                  # every kind the manifest marks poor
    python backend/tools/regen.py scientist relic  # named kinds
    python backend/tools/regen.py --attempts 2 ... # fewer seeds per kind (default 3)

For each kind: the old model and its library entry are retired (kept under
assets/library/_retired), the generation cache for that noun is cleared so
SDXL and TRELLIS run again on a fresh seed, the result is rigged, rendered
(assetview.mjs) and judged (assetjudge.py), and the manifest is rebuilt.
A verdict of good or fair keeps the new model; poor retires it and tries
the next seed. After the last attempt a still-poor kind is left OUT of the
library, which is the honest state: a stand-in beats a flayed figure.
Runs on the GPU; a character is six to ten minutes an attempt.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
LIB_JSON = BACKEND / "assets" / "library.json"
MANIFEST = BACKEND / "assets" / "library_manifest.json"
RENDER_JSON = BACKEND / "assets" / "library_render.json"
RETIRED = BACKEND / "assets" / "library" / "_retired"
SHOTGATE = BACKEND / "tools" / "shotgate"
PY = sys.executable


def _lib() -> dict:
    return json.loads(LIB_JSON.read_text(encoding="utf-8"))


def _save_lib(d: dict) -> None:
    LIB_JSON.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _verdict(kind: str) -> tuple[str, dict]:
    lib = _lib()
    entry = lib.get(kind)
    file = Path(entry if isinstance(entry, str) else (entry or {}).get("raw", "")).name.lower()
    for r in json.loads(MANIFEST.read_text(encoding="utf-8")).get("assets", []):
        if r.get("file", "").lower() == file:
            return r.get("verdict", "unknown"), r
    return "unknown", {}


def _retire(kind: str, why: str) -> list[str]:
    """Move the kind's files out of the library and drop its entry."""
    RETIRED.mkdir(parents=True, exist_ok=True)
    lib = _lib()
    moved = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for stem in (kind.replace(" ", "_"), kind.replace(" ", "_") + "_anim"):
        for f in (BACKEND / "assets" / "library").glob(stem + ".glb"):
            dest = RETIRED / f"{f.stem}_{stamp}_{why}.glb"
            shutil.move(str(f), str(dest))
            moved.append(dest.name)
    entry = lib.pop(kind, None)
    _save_lib(lib)
    # the generation cache for this noun, so the next attempt is a fresh roll
    from app.game_export.generate import CACHE_DIR
    key = hashlib.md5(kind.lower().encode("utf-8")).hexdigest()[:12]
    for p in CACHE_DIR.glob(key + "*"):
        try:
            if p.name.endswith("_ref.png"):          # the picture it was made from, kept for the post-mortem
                shutil.copy(str(p), str(RETIRED / f"{kind.replace(' ', '_')}_{stamp}_{why}_ref.png"))
            p.unlink()
        except OSError:
            pass
    # the library's own resolve cache of the manifest
    return moved


def _serve() -> subprocess.Popen | None:
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", 8791)) == 0:
            return None
    return subprocess.Popen([PY, "-m", "http.server", "8791"], cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _judge(kind: str) -> None:
    subprocess.run(["node", "assetview.mjs", kind], cwd=str(SHOTGATE), check=False, timeout=600)
    # fold this kind's render into the render file (assetview only writes it for --all)
    data = json.loads(RENDER_JSON.read_text(encoding="utf-8")) if RENDER_JSON.exists() else {}
    lib = _lib()
    entry = lib.get(kind)
    rel = entry if isinstance(entry, str) else (entry or {}).get("raw", "")
    stem = "".join(ch if ch.isalnum() else "_" for ch in kind)
    shaded = SHOTGATE / "renders" / f"{stem}_shaded.png"
    if rel and shaded.exists():
        data[Path(rel).name.lower()] = {"kind": kind, "shaded_png": str(shaded.relative_to(ROOT)).replace("\\", "/")}
        RENDER_JSON.write_text(json.dumps(data, indent=1), encoding="utf-8")
    subprocess.run([PY, str(BACKEND / "tools" / "assetjudge.py"), kind], cwd=str(BACKEND), check=False, timeout=900)
    subprocess.run([PY, str(BACKEND / "tools" / "assetmeta.py")], cwd=str(BACKEND), check=False, timeout=1800)


def _free_gpu() -> None:
    """The headless Blender the bake leaves behind keeps GPU memory for EEVEE;
    TRELLIS.2's texture bake ran out of it on the second attempt of a run
    (2026-09-25). Only the bridge instance is stopped, never a user's Blender."""
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*headless_bridge_startup*' } "
                    "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], check=False, timeout=60,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def regen(kind: str, attempts: int) -> str:
    from app.game_export.generate import ensure_asset, guess_pattern
    from app.game_export.bake import ensure_playable
    from app.game_export import library
    print(f"\n== {kind} ==", flush=True)
    before, rec = _verdict(kind)
    print(f"  before: {before} {rec.get('quality_reasons') or ''}", flush=True)
    _retire(kind, "poor")
    for attempt in range(attempts):
        seed = 1000 + attempt * 7919
        os.environ["FS_TRELLIS_SEED"] = str(seed)
        os.environ["FS_REF_SEED"] = str(seed + 1)          # a fresh reference too: a flayed figure may be the picture's fault, not the mesh's
        t0 = time.time()
        _free_gpu()
        try:
            ensure_asset(kind, verbose=True)
            library._MANIFEST = None
            if guess_pattern(kind) in ("biped", "quadruped"):
                # THE RIG IS PART OF THE ASSET (2026-09-25): a scientist came
                # out good and unrigged because the bridge Blender was still
                # booting after the mesh; the rig gets a second chance with
                # the bridge up, and a character without one is a failed attempt.
                from app.game_export.bake import ensure_bridge
                anim = BACKEND / "assets" / "library" / f"{kind.lower().replace(' ', '_')}_anim.glb"
                for _try in range(2):
                    ensure_bridge(verbose=True)
                    ensure_playable(kind, verbose=True)
                    if anim.exists():
                        break
                    print(f"  rig missing after try {_try + 1}; the bridge is asked again", flush=True)
                if not anim.exists():
                    raise RuntimeError("no rig was baked; a character without one cannot walk")
                print(f"  rigged: {anim.name} ({anim.stat().st_size / 1e6:.1f} MB)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  attempt {attempt + 1}: generation failed ({type(e).__name__}: {str(e)[:120]})", flush=True)
            continue
        _judge(kind)
        v, rec = _verdict(kind)
        looks = (rec.get("render") or {}).get("looks_like")
        print(f"  attempt {attempt + 1} (seed {seed}, {int(time.time() - t0)} s): {v} | looks like it {looks} | {rec.get('quality_reasons') or ''}", flush=True)
        if v in ("good", "fair"):
            return v
        _retire(kind, f"poor_seed{seed}")
    print(f"  {kind}: still poor after {attempts} attempts; left out of the library (a stand-in plays it)", flush=True)
    return "poor"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    attempts = 3
    if "--attempts" in sys.argv:
        attempts = int(sys.argv[sys.argv.index("--attempts") + 1])
        args = [a for a in args if a != str(attempts)]
    if not args:
        args = [r["file"].replace("_anim", "").replace(".glb", "").replace("_", " ")
                for r in json.loads(MANIFEST.read_text(encoding="utf-8")).get("assets", []) if r.get("verdict") == "poor"]
        args = sorted(set(args))
    print("regenerating:", ", ".join(args), flush=True)
    srv = _serve()
    results = {}
    try:
        for k in args:
            results[k] = regen(k, attempts)
    finally:
        if srv:
            srv.terminate()
    print("\nresults:", json.dumps(results))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
