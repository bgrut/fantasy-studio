"""Package the flagship demo as one download.

    python backend/tools/flagship_pack.py                 # the demo, zipped
    python backend/tools/flagship_pack.py --adv 7         # ...with the race beside it (job 7's build)
    python backend/tools/flagship_pack.py --out C:/itch   # somewhere else than dist/

Rebuilds the demo from the runtime first (flagship_build.py, with --adv when
given), writes flagship/LICENSES.md, and zips flagship/ as
<out>/crystal-works-<date>.zip with a single top-level folder, so what a
stranger unzips is a folder they can serve or drop on itch.io. Dev files
(the grid unit test, the roadmap) stay out. Prints the file count and size.
"""
import argparse
import datetime
import pathlib
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "flagship"
SKIP = {"cubegrid.test.mjs", "ROADMAP.md", ".gitignore", "_shot.png", "audit_fixes.json"}

MANIFEST = """# Crystal Works: License Manifest

This demo was built with Fantasy Studio. Everything in this folder is yours:
the runtime is open source and every asset in it is drawn by the runtime
itself or dedicated to the public domain.

| Component | License |
|---|---|
| Game code and runtime (three.js) | MIT (vendor/three.LICENSE) |
| N8AO ambient occlusion | CC0 (vendor/n8ao.LICENSE) |
| Bricolage Grotesque, Instrument Sans, DM Mono | SIL Open Font License 1.1 (vendor/fonts/OFL-*.txt) |
| Machines, plating, sky, sounds | Drawn and synthesised by the runtime at load; no assets shipped |
| The race beside the demo (drift/, when present) | Its own LICENSES.md inside that folder |

No cloud services were used to build this demo. No third party holds rights
over its content. You may sell it, publish it, or modify it freely.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adv", type=int, default=None, help="ship job N's adventure build beside the demo")
    ap.add_argument("--out", default=str(ROOT / "dist"), help="where the zip goes (default: dist/, not tracked)")
    args = ap.parse_args()

    build = [sys.executable, str(ROOT / "backend" / "tools" / "flagship_build.py")]
    if args.adv is not None:
        build += ["--adv", str(args.adv)]
    r = subprocess.run(build, cwd=str(ROOT))
    if r.returncode != 0:
        return r.returncode
    (OUT / "LICENSES.md").write_text(MANIFEST, encoding="utf-8")

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().strftime("%Y%m%d")
    zpath = out_dir / f"crystal-works-{stamp}.zip"
    n = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(OUT.rglob("*")):
            if not p.is_file() or p.name in SKIP:
                continue
            z.write(p, "crystal-works/" + p.relative_to(OUT).as_posix())
            n += 1
    mb = zpath.stat().st_size / 1_000_000
    race = (OUT / "drift" / "index.html").exists()
    print(f"packed {n} files into {zpath.relative_to(ROOT) if zpath.is_relative_to(ROOT) else zpath}  ({mb:.1f} MB)"
          + ("  with the race beside the demo" if race else "  (factories only: no flagship/drift)"))
    print("unzip, then: cd crystal-works && python -m http.server 8123  ->  http://127.0.0.1:8123/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
