"""
Phase 18 — Vision-driven orientation agent.

Replaces the per-pattern Euler table with an iterative loop:

  1. Render the Hero from a known Z-up perspective camera (preview)
  2. Show the preview to a vision-capable LLM (Ollama gemma3:12b)
  3. LLM answers: "is the subject standing upright? if not, what rotation fixes it?"
  4. Apply the suggested rotation, bake, repeat

After at most N iterations, exit. If anything fails (Ollama down, model returns
garbage, etc.) the agent does NOTHING — the pipeline continues with the raw
imported orientation, and the composer's older behavior takes over. The whole
agent is opt-in friendly: if it can't help, it gets out of the way.

Why this scales:
  - Zero per-pattern measurement
  - Zero coordinate-frame conventions for humans to mess up
  - Works for any subject TripoSR/InstantMesh ever produces
  - Generalizes to size/framing checks later (same loop pattern)
"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Tunables
# ─────────────────────────────────────────────────────────────────────────────

# Phase 18 was paused — gemma3:12b's vision reasoning isn't strong enough for
# reliable 3D pose correction, and TRELLIS install hit a blocker (missing
# vox2seq source in upstream repo). Until a stronger vision model or
# canonical-mesh model is feasible (Claude API, Hunyuan3D-2, etc.), the agent
# runs a SINGLE diagnostic pass and logs whether the subject is oriented
# correctly. It does NOT apply rotations, because experiments showed the model
# suggests wrong axes ~half the time and chasing the wrong fix makes the mesh
# worse, not better. Once a stronger model is wired in, bump MAX_ITERATIONS
# back to 3 and remove the early return in correct_orientation().
MAX_ITERATIONS = 1
APPLY_ROTATIONS = False  # Set True when we trust the verdicts again.
# Three orthographic-ish views composited horizontally. Front shows whether
# the subject is upright or flat; Side shows body axis (horizontal=lying);
# Top shows whether feet are spread (lying) or stacked under body (standing).
PREVIEW_TILE = (384, 384)
PREVIEW_LENS = 50.0
# Each camera positioned along a world axis, looking at origin, with Z up.
# (loc, target, label) — label is annotated onto each tile.
PREVIEW_VIEWS = [
    ((0.0, -3.5, 0.75), (0.0, 0.0, 0.5), "FRONT"),
    ((3.5,  0.0, 0.75), (0.0, 0.0, 0.5), "SIDE"),
    ((0.0,  0.0, 3.5),  (0.0, 0.0, 0.0), "TOP"),
]

# Vision-capable models that have been verified to handle our prompt format
# via Ollama's OpenAI-compatible endpoint. gemma3:12b is multimodal.
DEFAULT_VISION_MODEL = "gemma3:12b"


# ─────────────────────────────────────────────────────────────────────────────
# Preview rendering
# ─────────────────────────────────────────────────────────────────────────────

def _render_single_view(runner, output_path: Path,
                        cam_loc: Tuple[float, float, float],
                        cam_target: Tuple[float, float, float]) -> bool:
    """Render one view via a throwaway camera + light. Returns True on success."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cx, cy, cz = cam_loc
    tx, ty, tz = cam_target
    w, h = PREVIEW_TILE

    code = f"""
import bpy, math
from mathutils import Vector

_prev_cam = bpy.context.scene.camera
_prev_engine = bpy.context.scene.render.engine
_prev_x = bpy.context.scene.render.resolution_x
_prev_y = bpy.context.scene.render.resolution_y
_prev_filepath = bpy.context.scene.render.filepath

_cam_data = bpy.data.cameras.new('OrientAgentCam')
_cam_data.lens = {PREVIEW_LENS}
_cam_obj = bpy.data.objects.new('OrientAgentCam', _cam_data)
bpy.context.scene.collection.objects.link(_cam_obj)
_cam_obj.location = Vector(({cx}, {cy}, {cz}))
_target = Vector(({tx}, {ty}, {tz}))
_direction = _target - _cam_obj.location
_cam_obj.rotation_euler = _direction.to_track_quat('-Z', 'Y').to_euler()

_temp_light = None
_lights = [o for o in bpy.context.scene.objects if o.type == 'LIGHT']
if not _lights:
    _light_data = bpy.data.lights.new('OrientAgentLight', type='SUN')
    _light_data.energy = 3.0
    _temp_light = bpy.data.objects.new('OrientAgentLight', _light_data)
    bpy.context.scene.collection.objects.link(_temp_light)
    _temp_light.rotation_euler = (math.radians(45), 0, math.radians(45))

bpy.context.scene.camera = _cam_obj
bpy.context.scene.render.engine = 'BLENDER_EEVEE'
bpy.context.scene.render.resolution_x = {w}
bpy.context.scene.render.resolution_y = {h}
bpy.context.scene.render.filepath = r'{str(output_path)}'

try:
    bpy.context.scene.eevee.taa_render_samples = 8
except Exception:
    pass

bpy.ops.render.render(write_still=True)

bpy.data.objects.remove(_cam_obj, do_unlink=True)
bpy.data.cameras.remove(_cam_data)
if _temp_light is not None:
    bpy.data.objects.remove(_temp_light, do_unlink=True)
    bpy.data.lights.remove(_light_data)

bpy.context.scene.camera = _prev_cam
bpy.context.scene.render.engine = _prev_engine
bpy.context.scene.render.resolution_x = _prev_x
bpy.context.scene.render.resolution_y = _prev_y
bpy.context.scene.render.filepath = _prev_filepath
__result__ = r'{str(output_path)}'
"""
    try:
        runner.run("orient_preview", "execute_python", {"code": code}, critical=False)
    except Exception:
        return False
    return output_path.exists()


def _composite_views(tile_paths: List[Path], labels: List[str],
                     output_path: Path) -> Optional[Path]:
    """Side-by-side composite of N tiles with labels above each."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None

    tiles: List[Any] = []
    for p in tile_paths:
        try:
            tiles.append(Image.open(p).convert("RGB"))
        except Exception:
            return None
    if not tiles:
        return None

    w, h = PREVIEW_TILE
    label_h = 28
    composite = Image.new("RGB", (w * len(tiles), h + label_h), (32, 32, 32))
    draw = ImageDraw.Draw(composite)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        font = ImageFont.load_default()
    for i, (tile, label) in enumerate(zip(tiles, labels)):
        x = i * w
        composite.paste(tile, (x, label_h))
        # Label centered above tile
        draw.text((x + 12, 4), label, fill=(255, 255, 255), font=font)
    composite.save(output_path)
    return output_path


def _render_preview(runner, hero_name: str, output_path: Path,
                    verbose: bool = True) -> Optional[Path]:
    """Render the Hero from FRONT + SIDE + TOP, composite into one wide PNG.

    Multi-view is what makes the vision LLM able to distinguish
    'lying flat' from 'upside-down standing' from 'standing on side' —
    a single isometric view is ambiguous between all three.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tile_paths: List[Path] = []
    labels: List[str] = []

    for cam_loc, cam_target, label in PREVIEW_VIEWS:
        tile_path = output_path.parent / f"{output_path.stem}_{label.lower()}.png"
        if _render_single_view(runner, tile_path, cam_loc, cam_target):
            tile_paths.append(tile_path)
            labels.append(label)
        else:
            if verbose:
                print(f"[orient-agent] {label} view failed to render")
            return None

    composite = _composite_views(tile_paths, labels, output_path)
    if composite is None and verbose:
        print(f"[orient-agent] composite failed (PIL missing?)")
    return composite


# ─────────────────────────────────────────────────────────────────────────────
# Vision LLM call
# ─────────────────────────────────────────────────────────────────────────────

_VISION_SYSTEM = (
    "You are a 3D scene-orientation expert. The user will show you THREE rendered "
    "views of a 3D object composited side-by-side: FRONT (camera looking at +Y), "
    "SIDE (camera looking at -X), and TOP (camera looking down -Z). Z is the world "
    "up-axis; gravity pulls toward -Z.\n\n"
    "Your job: decide if the subject is standing upright and, if not, output the "
    "rotation needed.\n\n"
    "USE ALL THREE VIEWS to disambiguate:\n"
    "  - If TOP view shows the FULL BODY SILHOUETTE with legs/wheels spread out → "
    "    the subject is LYING FLAT (body axis horizontal). It needs a 90° rotation "
    "    around a horizontal axis to stand it up, NOT 180°.\n"
    "  - If TOP view shows a small compact silhouette (just the head/top of subject) → "
    "    the subject is already vertical (good standing posture or upside-down).\n"
    "  - If FRONT view shows feet/wheels at the bottom of the frame and head/top at "
    "    the top of the frame → standing correctly.\n"
    "  - If FRONT view shows feet/wheels at the top of the frame and head at the "
    "    bottom → upside down. Fix: [180, 0, 0] (flip around X).\n"
    "  - If SIDE view shows a horizontal body silhouette (wider than tall by 2x+) → "
    "    lying flat. Fix: [90, 0, 0] or [0, 90, 0] depending on body orientation.\n\n"
    "ALWAYS respond with a single compact JSON object on one line — no prose, no "
    "markdown, no code fences. Schema:\n"
    "  {\"correct\": bool, \"reason\": str, \"fix_xyz_deg\": [x, y, z]}\n\n"
    "Common fixes (Euler XYZ degrees applied in world axes, extrinsic):\n"
    "  - lying flat, body along world X axis:     [0, 90, 0]\n"
    "  - lying flat, body along world Y axis:     [90, 0, 0]\n"
    "  - upside-down standing (rolled 180):       [180, 0, 0]\n"
    "  - facing wrong direction in XY plane:      [0, 0, 90] or [0, 0, 180]\n"
    "  - already correct:                         [0, 0, 0]\n\n"
    "IMPORTANT: If you applied the same correction in a previous turn and it didn't "
    "work, try a DIFFERENT axis or sign this time. The same fix repeating means "
    "your axis choice was wrong."
)

_VISION_USER_TEMPLATE = (
    "Subject category: {category}.\n"
    "Subject should be: {expected_pose}.\n\n"
    "Look at the three views (FRONT, SIDE, TOP). Is the subject standing correctly "
    "upright in a Z-up world? If not, what world-axis Euler rotation fixes it? "
    "Output the JSON object exactly as specified."
)

_EXPECTED_POSE_BY_PATTERN = {
    "quadruped":     "standing on all four legs, body horizontal, head forward",
    "biped":         "standing upright on two legs, head at top, feet at bottom",
    "vehicle":       "all wheels on the ground, body horizontal, roof up",
    "tree":          "trunk vertical, roots at bottom, canopy at top",
    "celestial":     "centered, no orientation requirement (any rotation is fine)",
    "primitive_geo": "centered, any rotation is fine",
}


def _encode_image_data_url(image_path: Path) -> str:
    raw = image_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _parse_verdict(content: str) -> Optional[Dict[str, Any]]:
    """Pull JSON out of model response. Be lenient about surrounding garbage."""
    if not content:
        return None
    # Strip code fences if present
    s = content.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    # Find first JSON object in the string
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    # Normalize required fields
    if "correct" not in obj or "fix_xyz_deg" not in obj:
        return None
    fix = obj.get("fix_xyz_deg")
    if not (isinstance(fix, list) and len(fix) == 3 and all(isinstance(v, (int, float)) for v in fix)):
        return None
    return {
        "correct": bool(obj["correct"]),
        "reason": str(obj.get("reason", "")),
        "fix_xyz_deg": [float(v) for v in fix],
    }


def _ask_vision_model(image_path: Path, base_pattern: str,
                      verbose: bool = True) -> Optional[Dict[str, Any]]:
    """Round-trip to Ollama. Returns parsed verdict dict or None on any failure."""
    from .orchestrator.llm import OllamaClient, OllamaError

    client = OllamaClient(model=DEFAULT_VISION_MODEL)
    if not client.is_alive():
        if verbose:
            print("[orient-agent] Ollama unreachable — falling back to no-op")
        return None

    expected = _EXPECTED_POSE_BY_PATTERN.get(base_pattern,
                                             "standing upright in a natural pose")
    user_text = _VISION_USER_TEMPLATE.format(
        category=base_pattern, expected_pose=expected
    )

    try:
        image_url = _encode_image_data_url(image_path)
    except Exception as e:
        if verbose:
            print(f"[orient-agent] could not encode preview: {e}")
        return None

    messages = [
        {"role": "system", "content": _VISION_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]},
    ]

    try:
        msg = client.chat(messages, temperature=0.1)
    except OllamaError as e:
        if verbose:
            print(f"[orient-agent] Ollama error: {e}")
        return None
    except Exception as e:
        if verbose:
            print(f"[orient-agent] vision call failed: {type(e).__name__}: {e}")
        return None

    verdict = _parse_verdict(msg.get("content", ""))
    if verdict is None:
        if verbose:
            preview = (msg.get("content") or "")[:200]
            print(f"[orient-agent] unparseable response: {preview!r}")
    return verdict


# ─────────────────────────────────────────────────────────────────────────────
# Rotation application
# ─────────────────────────────────────────────────────────────────────────────

def _apply_rotation(runner, hero_name: str, xyz_deg: Tuple[float, float, float],
                    verbose: bool = True) -> bool:
    """Apply Euler XYZ rotation in degrees to Hero, then bake it in."""
    rx, ry, rz = xyz_deg
    code = (
        "import bpy, math\n"
        f"o = bpy.data.objects.get('{hero_name}')\n"
        "if o:\n"
        "    o.rotation_mode = 'XYZ'\n"
        f"    o.rotation_euler = (math.radians({rx}), math.radians({ry}), math.radians({rz}))\n"
        "    bpy.ops.object.select_all(action='DESELECT')\n"
        "    o.select_set(True)\n"
        "    bpy.context.view_layer.objects.active = o\n"
        "    bpy.ops.object.transform_apply(rotation=True)\n"
        "    __result__ = 'rotated'\n"
        "else:\n"
        "    __result__ = 'no hero'\n"
    )
    try:
        runner.run("orient_apply", "execute_python", {"code": code}, critical=False)
        return True
    except Exception as e:
        if verbose:
            print(f"[orient-agent] rotation apply failed: {type(e).__name__}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main entry — drop-in replacement for the old per-pattern Euler step
# ─────────────────────────────────────────────────────────────────────────────

def correct_orientation(runner, hero_name: str, base_pattern: str,
                        work_dir: Path, verbose: bool = True) -> Dict[str, Any]:
    """Iteratively correct Hero orientation via vision-LLM feedback.

    Returns a dict summarizing what happened:
      {
        "iterations": int,
        "final_verdict": Optional[dict],   # last LLM response, or None on fallback
        "rotations_applied": List[Tuple[float, float, float]],
        "status": "corrected" | "no_change" | "max_iters" | "fallback",
      }

    Never raises — failures are surfaced through the status field. If the agent
    can't do its job (no Ollama, no preview, garbage response) it returns
    "fallback" and the pipeline continues with the raw imported orientation.
    """
    rotations_applied: List[Tuple[float, float, float]] = []
    final_verdict: Optional[Dict[str, Any]] = None
    work_dir = Path(work_dir)

    for i in range(MAX_ITERATIONS):
        preview_path = work_dir / f"orient_preview_{i}.png"
        t0 = time.time()
        rendered = _render_preview(runner, hero_name, preview_path, verbose=verbose)
        if rendered is None:
            if verbose:
                print(f"[orient-agent] iter {i}: preview unavailable, falling back")
            return {
                "iterations": i, "final_verdict": final_verdict,
                "rotations_applied": rotations_applied, "status": "fallback",
            }
        if verbose:
            print(f"[orient-agent] iter {i}: preview rendered → {preview_path.name} ({time.time()-t0:.1f}s)")

        verdict = _ask_vision_model(rendered, base_pattern, verbose=verbose)
        if verdict is None:
            if verbose:
                print(f"[orient-agent] iter {i}: no usable verdict, falling back")
            return {
                "iterations": i + 1, "final_verdict": final_verdict,
                "rotations_applied": rotations_applied, "status": "fallback",
            }
        final_verdict = verdict

        if verbose:
            print(f"[orient-agent] iter {i}: verdict correct={verdict['correct']} "
                  f"reason={verdict['reason']!r} fix={verdict['fix_xyz_deg']}")

        if verdict["correct"]:
            status = "corrected" if rotations_applied else "no_change"
            return {
                "iterations": i + 1, "final_verdict": verdict,
                "rotations_applied": rotations_applied, "status": status,
            }

        # Phase 18 paused — log the verdict for visibility but DO NOT apply
        # rotations. Vision model suggestions were unreliable; chasing them
        # makes the mesh worse, not better. Continue with raw orientation.
        if not APPLY_ROTATIONS:
            if verbose:
                print(f"[orient-agent] WARNING: subject not standing (Phase 18 known limit). "
                      f"Reason: {verdict['reason']}. Suggested fix (NOT applied): "
                      f"{verdict['fix_xyz_deg']}. Continuing with raw orientation.")
            return {
                "iterations": i + 1, "final_verdict": verdict,
                "rotations_applied": rotations_applied, "status": "warned_continued",
            }

        fix = tuple(verdict["fix_xyz_deg"])
        # Skip if model said "not correct" but suggested zero rotation
        if all(abs(v) < 0.1 for v in fix):
            if verbose:
                print(f"[orient-agent] iter {i}: model says not-correct but suggests zero fix, exiting")
            return {
                "iterations": i + 1, "final_verdict": verdict,
                "rotations_applied": rotations_applied, "status": "no_change",
            }

        if not _apply_rotation(runner, hero_name, fix, verbose=verbose):
            return {
                "iterations": i + 1, "final_verdict": verdict,
                "rotations_applied": rotations_applied, "status": "fallback",
            }
        rotations_applied.append(fix)

    return {
        "iterations": MAX_ITERATIONS, "final_verdict": final_verdict,
        "rotations_applied": rotations_applied, "status": "max_iters",
    }
