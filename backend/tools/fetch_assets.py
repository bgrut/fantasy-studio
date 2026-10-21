"""Fill a fresh checkout's 3D library from the release asset pack.

    python backend/tools/fetch_assets.py            # the newest assets-* release
    python backend/tools/fetch_assets.py --tag assets-2026-10-06

A clone of this repository does not download Git LFS objects (see
.lfsconfig): the models arrive as small pointer files, and this fetches the
real ones from a GitHub Release, which costs no LFS bandwidth (see
tools/assets_pack.py for why). Every file is checked against the sha256 its
pointer names; a file the pack does not have (a model committed after the
pack was made) is listed with the one command that fetches just that file
from LFS.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = "https://api.github.com/repos/bgrut/fantasy-studio/releases"
POINTER = b"version https://git-lfs.github.com/spec/v1"


def pointers() -> dict[str, str]:
    """{relative path: sha256} for every LFS pointer file in the working tree."""
    found = {}
    for pattern in ("backend/assets/library/*.glb", "backend/assets/mocap/mm/*.bin"):
        for p in REPO.glob(pattern):
            if p.stat().st_size > 400:
                continue
            head = p.read_bytes()
            if head.startswith(POINTER):
                for line in head.decode("utf-8", "replace").splitlines():
                    if line.startswith("oid sha256:"):
                        found[p.relative_to(REPO).as_posix()] = line.split(":", 1)[1].strip()
    return found


def release(tag: str | None) -> dict:
    with urllib.request.urlopen(API + ("/tags/" + tag if tag else "?per_page=50"), timeout=30) as r:
        data = json.loads(r.read())
    if tag:
        return data
    packs = [rel for rel in data if str(rel.get("tag_name", "")).startswith("assets-")]
    if not packs:
        raise SystemExit("no assets-* release found")
    return sorted(packs, key=lambda rel: rel["published_at"])[-1]


def overrides(rel: dict) -> dict[str, str]:
    """{path: sha256} for the files the pack ships in place of the committed version
    (2026-10-21: made after the repository's LFS budget was spent; see assets_pack.py)"""
    js = next((a for a in rel["assets"] if a["name"].endswith(".json")), None)
    if not js:
        return {}
    with urllib.request.urlopen(js["browser_download_url"], timeout=60) as r:
        man = json.loads(r.read())
    return {f["path"]: f["sha256"] for f in man.get("files", []) if f.get("override")}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


def main(argv: list[str]) -> int:
    want = pointers()
    rel = release(argv[argv.index("--tag") + 1] if "--tag" in argv else None)
    over = overrides(rel)
    stale = {p: s for p, s in over.items() if _sha(REPO / p) != s}
    if not want and not stale:
        print("every model is already here; nothing to fetch")
        return 0
    asset = next(a for a in rel["assets"] if a["name"].endswith(".zip"))
    print(f"{len(want) + len([p for p in stale if p not in want])} models to fetch from {rel['tag_name']} ({asset['size'] / 1e9:.2f} GB) ...")
    buf = io.BytesIO()
    with urllib.request.urlopen(asset["browser_download_url"], timeout=120) as r:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            buf.write(chunk)
    got, missing = 0, []
    with zipfile.ZipFile(buf) as z:
        names = set(z.namelist())
        # the pack's newer models first: written over the committed version and kept out
        # of git's way (skip-worktree), so the checkout reads clean
        newer = []
        for path, sha in stale.items():
            if path not in names:
                continue
            data = z.read(path)
            if hashlib.sha256(data).hexdigest() != sha:
                print(f"  {path}: the pack's copy does not match its manifest; skipped")
                continue
            (REPO / path).write_bytes(data)
            newer.append(path)
        for path, oid in want.items():
            if path in over:
                continue                      # an override stands in for this pointer
            if path not in names:
                missing.append(path)
                continue
            data = z.read(path)
            if hashlib.sha256(data).hexdigest() != oid:
                missing.append(path)          # the pack has an older version of this file
                continue
            (REPO / path).write_bytes(data)
            got += 1
    print(f"fetched {got} models" + (f", and {len(newer)} newer than the repository's" if newer else ""))
    import subprocess as _sp
    for p in newer:
        _sp.run(["git", "update-index", "--skip-worktree", "--", p], cwd=REPO, capture_output=True)
    # the index still holds the pointer files' stat data, so git lists every
    # fetched model as modified; adding them stores the identical pointer
    # (the LFS clean filter) and the checkout reads clean again
    done = [p for p in want if p not in missing and p not in over]
    import subprocess
    for i in range(0, len(done), 40):
        subprocess.run(["git", "add", "--", *done[i:i + 40]], cwd=REPO, capture_output=True)
    if missing:
        print(f"{len(missing)} not in this pack (newer than it); fetch just those from LFS with:")
        print('  git lfs pull --include="' + ",".join(missing) + '"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
