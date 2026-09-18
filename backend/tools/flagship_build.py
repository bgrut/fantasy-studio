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
# ONE GAME (2026-09-18). The demo is Crystal Works and nothing else: the card
# lists no other builds. The studio's range is shown in the studio.
DEMO_WORLDS = [
    {"slug": None, "home": True, "name": "Crystal Works",
     "prompt": "a crystal works on a worldlet adrift in the void, six faces of ore and one sky"},
]

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

    # the demo's own spec carries the sentence that made it, and lists no
    # other worlds: the demo is one game
    spec_for_demo = dict(DEMO_SPEC)
    spec_for_demo["prompt"] = DEMO_WORLDS[0]["prompt"]
    spec_for_demo["worlds"] = []
    js = BANNER + js.replace("__GAME_SPEC__", json.dumps(spec_for_demo))
    html = html.replace("__TITLE__", DEMO_SPEC["title"] + " — Fantasy Studio")
    # the demo keeps its historical filename; everything else is byte-identical
    # to what a build ships
    html = html.replace('src="./game.js"', 'src="./factory.js"')
    return {"factory.js": js, "index.html": html}


def sync_fonts(check: bool) -> bool:
    """The type system and the kit ship with the game: vendor/fonts and
    vendor/kit ride from the runtime into flagship/vendor exactly as the
    exporter copies them into a build. Returns False under --check if any
    file is missing or differs."""
    import shutil
    ok = True
    # a subdirectory ships whole; a single file ships alone (the AO library
    # and the two shims it imports)
    for sub in ("fonts", "kit", "jsm/postprocessing", "n8ao.module.js", "n8ao.LICENSE", "postprocessing-stub.js", "three.LICENSE"):
        src = RUNTIME / "vendor" / sub
        if not src.exists():
            continue
        if src.is_file():
            files, dst = [src], OUT / "vendor" / pathlib.Path(sub).parent
        else:
            files, dst = [x for x in sorted(src.iterdir()) if x.is_file()], OUT / "vendor" / sub
        dst.mkdir(parents=True, exist_ok=True)
        for f in files:
            d = dst / f.name
            same = d.exists() and d.read_bytes() == f.read_bytes()
            if same:
                continue
            if check:
                ok = False
                print(f"  stale: flagship/vendor/{sub}/{f.name}")
            else:
                shutil.copyfile(f, d)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the demo is stale instead of rewriting it")
    args = ap.parse_args()

    files = render()
    fonts_ok = sync_fonts(args.check)
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
        if not fonts_ok:
            print("STALE: flagship/vendor" + chr(10) + "run: python backend/tools/flagship_build.py")
            return 1
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
