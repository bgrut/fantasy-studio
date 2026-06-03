"""
Deterministic scene composer.

Takes slot dict (from slots.py) + output paths → composes the scene through
the existing MCP tools in a fixed, reliable order. NO LLM in this layer.

This is the Sora-style architecture: the LLM did the semantic extraction;
this module does the deterministic execution. Reliable, fast, predictable.

Composition order (single hero v1):
    1. reset_scene
    2. set_render_settings
    3. set_frame_range (if animation)
    4. create_primitive / spawn_asset for the hero
    5. tag the hero
    6. ground plane (if requested)
    7. create_material + apply_material
    8. apply_three_point_lighting (mood-driven)
    9. create_camera + look_at (framing/angle-driven)
    10. motion (if animation): orbit / rotate / translate / bounce / drift
    11. render_frame OR render_animation + encode_video
"""

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..mcp import registry, bridge
from .scene_inference import COLOR_MAP, MATERIAL_VIBES, LIGHTING_MOOD
from . import patterns as pattern_lib


# ───────────────────────────────────────────────────────────────────────
# Result type
# ───────────────────────────────────────────────────────────────────────

@dataclass
class CompositionResult:
    success: bool
    render_path: Optional[str] = None
    video_path: Optional[str] = None
    blend_path: Optional[str] = None  # Phase 17 — editable scene alongside output
    is_animation: bool = False
    steps_run: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_s: float = 0.0
    slots: Dict[str, Any] = field(default_factory=dict)


# ───────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────

def _resolve_color(color_name: str) -> List[float]:
    """color_name → RGB. Falls back to neutral gray if unknown."""
    return COLOR_MAP.get(color_name.lower(), [0.65, 0.65, 0.70])


def _material_params_from_slots(subj: Dict[str, Any], run_id: str, base_pattern: str = "primitive_geo") -> Dict[str, Any]:
    """Translate subject slots → PrincipledBSDF params for create_material.

    The material name includes a run-unique suffix so Blender NEVER silently
    falls back to a stale 'HeroMat' from a previous render.

    Special handling:
    - For bipeds with no color specified and "human/person" in name → skin tone
    - For celestial pattern → emission is controlled by the pattern preset, NOT the slot
      (the LLM extracts "emissive=True" for "moon" because moons emit light visually,
      but in 3D we want the moon to REFLECT light, not glow)
    """
    color_name = subj.get("color_name", "neutral")
    name_text = (subj.get("name") or "").lower() + " " + (subj.get("library_query") or "").lower()

    # Auto-skin for humans without explicit color
    if color_name in ("neutral", "") and base_pattern == "biped":
        if "human" in name_text or "person" in name_text or "kid" in name_text or "child" in name_text or "man" in name_text or "woman" in name_text:
            color_name = "skin"

    color_rgb = _resolve_color(color_name)
    material = subj.get("material", "matte")
    vibe = MATERIAL_VIBES.get(material, {"metallic": 0.0, "roughness": 0.55})

    params: Dict[str, Any] = {
        "name": f"HeroMat_{run_id}",
        "color": color_rgb + [1.0],
        "metallic": vibe.get("metallic", 0.0),
        "roughness": vibe.get("roughness", 0.55),
    }
    # Subsurface scattering for organic surfaces (skin, fur, wax, fabric).
    # Light penetrates the surface slightly → soft glow → looks alive vs plastic.
    if material in ("fuzzy", "fabric", "rubber") or color_name.startswith("skin"):
        params["subsurface"] = 0.25 if color_name.startswith("skin") else 0.15
        params["subsurface_color"] = color_rgb
        params["subsurface_radius"] = [1.0, 0.4, 0.3] if color_name.startswith("skin") else [0.5, 0.4, 0.4]

    # Vehicle bodies get anisotropic metal — directional highlights read as brushed/painted
    # car steel rather than flat plastic. Bumps metallic to ensure the BSDF actually
    # uses the anisotropy term.
    if base_pattern == "vehicle":
        params["metallic"] = max(params.get("metallic", 0.0), 0.85)
        params["roughness"] = max(0.20, min(params.get("roughness", 0.55), 0.45))
        params["anisotropic"] = 0.6
        params["anisotropic_rotation"] = 0.0  # 0 = horizontal highlights, classic car-panel look
        # Add a faint clearcoat for that just-waxed look
        params["clearcoat"] = 0.5
        params["clearcoat_roughness"] = 0.08

    # Emission ONLY when slot says emissive AND we're not on a pattern that owns its emission
    if subj.get("emissive") and base_pattern != "celestial":
        params["emission_color"] = color_rgb
        params["emission_strength"] = 15.0
    return params


def _lighting_params_from_mood(mood: str) -> Dict[str, Any]:
    """Mood → 3-point lighting parameters. Fallback matches 'neutral' studio."""
    return LIGHTING_MOOD.get(mood, {
        "color_temp": "neutral",
        "key_energy": 2500, "fill_energy": 900, "rim_energy": 1200,
    }).copy()


def _camera_position_for_framing(framing: str, angle: str, hero_loc: List[float], hero_scale: float) -> Tuple[List[float], List[float]]:
    """Compute camera location based on slot framing + angle. Returns (cam_xyz, target_xyz).

    Distances tuned so a 2m subject occupies ~40-55% of frame diagonal (the
    sweet spot HERO_VERIFY wants: [35%, 70%]).
    """
    # Tighter — previous values were leaving subjects at 14-27% fill. Target 40-55%.
    distances = {"close": 3.2, "medium": 4.8, "wide": 7.5, "ultrawide": 12.0}
    d = distances.get(framing, 4.8) * max(0.5, hero_scale)

    hx, hy, hz = hero_loc

    if angle == "front":
        cam = [hx, hy - d, hz + 0.5]
    elif angle == "side":
        cam = [hx + d, hy, hz + 0.5]
    elif angle == "above":
        cam = [hx, hy - d * 0.3, hz + d * 0.9]
    elif angle == "below":
        cam = [hx, hy - d * 0.7, hz - d * 0.3]
    else:  # three-quarter (default)
        # Was hz + d*0.45 → camera way too high, looked DOWN at subject.
        # 0.15 keeps it closer to subject eye level for asset-gen meshes
        # without losing the "slightly above" cinematic feel.
        cam = [hx + d * 0.7, hy - d * 0.7, hz + d * 0.18]

    return cam, [hx, hy, hz]


def _frames_for_speed(speed: str, base: int = 120) -> int:
    """Speed → frame count for a 5s @ 24fps render. (We keep duration constant; speed affects motion rate.)"""
    return base  # duration is set by output.duration_seconds; speed affects keyframe values


def _revolutions_for_speed(speed: str) -> float:
    return {"slow": 1.0, "medium": 1.5, "fast": 2.5}.get(speed, 1.0)


def _rotation_radians_for_speed(speed: str) -> float:
    return {"slow": 2 * math.pi, "medium": 4 * math.pi, "fast": 6 * math.pi}.get(speed, 2 * math.pi)


def _ensure_bridge() -> None:
    """Make sure the Blender bridge is reachable. Raises if not."""
    if not bridge.is_connected():
        bridge.connect(timeout=3.0)
    if not bridge.ping(timeout=2.0):
        raise RuntimeError("Blender bridge not reachable")


# ───────────────────────────────────────────────────────────────────────
# Phase 17 — asset-driven pipeline (reference → mesh → import)
# ───────────────────────────────────────────────────────────────────────

# Which base_patterns benefit from the asset-driven flow vs procedural.
# Celestial is procedural-only (planets are spheres and metaball blob fits well).
# primitive_geo is always procedural (the user literally asked for a cube/sphere).
ASSET_GEN_PATTERNS = {"quadruped", "biped", "vehicle", "tree"}


def _should_use_asset_gen(scene: Dict[str, Any], subj: Dict[str, Any], slots: Optional[Dict[str, Any]] = None,
                           verbose: bool = True) -> bool:
    """Decide whether to use Phase 17 asset-driven pipeline for this job.

    Returns False (→ procedural fallback) when:
    - base_pattern is celestial or primitive_geo (procedural is correct for those)
    - explicit subj.asset_gen=False (debug / direct procedural request)
    - SDXL text-to-image OR mesh generator deps unavailable

    Each gate prints a one-line explanation so the operator can see exactly
    which step bailed — critical for diagnosing install issues.
    """
    base_pattern = subj.get("base_pattern", "primitive_geo")
    if base_pattern not in ASSET_GEN_PATTERNS:
        if verbose:
            print(f"[composer] asset-gen skipped: base_pattern '{base_pattern}' not in {sorted(ASSET_GEN_PATTERNS)}")
        return False
    if subj.get("asset_gen") is False:
        if verbose:
            print("[composer] asset-gen skipped: explicit subj.asset_gen=False")
        return False
    try:
        from ..asset_gen import is_t2i_available, is_mesh_gen_available
    except Exception as e:
        if verbose:
            print(f"[composer] asset-gen skipped: cannot import asset_gen module ({type(e).__name__}: {e})")
        return False
    if not is_t2i_available():
        if verbose:
            print("[composer] asset-gen skipped: is_t2i_available()=False (SDXL weights or torch/diffusers unavailable)")
        return False
    tri = is_mesh_gen_available("triposr")
    ins = is_mesh_gen_available("instantmesh")
    if verbose:
        print(f"[composer] asset-gen mesh engines: triposr={tri}, instantmesh={ins}")
    if not (tri or ins):
        if verbose:
            print("[composer] asset-gen skipped: no mesh engine available")
        return False
    return True


def _run_asset_gen(slots: Dict[str, Any], scene: Dict[str, Any], subj: Dict[str, Any],
                   runner, paths: Dict[str, Any], run_id: str, verbose: bool = True) -> Optional[str]:
    """Generate reference image → mesh → import into Blender.

    Returns the imported hero object name on success, or None if anything
    failed (composer should fall back to procedural).
    """
    from ..asset_gen import generate_reference, generate_mesh
    tier, style = _resolve_tier_style(scene, subj, slots)

    # Paths — alongside render outputs
    work_dir = Path(paths.get("animation_dir") or Path(paths["render_filepath"]).parent)
    work_dir.mkdir(parents=True, exist_ok=True)
    ref_png = work_dir / f"reference_{run_id}.png"
    mesh_glb = work_dir / f"asset_{run_id}.glb"

    # 1. Reference image (SDXL text-to-image)
    try:
        if verbose:
            print(f"[composer] asset-gen: generating reference image (style={style})")
        t0 = time.time()
        generate_reference(slots, output_path=ref_png, style=style, seed=42)
        if verbose:
            print(f"[composer] asset-gen: reference done in {time.time() - t0:.1f}s → {ref_png.name}")
    except Exception as e:
        if verbose:
            print(f"[composer] asset-gen FAILED at reference step ({type(e).__name__}: {e})")
        return None

    # 2. Mesh generation. Default to TripoSR (proven asset quality; orientation
    # handled by our pose-aware silhouette + canonical-orient post-pass).
    # InstantMesh stays available as a fallback / explicit opt-in via
    # subj.mesh_engine="instantmesh".
    from ..asset_gen import is_mesh_gen_available
    if subj.get("mesh_engine"):
        engine = subj["mesh_engine"]
    elif is_mesh_gen_available("triposr"):
        engine = "triposr"
    else:
        engine = "instantmesh"
    try:
        if verbose:
            print(f"[composer] asset-gen: generating mesh via {engine}")
        t0 = time.time()
        generate_mesh(ref_png, output_path=mesh_glb, engine=engine, tier=tier,
                      base_pattern=subj.get("base_pattern"),
                      force_flip_vertical=bool(subj.get("force_flip_vertical", False)))
        if verbose:
            print(f"[composer] asset-gen: mesh done in {time.time() - t0:.1f}s → {mesh_glb.name}")
    except Exception as e:
        if verbose:
            print(f"[composer] asset-gen FAILED at mesh step ({type(e).__name__}: {e})")
        # Fall back to other engine before giving up
        fallback = "triposr" if engine == "instantmesh" else "instantmesh"
        try:
            if verbose:
                print(f"[composer] asset-gen: retrying with {fallback}")
            generate_mesh(ref_png, output_path=mesh_glb, engine=fallback, tier=tier,
                          base_pattern=subj.get("base_pattern"))
        except Exception as e2:
            if verbose:
                print(f"[composer] asset-gen FAILED on fallback ({type(e2).__name__}: {e2})")
            return None

    # 3. Import mesh into Blender as hero
    try:
        import_result = runner.run("asset_import", "import_mesh_file", {
            "filepath": str(mesh_glb),
            "name": "Hero",
            "normalize_size": 1.5,  # was 2m — feels too big for the standard noon framing
            "ground_to_z0": True,
            "join": True,
            # GLB is already canonically oriented at the trimesh level — no Blender rotation needed
            "orientation_fix": None,
        }, critical=False)
        if not isinstance(import_result, dict) or not import_result.get("ok"):
            return None
        hero_name = import_result.get("name", "Hero")

        # Phase 18 — vision-driven orientation agent. Replaces the brittle
        # per-pattern Euler table. Renders a preview, asks Ollama gemma3:12b
        # whether the subject is standing, applies suggested rotation, iterates.
        # If anything fails (Ollama down, garbage response, etc.) the agent
        # gracefully no-ops and the pipeline continues with the raw orientation.
        try:
            from ..orientation_agent import correct_orientation
            base_pattern = subj.get("base_pattern", "primitive_geo")
            agent_result = correct_orientation(
                runner=runner,
                hero_name=hero_name,
                base_pattern=base_pattern,
                work_dir=work_dir,
                verbose=verbose,
            )
            if verbose:
                status = agent_result.get("status", "unknown")
                iters = agent_result.get("iterations", 0)
                applied = agent_result.get("rotations_applied", [])
                print(f"[composer] orient_agent: status={status} iters={iters} "
                      f"rotations_applied={len(applied)}")
                for j, rot in enumerate(applied):
                    print(f"[composer]   step {j}: rotated by {rot}")
        except Exception as e:
            if verbose:
                print(f"[composer] orient_agent crashed, continuing with raw orientation "
                      f"({type(e).__name__}: {e})")

        return hero_name
    except Exception as e:
        if verbose:
            print(f"[composer] asset-gen FAILED at import step ({type(e).__name__}: {e})")
        return None


# ───────────────────────────────────────────────────────────────────────
# Phase 16 — diffusion refinement gate
# ───────────────────────────────────────────────────────────────────────

def _resolve_tier_style(scene: Dict[str, Any], subj: Dict[str, Any], slots: Optional[Dict[str, Any]] = None) -> tuple[str, str]:
    """Pull tier+style from whichever slot level the LLM populated.

    The slot extractor puts them under output.render_tier / output.style, but
    older paths also stashed them on subject. Check both, fall back to defaults.
    """
    out_slots = (slots or {}).get("output", {}) if slots else {}
    tier = (
        out_slots.get("render_tier")
        or scene.get("render_tier")
        or subj.get("requested_tier")
        or "fast"
    )
    style = (
        out_slots.get("style")
        or scene.get("style")
        or subj.get("requested_style")
        or "photoreal"
    )
    return str(tier).lower(), str(style).lower()


def _should_refine(scene: Dict[str, Any], subj: Dict[str, Any], slots: Optional[Dict[str, Any]] = None) -> bool:
    """Decide whether the per-frame img2img refiner should run.

    Phase 17 change: defaults to OFF. The asset-driven path produces real meshes
    that Blender renders correctly — per-frame img2img creates temporal artifacts
    (the spinning "blotchy brown marks" the user spotted in v1). We keep refinement
    available as an OPT-IN stylization pass for non-photoreal styles where the
    user explicitly wants diffusion polish.

    Opt-in via slot subj.use_refiner=True OR scene.use_refiner=True.

    Skips when:
    - Not explicitly opted in (default)
    - Style is 'raw'/'procedural' (debug)
    - Refinement module not installed
    - Render tier is 'preview'
    """
    tier, style = _resolve_tier_style(scene, subj, slots)
    if style in ("raw", "procedural", "none", "off"):
        return False
    if tier == "preview":
        return False
    # Opt-in gate — Phase 17 default off
    opt_in = bool(subj.get("use_refiner") or scene.get("use_refiner"))
    if not opt_in:
        return False
    try:
        from ..refinement import is_available
        return is_available()
    except Exception:
        return False


def _refine_params(scene: Dict[str, Any], subj: Dict[str, Any], slots: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Map render_tier → refinement quality settings."""
    tier, style = _resolve_tier_style(scene, subj, slots)
    tier_map = {
        "fast":      {"strength": 0.45, "steps": 18, "guidance_scale": 7.0},
        "standard":  {"strength": 0.55, "steps": 25, "guidance_scale": 7.5},
        "cinematic": {"strength": 0.65, "steps": 35, "guidance_scale": 8.0},
    }
    params = dict(tier_map.get(tier, tier_map["standard"]))
    params["style"] = style
    return params


def _maybe_refine_single(render_path: str, slots: Dict[str, Any], scene: Dict[str, Any],
                          subj: Dict[str, Any], runner, verbose: bool = True) -> None:
    if not _should_refine(scene, subj, slots):
        return
    try:
        from ..refinement import refine_frame
    except Exception as e:
        if verbose:
            print(f"[composer] refine skipped — module unavailable: {e}")
        return
    params = _refine_params(scene, subj, slots)
    if verbose:
        print(f"[composer] refining frame — style={params['style']}, "
              f"strength={params['strength']}, steps={params['steps']}")
    t0 = time.time()
    try:
        # Refine in-place so downstream paths keep working
        refine_frame(render_path, slots, output_path=render_path, **params)
        if verbose:
            print(f"[composer] refine done in {time.time() - t0:.1f}s")
    except Exception as e:
        # Non-fatal — fall back to the raw render
        if verbose:
            print(f"[composer] refine FAILED (non-fatal, using raw render): "
                  f"{type(e).__name__}: {e}")


def _maybe_refine_animation(anim_dir: str, slots: Dict[str, Any], scene: Dict[str, Any],
                             subj: Dict[str, Any], runner, verbose: bool = True) -> None:
    if not _should_refine(scene, subj):
        return
    try:
        from ..refinement import refine_animation
    except Exception as e:
        if verbose:
            print(f"[composer] refine skipped — module unavailable: {e}")
        return
    params = _refine_params(scene, subj)
    if verbose:
        print(f"[composer] refining animation frames — style={params['style']}, "
              f"strength={params['strength']}, steps={params['steps']}")
    t0 = time.time()
    try:
        n = refine_animation(anim_dir, slots, **params)
        if verbose:
            print(f"[composer] refined {n} frames in {time.time() - t0:.1f}s")
    except Exception as e:
        if verbose:
            print(f"[composer] refine FAILED (non-fatal, using raw frames): "
                  f"{type(e).__name__}: {e}")


def _build_accent_materials(runner, run_id: str, hero_mat_params: Dict[str, Any], subj: Dict[str, Any]) -> Dict[str, str]:
    """Create the small set of accent materials patterns reference via material_hint.

    Returns mapping {hint: material_name}. Created lazily so we don't pollute Blender
    with unused materials.
    """
    out: Dict[str, str] = {}

    def _make(hint: str, params: Dict[str, Any]) -> None:
        params = dict(params)
        params["name"] = f"{hint.title()}Mat_{run_id}"
        res = runner.run(f"accent_mat:{hint}", "create_material", params)
        out[hint] = (res or {}).get("name", params["name"]) if isinstance(res, dict) else params["name"]

    # Eyes — sclera (white), iris (colored), pupil (black). Layered spheres
    # produce a proper-reading eye instead of a single black bead.
    _make("eyes", {"color": [0.95, 0.93, 0.90, 1.0], "metallic": 0.0, "roughness": 0.20})
    # Iris — colored ring. Default warm brown; LLM can override via slot accent_color later.
    iris_color = subj.get("iris_color") or [0.30, 0.18, 0.10, 1.0]
    if len(iris_color) == 3:
        iris_color = list(iris_color) + [1.0]
    _make("iris", {"color": iris_color, "metallic": 0.0, "roughness": 0.30})
    # Pupil — pure black, slightly glossy for catchlight
    _make("pupil", {"color": [0.01, 0.01, 0.01, 1.0], "metallic": 0.0, "roughness": 0.05})
    # Lips — slightly redder than skin, soft sheen
    _make("lips", {"color": [0.65, 0.35, 0.32, 1.0], "metallic": 0.0, "roughness": 0.40,
                   "subsurface": 0.20, "subsurface_color": [0.65, 0.32, 0.30],
                   "subsurface_radius": [1.0, 0.4, 0.3]})
    # Nostril — dark recess
    _make("nostril", {"color": [0.10, 0.06, 0.06, 1.0], "metallic": 0.0, "roughness": 0.60})
    # Headlights — emissive white, used by vehicle
    _make("headlight", {
        "color": [0.95, 0.95, 0.85, 1.0],
        "metallic": 0.0, "roughness": 0.20,
        "emission_color": [1.0, 0.95, 0.85], "emission_strength": 12.0,
    })
    # Tire — dark matte rubber, used by vehicle wheels
    _make("tire", {"color": [0.08, 0.08, 0.08, 1.0], "metallic": 0.0, "roughness": 0.85})
    # Foliage — saturated green, used by tree canopy
    _make("foliage", {"color": [0.12, 0.40, 0.10, 1.0], "metallic": 0.0, "roughness": 0.85})
    # Wood — warm brown, used by tree trunk
    _make("wood", {"color": [0.30, 0.18, 0.08, 1.0], "metallic": 0.0, "roughness": 0.85})
    return out


# ───────────────────────────────────────────────────────────────────────
# Step runner — captures errors but keeps composing
# ───────────────────────────────────────────────────────────────────────

class _StepRunner:
    def __init__(self, result: CompositionResult, verbose: bool):
        self.result = result
        self.verbose = verbose

    def run(self, step_name: str, tool_name: str, params: Dict[str, Any], critical: bool = False) -> Any:
        """Run a tool call. Logs. If critical=True, propagates exceptions."""
        if self.verbose:
            preview = json.dumps(params, default=str)
            if len(preview) > 150:
                preview = preview[:147] + "..."
            print(f"[composer] {step_name}: {tool_name}({preview})")
        try:
            out = registry.call(tool_name, params)
            self.result.steps_run.append(step_name)
            if self.verbose and isinstance(out, dict):
                # Echo the result so we can debug name-collision issues like
                # Blender auto-renaming HeroMat → HeroMat.001
                rprev = json.dumps(out, default=str)
                if len(rprev) > 120:
                    rprev = rprev[:117] + "..."
                print(f"[composer]   → {rprev}")
            return out
        except Exception as e:
            err = f"{step_name} ({tool_name}) failed: {type(e).__name__}: {e}"
            self.result.errors.append(err)
            if self.verbose:
                print(f"[composer]   ✗ {err}")
            if critical:
                raise
            return None


# ───────────────────────────────────────────────────────────────────────
# Main composer
# ───────────────────────────────────────────────────────────────────────

def compose_scene(
    slots: Dict[str, Any],
    paths: Dict[str, str],
    verbose: bool = True,
) -> CompositionResult:
    """Deterministically build + render a scene from slots.

    paths must include:
        - render_filepath (.png target for stills)
        - animation_dir   (directory for PNG sequence)
        - video_filepath  (.mp4 target for video)
    """
    result = CompositionResult(success=False, slots=slots)
    t0 = time.time()

    try:
        _ensure_bridge()
    except Exception as e:
        result.errors.append(f"bridge unreachable: {e}")
        result.duration_s = time.time() - t0
        return result

    runner = _StepRunner(result, verbose)

    # Lazy-import environment to avoid circular issues
    from .patterns import environment as env_module

    # Per-run unique ID — used to suffix material/object names so we can't
    # accidentally pick up stale data from previous runs.
    import datetime
    run_id = datetime.datetime.now().strftime("%H%M%S%f")[:10]

    subj = slots["subject"]
    scene = slots["scene"]
    motion = slots["motion"]
    cam_slots = slots["camera"]
    out_slots = slots["output"]

    # ── Iteration-speed flags (set by the CLI / API to fast-path through testing).
    import os
    quick_mode = os.environ.get("FANTASY_STUDIO_QUICK") == "1"
    no_render = os.environ.get("FANTASY_STUDIO_NO_RENDER") == "1"
    if quick_mode and verbose:
        print("[composer] QUICK mode: single still frame instead of 120-frame animation")
    if no_render and verbose:
        print("[composer] NO-RENDER mode: producing reference + mesh + .blend only, no MP4")

    # ── Product decision: every render is a 5-second video by default.
    # If the user's prompt had no motion words, we add a subtle camera drift
    # ("ambient orbit") so even static subjects feel cinematic. This is the
    # Sora pattern — never deliver a still when the user is expecting a clip.
    is_animation = True
    if motion.get("type") == "static":
        # Inject a gentle camera arc — slower than an "orbit" intent
        motion = {"type": "ambient_orbit", "speed": "slow"}
        if verbose:
            print(f"[composer] static prompt → defaulting to ambient camera drift (5s)")

    # Iteration mode overrides — single frame for --quick, no animation
    if quick_mode:
        is_animation = False

    result.is_animation = is_animation
    duration_s = int(out_slots.get("duration_seconds") or 5)
    if duration_s == 0:
        duration_s = 5  # always at least 5 seconds of video
    fps = 24
    total_frames = duration_s * fps if is_animation else 1

    # 1. Clean slate
    runner.run("reset", "reset_scene", {})

    # 2. Render settings (engine + resolution + fps + tier-driven samples)
    res_x, res_y = (1280, 720) if out_slots.get("resolution") == "720p" else (1920, 1080)
    tier = out_slots.get("render_tier", "fast")
    # Tier mapping: preview/fast = EEVEE (real-time), standard/cinematic = CYCLES (ray-traced)
    tier_config = {
        "preview":   {"engine": "BLENDER_EEVEE", "samples": 16},
        "fast":      {"engine": "BLENDER_EEVEE", "samples": 64},
        "standard":  {"engine": "CYCLES",        "samples": 64},
        "cinematic": {"engine": "CYCLES",        "samples": 256},
    }
    rconf = tier_config.get(tier, tier_config["fast"])
    runner.run("render_settings", "set_render_settings", {
        "engine": rconf["engine"],
        "resolution_x": res_x,
        "resolution_y": res_y,
        "samples": rconf["samples"],
        "fps": fps,
    })
    # Enable GPU compute for Cycles when available
    if rconf["engine"] == "CYCLES":
        runner.run("cycles_gpu", "execute_python", {"code": (
            "import bpy\n"
            "try:\n"
            "    bpy.context.scene.cycles.device = 'GPU'\n"
            "    prefs = bpy.context.preferences.addons.get('cycles')\n"
            "    if prefs:\n"
            "        prefs.preferences.compute_device_type = 'OPTIX' if 'OPTIX' in [d.type for d in prefs.preferences.devices] else 'CUDA'\n"
            "        for d in prefs.preferences.devices:\n"
            "            d.use = True\n"
            "except Exception: pass\n"
            "__result__ = 'gpu_attempted'"
        )})

    # 3. Frame range
    if is_animation:
        runner.run("frame_range", "set_frame_range", {"frame_start": 1, "frame_end": total_frames})

    # 4-7. PATTERN INSTANTIATION + materials
    # Pick the anatomical/structural pattern (or pass-through primitive).
    base_pattern = subj.get("base_pattern", "primitive_geo")
    if pattern_lib.get_pattern(base_pattern) is None:
        result.errors.append(f"pattern '{base_pattern}' not registered; falling back to primitive_geo")
        base_pattern = "primitive_geo"

    # ── Phase 17 GATE: try asset-driven pipeline FIRST for organic/vehicle subjects.
    # If reference→mesh→import succeeds we get a real mesh hero. If anything fails
    # we fall back to procedural pattern instantiation (the rest of the flow is unchanged).
    asset_gen_hero_name: Optional[str] = None
    use_asset_gen = _should_use_asset_gen(scene, subj, slots)
    if use_asset_gen:
        if verbose:
            print(f"[composer] Phase 17 asset-driven path engaged for base_pattern='{base_pattern}'")
        asset_gen_hero_name = _run_asset_gen(slots, scene, subj, runner, paths, run_id, verbose=verbose)
        if asset_gen_hero_name is None and verbose:
            print(f"[composer] asset-gen unsuccessful → falling back to procedural")

    if asset_gen_hero_name:
        # Real mesh imported; skip procedural pattern parts entirely.
        parts = []
        if verbose:
            print(f"[composer] using imported mesh '{asset_gen_hero_name}' as hero — skipping pattern")
    else:
        parts = pattern_lib.instantiate(base_pattern, slots)
        if verbose:
            print(f"[composer] pattern '{base_pattern}' produced {len(parts)} part(s)")

    # Build the hero material (shared across non-detail parts).
    mat_params = _material_params_from_slots(subj, run_id=run_id, base_pattern=base_pattern)
    mat_result = runner.run("material", "create_material", mat_params)
    actual_mat_name = (mat_result or {}).get("name", mat_params["name"]) if isinstance(mat_result, dict) else mat_params["name"]
    if verbose and actual_mat_name != mat_params["name"]:
        print(f"[composer]   ⚠ material renamed: '{mat_params['name']}' → '{actual_mat_name}'")

    # Build accent materials for known hints (eyes, headlight, tire, foliage, wood)
    accent_mats: Dict[str, str] = _build_accent_materials(runner, run_id, mat_params, subj)

    # ── CELESTIAL OVERRIDE — when a part carries celestial params, build a richly-
    # textured material specifically for it (crater for moon, continent for earth, etc).
    celestial_parts: Dict[str, str] = {}
    for part in parts:
        if part.get("material_hint") == "celestial" and "_celestial_params" in part:
            cp = part["_celestial_params"]
            cel_mat_name = f"CelestialMat_{part['name']}_{run_id}"
            cel_params = {
                "name": cel_mat_name,
                "color": cp["color"],
                "metallic": cp.get("metallic", 0.0),
                "roughness": cp.get("roughness", 0.8),
                "texture_pattern": cp.get("texture_pattern"),
                "texture_scale": cp.get("texture_scale", 4.0),
                "texture_contrast": cp.get("texture_contrast", 0.6),
            }
            if cp.get("emissive"):
                cel_params["emission_color"] = cp["color"][:3]
                cel_params["emission_strength"] = cp.get("emission_strength", 15.0)
            cel_result = runner.run(f"cel_mat:{part['name']}", "create_material", cel_params)
            if isinstance(cel_result, dict) and cel_result.get("name"):
                celestial_parts[part["name"]] = cel_result["name"]

    # ── METABALL STRATEGY for organic creatures (quadruped, biped, except primitive_geo)
    # Instead of spawning each part as a separate primitive and trying to merge later,
    # build the ENTIRE creature as a single metaball family. Metaballs auto-blend into
    # one continuous surface — no gaps, no floating pieces. The right Blender tool
    # for organic character construction.
    METABALL_PATTERNS = {"quadruped", "biped"}
    use_metaball = base_pattern in METABALL_PATTERNS

    # Track which part is the hero — by convention the part with role="body"
    hero_name: Optional[str] = None
    placed_part_names: List[str] = []

    # Phase 17: if an imported mesh became the hero, register it now so the
    # rest of the flow (tag_hero, grounding, camera framing) treats it as primary.
    if asset_gen_hero_name:
        hero_name = asset_gen_hero_name
        placed_part_names.append(asset_gen_hero_name)

    # Phase 17: when asset-gen produced a real mesh hero, skip the entire
    # metaball / procedural-material / fur branch — that mesh already has
    # vertex colors baked from the SDXL reference and applying procedural
    # fur on a 76k-poly mesh kills the render.
    if asset_gen_hero_name and use_metaball:
        if verbose:
            print(f"[composer] asset-gen hero present — skipping metaball + procedural material + fur")
        use_metaball = False
        parts = []  # nothing more to spawn; HDRI/lights/camera/animation will run normally

    if use_metaball:
        # Build metaball element list from all hero-material parts
        meta_elements = []
        accent_parts = []
        for part in parts:
            if part.get("material_hint"):
                # Accent parts (eyes, etc) keep their own materials → spawn as primitives later
                accent_parts.append(part)
                continue
            scale = part.get("scale", [1, 1, 1])
            if isinstance(scale, (int, float)):
                scale = [float(scale)] * 3
            # Metaball size 1.0 ≈ a sphere of radius 1.0. The part's scale already
            # encodes the desired size. Multiply by 0.85 so blobs penetrate each
            # other (otherwise threshold would shrink them).
            ellipsoid_size = [float(s) * 0.85 for s in scale]
            meta_elements.append({
                "type": "ELLIPSOID",
                "location": part["location"],
                "rotation": part.get("rotation", [0, 0, 0]),
                "size_x": ellipsoid_size[0],
                "size_y": ellipsoid_size[1],
                "size_z": ellipsoid_size[2],
                "stiffness": 2.0,
            })

        # Create the unified blob (auto-converts to mesh)
        blob_result = runner.run("creature_blob", "create_metaball_blob", {
            "name": "Hero",
            "resolution": 0.06,
            "threshold": 0.6,
            "elements": meta_elements,
            "convert_to_mesh": True,
        })
        if isinstance(blob_result, dict) and blob_result.get("name"):
            hero_name = blob_result["name"]
            placed_part_names.append(hero_name)

        # Apply hero material to the blob
        if hero_name:
            runner.run("blob_material", "apply_material", {
                "object": hero_name, "material": actual_mat_name,
            })
            # Light subdivision + smooth shading for organic feel
            runner.run("blob_smooth", "execute_python", {
                "code": (
                    "import bpy\n"
                    f"o = bpy.data.objects.get('{hero_name}')\n"
                    "if o and o.data:\n"
                    "    sub = o.modifiers.new(name='BlobSmooth', type='SUBSURF')\n"
                    "    sub.levels = 1; sub.render_levels = 2\n"
                    "    for p in o.data.polygons: p.use_smooth = True\n"
                    "__result__ = 'smoothed'"
                )
            })

        # Spawn accent parts (eyes etc) as regular primitives with their own materials
        for part in accent_parts:
            spawn_result = runner.run(
                f"accent_part:{part['name']}",
                "create_primitive",
                {
                    "type": part["primitive"],
                    "name": part["name"],
                    "location": part["location"],
                    "rotation": part["rotation"],
                    "size": part["size"],
                },
            )
            actual_name = (spawn_result or {}).get("name", part["name"]) if isinstance(spawn_result, dict) else part["name"]
            placed_part_names.append(actual_name)
            if part["scale"] != [1, 1, 1]:
                runner.run(
                    f"accent_scale:{actual_name}",
                    "transform_object",
                    {"name": actual_name, "scale": part["scale"]},
                )
            hint = part.get("material_hint")
            mat_for_this = accent_mats.get(hint, actual_mat_name) if hint and hint != "celestial" else actual_mat_name
            runner.run(
                f"accent_mat:{actual_name}",
                "apply_material",
                {"object": actual_name, "material": mat_for_this},
            )
        # Skip the per-part loop below; metaball already handled all hero parts
        parts_to_spawn = []
    else:
        parts_to_spawn = parts

    for part in parts_to_spawn:
        # Spawn the primitive
        spawn_result = runner.run(
            f"part:{part['name']}",
            "create_primitive",
            {
                "type": part["primitive"],
                "name": part["name"],
                "location": part["location"],
                "rotation": part["rotation"],
                "size": part["size"],
            },
        )
        actual_name = (spawn_result or {}).get("name", part["name"]) if isinstance(spawn_result, dict) else part["name"]
        placed_part_names.append(actual_name)

        # Apply scale (transform_object handles tuple-or-scalar)
        if part["scale"] != [1, 1, 1]:
            runner.run(
                f"scale:{actual_name}",
                "transform_object",
                {"name": actual_name, "scale": part["scale"]},
            )

        # Apply optional modifiers (subdivision / bevel / etc.)
        for mod in part.get("modifiers", []):
            runner.run(
                f"mod:{actual_name}:{mod['kind']}",
                "add_modifier",
                {"object": actual_name, "kind": mod["kind"], "settings": mod.get("settings", {})},
            )

        # Pick material — celestial override > accent hint > hero
        if part["name"] in celestial_parts:
            mat_for_this = celestial_parts[part["name"]]
        else:
            hint = part.get("material_hint")
            mat_for_this = accent_mats.get(hint, actual_mat_name) if hint and hint != "celestial" else actual_mat_name
        runner.run(
            f"mat:{actual_name}",
            "apply_material",
            {"object": actual_name, "material": mat_for_this},
        )

        if part.get("role") == "body" and hero_name is None:
            hero_name = actual_name

    if hero_name is None and placed_part_names:
        hero_name = placed_part_names[0]

    # ── VEHICLE BODY MERGE: chassis + cabin via Boolean Union → one cohesive body.
    # Wheels and headlights stay separate (they need different materials anyway).
    if base_pattern == "vehicle":
        cabin_obj = next((n for n in placed_part_names if n.startswith("Cabin")), None)
        chassis_obj = next((n for n in placed_part_names if n.startswith("Chassis")), None)
        if cabin_obj and chassis_obj:
            runner.run("vehicle_body_merge", "boolean_union", {
                "target": chassis_obj,
                "operand": cabin_obj,
                "delete_operand": True,
            })

    # ── JOIN + VOXEL REMESH — only runs if we DIDN'T use metaball strategy.
    # Metaball patterns already produce a unified mesh, so skip this entirely.
    ORGANIC_PATTERNS = {"quadruped", "biped"}
    if base_pattern in ORGANIC_PATTERNS and hero_name and not use_metaball:
        # Find parts that use the HERO material (not eyes/accents)
        hero_part_names = [p["name"] for p in parts if not p.get("material_hint")]
        if len(hero_part_names) > 1:
            join_code = (
                "import bpy\n"
                "bpy.ops.object.select_all(action='DESELECT')\n"
                f"target = bpy.data.objects.get('{hero_name}')\n"
                f"names = {hero_part_names!r}\n"
                "joined = 0\n"
                "for n in names:\n"
                "    o = bpy.data.objects.get(n)\n"
                "    if o and o.type == 'MESH':\n"
                "        o.select_set(True)\n"
                "        joined += 1\n"
                "if target and joined > 1:\n"
                "    bpy.context.view_layer.objects.active = target\n"
                "    bpy.ops.object.join()\n"
                "    # Apply any pending modifiers on the joined mesh BEFORE remesh\n"
                "    for m in list(target.modifiers):\n"
                "        try:\n"
                "            bpy.ops.object.modifier_apply(modifier=m.name)\n"
                "        except Exception: pass\n"
                "    # VOXEL REMESH — this is the magic: wraps all input geometry in ONE\n"
                "    # continuous mesh. Body + head + ears + legs become one creature shape.\n"
                "    remesh = target.modifiers.new(name='OrganicMerge', type='REMESH')\n"
                "    remesh.mode = 'VOXEL'\n"
                "    remesh.voxel_size = 0.06\n"
                "    remesh.use_smooth_shade = True\n"
                "    try:\n"
                "        bpy.ops.object.modifier_apply(modifier=remesh.name)\n"
                "    except Exception as e:\n"
                "        print(f'[composer] remesh apply failed: {e}')\n"
                "    # Smooth the result with light subdivision\n"
                "    sub = target.modifiers.new(name='OrganicSmooth', type='SUBSURF')\n"
                "    sub.levels = 1; sub.render_levels = 2\n"
                "    for p in target.data.polygons: p.use_smooth = True\n"
                f"__result__ = f'remeshed {{joined}} parts into {hero_name}'\n"
            )
            runner.run("join_organic", "execute_python", {"code": join_code})

    # Tag hero for HERO_VERIFY
    if hero_name:
        runner.run("tag_hero", "execute_python", {
            "code": f"obj = bpy.data.objects.get('{hero_name}'); obj['is_forced_hero']=True; obj['hero']=True; __result__=obj.name",
        })

    # ── GROUND THE CHARACTER (Phase 15)
    # Procedural patterns place parts with feet/wheels at z<0 (e.g. legs at z=-0.1).
    # Result: the hero looks like it's floating above or sinking into the ground plane.
    # Fix: compute the lowest world-space Z across all placed parts and lift them so
    # the lowest point sits at z=0 (on the ground plane). Skip celestial — those float.
    GROUNDED_PATTERNS = {"quadruped", "biped", "vehicle"}
    if base_pattern in GROUNDED_PATTERNS and placed_part_names:
        names_repr = repr(placed_part_names)
        ground_code = (
            "import bpy\n"
            "from mathutils import Vector\n"
            f"names = {names_repr}\n"
            "objs = [bpy.data.objects.get(n) for n in names]\n"
            "objs = [o for o in objs if o is not None and o.type in ('MESH', 'META')]\n"
            "# Force depsgraph update so bbox reflects latest modifiers/positions\n"
            "bpy.context.view_layer.update()\n"
            "min_z = float('inf')\n"
            "for o in objs:\n"
            "    for corner in o.bound_box:\n"
            "        wp = o.matrix_world @ Vector(corner)\n"
            "        if wp.z < min_z:\n"
            "            min_z = wp.z\n"
            "delta = -min_z if min_z != float('inf') else 0.0\n"
            "# Only lift if there's a real gap or sinkage (>1mm). Small tolerance avoids jitter.\n"
            "if abs(delta) > 0.001:\n"
            "    for o in objs:\n"
            "        o.location.z += delta\n"
            "    bpy.context.view_layer.update()\n"
            "__result__ = f'grounded delta={delta:.3f}'\n"
        )
        runner.run("ground_character", "execute_python", {"code": ground_code})

    # ── FUR for quadrupeds (Phase 15). Real strand particles → reads as actual
    # fur instead of a smooth painted ball. Tier-scaled so previews stay fast.
    FURRY_SPECIES = {"cat", "dog", "fox", "rabbit", "sheep", "horse", "lion", "bear", "wolf"}
    species_hint = " ".join([
        str(subj.get("library_query") or ""),
        str(subj.get("name") or ""),
    ]).lower()
    # Phase 17: TripoSR/InstantMesh meshes already capture the surface in vertex
    # colors and silhouette. Adding fur particles on top kills perf (24k strands
    # × 76k polys) and re-introduces the "fluffy peanut" appearance we just removed.
    if base_pattern == "quadruped" and hero_name and not asset_gen_hero_name and any(sp in species_hint for sp in FURRY_SPECIES):
        tier = scene.get("render_tier") or subj.get("render_tier") or "fast"
        # Lower counts — 3k+ on a 2m hero became a hairball that occluded the shape.
        # These are TUNED for visible fur silhouette without losing the dog underneath.
        fur_count = {"preview": 400, "fast": 800, "standard": 2000, "cinematic": 5000}.get(tier, 800)
        # Shorter strands too — old 0.08m on a 1.5m subject was overpowering
        fur_length = 0.03 if "sheep" in species_hint else (0.06 if "lion" in species_hint or "bear" in species_hint else 0.04)
        try:
            runner.run("fur", "add_fur", {
                "object": hero_name,
                "count": fur_count,
                "length": fur_length,
                "children": 30 if tier in ("preview", "fast") else 80,
                "roughness": 0.85,
            })
        except Exception as e:
            # Non-fatal — fur is a polish step. Log via job_events if available.
            print(f"[composer] fur add failed (non-fatal): {e}")

    # ── Compute hero_loc + actual bbox-driven scale.
    # Metaball output and pattern-composed shapes have unpredictable bbox sizes
    # compared to slot.scale. Query the actual hero object's dimensions and
    # use that to scale camera distance correctly.
    hero_loc = list(subj.get("location", [0, 0, 1]))
    hero_scale = float(subj.get("scale", 1.0))
    if hero_name:
        try:
            info = registry.call("get_object_info", {"name": hero_name})
            if isinstance(info, dict) and info.get("location"):
                hero_loc = info["location"]
            if isinstance(info, dict) and info.get("dimensions"):
                # Use the longest axis of the actual bbox as our scale reference.
                # A 1.0 reference matches "a 2m cube at distance 4.8m" (medium framing).
                dims = info["dimensions"]
                longest_dim = max(dims)
                # Default reference is a 2m cube → hero_scale 1.0
                hero_scale = max(0.5, longest_dim / 2.0)
        except Exception:
            pass  # fall back to slot values

    # ── ENVIRONMENT (mood-driven, replaces the dumb gray ground from before)
    env = env_module.env_for_mood(scene.get("mood", "neutral"))

    # Try HDRI first (photoreal lighting + reflections). Fall back to flat sky if no file.
    from pathlib import Path as _Path
    backend_root = _Path(__file__).resolve().parents[2]
    hdri_dir = backend_root / "assets" / "hdri"
    hdri_path = env_module.hdri_for_mood(scene.get("mood", "neutral"), hdri_dir)
    if hdri_path is not None:
        # Phase 17: asset-gen meshes carry vertex colors that already encode
        # the SDXL reference's lighting. A 2.0 HDRI on top blows them out.
        # Drop strength by ~40% in asset-gen mode so the surface colors read.
        hdri_strength = env.get("sky_strength", 1.0)
        if asset_gen_hero_name:
            hdri_strength = min(hdri_strength, 1.2)
        runner.run("world_hdri", "set_hdri_environment", {
            "hdri_path": str(hdri_path),
            "strength": hdri_strength,
        })
    else:
        runner.run("world_bg", "set_world_background", {
            "color": env["sky_color"], "strength": env["sky_strength"],
        })

    # Ground plane — always create one if user mentioned ground, OR if mood is outdoor
    outdoor_moods = {"sunset", "sunrise", "golden hour", "dawn", "dusk", "noon", "daylight", "night", "moonlight", "bright"}
    needs_ground = scene.get("ground") or scene.get("mood") in outdoor_moods
    if needs_ground:
        ground_mat_name = f"GroundMat_{run_id}"
        runner.run("ground", "create_primitive", {
            "type": "plane", "name": "Ground", "location": [0, 0, 0], "size": 40.0,
        })
        runner.run("ground_material", "create_material", {
            "name": ground_mat_name, "color": env["ground_color"],
            "metallic": env["ground_metallic"], "roughness": env["ground_roughness"],
        })
        runner.run("ground_apply", "apply_material", {"object": "Ground", "material": ground_mat_name})

    # Shade-smooth all organic parts so subdivision actually softens the silhouette
    organic_names = [p["name"] for p in parts if p.get("primitive") in ("sphere", "icosphere") and p.get("role") in ("body", "head", "limb", "detail")]
    if organic_names:
        smooth_code = "; ".join([
            f"o = bpy.data.objects.get('{n}'); "
            f"[setattr(p, 'use_smooth', True) for p in o.data.polygons] if o and o.data else None"
            for n in organic_names
        ])
        runner.run("shade_smooth", "execute_python", {"code": smooth_code + "; __result__ = 'smoothed'"})

    # 8. Lighting (mood-driven). For asset-gen meshes, halve the energies —
    # the SDXL reference already baked lighting into vertex colors, so the
    # 3-point rig is just for shape definition/contact shadows, not exposure.
    light_params = _lighting_params_from_mood(scene.get("mood", "neutral"))
    light_scale = 0.5 if asset_gen_hero_name else 1.0
    runner.run("lighting", "apply_three_point_lighting", {
        "target": hero_loc,
        "color_temp": light_params.get("color_temp", "neutral"),
        "key_energy": light_params.get("key_energy", 1500) * light_scale,
        "fill_energy": light_params.get("fill_energy", 500) * light_scale,
        "rim_energy": light_params.get("rim_energy", 800) * light_scale,
    })

    # 9. Camera (framing + angle)
    cam_xyz, look_target = _camera_position_for_framing(
        cam_slots.get("framing", "medium"),
        cam_slots.get("angle", "three-quarter"),
        hero_loc, hero_scale,
    )
    runner.run("camera", "create_camera", {"name": "Cam", "location": cam_xyz, "lens": 50.0, "set_active": True})
    runner.run("look_at", "look_at", {"object": "Cam", "target": look_target})

    # 10. Motion (always — every render is a video)
    if is_animation:
        m_type = motion.get("type", "static")
        speed = motion.get("speed", "medium")

        if m_type == "ambient_orbit":
            # Subtle camera arc for static prompts — quarter rotation over 5s
            radius = math.dist(cam_xyz, look_target)
            runner.run("ambient_orbit", "orbit_camera_around", {
                "camera": "Cam", "target": look_target,
                "radius": radius, "height": cam_xyz[2] - look_target[2],
                "duration_frames": total_frames,
                "revolutions": 0.25,   # quarter turn = cinematic dolly feel
            })
        elif m_type == "orbit":
            # camera circles the hero
            radius = math.dist(cam_xyz, look_target)
            runner.run("orbit", "orbit_camera_around", {
                "camera": "Cam", "target": look_target,
                "radius": radius, "height": cam_xyz[2] - look_target[2],
                "duration_frames": total_frames,
                "revolutions": _revolutions_for_speed(speed),
            })
        elif m_type == "rotate_self":
            # hero spins in place around Z
            rotation_amount = _rotation_radians_for_speed(speed)
            runner.run("rotate_self", "animate_property", {
                "object": hero_name, "data_path": "rotation_euler",
                "start_value": [0, 0, 0],
                "end_value": [0, 0, rotation_amount],
                "start_frame": 1, "end_frame": total_frames,
            })
        elif m_type == "translate":
            # hero moves across the scene (default: -X to +X)
            # For organic creatures, layer a walking bounce on top of the X motion
            distance = {"slow": 4, "medium": 8, "fast": 14}.get(speed, 8)
            organic = base_pattern in ORGANIC_PATTERNS
            bounce_h = 0.15 if organic else 0.0
            # 5 keyframes for walking gait — start, peak1, down (mid), peak2, end
            walk_path = [
                (1,                     [hero_loc[0] - distance / 2,        hero_loc[1], hero_loc[2]]),
                (int(total_frames*0.25), [hero_loc[0] - distance / 4,        hero_loc[1], hero_loc[2] + bounce_h]),
                (int(total_frames*0.50), [hero_loc[0],                       hero_loc[1], hero_loc[2]]),
                (int(total_frames*0.75), [hero_loc[0] + distance / 4,        hero_loc[1], hero_loc[2] + bounce_h]),
                (total_frames,           [hero_loc[0] + distance / 2,        hero_loc[1], hero_loc[2]]),
            ]
            for frame, loc in walk_path:
                runner.run(f"walk_kf_{frame}", "set_keyframe", {
                    "object": hero_name, "data_path": "location",
                    "value": loc, "frame": frame,
                })
        elif m_type == "bounce":
            # hero bounces up — chain 3 keyframes via two animate_property calls
            up = [hero_loc[0], hero_loc[1], hero_loc[2] + 2.0]
            mid_frame = total_frames // 2
            runner.run("bounce_up", "animate_property", {
                "object": hero_name, "data_path": "location",
                "start_value": hero_loc, "end_value": up,
                "start_frame": 1, "end_frame": mid_frame,
            })
            runner.run("bounce_down", "animate_property", {
                "object": hero_name, "data_path": "location",
                "start_value": up, "end_value": hero_loc,
                "start_frame": mid_frame, "end_frame": total_frames,
            })
        elif m_type == "drift":
            # gentle XY drift
            distance = 2.0
            end = [hero_loc[0] + distance, hero_loc[1] + distance * 0.5, hero_loc[2]]
            runner.run("drift", "animate_property", {
                "object": hero_name, "data_path": "location",
                "start_value": hero_loc, "end_value": end,
                "start_frame": 1, "end_frame": total_frames,
            })

    # ── 10b. IDLE LIFE — organic creatures breathe; celestial bodies rotate.
    # These layer ON TOP of the motion patterns so subjects feel alive whether
    # they're static or moving.
    if is_animation and hero_name:
        # Breathing for creatures during ambient_orbit (static prompt → camera-moves only)
        if base_pattern in ORGANIC_PATTERNS and motion.get("type") == "ambient_orbit":
            breath_code = (
                "import bpy\n"
                f"o = bpy.data.objects.get('{hero_name}')\n"
                "if o:\n"
                "    sx, sy, sz = o.scale.x, o.scale.y, o.scale.z\n"
                "    # 5 keyframes: rest → inhale → rest → inhale → rest\n"
                "    for f, mult in [(1, 1.00), (30, 1.03), (60, 1.00), (90, 1.03), (120, 1.00)]:\n"
                "        o.scale = (sx, sy * mult, sz * (1.0 + (mult-1) * 0.5))\n"
                "        o.keyframe_insert(data_path='scale', frame=f)\n"
                "__result__ = 'breathing'\n"
            )
            runner.run("idle_breathing", "execute_python", {"code": breath_code})

        # Celestial bodies rotate on Z axis — planets spin
        if base_pattern == "celestial":
            import math as _m
            # ~0.3 of a full rotation in 5s (slow majestic spin)
            rotation_z = _m.pi * 0.6
            runner.run("planet_spin_start", "set_keyframe", {
                "object": hero_name, "data_path": "rotation_euler",
                "value": [0, 0, 0], "frame": 1,
            })
            runner.run("planet_spin_end", "set_keyframe", {
                "object": hero_name, "data_path": "rotation_euler",
                "value": [0, 0, rotation_z], "frame": total_frames,
            })

        # Trees sway gently — subtle Y-axis tilt back and forth
        if base_pattern == "tree":
            sway_code = (
                "import bpy, math\n"
                f"o = bpy.data.objects.get('{hero_name}')\n"
                "if o:\n"
                "    for f, deg in [(1, 0), (30, 2), (60, 0), (90, -2), (120, 0)]:\n"
                "        o.rotation_euler = (0, math.radians(deg), 0)\n"
                "        o.keyframe_insert(data_path='rotation_euler', frame=f)\n"
                "__result__ = 'swaying'\n"
            )
            runner.run("tree_sway", "execute_python", {"code": sway_code})

    # 11. Verify (informational — we don't abort on failure)
    verify_result = runner.run("verify", "hero_verify", {})
    if verbose and isinstance(verify_result, dict):
        passed = verify_result.get("passed")
        print(f"[composer] hero_verify: {'PASS' if passed else 'FAIL (continuing anyway)'}")
        if not passed:
            for r in verify_result.get("abort_reasons", []):
                print(f"[composer]   • {r}")

    # 12. Render — skipped entirely in --no-render mode
    if no_render:
        if verbose:
            print("[composer] NO-RENDER: skipping render_animation + encode_video.")
        # Still produce a render_path/video_path placeholder so the .blend save uses a real basename.
        result.render_path = paths.get("render_filepath")
    elif is_animation:
        anim_dir = paths["animation_dir"]
        video_path = paths["video_filepath"]
        runner.run("render_animation", "render_animation", {
            "output_dir": anim_dir,
            "frame_start": 1, "frame_end": total_frames, "fps": fps,
        }, critical=True)

        # 12a. Phase 16 — diffusion refinement (optional, between render and encode)
        _maybe_refine_animation(anim_dir, slots, scene, subj, runner, verbose=verbose)

        runner.run("encode_video", "encode_video", {
            "frame_dir": anim_dir, "mp4_path": video_path, "fps": fps,
        }, critical=True)
        result.video_path = video_path
        result.render_path = str(Path(anim_dir) / "frame_0001.png")
    else:
        render_path = paths["render_filepath"]
        runner.run("render_frame", "render_frame", {"filepath": render_path}, critical=True)

        # 12a. Phase 16 — single-frame refinement
        _maybe_refine_single(render_path, slots, scene, subj, runner, verbose=verbose)

        result.render_path = render_path

    # Phase 17 deliverable: ship a .blend file alongside the MP4 so users
    # can open it in Blender and tweak. Saved BEFORE we declare success so
    # a failed save shows up in errors but doesn't kill the render.
    primary_artifact = result.video_path or result.render_path
    if primary_artifact:
        blend_path = str(Path(primary_artifact).with_suffix(".blend"))
        try:
            save_res = runner.run("save_blend", "save_blend_file", {
                "filepath": blend_path,
                "compress": True,
            }, critical=False)
            if isinstance(save_res, dict) and save_res.get("ok"):
                result.blend_path = blend_path
        except Exception as e:
            if verbose:
                print(f"[composer] save_blend skipped: {type(e).__name__}: {e}")

    result.success = result.render_path is not None and (
        not is_animation or result.video_path is not None
    )
    result.duration_s = time.time() - t0

    if verbose:
        artifact = result.video_path or result.render_path
        print(f"[composer] DONE in {result.duration_s:.1f}s — {len(result.steps_run)} steps, "
              f"{len(result.errors)} errors")
        print(f"[composer] artifact: {artifact}")
        if getattr(result, "blend_path", None):
            print(f"[composer] blend file: {result.blend_path}")

    return result
