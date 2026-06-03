"""
Video encoding tools — wraps the EXISTING FFmpeg integration at
app/blender_runner.py::stitch_pngs_to_mp4().

We don't reimplement ffmpeg invocation; we expose what's already battle-tested
in the legacy pipeline as an MCP tool the orchestrator can call.
"""

from pathlib import Path
from typing import Optional

from ..registry import register_fn


# ───────────────────────────────────────────────────────────────────────
# Reuse the legacy encoder. Lazy import so this module loads even if
# blender_runner has heavy deps.
# ───────────────────────────────────────────────────────────────────────

def _stitch(frame_dir: Path, output_mp4: Path, fps: int = 24, ffmpeg_exe: Optional[str] = None) -> dict:
    """Defensive wrapper. Tries the legacy stitcher first; falls back to direct
    subprocess if it can't be imported (so this tool stays useful in isolation)."""
    try:
        from app.blender_runner import stitch_pngs_to_mp4  # type: ignore
        # Existing function signature: (frame_dir, output_mp4, ffmpeg_exe, fps)
        stitch_pngs_to_mp4(frame_dir, output_mp4, ffmpeg_exe, fps)
        return {"backend": "legacy_stitch_pngs_to_mp4", "mp4_path": str(output_mp4)}
    except ImportError:
        # Fallback: run ffmpeg directly using the same command shape
        return _direct_ffmpeg(frame_dir, output_mp4, fps, ffmpeg_exe)


def _direct_ffmpeg(frame_dir: Path, output_mp4: Path, fps: int, ffmpeg_exe: Optional[str]) -> dict:
    import shutil
    import subprocess
    exe = ffmpeg_exe or shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError(
            "ffmpeg executable not found. Install ffmpeg and ensure it's on PATH, "
            "or set the ffmpeg_executable_path setting via /api/settings."
        )
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        exe, "-y",
        "-framerate", str(fps),
        "-start_number", "1",
        "-i", str(frame_dir / "frame_%04d.png"),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(output_mp4),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (rc={proc.returncode}): {proc.stderr[-2000:]}")
    return {"backend": "direct_ffmpeg", "mp4_path": str(output_mp4), "cmd": " ".join(cmd)}


# ───────────────────────────────────────────────────────────────────────
# Tool: encode_video
# ───────────────────────────────────────────────────────────────────────

@register_fn(
    name="encode_video",
    description=(
        "Stitch a PNG sequence (frame_0001.png, frame_0002.png, ...) into an MP4 video "
        "using libx264 at CRF 18. Use this AFTER render_animation to produce the final video. "
        "Returns the MP4 filepath. The orchestrator provides a suggested mp4_path in context "
        "as 'video_filepath' — use that exact path."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "frame_dir": {
                "type": "string",
                "description": "Directory containing the rendered PNG sequence (output_dir from render_animation)",
            },
            "mp4_path": {
                "type": "string",
                "description": "Output MP4 filepath (must end in .mp4)",
            },
            "fps": {"type": "integer", "default": 24},
        },
        "required": ["frame_dir", "mp4_path"],
        "additionalProperties": False,
    },
    category="render",
)
def encode_video(params: dict) -> dict:
    frame_dir = Path(params["frame_dir"]).resolve()
    mp4_path = Path(params["mp4_path"]).resolve()
    fps = int(params.get("fps", 24))

    if not frame_dir.is_dir():
        raise FileNotFoundError(f"frame_dir does not exist: {frame_dir}")

    frames = sorted(frame_dir.glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError(f"no frame_*.png files in {frame_dir}")

    result = _stitch(frame_dir, mp4_path, fps=fps)
    result.update({
        "frame_count": len(frames),
        "fps": fps,
        "duration_s": round(len(frames) / fps, 2),
        "size_bytes": mp4_path.stat().st_size if mp4_path.exists() else 0,
    })
    return result
