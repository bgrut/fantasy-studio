"""Put the current runtime into a build that already exists.

    python backend/tools/respin.py 213            # job_213's game.js, from today's runtime
    python backend/tools/respin.py 213 214 215

A change to the runtime template reaches a game only when the game is built
again, and a build re-runs the planner, the casting and any generation first:
minutes, for a change that is pure JavaScript. This does the one step that
matters: it reads the spec the build already carries out of its game.js and
writes game.js again from the template on disk, exactly as the exporter does.
Nothing else in the build is touched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
RUNTIME = BACKEND / "app" / "game_export" / "runtime"
JOBS = BACKEND / "renders" / "game_jobs"


def embedded_spec(js: str) -> dict:
    """The spec the exporter wrote in place of __GAME_SPEC__."""
    for marker in ("const SPEC = ", "  return "):
        for line in js.splitlines():
            if line.startswith(marker) and line.rstrip().endswith(";") and line.lstrip(" ").startswith(marker.strip() + " {"):
                return json.loads(line.strip()[len(marker.strip()) + 1:-1])
    raise ValueError("no embedded spec found")


def respin(job: str) -> str:
    dist = JOBS / ("job_%s" % job) / "dist"
    game = dist / "game.js"
    if not game.exists():
        return "job %s: no game.js" % job
    js = game.read_text(encoding="utf-8")
    spec = embedded_spec(js)
    factory = spec.get("genre") == "factory"
    tpl = "factory.js.tpl" if factory else "main.js.tpl"
    out = (RUNTIME / tpl).read_text(encoding="utf-8").replace("__GAME_SPEC__", json.dumps(spec))
    game.write_text(out, encoding="utf-8")
    # the page too: the build bar and the HUD live in the page template
    page = "factory.index.html.tpl" if factory else "index.html.tpl"
    (dist / "index.html").write_text(
        (RUNTIME / page).read_text(encoding="utf-8").replace("__TITLE__", spec.get("title") or ""),
        encoding="utf-8")
    # and the procedural modules the runtime imports (2026-10-08): a respun game
    # imported gait.js's new makePlanter from the build's old copy and died at load
    import shutil
    if (dist / "proc").is_dir():
        for f in (RUNTIME / "proc").glob("*.js"):
            shutil.copy2(f, dist / "proc" / f.name)
    return "job %s: game.js, index.html and proc/ rewritten from %s (%d bytes)" % (job, tpl, len(out))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    bad = 0
    for j in argv:
        try:
            print(respin(j))
        except Exception as exc:
            bad += 1
            print("job %s: %s: %s" % (j, type(exc).__name__, exc))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
