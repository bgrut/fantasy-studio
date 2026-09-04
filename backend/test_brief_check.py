"""Every case here is a bug that actually shipped.

The visual gate passed all four of them: they rendered, they had no runtime
errors, and they were the wrong game. Run with:  python test_brief_check.py
"""
from __future__ import annotations

import sys

from app.game_export.brief_check import check_brief
from app.game_export.spec import GameSpec


def _spec(archetype="plain", style="default", mode="walk") -> GameSpec:
    s = GameSpec(title="t", world={"name": "w"}, player={"name": "man"},
                 objectives=[])
    s.world.archetype = archetype
    s.style = style
    s.player.mode = mode
    return s


CASES = [
    ("a canyon carpeted in meadow grass",
     _spec(archetype="canyon"),
     {"archetype": "canyon", "style": "default", "mode": "walk",
      "ground_tex": "grass.jpg"},
     True),
    ("a sailboat seven metres under the sea",
     _spec(archetype="archipelago", mode="swim"),
     {"archetype": "archipelago", "style": "default", "mode": "swim",
      "buoyant": True, "ground_tex": "sand.jpg", "depth_below_water": 6.76},
     True),
    ("a hero lying on his side",
     _spec(),
     {"archetype": "plain", "style": "default", "mode": "walk",
      "player_dims": [1.0, 0.26, 0.96]},
     True),
    ("art direction the renderer never received",
     _spec(style="pixel"),
     {"archetype": "plain", "style": "default", "mode": "walk"},
     True),
    ("playing as a wolf: longer than it is tall, and perfectly fine",
     _spec(),
     {"archetype": "plain", "style": "default", "mode": "walk",
      "player_dims": [0.36, 0.85, 1.0], "player_bones": 12},
     False),
    ("a wolf that has actually fallen over",
     _spec(),
     {"archetype": "plain", "style": "default", "mode": "walk",
      "player_dims": [1.0, 0.22, 0.85], "player_bones": 12},
     True),
    ("a biped is still held to standing upright",
     _spec(),
     {"archetype": "plain", "style": "default", "mode": "walk",
      "player_dims": [1.0, 0.26, 0.96], "player_bones": 19},
     True),
    ("a canyon that got it right",
     _spec(archetype="canyon"),
     {"archetype": "canyon", "style": "default", "mode": "walk",
      "ground_tex": "rock.jpg", "player_dims": [1.67, 1.8, 1.14]},
     False),
    ("a car, which is legitimately wider than it is tall",
     _spec(mode="drive"),
     {"archetype": "plain", "style": "default", "mode": "drive",
      "player_dims": [1.8, 1.4, 4.5]},
     False),
]


def main() -> int:
    bad = 0
    for name, spec, facts, should_flag in CASES:
        out = check_brief(spec, facts)
        ok = bool(out) == should_flag
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {name}")
        for o in out:
            print(f"        -> {o}")
    print(f"\n{len(CASES) - bad}/{len(CASES)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
