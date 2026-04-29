from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

from .config import OUTPUT_DIR, ROOT
from .planning.scene_plan import GenerationInput
from .services.prompt_scene_planner import build_scene_plan
from .services.asset_agent import enrich_manifest_with_assets
from .services.asset_post_filter import apply_asset_post_filters
from .services.director_validator import validate_director_output
from .services.environment_fetcher import fetch_complex_environment
from .services.template_family_registry import resolve_template_name


# ──────────────────────────────────────────────────────────────────────
# V1.3.4 Bug 3 — HERO_VERIFY abort error formatter
# ──────────────────────────────────────────────────────────────────────

def _format_hero_verify_abort(stdout: str, rc: int) -> str | None:
    """When Blender exits with rc=2, scan stdout for the HERO_VERIFY
    abort signature and return a user-facing error string.  Returns
    None if no abort line was found (caller falls back to stderr).

    rc=2 is the dedicated exit code emitted by render_from_manifest.py's
    _hero_verify_abort.  Other failure modes (Blender crash, OOM, etc.)
    keep the original stderr-based message.
    """
    if rc != 2 or not stdout:
        return None
    abort_line = None
    snapshot_line = None
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[HERO_VERIFY] ABORT:"):
            abort_line = line
        elif line.startswith("[HERO_VERIFY] debug snapshot:"):
            snapshot_line = line
    if not abort_line:
        return None

    # Parse the abort line for diag, fill, polys.
    # Format: "[HERO_VERIFY] ABORT: ['fill_ok'] | diag=125.35m fill=10% polys=105202"
    import re as _hv_re
    failed = []
    diag = None
    fill = None
    polys = None
    m = _hv_re.search(r"ABORT:\s*(\[[^\]]*\])", abort_line)
    if m:
        try:
            failed = eval(m.group(1))  # safe: matches a python list literal of strings
            if not isinstance(failed, list):
                failed = []
        except Exception:
            failed = []
    md = _hv_re.search(r"diag=([\d.]+)m", abort_line)
    if md:
        try: diag = float(md.group(1))
        except Exception: pass
    mf = _hv_re.search(r"fill=(\d+)%", abort_line)
    if mf:
        try: fill = int(mf.group(1))
        except Exception: pass
    mp = _hv_re.search(r"polys=(\d+)", abort_line)
    if mp:
        try: polys = int(mp.group(1))
        except Exception: pass

    # Build user-facing message
    parts: list[str] = ["Render aborted: hero detection failed"]
    causes: list[str] = []
    if "bbox_sane" in failed and diag is not None:
        # V1.4.1: lower bound 0.3m → 0.2m. Mirror render_from_manifest.py
        # bbox_sane check.
        if diag <= 0.2:
            causes.append(f"hero too small ({diag:.2f}m, expected 0.2-50m)")
        elif diag >= 50.0:
            causes.append(f"hero too large ({diag:.1f}m, expected 0.2-50m)")
        else:
            causes.append(f"hero size out of range ({diag:.2f}m)")
    if "in_frustum" in failed:
        causes.append("hero outside camera frustum")
    if "fill_ok" in failed and fill is not None:
        causes.append(f"hero fills only {fill}% of frame (need 35-70%)")
    if "has_hero_tag" in failed:
        causes.append("no hero mesh was tagged after import")
    if "not_primitive" in failed:
        causes.append(
            f"hero appears to be a primitive shape "
            f"({polys if polys is not None else '?'} polys, expected >100)"
        )
    # V1.3.5 Fix 4 — surface oriented_correctly failures
    if "oriented_correctly" in failed:
        causes.append("hero appears upside-down or sideways (orientation gate)")
    if causes:
        parts.append("(" + "; ".join(causes) + ")")
    parts.append("Asset may need re-tagging.")
    if snapshot_line:
        # Strip the "[HERO_VERIFY] debug snapshot:" prefix
        snap = snapshot_line.split("debug snapshot:", 1)[-1].strip()
        parts.append(f"Debug snapshot saved: {snap}")
    else:
        parts.append("Debug snapshot saved.")
    return " ".join(parts)


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

    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
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


def _resolution_for_tier(render_tier: str) -> dict:
    """
    Pick a resolution that's appropriate for the chosen render tier.
    Preview drops to 720x1280 so the Eevee fast pass stays sub-30s.
    Cinematic drops to 1080x1920 (we keep 4K out of the default path so
    a single hero render doesn't accidentally take an hour).
    """
    tier = (render_tier or "standard").lower()
    if tier == "preview":
        return {"width": 720, "height": 1280}
    return {"width": 1080, "height": 1920}


def _build_manifest_from_topic(
    topic: str,
    template_name: str,
    directorial_controls: dict | None = None,
    render_tier: str = "standard",
    forced_hero_id: str | None = None,
    forced_environment_id: str | None = None,
    template_v2_enabled: bool = False,
) -> dict:
    gen_input = GenerationInput(
        manifest_name=(topic or "Untitled Production")[:80],
        raw_prompt=topic,
        template_bias=str(template_name or "auto"),
        duration_seconds=12,
        brand_primary="#0EA5E9",
        sonic_frequency="cinematic",
        technical_style_constraints="",
        references=[],
        raw_ui_context={},
    )

    scene_plan = build_scene_plan(gen_input)

    resolved_template = template_name
    if not resolved_template or str(resolved_template).strip().lower() in ("", "auto"):
        resolved_template = resolve_template_name(
            scene_plan.scene_family,
            fallback=scene_plan.template_name,
        )

    resolution = _resolution_for_tier(render_tier)
    # WS5: shorter clip on preview to keep round-trip latency low.
    duration_seconds = 4 if str(render_tier).lower() == "preview" else scene_plan.duration_seconds

    manifest = {
        "project_name": gen_input.manifest_name,
        "topic": topic,
        "core_objective_prompt": topic,
        "template_name": resolved_template,
        "duration_seconds": duration_seconds,
        "fps": 24,
        "aspect_ratio": "9:16",
        "output_resolution": resolution,
        "render_tier": str(render_tier or "standard").lower(),
        "quality_tier": "high",
        "scene_plan": asdict(scene_plan),
        "scene_params": {
            "environment": scene_plan.environment,
            "lighting_preset": scene_plan.lighting_mode,
            "camera_mode": scene_plan.camera_mode,
            "focal_subject": scene_plan.focal_subject,
            "brand_primary": gen_input.brand_primary,
        },
        "animation_instructions": [
            {
                "subject": a.subject,
                "action": a.action,
                "mode": a.mode,
                "intensity": a.intensity,
                "timing": a.timing,
                "notes": a.notes,
            }
            for a in scene_plan.animation_instructions
        ],
    }

    # ── Inject directorial controls if user provided them ────────────
    if directorial_controls:
        manifest["directorial_controls"] = directorial_controls

    # ── Asset Picker: user-forced hero id short-circuits auto-match ──
    # Written into the manifest BEFORE enrich_manifest_with_assets so
    # the resolver's forced_hero_id branch (asset_agent.py:149) fires
    # and the library bucket gets the forced pick.
    if forced_hero_id:
        manifest["forced_hero_id"] = str(forced_hero_id).strip()
        print(
            f"[RUNNER] manifest built with forced_hero_id="
            f"{manifest['forced_hero_id']!r} — resolver will skip auto-match",
            flush=True,
        )

    # Multi-asset composition: user picked a specific environment asset.
    # The resolver will look this up in the library and stash it on the
    # manifest for the render script to import as backdrop.  Hero
    # placement will then snap to the environment's top surface.
    if forced_environment_id:
        manifest["forced_environment_id"] = str(forced_environment_id).strip()
        print(
            f"[RUNNER] manifest built with forced_environment_id="
            f"{manifest['forced_environment_id']!r} — environment will be "
            f"imported as backdrop before hero placement",
            flush=True,
        )

    # V1.3 Template System v2 — per-request opt-in.  When False (default),
    # enrich_manifest_with_assets skips the V2 dispatch + executor.
    if template_v2_enabled:
        manifest["_template_v2_enabled"] = True

    manifest = enrich_manifest_with_assets(manifest)
    # Director validation — catch obvious contradictions the LLM
    # director leaves behind (idle behavior on a racing ferrari, static
    # camera on a flying eagle, etc.) before the render consumes them.
    try:
        manifest = validate_director_output(manifest)
    except Exception as _dv_e:
        print(f"[RUNNER] director validation skipped: {_dv_e}", flush=True)
    # Post-filter: sanity-check the resolved assets against the request
    # (e.g. drop a sleeping-cat hero when the user asked for dancing,
    # or a cat hero when the user asked for a robot).
    manifest = apply_asset_post_filters(manifest)
    # Complex environment: for "in a stadium", "in a restaurant", etc.
    # fetch a venue-scale scene model so the hero has a real world around
    # it instead of an infinite gray plane. Safe no-op for simple envs.
    try:
        fetch_complex_environment(manifest)
    except Exception as _env_e:
        print(f"[RUNNER] complex environment fetch skipped: {_env_e}", flush=True)
    return manifest


def run_blender_ai_render(
    topic: str,
    template_name: str,
    blender_exe: str,
    ffmpeg_exe: str | None,
    directorial_controls: dict | None = None,
    render_tier: str = "standard",
) -> dict:
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
        manifest = _build_manifest_from_topic(
            topic,
            template_name,
            directorial_controls,
            render_tier=render_tier,
        )
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

    print(f"[RUNNER] launching Blender: {blender_path.name} --python {blender_script.name}", flush=True)
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    # CRITICAL: forward the captured Blender output to the backend console so
    # diagnostic prints ([PRE_RENDER], [FORCE_FIX], [CAMERA_FIX], template logs)
    # are visible during development. capture_output=True alone swallows them.
    if proc.stdout:
        print("===== BLENDER STDOUT =====", flush=True)
        print(proc.stdout, flush=True)
        print("===== END BLENDER STDOUT =====", flush=True)
    if proc.stderr:
        print("===== BLENDER STDERR =====", flush=True)
        print(proc.stderr, flush=True)
        print("===== END BLENDER STDERR =====", flush=True)
    print(f"[RUNNER] Blender exited rc={proc.returncode}", flush=True)

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
    combined_stdout = (
        f"MANIFEST_PATH: {manifest_path}\n"
        f"OUTPUT_DIR: {output_dir}\n\n"
        + (proc.stdout or "")
        + ("\n\n--- FFMPEG ---\n" + (stitch.get("stdout") or ""))
    )
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


# ════════════════════════════════════════════════════════════════════════════
# WS5: Run Blender from a fully-formed manifest (preview / iterate / variation)
# ════════════════════════════════════════════════════════════════════════════

def run_blender_from_manifest(
    manifest: dict,
    blender_exe: str,
    ffmpeg_exe: str | None,
) -> dict:
    """
    Render a previously-built manifest dict (rather than rebuilding from a
    topic). Used by:
      - /api/render/preview   (PREVIEW tier, fast turnaround)
      - /api/render/iterate   (mutated manifest from scene_iterator)
      - /api/render/with_controls (manifest override path)
      - /api/render/variations (per-variation manifest)
    """
    blender_path = Path(blender_exe)
    if not blender_path.exists():
        return {
            "ok": False,
            "output_path": None,
            "stdout": "",
            "stderr": "",
            "error": f"Blender executable not found: {blender_exe}",
        }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_mp4 = OUTPUT_DIR / f"blender_render_{ts}.mp4"
    output_dir = OUTPUT_DIR / f"blender_render_{ts}"
    manifest_path = OUTPUT_DIR / "manifests" / f"manifest_{ts}.json"
    blender_script = ROOT / "render_scripts" / "render_from_manifest.py"

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

    print(f"[RUNNER] launching Blender from manifest: {blender_path.name} --python {blender_script.name}", flush=True)
    print(f"[RUNNER] manifest: {manifest_path}", flush=True)
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    # CRITICAL: forward the captured Blender output to the backend console so
    # diagnostic prints ([PRE_RENDER], [FORCE_FIX], [CAMERA_FIX], template logs)
    # are visible during development. capture_output=True alone swallows them.
    if proc.stdout:
        print("===== BLENDER STDOUT =====", flush=True)
        print(proc.stdout, flush=True)
        print("===== END BLENDER STDOUT =====", flush=True)
    if proc.stderr:
        print("===== BLENDER STDERR =====", flush=True)
        print(proc.stderr, flush=True)
        print("===== END BLENDER STDERR =====", flush=True)
    print(f"[RUNNER] Blender exited rc={proc.returncode}", flush=True)

    png_frames = sorted(output_dir.glob("frame_*.png")) if output_dir.exists() else []

    if proc.returncode != 0:
        # ── V1.3.4 Bug 3 — surface HERO_VERIFY ABORT in user-facing error ──
        # When the render script aborts via the HERO_VERIFY gate it exits
        # with rc=2 and writes a clear `[HERO_VERIFY] ABORT:` line to stdout.
        # The previous behaviour surfaced proc.stderr (full of harmless
        # Blender DeprecationWarnings); the user saw warnings instead of
        # the actual abort reason.  Now: scan stdout for the abort line
        # and craft a human-readable error.
        _user_err = _format_hero_verify_abort(proc.stdout, proc.returncode)
        if _user_err is None:
            _user_err = (
                proc.stderr.strip()
                or f"Blender render failed with exit code {proc.returncode}"
            )
        return {
            "ok": False,
            "output_path": None,
            "manifest_path": str(manifest_path),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "error": _user_err,
        }

    if not png_frames:
        return {
            "ok": False,
            "output_path": None,
            "manifest_path": str(manifest_path),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "error": "Render finished but no PNG frames were found",
        }

    stitch = stitch_pngs_to_mp4(
        output_dir,
        output_mp4,
        ffmpeg_exe=ffmpeg_exe,
        fps=manifest.get("fps", 24),
    )

    combined_stdout = (
        f"MANIFEST_PATH: {manifest_path}\n"
        f"OUTPUT_DIR: {output_dir}\n\n"
        + (proc.stdout or "")
        + ("\n\n--- FFMPEG ---\n" + (stitch.get("stdout") or ""))
    )
    combined_stderr = (proc.stderr or "") + ("\n\n--- FFMPEG ---\n" + (stitch.get("stderr") or ""))

    if stitch["ok"]:
        return {
            "ok": True,
            "output_path": str(output_mp4),
            "manifest_path": str(manifest_path),
            "stdout": combined_stdout,
            "stderr": combined_stderr,
            "error": None,
        }

    return {
        "ok": False,
        "output_path": None,
        "manifest_path": str(manifest_path),
        "stdout": combined_stdout,
        "stderr": combined_stderr,
        "error": stitch.get("error") or "PNG frames rendered but MP4 stitching failed",
    }
