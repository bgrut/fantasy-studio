"""Run every factory gate against BOTH the studio build and the standalone demo.

The demo is generated from the studio runtime, so the two can only disagree if
the generator was not re-run — which this checks first. After that it is the
same four gates twice, because "it works in the studio" and "it works in the
thing people download" are different claims and only one of them was ever
getting tested.

    python backend/tools/factory_check.py --job 18
    python backend/tools/factory_check.py --job 18 --demo http://127.0.0.1:8790/

Serve the demo with:  cd flagship && python -m http.server 8790
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATES = [
    ("fact.mjs", "core loop, cube walk, belt wrap, minerals, forge, filter, market, meltdown"),
    ("frift.mjs", "chronos rift: lends, is repaid, storms when it is not"),
    ("finspect.mjs", "the studio's picking bridge, driven through a real iframe"),
    ("fsave.mjs", "a factory survives a real reload"),
    ("fphys.mjs", "you cannot walk through machines; a merge does not eat items"),
    ("fgoals.mjs", "locked machines refuse; the goal chain advances on what it asks for"),
    ("fart.mjs", "icons, instanced belts, a tread that scrolls, a sky that is drawn"),
    ("fperf.mjs", "a 250-machine factory stays inside its draw-call budget"),
    ("fworld.mjs", "worlds unlock with cores, change the scene, and survive a reload"),
    ("fground.mjs", "the factory is grounded: shadows land on a lit face and an unlit one"),
]


def run(gate: str, env_extra: dict[str, str]) -> tuple[bool, str]:
    import os
    env = dict(os.environ, **env_extra)
    r = subprocess.run([_node(), gate], cwd=str(ROOT / "backend" / "tools" / "shotgate"),
                       env=env, capture_output=True, text=True, timeout=600)
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def _node() -> str:
    return "node"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job", help="game job id to gate (the studio build)")
    ap.add_argument("--demo", default="http://127.0.0.1:8790/",
                    help="URL the standalone demo is served at")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    print("== the demo is up to date with the runtime ==")
    r = subprocess.run([sys.executable, str(ROOT / "backend/tools/flagship_build.py"), "--check"],
                       capture_output=True, text=True)
    print("  " + (r.stdout or r.stderr).strip())
    if r.returncode != 0:
        return 1

    targets = []
    if args.job:
        targets.append(("studio build", {"J": str(args.job)}))
    if args.demo:
        targets.append(("standalone demo", {"URL": args.demo}))
    if not targets:
        print("nothing to check: pass --job and/or --demo")
        return 1

    bad = 0
    for label, env in targets:
        print(f"\n== {label} ==")
        for gate, what in GATES:
            ok, out = run(gate, env)
            print(f"  {'PASS' if ok else 'FAIL'}  {gate:<14} {what}")
            if not ok:
                bad += 1
            if args.verbose or not ok:
                for line in out.strip().splitlines():
                    print("        " + line)

    print("\nall gates passed" if not bad else f"\n{bad} gate(s) failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
