from __future__ import annotations

"""
render_budget.py
================
Render budget analyzer and enforcer.

Controls Cycles render settings to achieve predictable render times per
quality tier while maintaining cinematic output quality.  Think of this as
the technical director who configures the render farm -- not the creative
director who designs the shot.

Applied AFTER scene construction and scene optimization, BEFORE render
begins.

Usage:
    from app.render.render_budget import apply_render_budget
    budget_info = apply_render_budget(bpy, scene, quality_tier, scene_plan)
"""

import time

# ═══════════════════════════════════════════════════════════════════════════
# Tier render configs -- the "intelligence" that a real TD would apply
# ═══════════════════════════════════════════════════════════════════════════
# These are tuned for "cinematic illusion with controlled compute":
# - Adaptive sampling does the heavy lifting (stops sampling clean pixels early)
# - Denoiser cleans up what's left
# - Bounce limits prevent infinite recursion in glass/SSS
# - Resolution scaling gives FAST tier a massive speedup

_BUDGET_CONFIGS = {
    "fast": {
        # Samples: low but denoiser compensates well
        "samples": 48,
        "adaptive_threshold": 0.05,
        "use_adaptive_sampling": True,
        "use_denoising": True,
        "denoiser": "OPENIMAGEDENOISE",
        "denoising_input_passes": "RGB_ALBEDO_NORMAL",
        # Bounces: enough for readable reflections and glass
        "max_bounces": 4,
        "diffuse_bounces": 2,
        "glossy_bounces": 3,
        "transmission_bounces": 2,
        "transparent_max_bounces": 2,
        "volume_bounces": 1,
        # Resolution: full res -- denoiser handles noise at low samples
        "resolution_percentage": 100,
        # Volumetrics: reduced but present
        "volume_step_rate": 8.0,
        "volume_max_steps": 64,
        # Caustics: expensive and rarely visible at this tier
        "use_caustics_reflective": False,
        "use_caustics_refractive": False,
        # Light paths
        "sample_clamp_indirect": 10.0,
        # Time budget (seconds)
        "time_budget_seconds": 1800,  # 30 minutes
    },
    "standard": {
        "samples": 128,
        "adaptive_threshold": 0.02,
        "use_adaptive_sampling": True,
        "use_denoising": True,
        "denoiser": "OPENIMAGEDENOISE",
        "denoising_input_passes": "RGB_ALBEDO_NORMAL",
        "max_bounces": 5,
        "diffuse_bounces": 3,
        "glossy_bounces": 3,
        "transmission_bounces": 4,
        "transparent_max_bounces": 4,
        "volume_bounces": 1,
        "resolution_percentage": 100,
        "volume_step_rate": 5.0,
        "volume_max_steps": 128,
        "use_caustics_reflective": False,
        "use_caustics_refractive": False,
        "sample_clamp_indirect": 10.0,
        "time_budget_seconds": 2400,  # 40 minutes
    },
    "ultra": {
        "samples": 256,
        "adaptive_threshold": 0.008,
        "use_adaptive_sampling": True,
        "use_denoising": True,
        "denoiser": "OPENIMAGEDENOISE",
        "denoising_input_passes": "RGB_ALBEDO_NORMAL",
        "max_bounces": 8,
        "diffuse_bounces": 4,
        "glossy_bounces": 4,
        "transmission_bounces": 6,
        "transparent_max_bounces": 6,
        "volume_bounces": 2,
        "resolution_percentage": 100,
        "volume_step_rate": 2.0,
        "volume_max_steps": 256,
        "use_caustics_reflective": True,
        "use_caustics_refractive": False,
        "sample_clamp_indirect": 0.0,  # no clamping for ultra
        "time_budget_seconds": 5400,  # 90 minutes
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# GPU/CPU device selection
# ═══════════════════════════════════════════════════════════════════════════

def _configure_device(bpy) -> str:
    """
    Force GPU compute if available, fallback to CPU.
    Returns device description string for logging.
    """
    try:
        prefs = bpy.context.preferences.addons.get("cycles")
        if prefs is None:
            return "CPU (cycles addon not found)"

        cprefs = prefs.preferences

        # Try to enable GPU compute
        # Check available device types in priority order
        for device_type in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                cprefs.compute_device_type = device_type
                cprefs.get_devices()

                # Enable all devices of this type
                devices = cprefs.devices
                gpu_found = False
                device_names = []
                for device in devices:
                    if device.type != "CPU":
                        device.use = True
                        gpu_found = True
                        device_names.append(f"{device.name} ({device_type})")
                    else:
                        device.use = False  # don't hybrid render

                if gpu_found:
                    bpy.context.scene.cycles.device = "GPU"
                    desc = ", ".join(device_names)
                    print(f"[BUDGET] GPU compute enabled: {desc}", flush=True)
                    return f"GPU: {desc}"
            except Exception:
                continue

        # No GPU found -- use CPU
        bpy.context.scene.cycles.device = "CPU"
        print("[BUDGET] No GPU found, using CPU", flush=True)
        return "CPU"

    except Exception as e:
        print(f"[BUDGET] Device config failed ({e}), defaulting to CPU", flush=True)
        return f"CPU (fallback: {e})"


# ═══════════════════════════════════════════════════════════════════════════
# Apply render settings
# ═══════════════════════════════════════════════════════════════════════════

def _apply_cycles_settings(scene, cfg: dict) -> None:
    """Apply all Cycles render settings from config dict."""
    cycles = scene.cycles

    # Core sampling
    cycles.samples = cfg["samples"]
    cycles.use_adaptive_sampling = cfg["use_adaptive_sampling"]
    cycles.adaptive_threshold = cfg["adaptive_threshold"]
    cycles.use_denoising = cfg["use_denoising"]

    # Denoiser type
    try:
        cycles.denoiser = cfg["denoiser"]
    except Exception:
        pass
    try:
        cycles.denoising_input_passes = cfg["denoising_input_passes"]
    except Exception:
        pass

    # Light path bounces
    cycles.max_bounces = cfg["max_bounces"]
    cycles.diffuse_bounces = cfg["diffuse_bounces"]
    cycles.glossy_bounces = cfg["glossy_bounces"]
    cycles.transmission_bounces = cfg["transmission_bounces"]
    cycles.transparent_max_bounces = cfg["transparent_max_bounces"]
    cycles.volume_bounces = cfg["volume_bounces"]

    # Caustics
    cycles.caustics_reflective = cfg["use_caustics_reflective"]
    cycles.caustics_refractive = cfg["use_caustics_refractive"]

    # Clamping
    if cfg["sample_clamp_indirect"] > 0:
        cycles.sample_clamp_indirect = cfg["sample_clamp_indirect"]

    # Volumetric sampling
    try:
        cycles.volume_step_rate = cfg["volume_step_rate"]
        cycles.volume_max_steps = cfg["volume_max_steps"]
    except Exception:
        pass

    # Resolution scaling
    scene.render.resolution_percentage = cfg["resolution_percentage"]

    # Performance: use persistent data to avoid re-uploading geometry
    try:
        scene.render.use_persistent_data = True
    except Exception:
        pass

    # Tile size optimization (larger tiles = more GPU efficient)
    try:
        # Blender 3.x+ uses automatic tile sizing but we can hint
        if hasattr(cycles, "tile_size"):
            cycles.tile_size = 2048 if cycles.device == "GPU" else 256
        elif hasattr(scene.render, "tile_x"):
            tile = 256 if cycles.device == "GPU" else 64
            scene.render.tile_x = tile
            scene.render.tile_y = tile
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Render time safeguard
# ═══════════════════════════════════════════════════════════════════════════

def _install_time_guard(bpy, scene, time_budget: int) -> None:
    """
    Install a frame-change handler that monitors cumulative render time
    and cancels if budget is exceeded.

    The handler is registered as a persistent app handler so it survives
    across frames in animation rendering.
    """
    _state = {"start_time": None, "budget": time_budget, "warned": False}

    def _render_init_handler(scene):
        if _state["start_time"] is None:
            _state["start_time"] = time.time()
            print(
                f"[BUDGET] Render started | budget={_state['budget']}s "
                f"({_state['budget']//60}m)",
                flush=True,
            )

    def _render_post_handler(scene):
        if _state["start_time"] is None:
            return
        elapsed = time.time() - _state["start_time"]
        budget = _state["budget"]

        # Warn at 80%
        if elapsed > budget * 0.8 and not _state["warned"]:
            _state["warned"] = True
            remaining = budget - elapsed
            print(
                f"[BUDGET] WARNING: 80% of render budget consumed | "
                f"elapsed={elapsed:.0f}s remaining={remaining:.0f}s",
                flush=True,
            )

        # Hard stop at 100%
        if elapsed > budget:
            print(
                f"[BUDGET] EXCEEDED render budget | "
                f"elapsed={elapsed:.0f}s budget={budget}s -- stopping render",
                flush=True,
            )
            # Cancel the render -- this is Blender's way to stop animation render
            try:
                bpy.ops.render.view_cancel("INVOKE_DEFAULT")
            except Exception:
                pass

    def _render_cancel_handler(scene):
        if _state["start_time"] is not None:
            elapsed = time.time() - _state["start_time"]
            print(f"[BUDGET] Render cancelled after {elapsed:.0f}s", flush=True)

    def _render_complete_handler(scene):
        if _state["start_time"] is not None:
            elapsed = time.time() - _state["start_time"]
            print(f"[BUDGET] Render complete in {elapsed:.0f}s ({elapsed/60:.1f}m)", flush=True)

    # Register handlers
    try:
        handlers = bpy.app.handlers
        if _render_init_handler not in handlers.render_init:
            handlers.render_init.append(_render_init_handler)
        if _render_post_handler not in handlers.render_post:
            handlers.render_post.append(_render_post_handler)
        if _render_cancel_handler not in handlers.render_cancel:
            handlers.render_cancel.append(_render_cancel_handler)
        if _render_complete_handler not in handlers.render_complete:
            handlers.render_complete.append(_render_complete_handler)
        print(f"[BUDGET] Time guard installed | budget={time_budget}s ({time_budget//60}m)", flush=True)
    except Exception as e:
        print(f"[BUDGET] Time guard install failed: {e}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════

def apply_render_budget(
    bpy,
    scene,
    quality_tier: str = "standard",
    scene_plan: dict | None = None,
) -> dict:
    """
    Configure all render settings for the given quality tier.

    This OVERRIDES whatever configure_scene() set earlier -- it's the
    final authority on render settings, informed by the optimization
    pass that already cleaned up the scene.

    Returns info dict for logging.
    """
    tier = quality_tier.lower()
    cfg = _BUDGET_CONFIGS.get(tier, _BUDGET_CONFIGS["standard"])

    print(f"[BUDGET] Applying render budget | tier={tier}", flush=True)

    # Device selection
    device = _configure_device(bpy)

    # Apply all Cycles settings
    if hasattr(scene, "cycles"):
        _apply_cycles_settings(scene, cfg)

    # Install time guard
    _install_time_guard(bpy, scene, cfg["time_budget_seconds"])

    # Build info dict
    info = {
        "tier": tier,
        "device": device,
        "samples": cfg["samples"],
        "adaptive_sampling": cfg["use_adaptive_sampling"],
        "adaptive_threshold": cfg["adaptive_threshold"],
        "denoising": cfg["use_denoising"],
        "max_bounces": cfg["max_bounces"],
        "resolution_percentage": cfg["resolution_percentage"],
        "volume_step_rate": cfg["volume_step_rate"],
        "volume_max_steps": cfg["volume_max_steps"],
        "caustics": cfg["use_caustics_reflective"],
        "time_budget_seconds": cfg["time_budget_seconds"],
    }

    # Log the full render config
    print(
        f"[BUDGET] Render config applied:\n"
        f"  Device:              {device}\n"
        f"  Samples:             {cfg['samples']}\n"
        f"  Adaptive sampling:   {cfg['use_adaptive_sampling']} (threshold={cfg['adaptive_threshold']})\n"
        f"  Denoising:           {cfg['use_denoising']} ({cfg['denoiser']})\n"
        f"  Max bounces:         {cfg['max_bounces']} (diff={cfg['diffuse_bounces']} "
        f"gloss={cfg['glossy_bounces']} trans={cfg['transmission_bounces']} "
        f"vol={cfg['volume_bounces']})\n"
        f"  Resolution:          {cfg['resolution_percentage']}%\n"
        f"  Volumetric steps:    {cfg['volume_max_steps']} (rate={cfg['volume_step_rate']})\n"
        f"  Caustics:            reflect={cfg['use_caustics_reflective']} "
        f"refract={cfg['use_caustics_refractive']}\n"
        f"  Time budget:         {cfg['time_budget_seconds']}s ({cfg['time_budget_seconds']//60}m)\n"
        f"  Persistent data:     True",
        flush=True,
    )

    return info
