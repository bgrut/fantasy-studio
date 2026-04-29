"""
credits_writer.py
=================
Attribution sidecar writer for renders.

Every render produces ``credits.txt`` + ``credits_short.txt`` alongside
the output MP4.  The credits list every library asset referenced by the
render (hero + HDRI + environment + props + textures), grouped by
license type, formatted to be pasted into YouTube/social-media
descriptions without further editing.

Design principle: credits are NEVER rendered into the video.  The MP4
stays clean.  Users who publish the video in public work are
responsible for copying the sidecar contents into their description.

Public API:
    register_used_asset(manifest, library_id, role=None) -> None
    write_credits_sidecar(manifest, output_dir) -> dict
    check_attribution_gate(manifest, tier) -> tuple[bool, list]  # True=OK to render
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_LIBRARY_PATH = _ROOT / "app" / "data" / "library.json"


# License ranking order — CC0 first (no attribution needed), then
# CC-BY (attribution required), then SA, then proprietary.
_LICENSE_ORDER = (
    "CC0", "Public Domain",
    "CC-BY-4.0", "CC-BY-3.0", "CC-BY",
    "CC-BY-SA-4.0", "CC-BY-SA-3.0", "CC-BY-SA",
    "CC-BY-NC-4.0", "CC-BY-NC",
    "MIT", "Apache-2.0",
    "proprietary", "unknown",
)


def register_used_asset(manifest: dict, library_id: str, role: str = "") -> None:
    """Add a library asset id to the render's used_assets list.

    Called by the render pipeline as each asset is imported.  Dedupes
    within a single render.  Non-fatal on failure.
    """
    if not manifest or not library_id:
        return
    try:
        used = manifest.setdefault("used_assets", [])
        # Dedup by id
        for u in used:
            if isinstance(u, dict) and u.get("id") == library_id:
                return
        used.append({
            "id":   library_id,
            "role": role or "asset",
        })
    except Exception as e:
        print(f"[CREDITS] register_used_asset failed: {e}", flush=True)


def _load_library() -> dict:
    try:
        if _LIBRARY_PATH.exists():
            return json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[CREDITS] library load failed: {e}", flush=True)
    return {"assets": []}


def _find_entry_by_id(library: dict, asset_id: str) -> dict | None:
    for a in library.get("assets", []):
        if isinstance(a, dict) and a.get("id") == asset_id:
            return a
    return None


def _find_entry_by_path(library: dict, path: str) -> dict | None:
    """Fallback when used_assets has a path but not an id (legacy callers)."""
    if not path:
        return None
    norm = str(path).replace("\\", "/").lower()
    for a in library.get("assets", []):
        if not isinstance(a, dict):
            continue
        ap = str(a.get("path", "")).replace("\\", "/").lower()
        if ap and (ap == norm or ap.endswith(norm) or norm.endswith(ap)):
            return a
    return None


def _license_sort_key(entry: dict) -> tuple:
    attr = entry.get("attribution") or {}
    lic = str(attr.get("license") or "unknown")
    try:
        rank = _LICENSE_ORDER.index(lic)
    except ValueError:
        rank = len(_LICENSE_ORDER)
    return (rank, (entry.get("subject") or "").lower())


def check_attribution_gate(manifest: dict, tier: str) -> tuple:
    """Return (allow_render, missing_list).

    Preview tier is permissive (always allow, warn in log).
    Cinematic tier blocks if any used asset has needs_attribution=True.
    """
    tier_lc = str(tier or "").lower()
    used = manifest.get("used_assets") or []
    if not used:
        return True, []

    library = _load_library()
    missing: list = []
    for u in used:
        if not isinstance(u, dict):
            continue
        entry = _find_entry_by_id(library, u.get("id", ""))
        if entry is None:
            entry = _find_entry_by_path(library, u.get("path", ""))
        if entry and entry.get("needs_attribution"):
            missing.append({
                "id":      entry.get("id"),
                "subject": entry.get("subject"),
                "path":    entry.get("path"),
            })

    if not missing:
        return True, []

    if tier_lc == "cinematic":
        print(
            f"[CREDITS] GATE BLOCKED for tier={tier_lc}: "
            f"{len(missing)} asset(s) missing attribution",
            flush=True,
        )
        for m in missing:
            print(f"[CREDITS]   - id={m.get('id')!r} subject={m.get('subject')!r}", flush=True)
        return False, missing

    print(
        f"[CREDITS] WARN tier={tier_lc}: {len(missing)} asset(s) missing attribution "
        f"(preview tier — permissive)",
        flush=True,
    )
    return True, missing


def _format_full_credits(manifest: dict, entries: list) -> str:
    lines: list = []
    title = (
        str(manifest.get("topic", "")).strip()
        or str(manifest.get("core_objective_prompt", "")).strip()
        or "Fantasy Studio render"
    )
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines.append(f"Fantasy Studio render — {title}")
    lines.append(f"Rendered: {ts}")
    lines.append("")
    lines.append("Assets used:")
    lines.append("")

    for entry in entries:
        attr = entry.get("attribution") or {}
        asset_title = (
            attr.get("title")
            or entry.get("subject")
            or entry.get("id")
            or "Untitled"
        )
        author = attr.get("author") or "Author unknown"
        lic = attr.get("license") or "unknown license"
        lic_url = attr.get("license_url") or ""
        source_url = attr.get("source_url") or ""

        lines.append(f"  • {asset_title}")
        if entry.get("needs_attribution"):
            lines.append(f"    Author unknown — {Path(str(entry.get('path', ''))).name}")
        else:
            lines.append(f"    by {author}")
        if lic_url:
            lines.append(f"    {lic} — {lic_url}")
        else:
            lines.append(f"    {lic}")
        if source_url:
            lines.append(f"    Source: {source_url}")
        lines.append("")

    lines.append("Made with Fantasy Studio")
    return "\n".join(lines) + "\n"


def _format_short_credits(entries: list) -> str:
    """Twitter/Instagram-friendly credits under 280 chars."""
    if not entries:
        return "Made with Fantasy Studio."

    authors: list = []
    licenses: set = set()
    for entry in entries:
        attr = entry.get("attribution") or {}
        if entry.get("needs_attribution"):
            continue
        a = attr.get("author")
        if a and a not in authors:
            authors.append(a)
        lic = attr.get("license")
        if lic:
            licenses.add(lic)

    if not authors:
        return "Made with Fantasy Studio."

    # Start building up — stop adding authors once we'd exceed budget
    base = f"Assets by {', '.join(authors[:4])}"
    if len(authors) > 4:
        base += f" + {len(authors) - 4} more"
    if licenses:
        lic_str = " / ".join(sorted(licenses)[:3])
        base += f" ({lic_str})"
    base += ". Made with Fantasy Studio."

    if len(base) > 280:
        base = (
            f"{len(entries)} assets credited — see full credits.txt file. "
            "Made with Fantasy Studio."
        )
    return base


def write_credits_sidecar(manifest: dict, output_dir) -> dict:
    """Write credits.txt + credits_short.txt alongside the MP4.

    Returns a summary dict with counts + paths.  Non-fatal on failure.
    """
    report = {
        "written":           False,
        "n_assets":          0,
        "n_missing":         0,
        "credits_path":      None,
        "credits_short_path": None,
    }
    try:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        used = manifest.get("used_assets") or []
        library = _load_library()

        entries: list = []
        seen_ids: set = set()
        for u in used:
            if not isinstance(u, dict):
                continue
            aid = u.get("id") or ""
            if aid in seen_ids:
                continue
            entry = _find_entry_by_id(library, aid)
            if entry is None:
                entry = _find_entry_by_path(library, u.get("path", ""))
            if entry is None:
                # Synthetic entry so something shows up in credits
                entry = {
                    "id":                aid or "unknown",
                    "subject":           u.get("subject") or "unknown",
                    "path":              u.get("path") or "",
                    "attribution":       {
                        "author":  None,
                        "license": None,
                    },
                    "needs_attribution": True,
                }
            entries.append(entry)
            seen_ids.add(aid or entry.get("id") or "?")

        # Sort by license rank (CC0 first → CC-BY → unknown last)
        entries.sort(key=_license_sort_key)

        missing_count = sum(1 for e in entries if e.get("needs_attribution"))

        full_text = _format_full_credits(manifest, entries)
        short_text = _format_short_credits(entries)

        credits_path = out / "credits.txt"
        credits_short_path = out / "credits_short.txt"
        credits_path.write_text(full_text, encoding="utf-8")
        credits_short_path.write_text(short_text, encoding="utf-8")

        report.update({
            "written":            True,
            "n_assets":           len(entries),
            "n_missing":          missing_count,
            "credits_path":       str(credits_path),
            "credits_short_path": str(credits_short_path),
        })
        print(
            f"[CREDITS] wrote credits.txt ({len(entries)} assets credited, "
            f"{missing_count} need attribution)",
            flush=True,
        )
    except Exception as e:
        print(f"[CREDITS] write_credits_sidecar failed: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
    return report
