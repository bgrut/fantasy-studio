"""Arc B slice: pull curated CC0 HDRIs from Poly Haven (2026-07-28).

Research finding: an HDRI environment map is the single highest visual-impact
action for scene realism (real captured light -> correct reflections + ambient
color on every PBR material). All Poly Haven content is CC0 — mirroring the
files is unconditionally safe; no attribution required (we credit them in the
README acknowledgments anyway).

Downloads one 2k .hdr per sky mood into assets/hdri/ (gitignored; run once
per install — bootstrap can call this). Exporter bundles the matching file
into each game's dist/hdri/.

Usage: python scripts/fetch_hdris.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "assets" / "hdri"

# mood -> Poly Haven asset id (curated: outdoor pure-sky captures that match
# the runtime's procedural sky so the background and IBL agree)
CURATED = {
    "day": "kloofendal_48d_partly_cloudy_puresky",
    "sunset": "kloppenheim_06_puresky",
    "night": "moonless_golf",
    "overcast": "kloofendal_overcast",
}


def fetch(mood: str, asset_id: str) -> bool:
    dest = OUT / f"{mood}.hdr"
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f"  {mood}: already present")
        return True
    # Poly Haven's CDN 403s the default urllib agent — identify ourselves
    ua = {"User-Agent": "FantasyStudio/1.1 (github.com/bgrut/fantasy-studio)"}
    try:
        req = urllib.request.Request(
            f"https://api.polyhaven.com/files/{asset_id}", headers=ua)
        with urllib.request.urlopen(req, timeout=30) as r:
            files = json.load(r)
        url = files["hdri"]["2k"]["hdr"]["url"]
        print(f"  {mood}: {asset_id} <- {url}")
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=ua), timeout=120) as r:
            dest.write_bytes(r.read())
        print(f"  {mood}: {dest.stat().st_size / 1e6:.1f} MB")
        return True
    except Exception as e:  # noqa: BLE001 — best-effort; runtime falls back
        print(f"  {mood}: FAILED ({e})")
        return False


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Fetching CC0 HDRIs from Poly Haven…")
    ok = sum(fetch(m, a) for m, a in CURATED.items())
    print(f"{ok}/{len(CURATED)} HDRIs ready in {OUT}")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
