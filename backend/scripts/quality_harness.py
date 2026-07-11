"""Quality harness (Phase 53) — the regression gate for character/scene work.

Two checks, per the quality-uplift plan (Section 9):

  morph   Edge-stretch morph metric on animated library rigs, via headless
          Blender (scripts/_harness_measure.py). p95 edge stretch = morph
          score; lower is better.
  styles  Style/view protection: export one fixed-seed game per style preset
          and per view preset, hash the emitted runtime files. Any hash drift
          without an intended runtime change = regression.

Usage (backend venv):
  python scripts/quality_harness.py morph --baseline          # capture
  python scripts/quality_harness.py morph --compare           # gate a change
  python scripts/quality_harness.py morph --assets cat,fox    # subset
  python scripts/quality_harness.py styles --baseline
  python scripts/quality_harness.py styles --compare

Baselines live in renders/quality_baseline/ (gitignored). --compare exits 1 on
regression (morph score >5% worse on any asset, or unexplained style drift),
so it can gate commits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

BASELINE_DIR = BACKEND / "renders" / "quality_baseline"
DEFAULT_ASSETS = ["cat", "fox", "man", "polar_bear"]
MORPH_TOLERANCE = 1.05          # compare fails if score > baseline * 1.05

STYLES = ["default", "cartoon", "anime", "horror", "pixel", "lowpoly"]
VIEWS = ["3d", "topdown", "side"]


def _blender_exe() -> str:
    cand = os.environ.get("FS_BLENDER_EXE")
    if cand and Path(cand).exists():
        return cand
    for c in (r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
              r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"):
        if Path(c).exists():
            return c
    raise FileNotFoundError("Blender not found — set FS_BLENDER_EXE")


# ── morph check ─────────────────────────────────────────────────────────────

def run_morph(assets: list[str]) -> dict:
    measure = BACKEND / "scripts" / "_harness_measure.py"
    results: dict = {}
    for kind in assets:
        glb = BACKEND / "assets" / "library" / f"{kind}_anim.glb"
        if not glb.exists():
            results[kind] = {"ok": False, "reason": f"missing {glb.name}"}
            continue
        out_json = BASELINE_DIR / f"_tmp_{kind}.json"
        out_json.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [_blender_exe(), "--background", "--python", str(measure),
             "--", str(glb), str(out_json)],
            capture_output=True, text=True, timeout=600, cwd=str(BACKEND),
            encoding="utf-8", errors="replace")   # Blender stdout isn't cp1252-safe
        try:
            results[kind] = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception:
            tail = (proc.stdout or "")[-400:] + (proc.stderr or "")[-400:]
            results[kind] = {"ok": False, "reason": f"no output; {tail}"}
        finally:
            out_json.unlink(missing_ok=True)
        score = results[kind].get("morph_score")
        print(f"  {kind:12} -> " + (f"morph_score={score}" if results[kind].get("ok")
                                    else f"FAILED: {results[kind].get('reason','')[:120]}"))
    return results


# ── style/view artifact check ───────────────────────────────────────────────

def _mini_spec(style: str, view: str):
    """Deterministic minimal GameSpec — fixed seed, library cat, no scatter."""
    from app.game_export.spec import GameSpec
    d = {
        "title": "Harness Probe", "prompt": "harness probe",
        "seed": 424242, "style": style, "view": view,
        "player": {"asset": str(BACKEND / "assets" / "library" / "cat_anim.glb"),
                   "name": "cat", "height_m": 0.5},
        "world": {"name": "park", "size_m": 80.0, "grass": False,
                  "scatter": [], "placed_items": []},
        "entities": [], "objectives": [],
    }
    return GameSpec.model_validate(d)


def run_styles() -> dict:
    from app.game_export.web_exporter import export_web_game
    out: dict = {}
    combos = [(s, "3d") for s in STYLES] + [("default", v) for v in VIEWS[1:]]
    for style, view in combos:
        tag = f"{style}_{view}"
        try:
            dist = export_web_game(_mini_spec(style, view),
                                   BASELINE_DIR / "_style_probe" / tag,
                                   verbose=False)
            h = hashlib.sha256()
            for name in ("game.js", "index.html", "spec.json"):
                p = Path(dist) / name
                if p.exists():
                    h.update(p.read_bytes())
            out[tag] = h.hexdigest()[:16]
            print(f"  {tag:16} -> {out[tag]}")
        except Exception as e:  # noqa: BLE001
            out[tag] = f"ERROR: {type(e).__name__}: {e}"
            print(f"  {tag:16} -> {out[tag]}")
    return out


# ── baseline/compare plumbing ───────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("check", choices=["morph", "styles"])
    ap.add_argument("--baseline", action="store_true", help="capture baseline")
    ap.add_argument("--compare", action="store_true", help="gate vs baseline")
    ap.add_argument("--assets", default=",".join(DEFAULT_ASSETS))
    args = ap.parse_args()

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    bl_file = BASELINE_DIR / f"{args.check}_baseline.json"

    if args.check == "morph":
        current = run_morph([a.strip() for a in args.assets.split(",") if a.strip()])
    else:
        current = run_styles()

    if args.baseline:
        bl_file.write_text(json.dumps(current, indent=1), encoding="utf-8")
        print(f"[harness] baseline written -> {bl_file}")
        return

    if args.compare:
        if not bl_file.exists():
            print("[harness] NO BASELINE — run with --baseline first")
            sys.exit(2)
        base = json.loads(bl_file.read_text(encoding="utf-8"))
        failed = []
        if args.check == "morph":
            for kind, cur in current.items():
                ref = base.get(kind, {})
                if not cur.get("ok"):
                    failed.append(f"{kind}: measurement failed ({cur.get('reason','')[:80]})")
                elif ref.get("ok") and cur["morph_score"] > ref["morph_score"] * MORPH_TOLERANCE:
                    failed.append(f"{kind}: morph {ref['morph_score']} -> "
                                  f"{cur['morph_score']} (worse)")
                else:
                    delta = (cur["morph_score"] - ref.get("morph_score", cur["morph_score"]))
                    print(f"  {kind:12} OK  ({ref.get('morph_score','?')} -> "
                          f"{cur['morph_score']}, Δ{delta:+.4f})")
        else:
            for tag, h in current.items():
                if base.get(tag) != h:
                    failed.append(f"{tag}: {base.get(tag)} -> {h}")
                else:
                    print(f"  {tag:16} OK")
        if failed:
            print("[harness] REGRESSION:")
            for f in failed:
                print("   ", f)
            sys.exit(1)
        print("[harness] all checks pass")


if __name__ == "__main__":
    main()
