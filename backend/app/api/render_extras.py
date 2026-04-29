from __future__ import annotations

"""
api/render_extras.py
====================
WS5/WS7/WS8 — render-time extension endpoints.

    POST /api/render/preview            Quick Eevee fast-pass render
    POST /api/render/iterate            Conversational manifest mutation + render
    GET  /api/render/iterate/{session}  Inspect iteration history
    POST /api/render/with_controls      Render with explicit directorial overrides

Each endpoint runs the render synchronously inside a worker thread so the
existing job table is not touched. Outputs land under /outputs/ and are
served by the static mount that already exists in main.py.
"""

from typing import Any, Optional
import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..blender_runner import (
    _build_manifest_from_topic,
    run_blender_from_manifest,
)
from ..services import scene_iterator
from ..services import variation_generator
from ..db import get_conn


def _recipe_name_from_manifest(manifest_path: Optional[str]) -> Optional[str]:
    """Read ``_template_v2_recipe`` from a written manifest JSON. Returns None
    if the file doesn't exist, isn't JSON, or the field isn't set."""
    if not manifest_path or not os.path.exists(manifest_path):
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        v = data.get("_template_v2_recipe")
        return str(v) if v else None
    except Exception:
        return None


def _record_preview_in_render_jobs(
    *,
    topic: str,
    template_name: str,
    ok: bool,
    output_path: Optional[str],
    output_url: Optional[str],
    error: Optional[str],
    stdout_tail: Optional[str],
    stderr_tail: Optional[str],
    recipe_name: Optional[str],
) -> None:
    """Insert a render_jobs row so Studio-preview renders appear in Gallery /
    Analytics. Swallow errors — this is a non-critical logging side-effect."""
    try:
        status = "complete" if ok and output_url else "failed"
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO render_jobs(
                    project_name, topic, template_name, status, provider_name,
                    local_output_path, output_url, stdout_log, stderr_log,
                    error_text, recipe_name, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    None,
                    topic,
                    template_name,
                    status,
                    "LocalBlenderCliProvider",
                    output_path,
                    output_url,
                    stdout_tail,
                    stderr_tail,
                    error,
                    recipe_name,
                    "preview",
                ),
            )
    except Exception:
        pass


router = APIRouter(prefix="/api/render", tags=["render-extras"])


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _resolve_executables() -> tuple[str | None, str | None, str | None]:
    """
    Read blender + ffmpeg paths from the settings table. Imports are lazy to
    avoid a circular import with main.py.
    """
    from ..main import get_setting
    from ..config import BLENDER_EXE

    blender_exe = get_setting("blender_executable_path", BLENDER_EXE)
    ffmpeg_exe = get_setting("ffmpeg_executable_path", "") or None
    local_render_mode = get_setting("local_render_mode", "1") == "1"
    if not local_render_mode:
        return None, None, "local_render_mode is disabled in settings"
    if not blender_exe:
        return None, None, "blender_executable_path is not configured"
    return blender_exe, ffmpeg_exe, None


def _output_url(local_path: str | None) -> str | None:
    if not local_path:
        return None
    from pathlib import Path

    return f"/outputs/{Path(local_path).name}"


def _blend_url(output_local_path: str | None) -> str | None:
    """v1.4.3 polish — Companion .blend file URL for an MP4 output.

    The render script saves a `<basename>.blend` next to the `<basename>.mp4`
    so users can download + remix. We only return the URL when the file
    actually exists on disk; the script logs a non-fatal warning if save
    fails, in which case we omit the field and the frontend hides the
    download button.
    """
    if not output_local_path:
        return None
    from pathlib import Path

    p = Path(output_local_path)
    blend_path = p.with_suffix(".blend")
    if not blend_path.exists():
        return None
    return f"/outputs/{blend_path.name}"


# ════════════════════════════════════════════════════════════════════════════
# Models
# ════════════════════════════════════════════════════════════════════════════

class PreviewRequest(BaseModel):
    topic: str
    template_name: str = "auto"
    directorial_controls: Optional[dict[str, Any]] = None
    start_session: bool = True
    # Asset Picker UI: when user picks a specific asset from /api/assets/match,
    # the frontend sends the library id here.  Resolver short-circuits to that
    # exact entry instead of running auto-match + diversity picker.
    forced_hero_id: Optional[str] = None
    forced_environment_id: Optional[str] = None
    # V1.3 Template System v2 — gated opt-in until the full test suite
    # passes in production.  When True, the dispatcher picks a recipe
    # and the executor writes preset hints into scene_plan; when False
    # (default), V1.1 behaviour runs unchanged.
    template_v2_enabled: bool = False
    # v1.3.7 Frontend Polish — Scene Controls panel must mutate the actual
    # render. The main Studio Generate button now sends these directly so
    # the controls aren't decorative. (WithControlsRequest already has them;
    # surfacing them here lets a single render path honour everything.)
    render_tier: Optional[str] = None
    scene_params_override: Optional[dict[str, Any]] = None
    duration_seconds: Optional[int] = None


class IterateRequest(BaseModel):
    session_id: str
    instruction: str
    render: bool = True
    render_tier: str = "preview"
    forced_hero_id: Optional[str] = None
    forced_environment_id: Optional[str] = None
    # V1.3 Template System v2 — gated opt-in until the full test suite
    # passes in production.  When True, the dispatcher picks a recipe
    # and the executor writes preset hints into scene_plan; when False
    # (default), V1.1 behaviour runs unchanged.
    template_v2_enabled: bool = False


class WithControlsRequest(BaseModel):
    topic: str
    template_name: str = "auto"
    render_tier: str = "standard"
    directorial_controls: Optional[dict[str, Any]] = None
    scene_params_override: Optional[dict[str, Any]] = None
    duration_seconds: Optional[int] = None
    forced_hero_id: Optional[str] = None
    forced_environment_id: Optional[str] = None
    # V1.3 Template System v2 — gated opt-in until the full test suite
    # passes in production.  When True, the dispatcher picks a recipe
    # and the executor writes preset hints into scene_plan; when False
    # (default), V1.1 behaviour runs unchanged.
    template_v2_enabled: bool = False


class VariationsRequest(BaseModel):
    topic: str
    template_name: str = "auto"
    count: int = 4
    render: bool = True
    render_tier: str = "preview"
    directorial_controls: Optional[dict[str, Any]] = None
    forced_hero_id: Optional[str] = None
    forced_environment_id: Optional[str] = None
    # V1.3 Template System v2 — gated opt-in until the full test suite
    # passes in production.  When True, the dispatcher picks a recipe
    # and the executor writes preset hints into scene_plan; when False
    # (default), V1.1 behaviour runs unchanged.
    template_v2_enabled: bool = False


# ════════════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════════════

@router.post("/preview")
def render_preview(payload: PreviewRequest):
    """Build a fresh manifest and render it.

    v1.3.7 — render_tier is now honored on this endpoint (was hardcoded to
    "preview"). Scene Controls panel mutations (lighting/camera/duration/
    brand) flow in via ``scene_params_override`` and ``duration_seconds``.
    """
    blender_exe, ffmpeg_exe, err = _resolve_executables()
    if err:
        raise HTTPException(status_code=400, detail=err)

    # v1.3.7 — clamp tier to valid backend keys so an unknown frontend value
    # falls back safely instead of producing a confusing render.
    requested_tier = (payload.render_tier or "preview").strip().lower()
    if requested_tier not in ("preview", "fast", "standard", "cinematic"):
        requested_tier = "preview"

    try:
        manifest = _build_manifest_from_topic(
            payload.topic,
            payload.template_name,
            directorial_controls=payload.directorial_controls,
            render_tier=requested_tier,
            forced_hero_id=payload.forced_hero_id,
            forced_environment_id=payload.forced_environment_id,
            template_v2_enabled=payload.template_v2_enabled,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build manifest: {e}")

    # v1.3.7 — layer scene_params_override (mirrors with_controls behavior).
    if payload.scene_params_override:
        existing = dict(manifest.get("scene_params") or {})
        for k, v in payload.scene_params_override.items():
            if v is not None:
                existing[k] = v
        manifest["scene_params"] = existing
        # The camera-motion guard in cinematic_presets.apply_camera_motion()
        # reads scene_plan, not scene_params. Propagate the flag so the
        # explicit "Static" override fires whichever path is live.
        if existing.get("camera_motion_disabled"):
            sp = dict(manifest.get("scene_plan") or {})
            sp["camera_motion_disabled"] = True
            manifest["scene_plan"] = sp

    if payload.duration_seconds and 1 <= int(payload.duration_seconds) <= 120:
        manifest["duration_seconds"] = int(payload.duration_seconds)

    session_id = None
    seed_step = None
    if payload.start_session:
        session_id, seed_step = scene_iterator.start_session(manifest)

    result = run_blender_from_manifest(manifest, blender_exe, ffmpeg_exe)

    recipe_name = _recipe_name_from_manifest(result.get("manifest_path"))
    output_url = _output_url(result.get("output_path"))
    stdout_tail = (result.get("stdout") or "")[-2000:]
    stderr_tail = (result.get("stderr") or "")[-2000:]

    # Persist the preview render into render_jobs so it shows up in Gallery
    # and Analytics. (Preview renders historically bypassed the jobs table.)
    _record_preview_in_render_jobs(
        topic=payload.topic,
        template_name=(payload.template_name or "auto"),
        ok=bool(result.get("ok")),
        output_path=result.get("output_path"),
        output_url=output_url,
        error=result.get("error"),
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        recipe_name=recipe_name,
    )

    return {
        "ok": result["ok"],
        "session_id": session_id,
        "step_id": seed_step.step_id if seed_step else None,
        "render_tier": requested_tier,
        "output_path": result.get("output_path"),
        "output_url": output_url,
        # v1.4.3 polish — companion .blend URL when the render saved one
        "blend_url": _blend_url(result.get("output_path")),
        "manifest_path": result.get("manifest_path"),
        "recipe_name": recipe_name,
        "error": result.get("error"),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


@router.post("/iterate")
def render_iterate(payload: IterateRequest):
    """
    Apply a natural-language instruction to the latest manifest in the
    session and (optionally) re-render it at the requested tier.
    """
    if not payload.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    if not payload.instruction or not payload.instruction.strip():
        raise HTTPException(status_code=400, detail="instruction is required")

    step = scene_iterator.iterate(payload.session_id, payload.instruction.strip())
    if step is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Force render_tier from request (preview by default)
    new_manifest = step.manifest
    if payload.render_tier:
        new_manifest["render_tier"] = payload.render_tier.lower()

    response: dict[str, Any] = {
        "ok": True,
        "session_id": payload.session_id,
        "step": scene_iterator.step_to_dict(step),
        "rendered": False,
    }

    if not payload.render:
        return response

    blender_exe, ffmpeg_exe, err = _resolve_executables()
    if err:
        raise HTTPException(status_code=400, detail=err)

    result = run_blender_from_manifest(new_manifest, blender_exe, ffmpeg_exe)
    response["rendered"] = True
    response["render_result"] = {
        "ok": result["ok"],
        "render_tier": new_manifest.get("render_tier"),
        "output_path": result.get("output_path"),
        "output_url": _output_url(result.get("output_path")),
        # v1.4.3 polish — companion .blend URL on iterated renders too
        "blend_url": _blend_url(result.get("output_path")),
        "manifest_path": result.get("manifest_path"),
        "error": result.get("error"),
        "stdout_tail": (result.get("stdout") or "")[-2000:],
        "stderr_tail": (result.get("stderr") or "")[-2000:],
    }
    return response


@router.get("/iterate/{session_id}")
def get_iteration_history(session_id: str):
    history = scene_iterator.get_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "ok": True,
        "session_id": session_id,
        "steps": [scene_iterator.step_to_dict(s) for s in history],
    }


@router.post("/with_controls")
def render_with_controls(payload: WithControlsRequest):
    """
    Build a fresh manifest, apply explicit directorial overrides, then
    render at the requested tier. Used by the SceneControls UI panel.
    """
    blender_exe, ffmpeg_exe, err = _resolve_executables()
    if err:
        raise HTTPException(status_code=400, detail=err)

    try:
        manifest = _build_manifest_from_topic(
            payload.topic,
            payload.template_name,
            directorial_controls=payload.directorial_controls,
            render_tier=payload.render_tier or "standard",
            forced_hero_id=payload.forced_hero_id,
            forced_environment_id=payload.forced_environment_id,
            template_v2_enabled=payload.template_v2_enabled,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build manifest: {e}")

    # Layer scene_params_override on top
    if payload.scene_params_override:
        existing = dict(manifest.get("scene_params") or {})
        for k, v in payload.scene_params_override.items():
            if v is not None:
                existing[k] = v
        manifest["scene_params"] = existing
        # v1.3.7 — propagate the explicit camera-motion-disabled flag into
        # scene_plan so apply_camera_motion() can honor it. (Same logic as
        # /preview.)
        if existing.get("camera_motion_disabled"):
            sp = dict(manifest.get("scene_plan") or {})
            sp["camera_motion_disabled"] = True
            manifest["scene_plan"] = sp

    if payload.duration_seconds and 1 <= payload.duration_seconds <= 120:
        manifest["duration_seconds"] = payload.duration_seconds

    result = run_blender_from_manifest(manifest, blender_exe, ffmpeg_exe)

    recipe_name = _recipe_name_from_manifest(result.get("manifest_path"))
    output_url = _output_url(result.get("output_path"))
    stdout_tail = (result.get("stdout") or "")[-2000:]
    stderr_tail = (result.get("stderr") or "")[-2000:]

    # Persist into render_jobs so Gallery/Analytics see it.
    _record_preview_in_render_jobs(
        topic=payload.topic,
        template_name=(payload.template_name or "auto"),
        ok=bool(result.get("ok")),
        output_path=result.get("output_path"),
        output_url=output_url,
        error=result.get("error"),
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        recipe_name=recipe_name,
    )

    return {
        "ok": result["ok"],
        "render_tier": manifest.get("render_tier"),
        "output_path": result.get("output_path"),
        "output_url": output_url,
        # v1.4.3 polish — companion .blend URL on with_controls renders
        "blend_url": _blend_url(result.get("output_path")),
        "manifest_path": result.get("manifest_path"),
        "recipe_name": recipe_name,
        "error": result.get("error"),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }


# ════════════════════════════════════════════════════════════════════════════
# WS8 — Batch variations
# ════════════════════════════════════════════════════════════════════════════

@router.post("/variations")
def render_variations(payload: VariationsRequest):
    """
    Generate `count` directorial variations from a single topic and render
    each one synchronously. Renders default to the preview tier so the
    whole batch finishes in a reasonable amount of time.
    """
    blender_exe, ffmpeg_exe, err = _resolve_executables()
    if err:
        raise HTTPException(status_code=400, detail=err)

    try:
        seed_manifest = _build_manifest_from_topic(
            payload.topic,
            payload.template_name,
            directorial_controls=payload.directorial_controls,
            render_tier=payload.render_tier or "preview",
            forced_hero_id=payload.forced_hero_id,
            forced_environment_id=payload.forced_environment_id,
            template_v2_enabled=payload.template_v2_enabled,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build seed manifest: {e}")

    batch = variation_generator.generate_variations(seed_manifest, count=payload.count)

    if payload.render:
        for v in batch.variations:
            # Force the requested tier so the per-variation manifests are
            # all rendered with the same speed budget
            v.manifest["render_tier"] = (payload.render_tier or "preview").lower()
            result = run_blender_from_manifest(v.manifest, blender_exe, ffmpeg_exe)
            v.render_result = {
                "ok": result["ok"],
                "output_path": result.get("output_path"),
                "output_url": _output_url(result.get("output_path")),
                "manifest_path": result.get("manifest_path"),
                "error": result.get("error"),
            }

    return {
        "ok": True,
        "batch_id": batch.batch_id,
        "source": batch.source,
        "count": len(batch.variations),
        "variations": [variation_generator.variation_to_dict(v) for v in batch.variations],
    }


@router.get("/variations/{batch_id}")
def get_variations(batch_id: str):
    batch = variation_generator.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="variation batch not found")
    return {"ok": True, "batch": variation_generator.batch_to_dict(batch)}
