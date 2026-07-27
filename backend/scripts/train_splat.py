"""Tier 2 Gaussian-splat training: video -> splat world (2026-07-27).

Pipeline (all commercially safe):
  1. ffmpeg   — sample ~150 frames from the walkthrough video
  2. COLMAP   (BSD)     — solve camera poses (automatic_reconstructor, sparse)
  3. Brush    (Apache-2) — train 3D Gaussian Splatting on the posed frames,
                           export a .ply the game runtime loads directly

Tools live in backend/tools/{colmap,brush} (downloaded binaries, gitignored).
This intentionally avoids the INRIA reference trainer (non-commercial).

Usage: python train_splat.py <video> <out.ply> [--steps 8000] [--frames 150]
Prints stage markers (STAGE:frames / STAGE:poses / STAGE:train) so the API
job can surface progress, and TRAIN-SPLAT-OK <out> on success.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TOOLS = BACKEND / "tools"


def _find(tool_dir: str, exe: str) -> Path:
    hits = sorted((TOOLS / tool_dir).rglob(exe))
    if not hits:
        sys.exit(f"TRAIN-SPLAT-FAIL missing {exe} under backend/tools/{tool_dir} "
                 f"(re-run the tool download)")
    return hits[0]


def _run(cmd: list, **kw) -> None:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode != 0:
        sys.exit(f"TRAIN-SPLAT-FAIL exit {r.returncode}: {cmd[0]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--steps", type=int, default=8000)
    ap.add_argument("--frames", type=int, default=150)
    a = ap.parse_args()

    video = Path(a.video)
    out = Path(a.out)
    if not video.exists():
        sys.exit(f"TRAIN-SPLAT-FAIL video not found: {video}")

    ws = video.parent / (video.stem + "_ws")
    frames = ws / "images"
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)
    frames.mkdir(parents=True)

    # 1 — frames: sample evenly across the whole clip, longest edge 1600px
    print("STAGE:frames", flush=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    dur = float((probe.stdout or "30").strip() or 30)
    fps = max(0.5, min(4.0, a.frames / max(dur, 1.0)))
    _run(["ffmpeg", "-y", "-v", "error", "-i", video,
          "-vf", f"fps={fps:.3f},scale='if(gt(iw,ih),1600,-2)':'if(gt(iw,ih),-2,1600)'",
          "-q:v", "2", frames / "%05d.jpg"])
    n = len(list(frames.glob("*.jpg")))
    print(f"frames: {n}", flush=True)
    if n < 20:
        sys.exit("TRAIN-SPLAT-FAIL too few frames extracted (need a 15s+ video)")

    # 2 — poses: COLMAP sparse reconstruction (this is the slow, fragile step;
    # blurry or spin-in-place videos fail here — reshoot with steady sideways
    # motion and overlap between frames)
    print("STAGE:poses", flush=True)
    colmap = _find("colmap", "colmap.exe")
    _run([colmap, "automatic_reconstructor",
          "--workspace_path", ws, "--image_path", frames,
          "--quality", "medium", "--single_camera", "1",
          "--sparse", "1", "--dense", "0"])
    sparse = ws / "sparse" / "0"
    if not (sparse / "cameras.bin").exists():
        sys.exit("TRAIN-SPLAT-FAIL COLMAP found no camera poses — video needs "
                 "steady motion, texture-rich scenery, and frame overlap")

    # 3 — train: Brush reads the COLMAP workspace directly
    print("STAGE:train", flush=True)
    brush = _find("brush", "brush_app.exe")
    exp = ws / "export"
    exp.mkdir(exist_ok=True)
    _run([brush, ws, "--total-steps", a.steps,
          "--export-every", a.steps, "--export-path", exp,
          "--export-name", "world.ply"])
    plys = sorted(exp.rglob("*.ply"), key=lambda p: p.stat().st_mtime)
    if not plys:
        sys.exit("TRAIN-SPLAT-FAIL Brush produced no .ply export")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plys[-1], out)
    shutil.rmtree(ws, ignore_errors=True)
    print(f"TRAIN-SPLAT-OK {out}", flush=True)


if __name__ == "__main__":
    main()
