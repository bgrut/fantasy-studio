"""CLI: export a playable three.js web game from a prompt/PRD, a GameSpec
JSON file, or flags. Every export is auto-verified (verify_game gate).

Usage:
    python scripts/export_game.py --prompt "a knight in a foggy forest at night" --player-glb hero.glb
    python scripts/export_game.py --prd my_game_prd.md --player-glb hero.glb
    python scripts/export_game.py --spec my_game.json --out renders/game_park
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.game_export.spec import GameSpec, spec_from_dict          # noqa: E402
from app.game_export.web_exporter import export_web_game          # noqa: E402
from app.game_export.dressing import game_scatter                 # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", help="game idea as text (Ollama → GameSpec)")
    ap.add_argument("--prd", help="path to a PRD document (Ollama → GameSpec)")
    ap.add_argument("--spec", help="GameSpec JSON file")
    ap.add_argument("--player-glb", help="player .glb (overrides spec)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default=str(BACKEND_ROOT / "renders" / "game_out"))
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    if args.spec:
        spec = spec_from_dict(json.loads(Path(args.spec).read_text(encoding="utf-8")))
    elif args.prompt or args.prd:
        from app.game_export.extractor import extract_game_spec
        text = args.prompt or Path(args.prd).read_text(encoding="utf-8")
        spec = extract_game_spec(text)
    else:
        spec = GameSpec()
    if args.player_glb:
        spec.player.asset = args.player_glb
    if args.title:
        spec.title = args.title
    if not spec.player.asset:
        ap.error("need --player-glb or a spec with player.asset")

    # shared world-dressing: default scatter recipe for the world's setting
    if not spec.world.scatter:
        from app.game_export.spec import ScatterSpec
        spec.world.scatter = [ScatterSpec(**s) for s in game_scatter(spec.world.name)]

    # resolve entity assets from the local library (Phase 27 will generate
    # missing ones on demand); unresolvable entities are dropped LOUDLY
    from app.game_export import library
    kept = []
    for ent in spec.entities:
        if not ent.asset:
            glb = library.resolve(ent.name)
            if glb:
                ent.asset = glb
                if ent.height_m == 1.0:
                    ent.height_m = library.default_height(ent.name)
            else:
                print(f"[game] entity '{ent.name}' has no library asset yet — dropped "
                      f"(Phase 27 will generate it)")
                continue
        kept.append(ent)
    spec.entities = kept

    dist = export_web_game(spec, args.out)

    if not args.no_verify:
        from app.game_export.verify_game import verify_dist
        v = verify_dist(dist)
        if v["ok"]:
            print(f"[game] verify: PASS ({len(v['checks'])} checks)")
        else:
            print(f"[game] verify: FAIL — {v['errors']}")
            sys.exit(2)

    print(f"serve it:  python -m http.server 8770 --directory \"{dist}\"")


if __name__ == "__main__":
    main()
