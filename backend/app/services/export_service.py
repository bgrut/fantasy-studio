from __future__ import annotations

"""
export_service.py
=================
WS6 — Multi-format export pipeline.

Given a render job (or a raw mp4 + frame directory) we can produce:

    mp4         the original (just returned)
    gif         ffmpeg conversion (palettegen for clean colors)
    png_seq     zip of all PNG frames
    poster      single PNG poster frame (the midpoint)
    blend       sidecar .blend, if the original render saved one
    glb         stub — needs a separate Blender pass; returns "not_supported"

All exports land under outputs/exports/<job_id>/. Existing files are
returned as-is on subsequent calls so the UI can poll cheaply.
"""

import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import OUTPUT_DIR


SUPPORTED_FORMATS = {"mp4", "gif", "png_seq", "poster", "blend", "glb"}

EXPORTS_DIR = OUTPUT_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ExportResult:
    ok: bool
    format: str
    local_path: Optional[str] = None
    output_url: Optional[str] = None
    error: Optional[str] = None
    note: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════
# Path discovery
# ════════════════════════════════════════════════════════════════════════════

def _frame_dir_for(mp4_path: Path) -> Path:
    """Frame dir for a render is the sibling folder with the same stem."""
    return mp4_path.parent / mp4_path.stem


def _ensure_export_dir(job_id: int | str) -> Path:
    d = EXPORTS_DIR / str(job_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _public_url(local_path: Path) -> str:
    """
    Build the URL for files served by the /outputs static mount. Anything
    we want to expose must live somewhere under OUTPUT_DIR.
    """
    try:
        rel = local_path.resolve().relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return ""
    return "/outputs/" + str(rel).replace("\\", "/")


# ════════════════════════════════════════════════════════════════════════════
# Individual exporters
# ════════════════════════════════════════════════════════════════════════════

def export_mp4(mp4_path: Path, job_id: int | str) -> ExportResult:
    """The mp4 already exists; just expose it."""
    if not mp4_path.exists():
        return ExportResult(ok=False, format="mp4", error="source mp4 not found")
    return ExportResult(
        ok=True,
        format="mp4",
        local_path=str(mp4_path),
        output_url=_public_url(mp4_path),
    )


def export_gif(mp4_path: Path, job_id: int | str, ffmpeg_exe: str | None = None) -> ExportResult:
    if not mp4_path.exists():
        return ExportResult(ok=False, format="gif", error="source mp4 not found")
    ffmpeg_path = ffmpeg_exe or shutil.which("ffmpeg")
    if not ffmpeg_path:
        return ExportResult(ok=False, format="gif", error="ffmpeg not found on PATH")

    out_dir = _ensure_export_dir(job_id)
    gif_path = out_dir / f"{mp4_path.stem}.gif"
    palette = out_dir / f"{mp4_path.stem}.palette.png"

    if gif_path.exists():
        return ExportResult(
            ok=True,
            format="gif",
            local_path=str(gif_path),
            output_url=_public_url(gif_path),
            note="cached",
        )

    # Two-pass palette for clean colors at small file size
    pal_cmd = [
        str(ffmpeg_path), "-y", "-i", str(mp4_path),
        "-vf", "fps=15,scale=540:-1:flags=lanczos,palettegen",
        str(palette),
    ]
    p1 = subprocess.run(
        pal_cmd,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if p1.returncode != 0:
        return ExportResult(ok=False, format="gif", error=f"palettegen failed: {p1.stderr.strip()[:200]}")

    gif_cmd = [
        str(ffmpeg_path), "-y", "-i", str(mp4_path), "-i", str(palette),
        "-lavfi", "fps=15,scale=540:-1:flags=lanczos [x]; [x][1:v] paletteuse",
        str(gif_path),
    ]
    p2 = subprocess.run(
        gif_cmd,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    try:
        palette.unlink(missing_ok=True)
    except Exception:
        pass

    if p2.returncode != 0 or not gif_path.exists():
        return ExportResult(ok=False, format="gif", error=f"gif encode failed: {p2.stderr.strip()[:200]}")

    return ExportResult(
        ok=True,
        format="gif",
        local_path=str(gif_path),
        output_url=_public_url(gif_path),
    )


def export_png_seq(mp4_path: Path, job_id: int | str) -> ExportResult:
    frame_dir = _frame_dir_for(mp4_path)
    if not frame_dir.exists():
        return ExportResult(
            ok=False,
            format="png_seq",
            error=f"frame directory not found: {frame_dir.name}",
        )

    pngs = sorted(frame_dir.glob("frame_*.png"))
    if not pngs:
        return ExportResult(ok=False, format="png_seq", error="no PNG frames in source directory")

    out_dir = _ensure_export_dir(job_id)
    zip_path = out_dir / f"{mp4_path.stem}_frames.zip"

    if zip_path.exists():
        return ExportResult(
            ok=True,
            format="png_seq",
            local_path=str(zip_path),
            output_url=_public_url(zip_path),
            note="cached",
        )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for png in pngs:
            zf.write(png, arcname=png.name)

    return ExportResult(
        ok=True,
        format="png_seq",
        local_path=str(zip_path),
        output_url=_public_url(zip_path),
    )


def export_poster(mp4_path: Path, job_id: int | str) -> ExportResult:
    """Pick the middle PNG frame as the poster image."""
    frame_dir = _frame_dir_for(mp4_path)
    pngs = sorted(frame_dir.glob("frame_*.png")) if frame_dir.exists() else []
    if not pngs:
        return ExportResult(ok=False, format="poster", error="no PNG frames available")

    middle = pngs[len(pngs) // 2]
    out_dir = _ensure_export_dir(job_id)
    poster_path = out_dir / f"{mp4_path.stem}_poster.png"

    try:
        shutil.copyfile(middle, poster_path)
    except Exception as e:
        return ExportResult(ok=False, format="poster", error=f"copy failed: {e}")

    return ExportResult(
        ok=True,
        format="poster",
        local_path=str(poster_path),
        output_url=_public_url(poster_path),
    )


def export_blend(mp4_path: Path, job_id: int | str) -> ExportResult:
    """
    The render pipeline doesn't currently save a sidecar .blend file. If
    one exists next to the mp4 we surface it; otherwise we report
    not_supported so the UI can disable the button.
    """
    candidate = mp4_path.with_suffix(".blend")
    if candidate.exists():
        return ExportResult(
            ok=True,
            format="blend",
            local_path=str(candidate),
            output_url=_public_url(candidate),
        )
    return ExportResult(
        ok=False,
        format="blend",
        error="not_supported",
        note="enable save_blend in render pipeline to generate sidecars",
    )


def export_glb(mp4_path: Path, job_id: int | str) -> ExportResult:
    """
    GLB export requires a separate Blender pass that opens the .blend
    and runs `bpy.ops.export_scene.gltf`. That work is queued for a
    future workstream; this stub keeps the API surface stable.
    """
    return ExportResult(
        ok=False,
        format="glb",
        error="not_supported",
        note="GLB export requires a follow-up Blender pass — wired in a later workstream",
    )


# ════════════════════════════════════════════════════════════════════════════
# Top-level dispatcher
# ════════════════════════════════════════════════════════════════════════════

def export_render(
    job_id: int | str,
    mp4_path: str,
    fmt: str,
    *,
    ffmpeg_exe: str | None = None,
) -> ExportResult:
    fmt = (fmt or "").strip().lower()
    if fmt not in SUPPORTED_FORMATS:
        return ExportResult(ok=False, format=fmt, error=f"unknown format: {fmt}")

    src = Path(mp4_path)

    if fmt == "mp4":
        return export_mp4(src, job_id)
    if fmt == "gif":
        return export_gif(src, job_id, ffmpeg_exe=ffmpeg_exe)
    if fmt == "png_seq":
        return export_png_seq(src, job_id)
    if fmt == "poster":
        return export_poster(src, job_id)
    if fmt == "blend":
        return export_blend(src, job_id)
    if fmt == "glb":
        return export_glb(src, job_id)

    return ExportResult(ok=False, format=fmt, error="unhandled format")


def result_to_dict(r: ExportResult) -> dict:
    return {
        "ok": r.ok,
        "format": r.format,
        "local_path": r.local_path,
        "output_url": r.output_url,
        "error": r.error,
        "note": r.note,
    }
