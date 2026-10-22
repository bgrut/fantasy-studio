"""Build a Fantasy Studio release's files (2026-10-22).

    python backend/tools/package_release.py 1.3.0            # builds into dist/release-1.3.0/
    python backend/tools/package_release.py 1.3.0 --no-ui    # reuse frontend/dist as it is

Makes, for the version given:
  fantasy-studio-engine-v<ver>.zip   the backend as committed at HEAD (3D models as
                                     their small LFS pointer files; the installed app's
                                     setup fills them from the asset pack) plus the
                                     freshly built frontend (frontend/dist)
  FantasyStudio-Setup-<ver>.exe      the desktop installer (desktop/, tauri build)
  <each>.sha256                      the hash the installer's setup checks downloads against
  SHA256SUMS.txt                     every file's hash in one list, for people to verify

The desktop app's first-run setup (desktop/installer/engine-setup.ps1) downloads the
engine zip from the GitHub release v<ver> and checks it against its .sha256.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def sh(cmd: list[str], cwd: Path) -> None:
    print("  $", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True, shell=(sys.platform == "win32" and cmd[0] in ("npm", "npx")))


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    ver = argv[0].lstrip("v")
    out = REPO / "dist" / f"release-{ver}"
    out.mkdir(parents=True, exist_ok=True)

    # the desktop app must say the same version, or its setup fetches another engine
    conf = json.loads((REPO / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    if conf.get("version") != ver:
        print(f"desktop/src-tauri/tauri.conf.json says {conf.get('version')}, not {ver}: bump it (and Cargo.toml) first")
        return 1

    # the engine is packed from HEAD: an uncommitted backend change would silently be left out
    # (tracked code that ships: the app, its scripts and tools, the requirements; not test fixtures)
    dirty = "\n".join(l for l in subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "backend/app", "backend/scripts", "backend/tools", "backend/requirements.txt"],
        cwd=REPO, capture_output=True, text=True).stdout.splitlines() if "/shotgate/" not in l and l.endswith((".py", ".txt", ".js", ".tpl", ".json", ".ps1")))
    if dirty and "--allow-dirty" not in argv:
        print("uncommitted backend changes would be left out of the engine; commit them first:\n" + dirty)
        return 1

    if "--no-ui" not in argv:
        sh(["npm", "run", "build"], REPO / "frontend")
    dist = REPO / "frontend" / "dist"
    if not (dist / "index.html").exists():
        print("frontend/dist has no index.html")
        return 1

    # the engine: the committed backend (git archive keeps LFS files as pointers) + the UI
    engine = out / f"fantasy-studio-engine-v{ver}.zip"
    arch = subprocess.run(["git", "archive", "--format=zip", "HEAD", "backend"], cwd=REPO, capture_output=True, check=True).stdout
    with zipfile.ZipFile(io.BytesIO(arch)) as src, zipfile.ZipFile(engine, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for info in src.infolist():
            if info.is_dir():
                continue
            z.writestr(info.filename, src.read(info))
        for f in dist.rglob("*"):
            if f.is_file():
                z.write(f, "frontend/dist/" + f.relative_to(dist).as_posix())
        z.writestr("VERSION", ver + "\n")
    print(f"  engine  {engine.name}  {engine.stat().st_size / 1e6:.1f} MB")

    # the installer
    if "--no-installer" not in argv:
        sh(["npx", "tauri", "build"], REPO / "desktop")
    built = REPO / "desktop" / "src-tauri" / "target" / "release" / "bundle" / "nsis" / f"Fantasy Studio_{ver}_x64-setup.exe"
    setup = out / f"FantasyStudio-Setup-{ver}.exe"
    if built.exists():
        shutil.copy2(built, setup)
        print(f"  setup   {setup.name}  {setup.stat().st_size / 1e6:.1f} MB")

    sums = []
    for f in sorted(out.iterdir()):
        if f.suffix in (".zip", ".exe"):
            h = sha(f)
            (out / (f.name + ".sha256")).write_text(f"{h}  {f.name}\n", encoding="utf-8")
            sums.append(f"{h}  {f.name}")
    (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"done: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
