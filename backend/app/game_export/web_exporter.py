"""three.js web-game emitter: GameSpec + asset files → self-contained dist/.

Deterministic assembly only — templates are hand-written under runtime/, the
spec is injected as JSON, asset files are copied in and paths rewritten to
dist-relative. No network at build OR run time (vendored three.js + Rapier).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .spec import GameSpec

RUNTIME = Path(__file__).resolve().parent / "runtime"


def export_web_game(spec: GameSpec, out_dir: str | Path, verbose: bool = True) -> Path:
    """Emit the playable game into `out_dir` (created/overwritten). Returns the
    dist path. Raises on missing player asset — a game without a player is a
    build error, not a warning."""
    out = Path(out_dir)
    dist = out / "dist"
    assets = dist / "assets"
    if assets.exists():          # purge stale assets from prior exports
        shutil.rmtree(assets)
    assets.mkdir(parents=True, exist_ok=True)

    # ── vendored runtime libs ────────────────────────────────────────────────
    vend_src = RUNTIME / "vendor"
    vend_dst = dist / "vendor"
    if vend_dst.exists():
        shutil.rmtree(vend_dst)
    shutil.copytree(vend_src, vend_dst)

    # ── copy assets, rewrite spec paths to dist-relative ────────────────────
    rt = spec.runtime_json()

    def bring(src_path: str, tag: str) -> str:
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"{tag} asset missing: {src}")
        dst = assets / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        return f"./assets/{src.name}"

    if not spec.player.asset:
        raise ValueError("GameSpec.player.asset is required for export")
    rt["player"]["asset"] = bring(spec.player.asset, "player")
    for i, sct in enumerate(spec.world.scatter):
        rt["world"]["scatter"][i]["asset"] = bring(sct.asset, f"scatter[{i}]")
    for i, ent in enumerate(spec.entities):
        rt["entities"][i]["asset"] = bring(ent.asset, f"entity[{i}]")
    for i, ob in enumerate(spec.objectives):
        if getattr(ob, "asset", None):       # collect steps with a generated mesh
            rt["objectives"][i]["asset"] = bring(ob.asset, f"objective[{i}]")

    # ── render templates ─────────────────────────────────────────────────────
    html = (RUNTIME / "index.html.tpl").read_text(encoding="utf-8")
    (dist / "index.html").write_text(
        html.replace("__TITLE__", spec.title), encoding="utf-8")

    js = (RUNTIME / "main.js.tpl").read_text(encoding="utf-8")
    (dist / "game.js").write_text(
        js.replace("__GAME_SPEC__", json.dumps(rt)), encoding="utf-8")
    # machine-readable copy of the injected spec — read by verify_game + debugging
    (dist / "spec.json").write_text(json.dumps(rt, indent=2), encoding="utf-8")

    if verbose:
        n = sum(1 for _ in dist.rglob("*") if _.is_file())
        mb = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file()) / 1e6
        print(f"[game] exported '{spec.title}' -> {dist} ({n} files, {mb:.1f} MB)")
    return dist
