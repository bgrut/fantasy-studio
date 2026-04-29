#!/usr/bin/env python3
"""
tools/launch_ready_cli.py
=========================
V1.2.5 Part B — bulk-flip ``launch_ready`` flags on library entries.

Safety:
  - Backs up library.json to ``.bak_cli`` before every modification.
  - Preserves the ``manual_rejected`` sticky flag (rejected assets stay
    rejected even if re-scanned by the healer).
  - Works with the v2 library schema (``{"assets": [...]}``).

Examples:
    python tools/launch_ready_cli.py status
    python tools/launch_ready_cli.py approve --ids lib_cat_1 lib_cat_2
    python tools/launch_ready_cli.py approve --category environment --shape 3d_terrain
    python tools/launch_ready_cli.py approve --from-clipboard
    python tools/launch_ready_cli.py approve --provisional-only --category environment
    python tools/launch_ready_cli.py reject --ids lib_broken_car
    python tools/launch_ready_cli.py revert --ids lib_x

Filter flags combine (AND) except --ids, which is additive (OR).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "app" / "data" / "library.json"
BACKUP_PATH = ROOT / "app" / "data" / "library.json.bak_cli"


def _load_library() -> tuple[object, list[dict], bool]:
    raw = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "assets" in raw:
        return raw, raw["assets"], True
    if isinstance(raw, list):
        return raw, raw, False
    raise RuntimeError(f"unexpected library shape: {type(raw)}")


def _save(raw) -> None:
    if LIBRARY_PATH.exists():
        shutil.copy2(LIBRARY_PATH, BACKUP_PATH)
    LIBRARY_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")


# ── commands ───────────────────────────────────────────────────────────────

def cmd_status() -> None:
    _, assets, _ = _load_library()
    by_status = {"launch_ready": 0, "provisional": 0, "failed": 0, "rejected": 0}
    by_category: dict[str, dict] = {}
    for e in assets:
        if not isinstance(e, dict):
            continue
        if e.get("manual_rejected"):
            by_status["rejected"] += 1
        elif e.get("launch_ready"):
            by_status["launch_ready"] += 1
        elif e.get("provisional_ready"):
            by_status["provisional"] += 1
        else:
            by_status["failed"] += 1
        cat = e.get("category") or "none"
        bc = by_category.setdefault(cat, {"launch_ready": 0, "provisional": 0, "total": 0})
        bc["total"] += 1
        if e.get("launch_ready"):
            bc["launch_ready"] += 1
        if e.get("provisional_ready") and not e.get("launch_ready"):
            bc["provisional"] += 1

    print(f"Total entries: {len(assets)}")
    print(f"  launch_ready:        {by_status['launch_ready']}")
    print(f"  provisional (only):  {by_status['provisional']}")
    print(f"  manual_rejected:     {by_status['rejected']}")
    print(f"  failed:              {by_status['failed']}")
    print()
    print("By category (launch_ready / provisional / total):")
    for cat, stats in sorted(by_category.items()):
        print(
            f"  {cat:<14} {stats['launch_ready']:>3} / "
            f"{stats['provisional']:>3} / {stats['total']:<3}"
        )


def cmd_approve(args: list[str]) -> None:
    raw, assets, _ = _load_library()
    target_ids = _resolve_ids(args, assets)
    if not target_ids:
        print("[LAUNCH_READY] no matching ids — nothing to do")
        return
    changed = 0
    for e in assets:
        if not isinstance(e, dict):
            continue
        if e.get("id") in target_ids:
            if not e.get("launch_ready"):
                e["launch_ready"] = True
                # Clearing a previous rejection is explicit behaviour
                if e.get("manual_rejected"):
                    e.pop("manual_rejected", None)
                changed += 1
    _save(raw)
    print(f"[LAUNCH_READY] approved {changed} asset(s) (of {len(target_ids)} matched)")


def cmd_reject(args: list[str]) -> None:
    raw, assets, _ = _load_library()
    target_ids = _resolve_ids(args, assets)
    if not target_ids:
        print("[LAUNCH_READY] no matching ids — nothing to do")
        return
    changed = 0
    for e in assets:
        if not isinstance(e, dict):
            continue
        if e.get("id") in target_ids:
            if e.get("launch_ready") or not e.get("manual_rejected"):
                e["launch_ready"] = False
                e["manual_rejected"] = True
                changed += 1
    _save(raw)
    print(f"[LAUNCH_READY] rejected {changed} asset(s) (of {len(target_ids)} matched)")


def cmd_revert(args: list[str]) -> None:
    raw, assets, _ = _load_library()
    target_ids = _resolve_ids(args, assets)
    if not target_ids:
        print("[LAUNCH_READY] no matching ids — nothing to do")
        return
    changed = 0
    for e in assets:
        if not isinstance(e, dict):
            continue
        if e.get("id") in target_ids:
            if e.get("launch_ready") or e.get("manual_rejected"):
                e["launch_ready"] = False
                e.pop("manual_rejected", None)
                changed += 1
    _save(raw)
    print(f"[LAUNCH_READY] reverted {changed} asset(s) (of {len(target_ids)} matched)")


# ── id-resolver ─────────────────────────────────────────────────────────────

def _read_clipboard() -> str:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw"],
            timeout=10,
        )
        # Strip UTF-8 BOM if present, then decode defensively
        if out[:3] == b"\xef\xbb\xbf":
            out = out[3:]
        return out.decode("utf-8", errors="replace").strip()
    except Exception as e:
        print(f"[CLIPBOARD] read failed: {e}")
        return ""


def _resolve_ids(args: list[str], assets: list[dict]) -> set[str]:
    """Combine --ids / --from-clipboard (additive) with --category /
    --shape / --provisional-only (filter).  Always returns a set of ids
    present in the library."""
    explicit: set[str] = set()
    if "--ids" in args:
        idx = args.index("--ids")
        # Gather until next --flag
        for a in args[idx + 1:]:
            if a.startswith("--"):
                break
            explicit.add(a)
    if "--from-file" in args:
        idx = args.index("--from-file")
        if idx + 1 < len(args):
            fp = Path(args[idx + 1])
            if not fp.exists():
                print(f"[FILE] patch file not found: {fp}")
            else:
                raw = fp.read_text(encoding="utf-8-sig", errors="replace").strip()
                try:
                    data = json.loads(raw)
                    approved = data.get("approved") if isinstance(data, dict) else None
                    if isinstance(approved, list):
                        explicit.update(str(x) for x in approved)
                    elif isinstance(data, list):
                        explicit.update(str(x) for x in data)
                    else:
                        print("[FILE] JSON did not contain 'approved' list")
                except Exception as e:
                    print(f"[FILE] failed to parse {fp}: {e}")
    if "--from-clipboard" in args:
        clip = _read_clipboard()
        if clip:
            try:
                data = json.loads(clip)
                approved = data.get("approved") if isinstance(data, dict) else None
                if isinstance(approved, list):
                    explicit.update(str(x) for x in approved)
                elif isinstance(data, list):
                    explicit.update(str(x) for x in data)
                else:
                    print("[CLIPBOARD] JSON did not contain 'approved' list")
            except Exception as e:
                # Fallback: whitespace-separated ids
                toks = [t.strip() for t in clip.split() if t.strip()]
                if toks and all(not t.startswith("{") for t in toks):
                    explicit.update(toks)
                else:
                    print(f"[CLIPBOARD] failed to parse JSON: {e}")

    existing = {
        e["id"]
        for e in assets
        if isinstance(e, dict) and e.get("id")
    }
    candidates: set[str] | None = None
    if explicit:
        candidates = explicit & existing

    # Filters — AND-combine with whatever we have so far
    def _apply_filter(pred):
        nonlocal candidates
        filtered = {e["id"] for e in assets if isinstance(e, dict) and e.get("id") and pred(e)}
        candidates = filtered if candidates is None else (candidates & filtered)

    if "--category" in args:
        idx = args.index("--category")
        if idx + 1 < len(args):
            cat = args[idx + 1]
            _apply_filter(lambda e: e.get("category") == cat)
    if "--shape" in args:
        idx = args.index("--shape")
        if idx + 1 < len(args):
            shape = args[idx + 1]
            _apply_filter(lambda e: e.get("shape_class") == shape)
    if "--provisional-only" in args:
        _apply_filter(
            lambda e: e.get("provisional_ready") and not e.get("launch_ready")
        )

    return candidates or set()


# ── main ────────────────────────────────────────────────────────────────────

def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "status":
        cmd_status()
    elif cmd == "approve":
        cmd_approve(rest)
    elif cmd == "reject":
        cmd_reject(rest)
    elif cmd == "revert":
        cmd_revert(rest)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
