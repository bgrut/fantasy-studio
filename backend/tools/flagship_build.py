"""Build the standalone flagship demo FROM the studio's factory runtime.

WHY THIS EXISTS (2026-09-07)
----------------------------
The demo used to be its own file. Within a week of shipping the cube grid, the
meltdown, the minerals, the filter and the market into the studio template, the
standalone copy was 601 lines behind and nobody had noticed — the two were
"kept in parallel" by discipline, which is another way of saying not at all.

So the demo is not a copy any more. It is the studio's output with a fixed spec
substituted, which makes parity structural: a feature cannot exist in one and
not the other, because there is only one source. It also makes the demo the
honest proof of the claim on the box — what you play IS what a prompt produces.

Run it after any change to the factory runtime:

    python backend/tools/flagship_build.py

and it rewrites flagship/factory.js and flagship/index.html. --check exits
non-zero if they are stale, which is what CI should call.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "backend" / "app" / "game_export" / "runtime"
OUT = ROOT / "flagship"

# The demo's spec. Every field here is one the studio itself fills in from a
# prompt — this is a hand-written example of the same document, not a special
# case in the runtime.
DEMO_SPEC = {
    "title": "Crystal Works",
    "genre": "factory",
    "style": "lowpoly",
    "world": {
        "name": "a floating worldlet of six mining faces",
        "size_m": 200,
        "palette": {"sky": "#0b0d18", "fog": "#0b0d18", "accent": "#39e6ff"},
    },
    "objectives": [
        {"kind": "produce", "text": "automate an alloy line across two faces"},
    ],
}

BANNER = (
    "// GENERATED FILE — do not edit.\n"
    "//\n"
    "// Built from backend/app/game_export/runtime/factory.js.tpl by\n"
    "// backend/tools/flagship_build.py. The standalone demo is the studio's\n"
    "// own output with a fixed spec, so the two cannot drift apart. Edit the\n"
    "// template and re-run the builder.\n"
)


def render() -> dict[str, str]:
    js = (RUNTIME / "factory.js.tpl").read_text(encoding="utf-8")
    html = (RUNTIME / "factory.index.html.tpl").read_text(encoding="utf-8")

    if "__GAME_SPEC__" not in js:
        raise SystemExit("factory.js.tpl has no __GAME_SPEC__ placeholder")
    if "__TITLE__" not in html:
        raise SystemExit("factory.index.html.tpl has no __TITLE__ placeholder")

    js = BANNER + js.replace("__GAME_SPEC__", json.dumps(DEMO_SPEC))
    html = html.replace("__TITLE__", DEMO_SPEC["title"] + " — Fantasy Studio")
    # the demo keeps its historical filename; everything else is byte-identical
    # to what a build ships
    html = html.replace('src="./game.js"', 'src="./factory.js"')
    return {"factory.js": js, "index.html": html}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the demo is stale instead of rewriting it")
    args = ap.parse_args()

    files = render()
    stale = []
    for name, text in files.items():
        p = OUT / name
        current = p.read_text(encoding="utf-8") if p.exists() else None
        if current == text:
            continue
        stale.append(name)
        if not args.check:
            p.write_text(text, encoding="utf-8")

    if args.check:
        if stale:
            print("STALE: " + ", ".join(stale)
                  + "\nrun: python backend/tools/flagship_build.py")
            return 1
        print("flagship demo is up to date with the runtime")
        return 0

    if stale:
        print("rebuilt " + ", ".join(stale))
    else:
        print("flagship demo already up to date")
    for name in files:
        p = OUT / name
        print(f"  {p.relative_to(ROOT)}  {p.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
