"""Package the flagship demo as one download.

    python backend/tools/flagship_pack.py                 # the demo, zipped
    python backend/tools/flagship_pack.py --out C:/itch   # somewhere else than dist/
    python backend/tools/flagship_pack.py --desktop       # and the desktop game, one .exe

--desktop (2026-09-29) is the Steam path: the same files are staged in
dist/crystal-works/ and built into flagship-desktop/ (Tauri 2, the studio
shell's crates and CLI), which embeds them in one executable,
dist/crystal-works-desktop/CrystalWorks.exe. It needs the Rust toolchain and
the WebView2 runtime (part of Windows 11; Steam can install it on Windows 10).

Rebuilds the demo from the runtime first (flagship_build.py), writes
flagship/LICENSES.md, and zips flagship/ as
<out>/crystal-works-<date>.zip with a single top-level folder, so what a
stranger unzips is a folder they can serve or drop on itch.io. Dev files
(the grid unit test, the roadmap) stay out. Prints the file count and size.
"""
import argparse
import datetime
import pathlib
import shutil
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

No cloud services were used to build this demo. No third party holds rights
over its content. You may sell it, publish it, or modify it freely.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"), help="where the zip goes (default: dist/, not tracked)")
    ap.add_argument("--desktop", action="store_true", help="also build the desktop game (flagship-desktop, Tauri)")
    ap.add_argument("--steam", action="store_true",
                    help="build the Steam variant instead: the Steamworks client in, steam_api64.dll beside it (dist/crystal-works-steam)")
    ap.add_argument("--app-id", type=int, default=480,
                    help="the Steam app id written to steam_appid.txt for runs outside Steam (480 is Valve's test app)")
    args = ap.parse_args()

    build = [sys.executable, str(ROOT / "backend" / "tools" / "flagship_build.py")]
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
    print(f"packed {n} files into {zpath.relative_to(ROOT) if zpath.is_relative_to(ROOT) else zpath}  ({mb:.1f} MB)  (one game)")
    print("unzip, then: cd crystal-works && python -m http.server 8123  ->  http://127.0.0.1:8123/")
    if args.desktop or args.steam:
        return desktop(n, steam=args.steam, app_id=args.app_id)
    return 0


def desktop(n_files: int, steam: bool = False, app_id: int = 480) -> int:
    """Stage the pack as a folder and build it into one executable."""
    stage = ROOT / "dist" / "crystal-works"
    if stage.exists():
        shutil.rmtree(stage)
    for p in sorted(OUT.rglob("*")):
        if not p.is_file() or p.name in SKIP:
            continue
        dst = stage / p.relative_to(OUT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
    cli = ROOT / "desktop" / "node_modules" / "@tauri-apps" / "cli" / "tauri.js"
    if not cli.exists():
        print("the Tauri CLI is not installed: run npm install in desktop/ first")
        return 1
    print(f"staged {n_files} files in dist/crystal-works; building the desktop game (a first build takes several minutes)")
    cmd = ["node", str(cli), "build"] + (["--features", "steam"] if steam else [])
    r = subprocess.run(cmd, cwd=str(ROOT / "flagship-desktop"))
    if r.returncode != 0:
        return r.returncode
    rel = ROOT / "flagship-desktop" / "src-tauri" / "target" / "release"
    exe = rel / "CrystalWorks.exe"
    if not exe.exists():
        print("the build finished but CrystalWorks.exe is not where it should be")
        return 1
    out = ROOT / "dist" / ("crystal-works-steam" if steam else "crystal-works-desktop")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, out / exe.name)
    shell = "| Desktop shell (Tauri 2, WebView2) | MIT / Apache-2.0 |"
    if steam:
        shell += ("\n| Steamworks bindings (steamworks-rs) | MIT / Apache-2.0 |"
                  "\n| steam_api64.dll | Valve's Steamworks SDK redistributable, shipped under the Steamworks SDK Access Agreement with a game released on Steam |")
    (out / "LICENSES.md").write_text(MANIFEST.replace("| Game code and runtime", shell + "\n| Game code and runtime"), encoding="utf-8")
    if steam:
        # the Steam build links Valve's DLL, which has to sit beside the game
        dll = rel / "steam_api64.dll"
        if not dll.exists():
            reg = pathlib.Path.home() / ".cargo" / "registry" / "src"
            dll = next(reg.glob("*/steamworks-sys-*/lib/steam/redistributable_bin/win64/steam_api64.dll"), dll)
        if not dll.exists():
            print("the Steam build needs steam_api64.dll beside it and it was not found")
            return 1
        shutil.copy2(dll, out / "steam_api64.dll")
        # run by hand, the client reads its app from here; launched by Steam it
        # is told, and this file is not needed in the depot
        (out / "steam_appid.txt").write_text(str(int(app_id)), encoding="ascii")
        print(f"steam build: app {app_id} in steam_appid.txt"
              + (" (480 is Valve's Spacewar test app: pass --app-id with yours)" if int(app_id) == 480 else ""))
    print(f"desktop game: {(out / exe.name).relative_to(ROOT)}  ({(out / exe.name).stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
