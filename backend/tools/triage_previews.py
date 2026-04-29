#!/usr/bin/env python3
"""
tools/triage_previews.py
========================
V1.2.5 Part A — bulk thumbnail preview generator.

Renders a 256×256 Eevee thumbnail of every library asset (or a filtered
subset) in one Blender subprocess, applying any healed orientation fix.
Writes a browsable gallery to ``outputs/triage_index.html`` with
approve/reject buttons — clicks are mirrored to the clipboard as a JSON
patch for ``tools/launch_ready_cli.py --from-clipboard``.

Usage:
    python tools/triage_previews.py                       # orientation_fixed (default)
    python tools/triage_previews.py all
    python tools/triage_previews.py orientation_fixed
    python tools/triage_previews.py missing_thumb
    python tools/triage_previews.py category:character
    python tools/triage_previews.py shape:flat_map
    python tools/triage_previews.py provisional_ready
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = ROOT / "app" / "data" / "library.json"
THUMBS_DIR = ROOT / "assets" / "thumbnails"
OUTPUT_DIR = ROOT / "outputs"
TRIAGE_SCRIPT = Path(__file__).parent / "_triage_blender_worker.py"
INDEX_PATH = OUTPUT_DIR / "triage_index.html"
JOB_FILE = OUTPUT_DIR / "triage_jobs.json"


def _resolve_blender_exe() -> str:
    for c in (
        r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",
    ):
        if Path(c).exists():
            return c
    return r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"


BLENDER_EXE = _resolve_blender_exe()


def _load_library() -> list[dict]:
    data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "assets" in data:
        return data["assets"]
    return data if isinstance(data, list) else []


def filter_entries(library: list[dict], mode: str) -> list[dict]:
    if mode == "all":
        return library
    if mode == "orientation_fixed":
        return [e for e in library if e.get("orientation_issue")]
    if mode == "missing_thumb":
        return [
            e for e in library
            if not (THUMBS_DIR / f"{e.get('id')}.png").exists()
        ]
    if mode == "provisional_ready":
        return [
            e for e in library
            if e.get("provisional_ready") and not e.get("launch_ready")
        ]
    if mode.startswith("category:"):
        cat = mode.split(":", 1)[1]
        return [e for e in library if e.get("category") == cat]
    if mode.startswith("shape:"):
        shape = mode.split(":", 1)[1]
        return [e for e in library if e.get("shape_class") == shape]
    return library


def _resolve_abs(entry_path: str) -> str:
    """Resolve a library path to an absolute path."""
    p = Path(entry_path or "")
    if p.is_absolute():
        return str(p)
    return str(ROOT / entry_path)


def _write_index(entries: list[dict], path: Path, mode: str) -> None:
    rows: list[str] = []
    for e in entries:
        eid = str(e.get("id") or "")
        thumb = THUMBS_DIR / f"{eid}.png"
        thumb_rel = f"../assets/thumbnails/{eid}.png" if thumb.exists() else ""
        issue = e.get("orientation_issue") or ""
        if e.get("launch_ready"):
            status = "✓ launch_ready"
            status_cls = "ok"
        elif e.get("provisional_ready"):
            status = "◦ provisional"
            status_cls = "prov"
        else:
            status = "✗ failed"
            status_cls = "bad"

        shape = e.get("shape_class") or "?"
        cat = e.get("category") or "?"
        subject = e.get("subject") or ""
        issue_html = (
            f'<div class="issue">⚠ {issue}</div>' if issue else ""
        )
        img_html = (
            f'<img src="{thumb_rel}" alt="{eid}" />'
            if thumb_rel
            else '<div class="noimg">(no preview)</div>'
        )
        rows.append(
            f"""<div class="card" data-id="{eid}">
  {img_html}
  <div class="meta">
    <div class="id">{eid}</div>
    <div class="tags">{cat} · {shape}{f' · {subject}' if subject else ''}</div>
    {issue_html}
    <div class="status {status_cls}">{status}</div>
    <div class="actions">
      <button class="approve" onclick="approve('{eid}')">Approve</button>
      <button class="reject" onclick="reject('{eid}')">Reject</button>
    </div>
  </div>
</div>"""
        )

    html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Asset Triage — MODE_PLACEHOLDER</title>
<style>
body { background: #0f0f0f; color: #eee; font-family: sans-serif; padding: 20px; }
h1 { color: #fff; margin: 0 0 8px 0; }
p.info { color: #888; margin: 0 0 16px 0; }
.toolbar { position: sticky; top: 0; background: #0f0f0fdd; padding: 8px 0; z-index: 10; border-bottom: 1px solid #222; }
.toolbar button { margin-right: 8px; padding: 6px 14px; background: #2a2a2a; border: 1px solid #444; color: #eee; cursor: pointer; font-size: 12px; }
.toolbar button:hover { background: #3a3a3a; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-top: 16px; }
.card { background: #1a1a1a; border: 1px solid #333; border-radius: 8px; overflow: hidden; }
.card img { width: 100%; height: 220px; object-fit: contain; background: #111; display: block; }
.card .noimg { height: 220px; display: flex; align-items: center; justify-content: center; color: #555; background: #111; }
.meta { padding: 10px; }
.id { font-family: monospace; font-size: 11px; color: #aaa; word-break: break-all; }
.tags { color: #888; font-size: 12px; margin-top: 4px; }
.issue { color: #ff9; font-size: 12px; margin-top: 4px; }
.status { font-size: 12px; margin-top: 4px; }
.status.ok { color: #6f6; }
.status.prov { color: #aaf; }
.status.bad { color: #f66; }
.actions { margin-top: 8px; }
button { margin-right: 6px; padding: 4px 10px; background: #2a2a2a; border: 1px solid #444; color: #eee; cursor: pointer; border-radius: 4px; }
button.approve:hover { background: #2f4f2f; }
button.reject:hover { background: #4f2f2f; }
.counter { color: #9f9; margin-left: 12px; font-size: 12px; }
</style></head>
<body>
<h1>Asset Triage — MODE_PLACEHOLDER</h1>
<p class="info">COUNT_PLACEHOLDER assets. Click approve / reject on each card, then hit <b>Download patch</b> and feed the file to <code>launch_ready_cli.py --from-file</code>.</p>
<div class="toolbar">
  <button onclick="downloadPatch()">💾 Download patch (triage_patch.json)</button>
  <button onclick="copyPatch()" title="May be silently blocked by Chrome on file:// pages">📋 Copy patch (best-effort)</button>
  <button onclick="clearAll()">Clear all selections</button>
  <span class="counter" id="counter">0 approved · 0 rejected</span>
</div>
<details style="margin-top:8px;color:#888;">
  <summary style="cursor:pointer;">Live patch JSON (paste into a file if you prefer)</summary>
  <textarea id="patchDump" readonly style="width:100%;height:140px;background:#111;color:#9f9;font-family:monospace;font-size:11px;border:1px solid #333;border-radius:4px;padding:8px;margin-top:8px;"></textarea>
</details>
<div class="grid">
ROWS_PLACEHOLDER
</div>
<script>
const approved = new Set();
const rejected = new Set();
function patchObj() {
  return { approved: [...approved], rejected: [...rejected] };
}
function patchJSON() {
  return JSON.stringify(patchObj(), null, 2);
}
function updateCounter() {
  document.getElementById('counter').textContent =
    approved.size + ' approved · ' + rejected.size + ' rejected';
  const ta = document.getElementById('patchDump');
  if (ta) ta.value = patchJSON();
}
function copyPatch() {
  // Chrome blocks navigator.clipboard on file:// URLs; try execCommand too.
  const json = patchJSON();
  try { navigator.clipboard.writeText(json); } catch (e) {}
  try {
    const ta = document.getElementById('patchDump');
    if (ta) { ta.focus(); ta.select(); document.execCommand('copy'); }
  } catch (e) {}
}
function downloadPatch() {
  const blob = new Blob([patchJSON()], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'triage_patch.json';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function approve(id) {
  approved.add(id); rejected.delete(id);
  const c = document.querySelector('[data-id="' + id + '"]');
  if (c) c.style.border = '2px solid #6f6';
  updateCounter();
}
function reject(id) {
  rejected.add(id); approved.delete(id);
  const c = document.querySelector('[data-id="' + id + '"]');
  if (c) c.style.border = '2px solid #f66';
  updateCounter();
}
function clearAll() {
  approved.clear(); rejected.clear();
  document.querySelectorAll('.card').forEach(c => c.style.border = '1px solid #333');
  updateCounter();
}
updateCounter();
</script>
</body></html>
"""
    html = (
        html
        .replace("MODE_PLACEHOLDER", mode)
        .replace("COUNT_PLACEHOLDER", str(len(entries)))
        .replace("ROWS_PLACEHOLDER", "\n".join(rows))
    )
    path.write_text(html, encoding="utf-8")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "orientation_fixed"
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    library = _load_library()
    entries = filter_entries(library, mode)
    if not entries:
        print(f"[TRIAGE] no entries match mode={mode!r}")
        return 0
    print(f"[TRIAGE] generating previews for {len(entries)} assets (mode={mode})", flush=True)

    # Project absolute paths into job payload so the worker doesn't have
    # to recompute relative resolution.
    job_entries: list[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        p = e.get("path") or ""
        abs_p = _resolve_abs(str(p))
        job_entries.append({
            "id": e.get("id"),
            "path": abs_p,
            "orientation_fix_rotation_euler": e.get("orientation_fix_rotation_euler"),
            "ground_offset_z": e.get("ground_offset_z"),
            "category": e.get("category"),
        })

    JOB_FILE.write_text(json.dumps(job_entries), encoding="utf-8")

    if not Path(BLENDER_EXE).exists():
        print(f"[TRIAGE] blender executable not found: {BLENDER_EXE}")
        return 1
    if not TRIAGE_SCRIPT.exists():
        print(f"[TRIAGE] worker script missing: {TRIAGE_SCRIPT}")
        return 1

    # Single Blender instance loops through the list
    result = subprocess.run(
        [
            BLENDER_EXE,
            "-b",
            "--factory-startup",
            "--python", str(TRIAGE_SCRIPT),
            "--",
            str(JOB_FILE),
            str(THUMBS_DIR),
        ],
        capture_output=False,  # stream to console so user sees progress
    )
    if result.returncode != 0:
        print(f"[TRIAGE] blender worker exited rc={result.returncode}")
        # Still write the index so user can see whatever was rendered

    _write_index(entries, INDEX_PATH, mode)
    print(f"[TRIAGE] index: file:///{INDEX_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
