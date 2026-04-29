"""
Fantasy Studio — Cinematic Post-Processing Pipeline
====================================================

Builds a Blender compositor node tree programmatically with up to 7 effects:

  1. Depth of Field (camera-level, not compositor)
  2. Vignette (ellipse mask + multiply)
  3. Bloom / Glare (fog glow)
  4. Color Grading (mood-based lift/gamma/gain + hue/sat)
  5. Film Grain (noise texture overlay)
  6. Atmospheric Mist / Fog (volumetric scatter cube)
  7. Lens Distortion (barrel + chromatic aberration)

Tier-based application:
  PREVIEW  — none (skip entirely)
  FAST     — bloom only (minimal)
  STANDARD — bloom + vignette + color grading + lens distortion
  CINEMATIC — all 7 effects at premium quality

Mood presets: warm, cool, neutral, dramatic, ethereal
Mood is inferred from scene_plan if not explicitly provided.

Usage from render_from_manifest.py:
    from app.scene.cinematic_compositor import build_cinematic_compositor, infer_mood
    mood = infer_mood(manifest.get("_scene_plan") or {})
    build_cinematic_compositor(scene, tier=tier, mood=mood, hero_object=hero_obj)
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("cinematic_compositor")


def apply_biome_grade(bpy, scene, tier: str = "fast") -> bool:
    """Apply biome color grade stored on scene by World Development.

    Reads ``scene['wd_grade_lift']``, ``wd_grade_gamma``, ``wd_grade_gain``,
    and ``wd_grade_saturation`` custom properties (set by develop_world)
    and wires a compositor ColorBalance + HueSaturation chain.

    Skips preview tier.  Non-fatal — any failure logs and continues.
    Returns True if grade was applied.
    """
    if str(tier).lower() == "preview":
        return False
    try:
        lift = list(scene.get("wd_grade_lift") or [0.0, 0.0, 0.0])
        gamma = list(scene.get("wd_grade_gamma") or [1.0, 1.0, 1.0])
        gain = list(scene.get("wd_grade_gain") or [1.0, 1.0, 1.0])
        sat = float(scene.get("wd_grade_saturation") or 1.0)
        biome = str(scene.get("wd_biome") or "unknown")

        # No-op: all neutral
        if (
            all(abs(v) < 0.001 for v in lift)
            and all(abs(v - 1.0) < 0.001 for v in gamma)
            and all(abs(v - 1.0) < 0.001 for v in gain)
            and abs(sat - 1.0) < 0.001
        ):
            print(f"[WORLD_DEV/GRADE] biome={biome} neutral — skipping", flush=True)
            return False

        # Enable compositor nodes.  Wrap the attribute access in try/except
        # because some Blender 5.x builds have moved node_tree access behind
        # scene.compositing_node_group.
        scene.use_nodes = True
        nt = None
        try:
            nt = scene.node_tree
        except AttributeError:
            try:
                nt = scene.compositing_node_group
            except AttributeError:
                nt = None
        if nt is None:
            print(
                f"[WORLD_DEV/GRADE] scene has no compositor node_tree — "
                f"skipping (Blender API drift)",
                flush=True,
            )
            return False

        # Find existing RenderLayers + Composite or create them
        rl_node = None
        comp_node = None
        for n in nt.nodes:
            if n.type == "R_LAYERS":
                rl_node = n
            elif n.type == "COMPOSITE":
                comp_node = n
        if rl_node is None:
            rl_node = nt.nodes.new("CompositorNodeRLayers")
        if comp_node is None:
            comp_node = nt.nodes.new("CompositorNodeComposite")

        # Append a color-balance + hue-sat BEFORE the composite output.
        # Find the current input source of the composite (the node connected
        # to its "Image" input).  We'll insert our chain between.
        upstream_socket = None
        upstream_link = None
        for link in nt.links:
            if link.to_node == comp_node and link.to_socket.name == "Image":
                upstream_socket = link.from_socket
                upstream_link = link
                break
        if upstream_socket is None:
            upstream_socket = rl_node.outputs.get("Image")

        cb = nt.nodes.new("CompositorNodeColorBalance")
        try:
            cb.correction_method = "LIFT_GAMMA_GAIN"
            cb.lift = (
                max(0.0, 1.0 + lift[0]),
                max(0.0, 1.0 + lift[1]),
                max(0.0, 1.0 + lift[2]),
                1.0,
            )
            cb.gamma = (max(0.01, gamma[0]), max(0.01, gamma[1]), max(0.01, gamma[2]), 1.0)
            cb.gain  = (max(0.0, gain[0]), max(0.0, gain[1]), max(0.0, gain[2]), 1.0)
        except Exception as e:
            print(f"[WORLD_DEV/GRADE] color balance setup warning: {e}", flush=True)

        hsat = nt.nodes.new("CompositorNodeHueSat")
        try:
            hsat.color_saturation = float(sat)
        except Exception:
            pass

        # Wire: upstream_socket -> cb.Image -> hsat.Image -> comp.Image
        if upstream_link is not None:
            try:
                nt.links.remove(upstream_link)
            except Exception:
                pass
        try:
            nt.links.new(upstream_socket, cb.inputs["Image"])
            nt.links.new(cb.outputs["Image"], hsat.inputs["Image"])
            nt.links.new(hsat.outputs["Image"], comp_node.inputs["Image"])
        except Exception as e:
            print(f"[WORLD_DEV/GRADE] link wiring warning: {e}", flush=True)
            return False

        print(
            f"[WORLD_DEV/GRADE] biome={biome} "
            f"lift={tuple(lift)} gain={tuple(gain)} "
            f"sat={sat} applied_to_tier={tier}",
            flush=True,
        )
        return True
    except Exception as e:
        print(f"[WORLD_DEV/GRADE] non-fatal error: {e}", flush=True)
        return False

# ---------------------------------------------------------------------------
# Mood Presets — lift/gamma/gain + hue/saturation adjustments
# ---------------------------------------------------------------------------
_MOOD_PRESETS = {
    "warm": {
        "lift":  (1.02, 0.98, 0.94),
        "gamma": (1.01, 1.00, 0.98),
        "gain":  (1.04, 1.01, 0.96),
        "hue":         0.50,
        "saturation":  1.08,
        "value":       1.02,
    },
    "cool": {
        "lift":  (0.94, 0.97, 1.03),
        "gamma": (0.98, 1.00, 1.02),
        "gain":  (0.96, 1.00, 1.05),
        "hue":         0.50,
        "saturation":  1.05,
        "value":       1.00,
    },
    "neutral": {
        "lift":  (1.00, 1.00, 1.00),
        "gamma": (1.00, 1.00, 1.00),
        "gain":  (1.00, 1.00, 1.00),
        "hue":         0.50,
        "saturation":  1.00,
        "value":       1.00,
    },
    "dramatic": {
        "lift":  (0.96, 0.94, 1.02),
        "gamma": (1.02, 0.98, 0.98),
        "gain":  (1.06, 1.00, 0.94),
        "hue":         0.50,
        "saturation":  1.15,
        "value":       1.04,
    },
    "ethereal": {
        "lift":  (0.98, 1.00, 1.04),
        "gamma": (1.01, 1.02, 1.03),
        "gain":  (1.00, 1.02, 1.06),
        "hue":         0.50,
        "saturation":  0.90,
        "value":       1.06,
    },
}

# ---------------------------------------------------------------------------
# Tier → effect matrix
# ---------------------------------------------------------------------------
_TIER_EFFECTS = {
    "preview": set(),
    "fast":    {"bloom"},
    "standard": {"bloom", "vignette", "color_grading", "lens_distortion"},
    "ultra":   {"bloom", "vignette", "color_grading", "lens_distortion",
                "film_grain", "dof"},
    "cinematic": {"bloom", "vignette", "color_grading", "lens_distortion",
                  "film_grain", "dof", "atmospheric_fog"},
}

# Tier-specific DoF f-stop values (lower = shallower depth of field)
_DOF_FSTOPS = {
    "ultra":    5.6,
    "cinematic": 2.8,
}

# Tier-specific bloom quality
_BLOOM_QUALITY = {
    "fast":      "LOW",
    "standard":  "MEDIUM",
    "ultra":     "HIGH",
    "cinematic": "HIGH",
}


# ---------------------------------------------------------------------------
# Mood inference from scene plan
# ---------------------------------------------------------------------------
def infer_mood(scene_plan: dict) -> str:
    """
    Derive a mood string from the scene plan dictionary.

    Priority:
        1. Explicit ``mood`` key in the plan
        2. Inference from ``time_of_day``
        3. Inference from ``environment`` / ``environment_preset``
        4. Fallback to ``neutral``
    """
    if not scene_plan:
        return "neutral"

    explicit = (scene_plan.get("mood") or "").strip().lower()
    if explicit in _MOOD_PRESETS:
        return explicit

    # Map explicit mood keywords that aren't exact preset names
    _MOOD_SYNONYMS = {
        "happy": "warm", "cheerful": "warm", "sunny": "warm",
        "romantic": "warm", "cozy": "warm", "golden": "warm",
        "cold": "cool", "icy": "cool", "winter": "cool",
        "serene": "cool", "calm": "cool", "peaceful": "cool",
        "dark": "dramatic", "intense": "dramatic", "moody": "dramatic",
        "noir": "dramatic", "gritty": "dramatic", "horror": "dramatic",
        "dreamy": "ethereal", "mystical": "ethereal", "fantasy": "ethereal",
        "magical": "ethereal", "otherworldly": "ethereal", "foggy": "ethereal",
    }
    if explicit in _MOOD_SYNONYMS:
        return _MOOD_SYNONYMS[explicit]

    # Infer from time of day
    tod = (scene_plan.get("time_of_day") or "").strip().lower()
    _TOD_MAP = {
        "golden_hour": "warm", "sunset": "warm", "sunrise": "warm",
        "dawn": "ethereal", "dusk": "dramatic",
        "night": "dramatic", "midnight": "dramatic",
        "overcast": "cool", "cloudy": "cool",
        "noon": "neutral", "midday": "neutral", "day": "neutral",
    }
    if tod in _TOD_MAP:
        return _TOD_MAP[tod]

    # Infer from environment
    env = (
        scene_plan.get("environment")
        or scene_plan.get("environment_preset")
        or ""
    ).strip().lower()
    if any(kw in env for kw in ("snow", "ice", "arctic", "tundra")):
        return "cool"
    if any(kw in env for kw in ("desert", "volcano", "lava", "fire")):
        return "warm"
    if any(kw in env for kw in ("space", "nebula", "cosmos", "alien")):
        return "ethereal"
    if any(kw in env for kw in ("dungeon", "cave", "ruin", "storm")):
        return "dramatic"

    return "neutral"


# ---------------------------------------------------------------------------
# Depth of Field (camera-level, not compositor)
# ---------------------------------------------------------------------------
def _setup_dof(scene, tier: str, hero_object=None):
    """
    Enable camera depth of field.
    Focus is set on hero_object if available, otherwise at a fixed distance.
    """
    try:
        import bpy

        cam = scene.camera
        if not cam or not hasattr(cam, "data"):
            logger.warning("No camera found — skipping DoF setup")
            return

        cam_data = cam.data
        cam_data.dof.use_dof = True
        cam_data.dof.aperture_fstop = _DOF_FSTOPS.get(tier, 5.6)
        cam_data.dof.aperture_blades = 6

        if hero_object and hero_object.name in bpy.data.objects:
            cam_data.dof.focus_object = hero_object
            logger.info(
                "DoF: focus on '%s', f/%.1f",
                hero_object.name, cam_data.dof.aperture_fstop,
            )
        else:
            # Fallback: focus 5m in front of camera
            cam_data.dof.focus_distance = 5.0
            cam_data.dof.focus_object = None
            logger.info(
                "DoF: fixed distance 5m, f/%.1f", cam_data.dof.aperture_fstop
            )

        print(
            f"[COMPOSITOR] DoF enabled: f/{cam_data.dof.aperture_fstop} "
            f"blades={cam_data.dof.aperture_blades} "
            f"focus={'object:' + hero_object.name if hero_object else 'distance:5m'}",
            flush=True,
        )
    except Exception as e:
        logger.error("DoF setup failed (non-fatal): %s", e)
        print(f"[COMPOSITOR] DoF setup skipped: {e}", flush=True)


# ---------------------------------------------------------------------------
# Atmospheric Fog (volumetric scatter cube)
# ---------------------------------------------------------------------------
def _add_atmospheric_fog(scene, mood: str, tier: str):
    """
    Create a large volume scatter cube to simulate atmospheric haze/fog.
    Density and color vary by mood.
    """
    try:
        import bpy

        _FOG_PARAMS = {
            "warm":     {"density": 0.003, "color": (1.0, 0.92, 0.82)},
            "cool":     {"density": 0.004, "color": (0.85, 0.90, 1.0)},
            "neutral":  {"density": 0.002, "color": (0.95, 0.95, 0.95)},
            "dramatic": {"density": 0.006, "color": (0.80, 0.78, 0.85)},
            "ethereal": {"density": 0.008, "color": (0.88, 0.92, 1.0)},
        }

        params = _FOG_PARAMS.get(mood, _FOG_PARAMS["neutral"])

        # Reduce density for non-cinematic tiers
        density = params["density"]
        if tier == "ultra":
            density *= 0.6

        bpy.ops.mesh.primitive_cube_add(size=200, location=(0, 0, 10))
        fog_cube = bpy.context.active_object
        fog_cube.name = "CinematicFog_Volume"
        fog_cube.display_type = 'BOUNDS'

        # Create volume scatter material
        mat = bpy.data.materials.new(name="CinematicFog_Material")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()

        output_node = nt.nodes.new("ShaderNodeOutputMaterial")
        output_node.label = "Fog Output"
        output_node.location = (300, 0)

        scatter = nt.nodes.new("ShaderNodeVolumeScatter")
        scatter.label = "Fog Scatter"
        scatter.inputs["Density"].default_value = density
        scatter.inputs["Color"].default_value = (*params["color"], 1.0)
        scatter.inputs["Anisotropy"].default_value = 0.3
        scatter.location = (0, 0)

        nt.links.new(scatter.outputs["Volume"], output_node.inputs["Volume"])

        fog_cube.data.materials.append(mat)
        fog_cube.hide_render = False
        fog_cube.hide_viewport = True  # Visible only during render

        print(
            f"[COMPOSITOR] Atmospheric fog: mood={mood} "
            f"density={density:.4f} color={params['color']}",
            flush=True,
        )
    except Exception as e:
        logger.error("Atmospheric fog failed (non-fatal): %s", e)
        print(f"[COMPOSITOR] Atmospheric fog skipped: {e}", flush=True)


# ---------------------------------------------------------------------------
# Main compositor builder
# ---------------------------------------------------------------------------
def build_cinematic_compositor(
    scene,
    tier: str = "standard",
    mood: str = "neutral",
    hero_object=None,
):
    """
    Build the full cinematic compositor node tree.

    Replaces the existing compositor nodes. Each effect is wrapped in
    try/except so a single failure doesn't break the render.

    Parameters
    ----------
    scene : bpy.types.Scene
        The active Blender scene.
    tier : str
        Render tier name (preview/fast/standard/ultra/cinematic).
    mood : str
        Color grading mood (warm/cool/neutral/dramatic/ethereal).
    hero_object : bpy.types.Object, optional
        The primary subject for DoF focus.
    """
    effects = _TIER_EFFECTS.get(tier, _TIER_EFFECTS["standard"])
    mood_preset = _MOOD_PRESETS.get(mood, _MOOD_PRESETS["neutral"])

    print(
        f"[COMPOSITOR] Building cinematic compositor: "
        f"tier={tier} mood={mood} effects={sorted(effects)}",
        flush=True,
    )

    if not effects:
        try:
            scene.use_nodes = False
        except Exception:
            pass
        print("[COMPOSITOR] No effects for this tier — compositor disabled", flush=True)
        return

    # --- Camera-level DoF (not a compositor node) ---
    if "dof" in effects:
        _setup_dof(scene, tier, hero_object)

    # --- Atmospheric fog (scene-level volume, not a compositor node) ---
    if "atmospheric_fog" in effects:
        _add_atmospheric_fog(scene, mood, tier)

    # --- Build compositor node tree ---
    try:
        scene.use_nodes = True
        nt = scene.node_tree
        nodes = nt.nodes
        links = nt.links
        nodes.clear()

        # Render Layers input
        rl = nodes.new("CompositorNodeRLayers")
        rl.label = "Render Layers"
        rl.location = (0, 0)

        last_output = rl.outputs["Image"]
        x_offset = 300

        # ── 1. Bloom / Glare ──────────────────────────────────────────
        if "bloom" in effects:
            try:
                glare = nodes.new("CompositorNodeGlare")
                glare.label = "Cinematic Bloom"
                glare.glare_type = "FOG_GLOW"
                glare.quality = _BLOOM_QUALITY.get(tier, "MEDIUM")
                glare.threshold = 0.80 if tier == "cinematic" else 0.85
                glare.size = 7 if tier == "cinematic" else 6
                glare.location = (x_offset, 0)
                links.new(last_output, glare.inputs["Image"])
                last_output = glare.outputs["Image"]
                x_offset += 250
                print("[COMPOSITOR]   + Bloom/Glare enabled", flush=True)
            except Exception as e:
                print(f"[COMPOSITOR]   ! Bloom skipped: {e}", flush=True)

        # ── 2. Color Grading (mood-based) ─────────────────────────────
        if "color_grading" in effects:
            try:
                # Lift/Gamma/Gain color balance
                cb = nodes.new("CompositorNodeColorBalance")
                cb.label = f"Color Grade — {mood.title()}"
                cb.correction_method = "LIFT_GAMMA_GAIN"
                cb.lift = mood_preset["lift"]
                cb.gamma = mood_preset["gamma"]
                cb.gain = mood_preset["gain"]
                cb.location = (x_offset, 0)
                links.new(last_output, cb.inputs["Image"])
                last_output = cb.outputs["Image"]
                x_offset += 250

                # Hue/Saturation/Value fine-tuning
                hsv = nodes.new("CompositorNodeHueSat")
                hsv.label = f"HSV Adjust — {mood.title()}"
                hsv.inputs["Hue"].default_value = mood_preset["hue"]
                hsv.inputs["Saturation"].default_value = mood_preset["saturation"]
                hsv.inputs["Value"].default_value = mood_preset["value"]
                hsv.inputs["Fac"].default_value = 1.0
                hsv.location = (x_offset, 0)
                links.new(last_output, hsv.inputs["Image"])
                last_output = hsv.outputs["Image"]
                x_offset += 250

                print(
                    f"[COMPOSITOR]   + Color grading: mood={mood} "
                    f"sat={mood_preset['saturation']:.2f}",
                    flush=True,
                )
            except Exception as e:
                print(f"[COMPOSITOR]   ! Color grading skipped: {e}", flush=True)

        # ── 3. Vignette ───────────────────────────────────────────────
        if "vignette" in effects:
            try:
                mask = nodes.new("CompositorNodeEllipseMask")
                mask.label = "Vignette Mask"
                mask.x = 0.5
                mask.y = 0.5
                mask.width = 0.80 if tier == "cinematic" else 0.82
                mask.height = 0.80 if tier == "cinematic" else 0.82
                mask.location = (x_offset, -300)

                blur = nodes.new("CompositorNodeBlur")
                blur.label = "Vignette Blur"
                blur.size_x = 250
                blur.size_y = 250
                blur.use_relative = False
                blur.filter_type = "FAST_GAUSS"
                blur.location = (x_offset + 250, -300)
                links.new(mask.outputs["Mask"], blur.inputs["Image"])

                mix = nodes.new("CompositorNodeMixRGB")
                mix.label = "Vignette Mix"
                mix.blend_type = "MULTIPLY"
                # Stronger vignette for dramatic/cinematic
                if mood == "dramatic":
                    mix.inputs["Fac"].default_value = 0.45
                elif tier == "cinematic":
                    mix.inputs["Fac"].default_value = 0.40
                else:
                    mix.inputs["Fac"].default_value = 0.35
                mix.location = (x_offset + 250, 0)
                links.new(last_output, mix.inputs[1])
                links.new(blur.outputs["Image"], mix.inputs[2])
                last_output = mix.outputs["Image"]
                x_offset += 500

                print("[COMPOSITOR]   + Vignette enabled", flush=True)
            except Exception as e:
                print(f"[COMPOSITOR]   ! Vignette skipped: {e}", flush=True)

        # ── 4. Film Grain ─────────────────────────────────────────────
        if "film_grain" in effects:
            try:
                # Use a noise texture mixed in at very low opacity
                tex = nodes.new("CompositorNodeTexture")
                tex.label = "Film Grain Texture"
                tex.location = (x_offset, -300)

                # Create noise texture in bpy.data
                import bpy
                noise_tex = bpy.data.textures.new("CinematicGrain", type="NOISE")
                noise_tex.noise_scale = 0.5
                tex.texture = noise_tex

                grain_mix = nodes.new("CompositorNodeMixRGB")
                grain_mix.label = "Film Grain Mix"
                grain_mix.blend_type = "OVERLAY"
                grain_mix.inputs["Fac"].default_value = (
                    0.06 if tier == "cinematic" else 0.04
                )
                grain_mix.location = (x_offset + 250, 0)
                links.new(last_output, grain_mix.inputs[1])
                links.new(tex.outputs[0], grain_mix.inputs[2])
                last_output = grain_mix.outputs["Image"]
                x_offset += 500

                print("[COMPOSITOR]   + Film grain enabled", flush=True)
            except Exception as e:
                print(f"[COMPOSITOR]   ! Film grain skipped: {e}", flush=True)

        # ── 5. Lens Distortion ────────────────────────────────────────
        if "lens_distortion" in effects:
            try:
                lens = nodes.new("CompositorNodeLensdist")
                lens.label = "Lens Distortion"
                lens.use_fit = True
                # Subtle barrel distortion + chromatic aberration
                if tier == "cinematic":
                    lens.inputs["Distort"].default_value = 0.008
                    lens.inputs["Dispersion"].default_value = 0.005
                else:
                    lens.inputs["Distort"].default_value = 0.005
                    lens.inputs["Dispersion"].default_value = 0.003
                lens.location = (x_offset, 0)
                links.new(last_output, lens.inputs["Image"])
                last_output = lens.outputs["Image"]
                x_offset += 250

                print("[COMPOSITOR]   + Lens distortion enabled", flush=True)
            except Exception as e:
                print(f"[COMPOSITOR]   ! Lens distortion skipped: {e}", flush=True)

        # ── Final output ──────────────────────────────────────────────
        comp = nodes.new("CompositorNodeComposite")
        comp.label = "Final Output"
        comp.location = (x_offset, 0)
        links.new(last_output, comp.inputs["Image"])

        print(
            f"[COMPOSITOR] Node tree complete: "
            f"{len(nodes)} nodes, {len(links)} links",
            flush=True,
        )

    except Exception as e:
        logger.error("Compositor build failed: %s", e)
        print(f"[COMPOSITOR] FATAL: compositor build failed: {e}", flush=True)
        # Fallback: disable compositor so render still works
        try:
            scene.use_nodes = False
        except Exception:
            pass
