"""Pack the repository's Git LFS files into one zip for a GitHub Release.

    python backend/tools/assets_pack.py                 # writes dist/assets pack + manifest
    python backend/tools/assets_pack.py --publish TAG   # ...and uploads them as release TAG
    python backend/tools/assets_pack.py --override a.glb,b.glb --publish TAG   # ...with these working-tree files in place of HEAD's

WHY (2026-10-06): the repository is public and its 3D library (~1 GB of
.glb models and the motion-matching database) lives in Git LFS. Every clone
by anyone pulls that gigabyte against the owner's LFS bandwidth (10 GB a
month free, then billed or, without a payment method, blocked until the
month turns over). Release downloads do not count against LFS bandwidth. So
the files are also published as a release asset, the repository's
.lfsconfig stops clones from fetching LFS objects, and tools/fetch_assets.py
fills a fresh checkout from the release instead.

The pack holds exactly the blobs HEAD points at (taken from the local LFS
store, so uncommitted edits in the working tree are not shipped), with a
manifest of path, sha256 and size that fetch_assets.py checks every file
against.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dist"


def lfs_files() -> list[tuple[str, str]]:
    """(sha256, path) for every LFS file HEAD tracks."""
    out = subprocess.run(["git", "lfs", "ls-files", "-l"], cwd=REPO, capture_output=True,
                         text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        oid, _mark, path = line.split(" ", 2)
        rows.append((oid, path.strip()))
    return rows


def blob(oid: str) -> Path:
    return REPO / ".git" / "lfs" / "objects" / oid[:2] / oid[2:4] / oid


def build(overrides: list[str] | None = None) -> tuple[Path, Path]:
    """overrides (2026-10-21): working-tree files packed in place of the version HEAD
    points at. The repository's LFS budget is spent, and GitHub refuses a push whose
    pointers name objects it does not hold, so a model made since then cannot be
    committed; it ships here instead, marked override, and fetch_assets.py installs it
    over the committed one."""
    OUT.mkdir(exist_ok=True)
    overrides = [o.replace("\\", "/") for o in (overrides or [])]
    rows = [r for r in lfs_files() if r[1] not in overrides]
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True,
                          text=True, check=True).stdout.strip()
    manifest = {"commit": head, "files": []}
    zpath = OUT / "fantasy-studio-assets.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for oid, path in rows:
            src = blob(oid)
            if not src.exists():
                raise SystemExit(f"missing LFS object for {path} ({oid}); run git lfs fetch first")
            data = src.read_bytes()
            if hashlib.sha256(data).hexdigest() != oid:
                raise SystemExit(f"LFS object for {path} does not match its oid")
            z.writestr(path, data)
            manifest["files"].append({"path": path, "sha256": oid, "size": len(data)})
        for path in overrides:
            data = (REPO / path).read_bytes()
            if data.startswith(b"version https://git-lfs"):
                raise SystemExit(f"{path} is a pointer file, not a model")
            z.writestr(path, data)
            manifest["files"].append({"path": path, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "override": True})
            rows.append(("override", path))
    mpath = OUT / "fantasy-studio-assets.json"
    mpath.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    total = sum(f["size"] for f in manifest["files"])
    print(f"packed {len(rows)} files, {total / 1e9:.2f} GB -> {zpath.name} ({zpath.stat().st_size / 1e9:.2f} GB) at {head}")
    return zpath, mpath


def publish(tag: str, zpath: Path, mpath: Path) -> None:
    notes = ("The 3D model library and motion database for Fantasy Studio, packed from Git LFS.\n\n"
             "A clone of this repository no longer downloads them from LFS; after cloning run\n"
             "`python backend/tools/fetch_assets.py` and it fills them in from this release.")
    subprocess.run(["gh", "release", "create", tag, str(zpath), str(mpath), "-R", "bgrut/fantasy-studio",
                    "--title", f"Asset pack {tag}", "--notes", notes, "--latest=false"],
                   cwd=REPO, check=True)
    print(f"published release {tag}")


if __name__ == "__main__":
    ov = sys.argv[sys.argv.index("--override") + 1].split(",") if "--override" in sys.argv else []
    z, m = build(ov)
    if "--publish" in sys.argv:
        publish(sys.argv[sys.argv.index("--publish") + 1], z, m)
