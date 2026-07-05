"""R0 — regression pack (spec level): the no-circles guarantee.

Runs the extraction + casting + world-design DECISIONS for a fixed prompt set
and asserts the invariants that past bugs violated. Seconds to run, no
renders, no GPU, no backend needed:

    venv/Scripts/python.exe scripts/regression_pack.py

Add a case every time a prompt-class bug is fixed. (The frame-level visual
pack is R1 — this is the fast structural floor beneath it.)
"""
import sys
from pathlib import Path

B = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(B))

from app.game_export.extractor import extract_game_spec          # noqa: E402
from app.game_export.generate import guess_pattern               # noqa: E402
from app.game_export.level import detect_place                   # noqa: E402
from app.game_export.dressing import recipe_for, wants_grass     # noqa: E402

# (prompt, expectations) — expectations checked against the extracted spec
CASES = [
    ("a horse galloping through the mountains, collect 5 gems",
     {"pattern": "quadruped", "world_has": "mountain"}),
    ("a dragon flying through the mountains, catch 5 fire flames",
     {"pattern": "flying"}),
    ("a whale exploring the deep ocean, collect 5 pearls",
     {"pattern": "aquatic", "world_has": "ocean"}),
    ("a chef running through a busy city street",
     {"pattern": "biped", "world_has": "city"}),
    ("car racing through the streets of new york, pass 5 rivals",
     {"pattern": "vehicle", "place": "new_york", "race": True}),
    ("a fox on a snowy night quest in the forest",
     {"pattern": "quadruped", "world_has": "forest"}),
]

# world classes that must have dressing recipes (empty sand plane bug class)
RECIPE_WORLDS = ["mountain", "canyon", "desert", "swamp", "ocean", "lake",
                 "hills", "forest", "city", "park", "arctic", "volcano"]
NO_GRASS_WORLDS = ["desert", "ocean", "city", "arctic", "volcano"]


def main() -> int:
    failures = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    for prompt, exp in CASES:
        print(f"\n{prompt!r}")
        spec = extract_game_spec(prompt, verbose=False)
        player = (spec.player.name or "man").lower()
        pat = guess_pattern(player)
        if "pattern" in exp:
            check(f"player '{player}' pattern", pat == exp["pattern"],
                  f"got {pat}, want {exp['pattern']}")
        if "world_has" in exp:
            check("world name", exp["world_has"] in (spec.world.name or "").lower(),
                  f"got '{spec.world.name}'")
        if "place" in exp:
            check("OSM place", detect_place(prompt) == exp["place"],
                  f"got {detect_place(prompt)}")
        if exp.get("race"):
            check("race objective", any(o.kind == "race" for o in spec.objectives),
                  f"got {[o.kind for o in spec.objectives]}")

    print("\nworld recipes")
    for w in RECIPE_WORLDS:
        check(f"recipe '{w}'", recipe_for(w) is not None)
    for w in NO_GRASS_WORLDS:
        check(f"no grass in '{w}'", not wants_grass(w))
    check("grass in 'meadow'", wants_grass("meadow"))

    print(f"\n{'ALL PASS' if not failures else f'{len(failures)} FAILURES: {failures}'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
