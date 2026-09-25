"""Pad, despeckle and solidify an asset's texture from the command line.

    python backend/tools/texpad.py assets/library/scientist.glb          # in place
    python backend/tools/texpad.py --opaque --normals a.glb              # solid, smooth
    python backend/tools/texpad.py --check assets/library/*.glb          # report only

The work itself lives in app/game_export/glbedit.py, which the bake calls at
the end of every generation; this is the same code pointed at files that were
made before the fix existed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.game_export.glbedit import pad_glb  # noqa: E402


def main() -> int:
    check = "--check" in sys.argv
    opaque = "--opaque" in sys.argv
    normals = "--normals" in sys.argv
    shrink = "--shrink" in sys.argv
    files = [Path(a) for a in sys.argv[1:] if not a.startswith("--")]
    if not files:
        print(__doc__)
        return 2
    for f in files:
        if not f.exists():
            print(f"  {f}: missing")
            continue
        r = pad_glb(f, check, opaque, normals, shrink)
        if r.get("shrink", {}).get("shrunk"):
            sh = r["shrink"]
            print(f"  {r['file']:26} {sh['shrunk']} map(s) recompressed, "
                  f"{sh['saved'] / 1e6:.1f} MB saved")
        if r.get("normals"):
            print(f"  {r['file']:26} {r['normals']:,} normals recomputed")
        if r.get("opaque"):
            print(f"  {r['file']:26} {r['opaque']} material(s) made solid")
        for im in r["images"]:
            if im["used"] is None:
                print(f"  {r['file']:26} {im['size'][0]}x{im['size'][1]} {im['role']:10} left alone")
                continue
            print(f"  {r['file']:26} {im['size'][0]}x{im['size'][1]} {im['role']:10} "
                  f"used {im['used']:.2f} padded {im['filled']:,} despeckled {im['specks']:,}"
                  + ("" if check else " (written)" if r.get("written") else ""))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
