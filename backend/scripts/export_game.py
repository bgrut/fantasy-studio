"""CLI: export a playable three.js web game from a GameSpec JSON file or from
flags. MVP entry point (the prompt/PRD extractor lands in Phase 26.5).

Usage:
    python scripts/export_game.py --player-glb renders/.../hero.glb --out renders/game_park
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
    ap.add_argument("--spec", help="GameSpec JSON file")
    ap.add_argument("--player-glb", help="player .glb (overrides spec)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default=str(BACKEND_ROOT / "renders" / "game_out"))
    args = ap.parse_args()

    if args.spec:
        spec = spec_from_dict(json.loads(Path(args.spec).read_text(encoding="utf-8")))
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

    dist = export_web_game(spec, args.out)
    print(f"serve it:  python -m http.server 8770 --directory \"{dist}\"")


if __name__ == "__main__":
    main()
