from __future__ import annotations

"""
cinematic_presets.py
====================
Reusable, deterministic preset functions for camera, lighting, and environment.

Every preset is a plain dict of values that builders can apply.  No bpy calls
happen inside the preset definitions themselves -- they are pure data.  The
``apply_*`` helpers translate presets into Blender scene state.

Usage in a builder:
    from ..scene.cinematic_presets import (
        CAMERA_PRESETS, LIGHTING_PRESETS, ENVIRONMENT_PRESETS,
        apply_camera_preset, apply_lighting_preset, apply_environment_preset,
    )

    cam, target = apply_camera_preset(bpy, scene, "hero_push_in", subject_center=(0, 5, 0.75))
    apply_lighting_preset(bpy, "studio_automotive")
    apply_environment_preset(bpy, scene, "reflective_ground")
"""

from math import radians

# ═══════════════════════════════════════════════════════════════════════════
# CAMERA PRESETS
# ═══════════════════════════════════════════════════════════════════════════
# Each preset defines the camera's *relationship* to the subject, not absolute
# world positions.  ``apply_camera_preset`` translates offsets relative to the
# provided ``subject_center``.
#
# Fields:
#   offset          (dx, dy, dz) from subject_center
#   target_offset   (dx, dy, dz) for look-at empty, relative to subject_center
#   lens            focal length in mm
#   motion          dict with frame_end offsets for keyframe animation
#                   keys: dx, dy, dz applied to camera start position

CAMERA_PRESETS: dict[str, dict] = {
    "low_orbit": {
        "offset": (-2.8, -5.5, 1.1),
        "target_offset": (0.0, 0.0, 0.75),
        "lens": 65,
        "motion": {"dx": 3.5, "dy": 2.5, "dz": -0.15},
    },
    "hero_push_in": {
        "offset": (-1.2, -7.5, 2.2),
        "target_offset": (0.0, 0.0, 0.9),
        "lens": 45,
        "motion": {"dx": 1.5, "dy": 3.5, "dz": -0.35},
    },
    "wide_establishing": {
        "offset": (0.0, -18.0, 3.5),
        "target_offset": (0.0, 0.0, 6.0),
        "lens": 50,
        "motion": {"dx": 1.2, "dy": 5.0, "dz": 1.8},
    },
    "cinematic_reveal": {
        "offset": (-0.4, -3.0, 0.6),
        "target_offset": (0.0, 0.0, 0.0),
        "lens": 80,
        "motion": {"dx": 1.2, "dy": 0.6, "dz": -0.08},
    },
    "stage_arc": {
        "offset": (-0.8, -5.5, 2.0),
        "target_offset": (0.0, 0.0, 0.85),
        "lens": 65,
        "motion": {"dx": 2.0, "dy": 1.8, "dz": -0.25},
    },
    "underwater_drift": {
        "offset": (0.0, -15.0, 2.8),
        "target_offset": (0.0, 0.0, 2.2),
        "lens": 55,
        "motion": {"dx": 1.0, "dy": 1.8, "dz": -0.15},
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# LIGHTING PRESETS
# ═══════════════════════════════════════════════════════════════════════════
# Each preset is a list of light definitions.  Types: "AREA", "POINT", "SUN".
# ``apply_lighting_preset`` creates all lights in one call.

LIGHTING_PRESETS: dict[str, list[dict]] = {
    "studio_automotive": [
        {"type": "AREA", "location": (0, 2, 7),     "rotation": (75, 0, 0),    "energy": 6000, "color": (1.0, 1.0, 1.0),   "size": 12},
        {"type": "AREA", "location": (-7, 3, 3),    "rotation": (60, 0, 50),   "energy": 2800, "color": (0.65, 0.75, 1.0),  "size": 8},
        {"type": "AREA", "location": (7, 3, 3),     "rotation": (60, 0, -50),  "energy": 2800, "color": (1.0, 0.88, 0.82),  "size": 8},
        {"type": "AREA", "location": (0, 14, 1.5),  "rotation": (95, 0, 0),    "energy": 4500, "color": (1.0, 0.95, 0.90), "size": 14},
        {"type": "AREA", "location": (0, 5, -0.5),  "rotation": (180, 0, 0),   "energy": 1200, "color": (0.85, 0.88, 1.0), "size": 10},
    ],
    "sunset_landscape": [
        {"type": "SUN",  "location": (0, 0, 0),     "rotation": (55, 0, -25),  "energy": 4.5,  "color": (1.0, 0.95, 0.88), "angle": 1.5},
        {"type": "AREA", "location": (0, -10, 14),   "rotation": (60, 0, 0),    "energy": 7000, "color": (1.0, 0.96, 0.92), "size": 14},
        {"type": "AREA", "location": (-12, -2, 8),   "rotation": (70, 0, 35),   "energy": 3500, "color": (0.75, 0.82, 1.0), "size": 10},
        {"type": "AREA", "location": (0, 35, 12),    "rotation": (110, 0, 0),   "energy": 5000, "color": (1.0, 0.92, 0.80), "size": 18},
    ],
    "neon_city": [
        {"type": "AREA",  "location": (0, -5, 7),    "rotation": (68, 0, 0),    "energy": 7000, "color": (1.0, 1.0, 1.0),   "size": 12},
        {"type": "AREA",  "location": (-6, 1, 5),    "rotation": (72, 0, 45),   "energy": 3500, "color": (0.30, 0.70, 1.0),  "size": 7},
        {"type": "AREA",  "location": (6, 1, 5),     "rotation": (72, 0, -45),  "energy": 3500, "color": (1.0, 0.40, 0.80),  "size": 7},
        {"type": "AREA",  "location": (0, 18, 8),    "rotation": (100, 0, 0),   "energy": 4000, "color": (0.90, 0.85, 1.0), "size": 14},
        {"type": "POINT", "location": (-3.5, 2.0, 3.5), "rotation": (0, 0, 0), "energy": 800,  "color": (1.0, 0.85, 0.65), "radius": 0.3},
        {"type": "POINT", "location": (3.5, 5.0, 3.5),  "rotation": (0, 0, 0), "energy": 600,  "color": (1.0, 0.90, 0.70), "radius": 0.3},
    ],
    "underwater_depth": [
        {"type": "AREA", "location": (0, 0, 12),    "rotation": (0, 0, 0),     "energy": 5000, "color": (0.10, 0.40, 0.90), "size": 14},
        {"type": "AREA", "location": (-8, -4, 5),   "rotation": (60, 0, 45),   "energy": 2500, "color": (0.05, 0.70, 0.85),  "size": 8},
        {"type": "AREA", "location": (4, 10, 3),    "rotation": (80, 0, -30),  "energy": 1800, "color": (0.00, 0.50, 0.65),  "size": 6},
    ],
    "studio_five_point": [
        {"type": "AREA", "location": (0, -4, 7),    "rotation": (65, 0, 0),    "energy": 7000, "color": (1.0, 1.0, 1.0),   "size": 10},
        {"type": "AREA", "location": (-5, 0, 4),    "rotation": (72, 0, 35),   "energy": 2800, "color": (0.70, 0.80, 1.0),  "size": 7},
        {"type": "AREA", "location": (5, 0, 4),     "rotation": (72, 0, -35),  "energy": 2800, "color": (1.0, 0.85, 0.90),  "size": 7},
        {"type": "AREA", "location": (0, 5, 5.5),   "rotation": (110, 0, 0),   "energy": 3500, "color": (1.0, 0.98, 0.95),  "size": 8},
        {"type": "AREA", "location": (0, 0, -0.3),  "rotation": (180, 0, 0),   "energy": 800,  "color": (0.80, 0.85, 1.0),  "size": 6},
    ],
    "product_studio": [
        {"type": "AREA", "location": (-2.5, -3.0, 3.5), "rotation": (55, 0, 30),   "energy": 2500, "color": (1.00, 0.97, 0.92), "size": 4},
        {"type": "AREA", "location": (2.5, -2.5, 2.0),  "rotation": (60, 0, -25),  "energy": 1000, "color": (0.88, 0.92, 1.00), "size": 3},
        {"type": "AREA", "location": (0.5, 3.0, 2.5),   "rotation": (90, 0, 0),    "energy": 800,  "color": (1.00, 1.00, 1.00), "size": 2},
        {"type": "AREA", "location": (0, 0, -0.2),      "rotation": (180, 0, 0),   "energy": 400,  "color": (0.90, 0.92, 1.0),  "size": 3},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# ENVIRONMENT PRESETS
# ═══════════════════════════════════════════════════════════════════════════
# Each preset describes ground material, HDRI, atmosphere layers, etc.
# ``apply_environment_preset`` creates ground + atmosphere.

ENVIRONMENT_PRESETS: dict[str, dict] = {
    "reflective_ground": {
        "ground_type": "automotive_floor",
        "ground_scale": (120, 120, 1),
        "ground_roughness": 0.35,
        "hdri_path": "assets/hdri/qwantani_moon_noon_puresky_4k.exr",
        "hdri_strength": 1.20,
        "exposure": 0.05,
        "world_color": (0.05, 0.055, 0.07, 1.0),
        "atmosphere": [
            {"location": (0, 8, 3),  "scale": (20, 14, 5), "density": 0.005, "color": (0.75, 0.78, 0.88, 1.0), "name": "Atmo_Near"},
            {"location": (0, 22, 5), "scale": (40, 12, 8), "density": 0.008, "color": (0.70, 0.72, 0.82, 1.0), "name": "Atmo_Far"},
        ],
    },
    "terrain_blend": {
        "ground_type": "natural_ground",
        "ground_scale": (120, 120, 1),
        "ground_roughness": 0.92,
        "hdri_path": "assets/hdri/horn-koppe_spring_4k.exr",
        "hdri_strength": 1.25,
        "exposure": 0.12,
        "world_color": (0.055, 0.065, 0.085, 1.0),
        "atmosphere": [
            {"location": (0, 6, 3),   "scale": (30, 10, 5),  "density": 0.005, "color": (0.82, 0.86, 0.92, 1.0), "name": "Atmo_Near"},
            {"location": (0, 22, 8),  "scale": (50, 16, 12), "density": 0.010, "color": (0.78, 0.82, 0.90, 1.0), "name": "Atmo_Far"},
        ],
    },
    "city_fog": {
        "ground_type": "automotive_floor",
        "ground_scale": (100, 100, 1),
        "ground_roughness": 0.40,
        "hdri_path": "assets/hdri/citrus_orchard_road_puresky_4k.exr",
        "hdri_strength": 1.10,
        "exposure": -0.05,
        "world_color": (0.05, 0.06, 0.08, 1.0),
        "atmosphere": [
            {"location": (0, 4, 2.5),  "scale": (16, 10, 4), "density": 0.006, "color": (0.72, 0.75, 0.85, 1.0), "name": "Atmo_Near"},
            {"location": (0, 18, 6),   "scale": (35, 14, 8), "density": 0.010, "color": (0.65, 0.68, 0.80, 1.0), "name": "Atmo_Far"},
        ],
    },
    "underwater_haze": {
        "ground_type": "ocean_floor",
        "ground_scale": (70, 70, 1),
        "ground_roughness": 0.92,
        "hdri_candidates": [
            "assets/hdris/ocean_blue_01.exr",
            "assets/hdris/docklands_02_4k.exr",
            "assets/hdris/shanghai_bund_4k.exr",
        ],
        "hdri_strength": 0.85,
        "exposure": -0.12,
        "world_color": (0.03, 0.08, 0.12, 1.0),
        "atmosphere": [
            {"location": (0, 6, 3.0), "scale": (22, 12, 7), "density": 0.016, "color": (0.10, 0.35, 0.55, 1.0), "name": "OceanAtmo"},
        ],
    },
    "studio_dark": {
        "ground_type": "dark_gloss",
        "ground_scale": (30, 30, 1),
        "ground_roughness": 0.25,
        "hdri_path": "assets/hdris/studio_small_03_4k.exr",
        "hdri_strength": 0.65,
        "exposure": 0.0,
        "world_color": (0.06, 0.065, 0.075, 1.0),
        "atmosphere": [
            {"location": (0, 4, 2.5), "scale": (10, 6, 4), "density": 0.004, "color": (0.55, 0.55, 0.62, 1.0), "name": "StageAtmo"},
        ],
    },
    "studio_product": {
        "ground_type": "studio_cyc",
        "ground_scale": (8, 8, 1),
        "ground_roughness": 0.92,
        "hdri_path": "assets/hdris/studio_clean_01.exr",
        "hdri_strength": 0.75,
        "exposure": 0.05,
        "world_color": (0.88, 0.88, 0.90, 1.0),
        "atmosphere": [
            {"location": (0, 2.0, 1.0), "scale": (5, 4, 3), "density": 0.003, "color": (0.75, 0.75, 0.78, 1.0), "name": "ProductAtmo"},
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# FAMILY -> PRESET MAPPING
# ═══════════════════════════════════════════════════════════════════════════
# Maps each scene family to its default camera/lighting/environment presets.
# Builders can override any of these when calling apply functions.

FAMILY_DEFAULTS: dict[str, dict] = {
    "car_hero": {
        "camera": "low_orbit",
        "lighting": "studio_automotive",
        "environment": "reflective_ground",
    },
    "street_scene": {
        "camera": "hero_push_in",
        "lighting": "neon_city",
        "environment": "city_fog",
    },
    "scenic_landscape": {
        "camera": "wide_establishing",
        "lighting": "sunset_landscape",
        "environment": "terrain_blend",
    },
    "ocean_scene": {
        "camera": "underwater_drift",
        "lighting": "underwater_depth",
        "environment": "underwater_haze",
    },
    "character_stage": {
        "camera": "stage_arc",
        "lighting": "studio_five_point",
        "environment": "studio_dark",
    },
    "product_scene": {
        "camera": "cinematic_reveal",
        "lighting": "product_studio",
        "environment": "studio_product",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# APPLY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _add_light(bpy, spec: dict):
    """Create a single light from a preset spec dict."""
    ltype = spec["type"]
    loc = spec["location"]
    rot_deg = spec["rotation"]
    energy = spec["energy"]
    color = spec["color"]

    if ltype == "POINT":
        bpy.ops.object.light_add(type="POINT", location=loc)
        light = bpy.context.object
        light.data.energy = energy
        light.data.color = color
        light.data.shadow_soft_size = spec.get("radius", 0.15)
        return light

    if ltype == "SUN":
        bpy.ops.object.light_add(
            type="SUN",
            rotation=tuple(radians(v) for v in rot_deg),
        )
        light = bpy.context.object
        light.data.energy = energy
        light.data.color = color
        light.data.angle = radians(spec.get("angle", 1.5))
        return light

    # Default: AREA
    bpy.ops.object.light_add(
        type="AREA",
        location=loc,
        rotation=tuple(radians(v) for v in rot_deg),
    )
    light = bpy.context.object
    light.data.energy = energy
    light.data.color = color
    light.data.shape = "RECTANGLE"
    size = spec.get("size", 7.0)
    light.data.size = size
    light.data.size_y = size
    return light


def apply_lighting_preset(bpy, preset_name: str) -> list:
    """
    Create all lights defined in the named preset.
    Returns list of created light objects.
    """
    specs = LIGHTING_PRESETS.get(preset_name)
    if not specs:
        print(f"[PRESETS] unknown lighting preset '{preset_name}'", flush=True)
        return []

    lights = []
    for spec in specs:
        try:
            lights.append(_add_light(bpy, spec))
        except Exception as e:
            print(f"[PRESETS] light creation failed: {e}", flush=True)
    print(f"[PRESETS] lighting preset '{preset_name}' applied ({len(lights)} lights)", flush=True)
    return lights


def apply_camera_preset(
    bpy,
    scene,
    preset_name: str,
    subject_center: tuple = (0, 0, 0),
    frame_end: int | None = None,
) -> tuple:
    """
    Create camera + look-at target from a named preset.

    IMPORTANT: This function positions the camera and sets lens/constraints
    but does NOT create motion keyframes.  Motion is applied separately by
    ``apply_camera_motion()`` AFTER framing adjustments, so that framing
    and motion work together instead of fighting each other.

    Returns (cam, target) Blender objects.
    """
    preset = CAMERA_PRESETS.get(preset_name)
    if not preset:
        print(f"[PRESETS] unknown camera preset '{preset_name}', using cinematic_reveal", flush=True)
        preset = CAMERA_PRESETS["cinematic_reveal"]

    sx, sy, sz = subject_center
    ox, oy, oz = preset["offset"]
    tx, ty, tz = preset["target_offset"]

    # Create look-at target
    bpy.ops.object.empty_add(
        type="PLAIN_AXES",
        location=(sx + tx, sy + ty, sz + tz),
    )
    target = bpy.context.object
    target.name = "CameraTarget"

    # Create camera — NO keyframes here; framing adjusts position first
    bpy.ops.object.camera_add(location=(sx + ox, sy + oy, sz + oz))
    cam = bpy.context.object
    cam.data.lens = preset["lens"]
    scene.camera = cam

    # TRACK_TO constraint
    c = cam.constraints.new(type="TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"

    print(
        f"[PRESETS] camera preset '{preset_name}' | "
        f"pos=({sx+ox:.1f},{sy+oy:.1f},{sz+oz:.1f}) lens={preset['lens']}mm "
        f"(motion deferred to apply_camera_motion)",
        flush=True,
    )
    return cam, target


def apply_camera_motion(
    cam,
    target,
    scene_plan: dict | None,
    frame_start: int = 1,
    frame_end: int = 240,
) -> str:
    """
    Apply camera motion AFTER framing.  Reads from scene_plan to determine
    the correct camera behavior.

    Call this AFTER frame_camera_to_meshes so motion starts from the
    correctly framed position.

    Returns the name of the motion applied.
    """
    if scene_plan is None:
        scene_plan = {}

    # v1.3.7 — explicit user override: when the Studio's Scene Controls panel
    # sets camera = "Static", the frontend sends scene_params.camera_motion_disabled.
    # That value lives in the manifest's scene_params and (depending on caller)
    # may also be folded into scene_plan. Honor either path. Real, deterministic,
    # logged — no silent fallback.
    if scene_plan.get("camera_motion_disabled") or (
        isinstance(scene_plan.get("scene_params"), dict)
        and scene_plan["scene_params"].get("camera_motion_disabled")
    ):
        print("[CAMERA] motion disabled by user override", flush=True)
        return "static_user_override"

    camera_style = scene_plan.get("_camera_style", "")
    preset_name = scene_plan.get("camera_preset", "")
    energy = scene_plan.get("energy_multiplier", 1.0)

    # Import camera_motion helpers
    from .camera_motion import (
        orbit_camera,
        push_in_camera,
        crane_up_camera,
        subtle_handheld_noise,
    )

    motion_applied = "default_drift"

    # ── Dispatch to distinct camera behaviors ─────────────────────────
    if camera_style == "orbit" or preset_name == "low_orbit":
        # True orbital arc around subject
        base = cam.location.copy()
        tgt = target.location.copy()
        radius = ((base.x - tgt.x)**2 + (base.y - tgt.y)**2) ** 0.5
        orbit_camera(
            cam,
            center=(tgt.x, tgt.y, tgt.z),
            radius=max(radius, 3.0),
            start_angle_deg=-90,
            sweep_deg=55 * energy,
            height=base.z - tgt.z,
            height_delta=-0.2 * energy,
            frame_start=frame_start,
            frame_end=frame_end,
        )
        motion_applied = "orbit"

    elif camera_style in ("tracking", "follow"):
        # Camera tracks forward alongside subject motion.  Travel must
        # scale with the subject's own travel — a vehicle moves ~32 units
        # in vehicle_drive, so a camera travel of 8 leaves the car driving
        # off-screen into blackness after ~25% of the shot.  We pull the
        # subject travel from scene_plan if the behavior layer set it.
        _subj_travel = float(scene_plan.get("_subject_travel", 0.0))
        if _subj_travel > 0.1:
            # Camera follows ~85% of subject distance — hero stays roughly
            # in frame while appearing to slightly overtake the camera.
            _cam_travel = _subj_travel * 0.85
        else:
            _cam_travel = 8.0 * energy
        from .directorial_motion import _tracking_camera
        _tracking_camera(
            cam, target,
            subject_center=(target.location.x, target.location.y, target.location.z),
            frame_start=frame_start,
            frame_end=frame_end,
            energy=energy,
            travel=_cam_travel,
        )
        motion_applied = "tracking"

    elif camera_style == "reveal" or preset_name == "cinematic_reveal":
        # Crane up reveal: camera lifts and pushes in
        crane_up_camera(
            cam,
            dz=2.0 * energy,
            dy=3.0 * energy,
            frame_start=frame_start,
            frame_end=frame_end,
        )
        motion_applied = "reveal"

    elif camera_style == "handheld":
        # Subtle organic noise — no major motion, just life
        push_in_camera(
            cam,
            dx=0.3 * energy,
            dy=1.0 * energy,
            dz=-0.1 * energy,
            frame_start=frame_start,
            frame_end=frame_end,
        )
        subtle_handheld_noise(
            cam,
            amplitude=0.025 * energy,
            frequency=2.0,
            frame_start=frame_start,
            frame_end=frame_end,
        )
        motion_applied = "handheld"

    else:
        # Default: use preset's motion dict for a gentle drift
        preset = CAMERA_PRESETS.get(preset_name)
        if preset:
            motion = preset.get("motion", {})
            dx = motion.get("dx", 1.5) * energy
            dy = motion.get("dy", 3.0) * energy
            dz = motion.get("dz", -0.2) * energy
        else:
            dx, dy, dz = 1.5 * energy, 3.0 * energy, -0.2 * energy

        push_in_camera(
            cam, dx=dx, dy=dy, dz=dz,
            frame_start=frame_start,
            frame_end=frame_end,
        )
        motion_applied = "push_in"

    print(
        f"[PRESETS] camera motion applied: {motion_applied} | "
        f"style={camera_style or 'auto'} energy={energy:.1f}",
        flush=True,
    )
    return motion_applied


def apply_environment_preset(
    bpy,
    scene,
    preset_name: str,
    *,
    ground_name: str = "Ground",
    ground_location: tuple = (0, 0, 0),
) -> dict:
    """
    Apply HDRI, exposure, ground plane, and atmosphere layers from a preset.

    Returns context dict with references to created objects:
        {"hdri_used": bool, "ground": obj, "atmosphere": [objs...]}
    """
    from .layout_ops import (
        ensure_hdri_world,
        ensure_world_background,
        ensure_scene_look,
        add_atmosphere_box,
    )
    from .materials import (
        make_automotive_floor_material,
        make_natural_ground_material,
        make_dark_gloss_material,
        make_studio_cyc_material,
        assign_material,
    )

    preset = ENVIRONMENT_PRESETS.get(preset_name)
    if not preset:
        print(f"[PRESETS] unknown environment preset '{preset_name}'", flush=True)
        return {"hdri_used": False, "ground": None, "atmosphere": []}

    ctx: dict = {}

    # Exposure
    ensure_scene_look(scene, exposure=preset.get("exposure", 0.0))

    # HDRI -- support single path or candidate list
    hdri_used = False
    candidates = preset.get("hdri_candidates", [])
    if not candidates and preset.get("hdri_path"):
        candidates = [preset["hdri_path"]]
    for hp in candidates:
        hdri_used = ensure_hdri_world(bpy, scene, hp, strength=preset.get("hdri_strength", 1.2))
        if hdri_used:
            break
    if not hdri_used:
        ensure_world_background(
            scene,
            strength=preset.get("world_strength", 1.25),
            color=preset.get("world_color", (0.05, 0.06, 0.08, 1.0)),
        )
    ctx["hdri_used"] = hdri_used

    # Ground plane
    gt = preset.get("ground_type", "automotive_floor")
    roughness = preset.get("ground_roughness", 0.35)

    if gt == "automotive_floor":
        mat = make_automotive_floor_material(bpy, name=f"{ground_name}Mat", roughness=roughness)
    elif gt == "natural_ground":
        mat = make_natural_ground_material(bpy, name=f"{ground_name}Mat", roughness=roughness)
    elif gt == "dark_gloss":
        mat = make_dark_gloss_material(bpy, name=f"{ground_name}Mat", roughness=roughness)
    elif gt == "studio_cyc":
        mat = make_studio_cyc_material(bpy, name=f"{ground_name}Mat", roughness=roughness)
    elif gt == "ocean_floor":
        # Ocean floor is custom -- just use dark natural ground
        mat = make_natural_ground_material(
            bpy, name=f"{ground_name}Mat",
            base=(0.05, 0.12, 0.20, 1.0), roughness=roughness,
        )
    else:
        mat = make_automotive_floor_material(bpy, name=f"{ground_name}Mat", roughness=roughness)

    gs = preset.get("ground_scale", (100, 100, 1))
    bpy.ops.mesh.primitive_plane_add(location=ground_location)
    ground = bpy.context.object
    ground.name = ground_name
    ground.scale = gs
    assign_material(ground, mat)
    ctx["ground"] = ground
    ctx["ground_mat"] = mat

    # Atmosphere layers
    atmo_objs = []
    for atmo_spec in preset.get("atmosphere", []):
        obj = add_atmosphere_box(
            bpy,
            location=atmo_spec["location"],
            scale=atmo_spec["scale"],
            density=atmo_spec["density"],
            color=atmo_spec.get("color", (0.80, 0.85, 0.95, 1.0)),
            name=atmo_spec.get("name", "Atmosphere"),
        )
        if obj:
            atmo_objs.append(obj)
    ctx["atmosphere"] = atmo_objs

    print(f"[PRESETS] environment preset '{preset_name}' applied | hdri={'yes' if hdri_used else 'fallback'}", flush=True)
    return ctx


def get_family_presets(family: str) -> dict:
    """
    Return the default preset names for a scene family.
    Returns dict with keys: camera, lighting, environment.
    Falls back to sensible defaults if family is unknown.
    """
    return FAMILY_DEFAULTS.get(family, {
        "camera": "cinematic_reveal",
        "lighting": "studio_five_point",
        "environment": "reflective_ground",
    })
