from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from datetime import datetime

from .config import OUTPUT_DIR, ROOT
from .ai.scene_planner import generate_scene_plan
from .services.manifest_builder import build_manifest


def run_mock_render(topic: str, template_name: str) -> dict:
    time.sleep(3)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"mock_render_{ts}.txt"
    output_path.write_text(
        f"MOCK RENDER\nTopic: {topic}\nTemplate: {template_name}\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "output_path": str(output_path),
        "stdout": f"Mock render completed for topic: {topic}",
        "stderr": "",
    }


def stitch_pngs_to_mp4(frame_dir: Path, output_mp4: Path, ffmpeg_exe: str | None, fps: int = 24) -> dict:
    ffmpeg_path = ffmpeg_exe or shutil.which("ffmpeg")
    if not ffmpeg_path:
        return {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "error": "ffmpeg not found on PATH",
        }

    cmd = [
        str(ffmpeg_path),
        "-y",
        "-framerate", str(fps),
        "-start_number", "1",
        "-i", str(frame_dir / "frame_%04d.png"),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(output_mp4),
    ]

    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return {
            "ok": False,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "error": f"ffmpeg stitch failed with exit code {proc.returncode}",
        }

    return {
        "ok": output_mp4.exists(),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "error": None if output_mp4.exists() else "ffmpeg finished but MP4 was not created",
    }


def run_blender_ai_render(topic: str, template_name: str, blender_exe: str, ffmpeg_exe: str | None) -> dict:
    blender_path = Path(blender_exe)
    if not blender_path.exists():
        return {
            "ok": False,
            "output_path": None,
            "stdout": "",
            "stderr": "",
            "error": f"Blender executable not found: {blender_exe}",
        }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_mp4 = OUTPUT_DIR / f"blender_render_{ts}.mp4"
    output_dir = OUTPUT_DIR / f"blender_render_{ts}"
    manifest_path = OUTPUT_DIR / "manifests" / f"manifest_{ts}.json"
    blender_script = ROOT / "render_scripts" / "render_from_manifest.py"

    try:
        scene_plan = generate_scene_plan(topic)
        manifest = build_manifest(topic, scene_plan)
    except Exception as e:
        return {
            "ok": False,
            "output_path": None,
            "stdout": "",
            "stderr": "",
            "error": f"Failed to generate manifest: {e}",
        }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    cmd = [
        str(blender_path),
        "-b",
        "--python",
        str(blender_script),
        "--",
        str(output_mp4),
        str(manifest_path),
    ]

    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    png_frames = sorted(output_dir.glob("frame_*.png")) if output_dir.exists() else []

    if proc.returncode != 0:
        return {
            "ok": False,
            "output_path": None,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "error": proc.stderr.strip() or f"Blender render failed with exit code {proc.returncode}",
        }

    if not png_frames:
        return {
            "ok": False,
            "output_path": None,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "error": "Render finished but no PNG frames were found",
        }

    stitch = stitch_pngs_to_mp4(output_dir, output_mp4, ffmpeg_exe=ffmpeg_exe, fps=manifest.get("fps", 24))
    combined_stdout = (proc.stdout or "") + ("\n\n--- FFMPEG ---\n" + (stitch.get("stdout") or ""))
    combined_stderr = (proc.stderr or "") + ("\n\n--- FFMPEG ---\n" + (stitch.get("stderr") or ""))

    if stitch["ok"]:
        return {
            "ok": True,
            "output_path": str(output_mp4),
            "stdout": combined_stdout,
            "stderr": combined_stderr,
            "error": None,
        }

    return {
        "ok": False,
        "output_path": None,
        "stdout": combined_stdout,
        "stderr": combined_stderr,
        "error": stitch.get("error") or "PNG frames rendered but MP4 stitching failed",
    }
