"""Third-party notices for a Rust build (2026-09-30).

    python backend/tools/rust_notices.py <crate dir with Cargo.toml> <out.md> [--features steam]

The desktop game's executable contains the Rust crates Tauri is built from:
MIT, Apache-2.0, MPL-2.0 and Unicode-3.0 licensed, each asking for its notice
to travel with the binary. This lists every crate actually compiled for
Windows (cargo metadata, filtered to the target; local, no download) with its
licence, followed by the licence and notice files each crate ships, identical
texts printed once.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TARGET = "x86_64-pc-windows-msvc"


def main() -> int:
    crate = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2])
    feats = []
    if "--features" in sys.argv:
        feats = ["--features", sys.argv[sys.argv.index("--features") + 1]]
    meta = json.loads(subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--offline", "--filter-platform", TARGET] + feats,
        cwd=str(crate), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout)
    root = meta["resolve"]["root"]
    used = {n["id"] for n in meta["resolve"]["nodes"]}
    pkgs = sorted((p for p in meta["packages"] if p["id"] in used and p["id"] != root),
                  key=lambda p: (p["name"], p["version"]))
    lines = ["# Third-party notices", "",
             "This program is built from the open-source Rust crates below. Each is listed with its",
             "licence; the licence and notice texts they ship follow, identical texts printed once.",
             "The MPL-2.0 crates are used unmodified; their source is the published crate at",
             "crates.io under the name and version listed.",
             "", "| Crate | Version | Licence |", "|---|---|---|"]
    texts: dict[str, list[str]] = {}
    for p in pkgs:
        lines.append(f"| {p['name']} | {p['version']} | {p.get('license') or p.get('license_file') or 'see files'} |")
        d = Path(p["manifest_path"]).parent
        for f in sorted(d.iterdir()):
            n = f.name.upper()
            if f.is_file() and (n.startswith("LICENSE") or n.startswith("LICENCE") or n.startswith("COPYING")
                                or n.startswith("NOTICE") or n.startswith("COPYRIGHT")):
                try:
                    t = f.read_text(encoding="utf-8", errors="replace").strip()
                except Exception:
                    continue
                texts.setdefault(t, []).append(f"{p['name']} {p['version']} ({f.name})")
    lines += ["", "## Licence and notice texts", ""]
    for t, who in texts.items():
        lines += ["### " + ", ".join(who[:12]) + (f" and {len(who) - 12} more" if len(who) > 12 else ""),
                  "", "```", t, "```", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"notices: {len(pkgs)} crates, {len(texts)} distinct texts -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
