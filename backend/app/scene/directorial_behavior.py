from __future__ import annotations

"""
directorial_behavior.py
=======================
Central behavior execution layer.

Translates a scene_plan into concrete subject + camera behavior.
This module is the single point where directorial intent becomes action.
It is called AFTER builders create geometry and position camera, and
BEFORE rendering begins.

Flow:
    builder creates scene → framing adjusts camera →
    execute_behavior() applies subject motion + camera motion

The behavior layer is asset-class-aware and intent-driven, not
hardcoded to specific templates.

Usage:
    from app.scene.directorial_behavior import execute_behavior

    result = execute_behavior(
        bpy, scene, cam, target,
        subject_instances=[[mesh1, mesh2]],
        scene_plan=scene_plan,
    )
"""


# ═══════════════════════════════════════════════════════════════════════════
# Asset class inference
# ═══════════════════════════════════════════════════════════════════════════

_FAMILY_TO_ASSET_CLASS: dict[str, str] = {
    "car_hero":         "vehicle",
    "street_scene":     "character_group",
    "scenic_landscape": "environment",
    "ocean_scene":      "creature",
    "character_stage":  "character_group",
    "product_scene":    "product",
    "city_scene":       "environment",
    "city_loop":        "vehicle",
}


def _infer_asset_class(scene_plan: dict) -> str:
    """Determine asset class from scene family."""
    family = scene_plan.get("scene_family", "")
    return _FAMILY_TO_ASSET_CLASS.get(family, "generic")


# ═══════════════════════════════════════════════════════════════════════════
# Behavior plan builder
# ═══════════════════════════════════════════════════════════════════════════

def _build_behavior_plan(scene_plan: dict) -> dict:
    """
    Build a complete behavior execution plan from scene_plan.

    Returns dict with:
        subject_motion:  str  (profile name or "none")
        camera_motion:   str  (camera behavior name)
        energy:          float
        asset_class:     str
        subject_travel:  float  (how far subject moves)
        camera_travel:   float  (how far camera moves)
    """
    asset_class = _infer_asset_class(scene_plan)
    anim_style = scene_plan.get("animation_style", "")
    camera_style = scene_plan.get("_camera_style", "")
    motion_style = scene_plan.get("_motion_style", "")
    energy = scene_plan.get("energy_multiplier", 1.0)

    # ── Subject motion ────────────────────────────────────────────────
    subject_motion = "none"
    subject_travel = 0.0

    if anim_style in ("vehicle_drive",):
        subject_motion = "vehicle_drive"
        subject_travel = 12.0 * energy
    elif anim_style in ("vehicle_drift",):
        subject_motion = "vehicle_drift"
        subject_travel = 8.0 * energy
    elif anim_style in ("character_dance",):
        subject_motion = "character_dance"
        subject_travel = 0.0  # dance is in-place
    elif anim_style in ("character_walk",):
        subject_motion = "character_walk"
        subject_travel = 6.0 * energy
    elif anim_style in ("character_performance",):
        subject_motion = "character_dance"  # performance defaults to dance
        subject_travel = 0.0
    elif anim_style in ("swim_school",):
        subject_motion = "none"  # handled by existing swim animation
    elif anim_style in ("product_turntable",):
        subject_motion = "none"  # handled by existing turntable
    elif anim_style in ("static_hero", "static_establishing"):
        subject_motion = "idle_breathe"
        subject_travel = 0.0

    # For any remaining "none" motion on character/creature types,
    # apply idle breathing so subjects look alive
    if subject_motion == "none" and asset_class in ("character_group", "creature", "generic"):
        subject_motion = "idle_breathe"

    # ── Camera motion ─────────────────────────────────────────────────
    # Camera motion must respond to BOTH camera_style AND subject motion
    camera_motion = "push_in"  # default
    camera_travel = 3.0 * energy

    if camera_style == "orbit":
        camera_motion = "orbit"
        camera_travel = 0.0  # orbital, not linear
    elif camera_style in ("tracking", "follow"):
        camera_motion = "tracking"
        camera_travel = subject_travel  # match subject travel
    elif camera_style == "reveal":
        camera_motion = "reveal"
        camera_travel = 3.5 * energy
    elif camera_style == "handheld":
        camera_motion = "handheld"
        camera_travel = 1.0 * energy
    elif subject_travel > 3.0:
        # Subject is moving significantly — camera should track by default
        camera_motion = "tracking"
        camera_travel = subject_travel * 0.8
    elif asset_class == "vehicle" and motion_style == "driving":
        camera_motion = "tracking"
        camera_travel = subject_travel * 0.8

    plan = {
        "asset_class":    asset_class,
        "subject_motion": subject_motion,
        "camera_motion":  camera_motion,
        "energy":         energy,
        "subject_travel": subject_travel,
        "camera_travel":  camera_travel,
        "anim_style":     anim_style,
        "camera_style":   camera_style,
        "motion_style":   motion_style,
    }

    print(
        f"[BEHAVIOR] plan: asset={asset_class} "
        f"subject={subject_motion}(travel={subject_travel:.1f}) "
        f"camera={camera_motion}(travel={camera_travel:.1f}) "
        f"energy={energy:.1f}",
        flush=True,
    )
    return plan


# ═══════════════════════════════════════════════════════════════════════════
# Execution
# ═══════════════════════════════════════════════════════════════════════════

def execute_behavior(
    bpy,
    scene,
    cam,
    target,
    subject_instances: list[list] | None = None,
    scene_plan: dict | None = None,
    frame_start: int = 1,
    frame_end: int = 240,
    stagger_frames: int = 8,
) -> dict:
    """
    Execute the complete directorial behavior plan.

    This is the single entry point that builders call AFTER framing.
    It applies subject motion and camera motion based on scene_plan.

    Returns the behavior plan dict for logging.
    """
    if scene_plan is None:
        scene_plan = {}

    plan = _build_behavior_plan(scene_plan)

    # ── 1. Apply subject motion ───────────────────────────────────────
    subject_applied = False
    if plan["subject_motion"] != "none" and subject_instances:
        try:
            from .directorial_motion import is_directorial_style, apply_directorial_motion

            if is_directorial_style(plan["subject_motion"]):
                # Override scene_plan animation_style temporarily for routing
                motion_plan = dict(scene_plan)
                motion_plan["animation_style"] = plan["subject_motion"]
                motion_plan["energy_multiplier"] = plan["energy"]

                subject_applied = apply_directorial_motion(
                    bpy, scene, subject_instances, motion_plan,
                    frame_start=frame_start,
                    frame_end=frame_end,
                    stagger_frames=stagger_frames,
                )
        except ImportError:
            print("[BEHAVIOR] directorial_motion not available", flush=True)

    if subject_applied:
        print(f"[BEHAVIOR] subject motion applied: {plan['subject_motion']}", flush=True)
    else:
        print(f"[BEHAVIOR] subject motion: {plan['subject_motion']} (not applied — handled by builder or none)", flush=True)

    # ── 2. Wire camera target follow if subject is moving ────────────
    # If subject motion was applied, the cam-aim target Empty must ride
    # along with the moving subject so the TRACK_TO constraint keeps the
    # camera locked on it. Without this, the subject drives out of frame
    # and the camera looks at empty space.
    primary_root = scene_plan.get("_primary_animated_root")
    if subject_applied and primary_root is not None and target is not None:
        try:
            from .directorial_motion import follow_target_to_subject
            follow_target_to_subject(
                target, primary_root,
                frame_start=frame_start,
                frame_end=frame_end,
            )
        except Exception as e:
            print(f"[BEHAVIOR] follow_target wiring failed: {e}", flush=True)

    # ── 3. Apply camera motion ────────────────────────────────────────
    try:
        from .cinematic_presets import apply_camera_motion

        # Inject behavior plan into scene_plan for camera motion dispatch
        cam_plan = dict(scene_plan)
        cam_plan["_camera_style"] = plan["camera_motion"]
        # Pass subject travel so _tracking_camera can match the hero's
        # distance — prevents the "car drives off into black" symptom where
        # the vehicle travels 32m but the camera only follows 8m.
        cam_plan["_subject_travel"] = plan.get("subject_travel", 0.0)

        motion_name = apply_camera_motion(
            cam, target, cam_plan,
            frame_start=frame_start,
            frame_end=frame_end,
        )
        plan["camera_motion_applied"] = motion_name
    except Exception as e:
        print(f"[BEHAVIOR] camera motion failed: {e}", flush=True)
        plan["camera_motion_applied"] = "fallback"

    # ── 3b. If camera is in TRACKING mode and subject is animated, also
    # ride the camera body forward with the subject (in addition to the
    # baseline tracking motion the apply_camera_motion dispatched).
    if (
        subject_applied
        and primary_root is not None
        and plan["camera_motion"] in ("tracking", "follow")
    ):
        try:
            from .directorial_motion import follow_camera_to_subject
            follow_camera_to_subject(
                cam, primary_root,
                frame_start=frame_start,
                frame_end=frame_end,
                forward_lag=0.9,
            )
        except Exception as e:
            print(f"[BEHAVIOR] follow_camera wiring failed: {e}", flush=True)

    # ── 3c. Camera-subject lock (belt-and-suspenders) ────────────────
    # If the subject got keyframed motion, enforce that the camera covers
    # at least the same frame range and has a TRACK_TO constraint as a
    # fallback aim lock.  Prevents the "car drives into black" symptom
    # where the camera stops animating partway through the hero's shot.
    if subject_applied and primary_root is not None and cam is not None:
        try:
            from .directorial_motion import lock_camera_to_subject
            lock_camera_to_subject(
                bpy, cam, primary_root,
                target_empty=target,
                frame_start=frame_start,
                frame_end=frame_end,
            )
        except Exception as e:
            print(f"[BEHAVIOR] camera-subject lock failed: {e}", flush=True)

    # ── 3. Log final state ────────────────────────────────────────────
    print(
        f"[BEHAVIOR] execution complete | "
        f"subject={plan['subject_motion']}(applied={subject_applied}) "
        f"camera={plan.get('camera_motion_applied', '?')}",
        flush=True,
    )

    return plan
