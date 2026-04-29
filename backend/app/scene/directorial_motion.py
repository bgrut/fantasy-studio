from __future__ import annotations

"""
directorial_motion.py
=====================
Procedural motion profiles driven by the director's scene_plan.

Each profile animates the *single root* of an imported asset hierarchy
(via find_animation_root) so the entire model translates and rotates as
one coherent unit. This replaces the prior approach of keyframing every
leaf mesh individually, which produced broken-looking per-part rotation
and made the camera-target follow logic brittle.

Profiles
--------
    vehicle_drive    forward driving + suspension bounce + body pitch/roll
                     + wheel spin (auto-detected by mesh name)
    vehicle_drift    lateral arc + yaw + body lean into the slide
    character_walk   stride translation + body bob + lean + side-to-side hip sway
    character_dance  in-place sway + bounce + head nod (looped via CYCLES)
    static_hero      no subject motion (camera only)

A "follow target" helper is also provided so a camera-aim Empty (used by
TRACK_TO constraints) keeps locked on the moving subject root.

Design notes
------------
- All keyframes are inserted on a SINGLE root object per instance, NOT on
  every leaf mesh. This prevents per-part rotation pivots and gives a
  10-100x reduction in fcurves for assets with many parts.
- Amplitudes are tuned to be visibly cinematic (not subtle):
  vehicles travel ~30+ units; characters stride ~10+ units with full body
  lean and hip sway.
- Wheel spin is added separately on detected wheel meshes (rotation around
  their own X axis at high frequency) — this gives the visual cue of
  rolling even when the camera is locked on the car.
- Easing uses smoothstep so motion has a natural accel/decel feel.
"""

from math import radians, sin, cos, pi


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _get_fcurves(action):
    """Get fcurves from an Action, compatible with both old and new Blender APIs.

    Blender 4.4+ uses a layered action system where ``action.fcurves`` no
    longer exists directly.  This helper tries the legacy attribute first
    and falls back to the layered path.
    """
    if action is None:
        return []
    # Legacy Blender (<4.4) — action.fcurves exists directly
    try:
        fc = action.fcurves
        if fc is not None:
            return fc
    except AttributeError:
        pass
    # Blender 4.4+ layered actions
    try:
        if hasattr(action, "layers") and action.layers:
            layer = action.layers[0]
            if hasattr(layer, "strips") and layer.strips:
                strip = layer.strips[0]
                if hasattr(strip, "channelbags") and strip.channelbags:
                    return strip.channelbags[0].fcurves
    except Exception:
        pass
    return []


def _smoothstep(t: float) -> float:
    """Smoothstep easing: 0..1 -> 0..1 with eased ends."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def _smooth_keyframes(obj) -> None:
    """Set all fcurves on obj to smooth bezier interpolation."""
    if obj is None:
        return
    ad = getattr(obj, "animation_data", None)
    if not ad or not ad.action:
        return
    for fc in _get_fcurves(ad.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.handle_left_type = "AUTO_CLAMPED"
            kp.handle_right_type = "AUTO_CLAMPED"


def _add_cycles_modifier(obj) -> None:
    """Add CYCLES modifier to all fcurves on obj for seamless looping."""
    if obj is None:
        return
    ad = getattr(obj, "animation_data", None)
    if not ad or not ad.action:
        return
    for fc in _get_fcurves(ad.action):
        try:
            fc.modifiers.new(type="CYCLES")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Vehicle motion profiles
# ═══════════════════════════════════════════════════════════════════════════

def _vehicle_drive(
    root,
    frame_start: int,
    frame_end: int,
    energy: float = 1.0,
    wheels: list | None = None,
    **kwargs,
) -> None:
    """
    Cinematic forward driving on a SINGLE root object.
    Whole-vehicle translation + suspension bounce + pitch + roll.
    Optional per-wheel spin is keyframed on detected wheel meshes.
    """
    if root is None:
        print("[MOTION] vehicle_drive: no root object", flush=True)
        return

    travel = 32.0 * energy           # CINEMATIC distance — clearly visible
    bounce_amp = 0.05 * energy       # subtle suspension bounce
    pitch_amp = radians(2.0) * energy
    roll_amp = radians(1.2) * energy
    bounce_period = 18

    base_x = root.location.x
    base_y = root.location.y
    base_z = root.location.z
    base_rx = root.rotation_euler.x
    base_ry = root.rotation_euler.y
    base_rz = root.rotation_euler.z

    total = max(1, frame_end - frame_start)

    try:
        for frame in range(frame_start, frame_end + 1, 2):
            t = (frame - frame_start) / total
            ease = _smoothstep(t)
            phase = 2 * pi * (frame - frame_start) / bounce_period

            # Forward translation (smooth accel/decel)
            # Drive in -Y so the vehicle moves TOWARD the camera (cinematic
            # approach / drive-by). The camera sits at negative Y looking at
            # the subject, so +Y would make the car recede = appear to drive
            # backward.
            root.location.y = base_y - travel * ease
            # Subtle vertical bounce
            root.location.z = base_z + bounce_amp * sin(phase)
            # Body pitch (nose dives slightly)
            root.rotation_euler.x = base_rx + pitch_amp * sin(phase * 0.5)
            # Body roll
            root.rotation_euler.y = base_ry + roll_amp * sin(phase * 0.7 + 1.2)

            root.keyframe_insert(data_path="location", frame=frame)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)

        _smooth_keyframes(root)

        # Reset live transform
        root.location.x = base_x
        root.location.y = base_y
        root.location.z = base_z
        root.rotation_euler.x = base_rx
        root.rotation_euler.y = base_ry
        root.rotation_euler.z = base_rz

        # Verify keyframes actually landed — an empty fcurve list here
        # means the keyframe_inserts silently failed and the vehicle will
        # render as static.
        ad = getattr(root, "animation_data", None)
        _kf_count = 0
        if ad and ad.action:
            for fc in _get_fcurves(ad.action):
                _kf_count += len(fc.keyframe_points)
        print(
            f"[MOTION] vehicle_drive | root={root.name} travel={travel:.1f} "
            f"energy={energy:.2f} keyframes={_kf_count}",
            flush=True,
        )
        if _kf_count == 0:
            print(
                f"[MOTION] WARNING: vehicle_drive inserted 0 keyframes on "
                f"{root.name} — vehicle will render static",
                flush=True,
            )
    except Exception as e:
        print(f"[MOTION] vehicle_drive error on {root.name}: {e}", flush=True)

    # Wheel spin (visual cue of rolling)
    if wheels:
        _spin_wheels(wheels, frame_start, frame_end, energy=energy)


def _spin_wheels(
    wheel_objs: list,
    frame_start: int,
    frame_end: int,
    energy: float = 1.0,
) -> None:
    """
    Spin each wheel mesh around its local X axis (typical wheel rotation).
    Spin rate scales with energy to feel like the car is going faster.
    """
    spins_per_second = 6.0 * energy
    fps = 24.0
    total_frames = max(1, frame_end - frame_start)
    total_radians = 2 * pi * spins_per_second * (total_frames / fps)

    for wheel in wheel_objs:
        try:
            base_rx = wheel.rotation_euler.x
            wheel.rotation_euler.x = base_rx
            wheel.keyframe_insert(data_path="rotation_euler", index=0, frame=frame_start)
            wheel.rotation_euler.x = base_rx + total_radians
            wheel.keyframe_insert(data_path="rotation_euler", index=0, frame=frame_end)

            ad = getattr(wheel, "animation_data", None)
            if ad and ad.action:
                for fc in _get_fcurves(ad.action):
                    if fc.data_path == "rotation_euler" and fc.array_index == 0:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"

            wheel.rotation_euler.x = base_rx
            print(f"[MOTION] wheel spin | {wheel.name}", flush=True)
        except Exception as e:
            print(f"[MOTION] wheel spin error on {wheel.name}: {e}", flush=True)


def _vehicle_drift(
    root,
    frame_start: int,
    frame_end: int,
    energy: float = 1.0,
    wheels: list | None = None,
    **kwargs,
) -> None:
    """Lateral drift arc with yaw and body lean."""
    if root is None:
        return

    travel_y = 22.0 * energy
    travel_x = 7.0 * energy
    yaw_amp = radians(22) * energy
    roll_amp = radians(4.0) * energy

    base = root.location.copy()
    base_rx = root.rotation_euler.x
    base_ry = root.rotation_euler.y
    base_rz = root.rotation_euler.z
    total = max(1, frame_end - frame_start)

    try:
        for frame in range(frame_start, frame_end + 1, 2):
            t = (frame - frame_start) / total
            ease = _smoothstep(t)

            root.location.y = base.y + travel_y * ease
            root.location.x = base.x + travel_x * sin(pi * t)
            root.rotation_euler.z = base_rz + yaw_amp * sin(pi * t)
            # Body leans into the slide (counter to the lateral motion)
            root.rotation_euler.y = base_ry - roll_amp * sin(pi * t)

            root.keyframe_insert(data_path="location", frame=frame)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)

        _smooth_keyframes(root)

        root.location = base
        root.rotation_euler.x = base_rx
        root.rotation_euler.y = base_ry
        root.rotation_euler.z = base_rz

        print(f"[MOTION] vehicle_drift | root={root.name}", flush=True)
    except Exception as e:
        print(f"[MOTION] vehicle_drift error: {e}", flush=True)

    if wheels:
        _spin_wheels(wheels, frame_start, frame_end, energy=energy * 1.4)


# ═══════════════════════════════════════════════════════════════════════════
# Character motion profiles
# ═══════════════════════════════════════════════════════════════════════════

def _hero_height(root) -> float:
    """Compute the world-space height of a root object's bounding box."""
    try:
        from mathutils import Vector
        zs = []
        for corner in root.bound_box:
            zs.append((root.matrix_world @ Vector(corner)).z)
        if zs:
            return max(zs) - min(zs)
    except Exception:
        pass
    # Walk children too — root might be an Empty
    try:
        from mathutils import Vector
        zs = []
        for child in root.children_recursive:
            if getattr(child, "type", None) != "MESH":
                continue
            for corner in child.bound_box:
                zs.append((child.matrix_world @ Vector(corner)).z)
        if zs:
            return max(zs) - min(zs)
    except Exception:
        pass
    return 1.8  # reasonable fallback for a humanoid


def _character_walk(
    root,
    frame_start: int,
    frame_end: int,
    energy: float = 1.0,
    stagger: int = 0,
    **kwargs,
) -> None:
    """
    Cinematic walk on a SINGLE root.
    - Forward translation (visible glide)
    - Subtle vertical bob (2% of hero height) synced to step rate
    - Forward body lean
    - Subtle hip sway (Z rotation) per step
    """
    if root is None:
        return

    height = _hero_height(root)
    travel = 16.0 * energy        # increased forward glide for cinematic read
    bob_amp = height * 0.02 * energy  # 2% of hero height — subtle, not hopping
    step_period = 16              # frames per step cycle (slightly slower = more cinematic)
    lean_amp = radians(3.0) * energy
    hip_sway_amp = radians(3.5) * energy

    base_x = root.location.x
    base_y = root.location.y
    base_z = root.location.z
    base_rx = root.rotation_euler.x
    base_rz = root.rotation_euler.z

    total = max(1, frame_end - frame_start)

    try:
        for frame in range(frame_start, frame_end + 1, 2):
            t = (frame - frame_start) / total
            phase = 2 * pi * (frame - frame_start + stagger) / step_period
            ease = _smoothstep(t)

            # Forward stride — smooth eased glide
            root.location.y = base_y + travel * ease
            # Vertical bob — smooth sine wave, NOT abs(sin) which double-bumps
            root.location.z = base_z + bob_amp * sin(phase)
            # Forward lean (eases in with walk)
            root.rotation_euler.x = base_rx + lean_amp * ease
            # Hip sway — alternates with each step
            root.rotation_euler.z = base_rz + hip_sway_amp * sin(phase * 0.5)

            root.keyframe_insert(data_path="location", frame=frame)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)

        _smooth_keyframes(root)

        root.location.x = base_x
        root.location.y = base_y
        root.location.z = base_z
        root.rotation_euler.x = base_rx
        root.rotation_euler.z = base_rz

        print(
            f"[MOTION] character_walk | root={root.name} height={height:.2f} "
            f"bob={bob_amp:.3f} travel={travel:.1f} energy={energy:.2f}",
            flush=True,
        )
    except Exception as e:
        print(f"[MOTION] character_walk error: {e}", flush=True)


def _character_dance(
    root,
    frame_start: int,
    frame_end: int,
    energy: float = 1.0,
    stagger: int = 0,
    **kwargs,
) -> None:
    """
    In-place dance on a SINGLE root.
    - Body sway (Z rotation, large amplitude)
    - Bounce (Z translation, beat-aligned)
    - Head nod (X rotation, off-phase from sway)
    - Subtle X/Y location wiggle for shoulder shimmy feel
    - Loops via CYCLES modifier
    """
    if root is None:
        return

    sway_amp = radians(28) * energy   # very visible rhythmic sway
    bounce_amp = 0.18 * energy        # strong beat bounce
    nod_amp = radians(8) * energy
    shimmy_amp = 0.04 * energy
    sway_period = 22
    bounce_period = 11

    base_x = root.location.x
    base_y = root.location.y
    base_z = root.location.z
    base_rx = root.rotation_euler.x
    base_rz = root.rotation_euler.z

    try:
        for frame in range(frame_start, frame_end + 1, 2):
            sway_phase = 2 * pi * (frame - frame_start + stagger) / sway_period
            bounce_phase = 2 * pi * (frame - frame_start + stagger) / bounce_period

            root.rotation_euler.z = base_rz + sway_amp * sin(sway_phase)
            root.rotation_euler.x = base_rx + nod_amp * sin(sway_phase * 1.5 + 0.8)
            root.location.z = base_z + bounce_amp * abs(sin(bounce_phase))
            root.location.x = base_x + shimmy_amp * sin(sway_phase * 0.5)
            root.location.y = base_y + shimmy_amp * 0.5 * cos(sway_phase * 0.5)

            root.keyframe_insert(data_path="location", frame=frame)
            root.keyframe_insert(data_path="rotation_euler", frame=frame)

        _smooth_keyframes(root)
        _add_cycles_modifier(root)

        root.location.x = base_x
        root.location.y = base_y
        root.location.z = base_z
        root.rotation_euler.x = base_rx
        root.rotation_euler.z = base_rz

        print(f"[MOTION] character_dance | root={root.name} energy={energy:.2f}", flush=True)
    except Exception as e:
        print(f"[MOTION] character_dance error: {e}", flush=True)


def _idle_breathe(
    root,
    frame_start: int,
    frame_end: int,
    energy: float = 1.0,
    stagger: int = 0,
    **kwargs,
) -> None:
    """
    Subtle breathing/sway for stationary subjects.
    - 0.5% vertical oscillation (of hero height)
    - 1 degree Z-axis rotation sway
    Keeps the subject visually alive without actual locomotion.
    """
    if root is None:
        return

    height = _hero_height(root)
    breathe_amp = height * 0.005 * energy   # 0.5% of hero height
    sway_amp = radians(1.0) * energy        # 1 degree sway
    breathe_period = 48                     # ~2 sec at 24fps — natural breath rate
    sway_period = 72                        # slower sway for organic feel

    base_z = root.location.z
    base_rz = root.rotation_euler.z

    try:
        for frame in range(frame_start, frame_end + 1, 3):
            phase_b = 2 * pi * (frame - frame_start + stagger) / breathe_period
            phase_s = 2 * pi * (frame - frame_start + stagger) / sway_period

            root.location.z = base_z + breathe_amp * sin(phase_b)
            root.rotation_euler.z = base_rz + sway_amp * sin(phase_s)

            root.keyframe_insert(data_path="location", index=2, frame=frame)
            root.keyframe_insert(data_path="rotation_euler", index=2, frame=frame)

        _smooth_keyframes(root)

        root.location.z = base_z
        root.rotation_euler.z = base_rz

        print(
            f"[MOTION] idle_breathe | root={root.name} height={height:.2f} "
            f"breathe={breathe_amp:.4f} sway={sway_amp:.4f}",
            flush=True,
        )
    except Exception as e:
        print(f"[MOTION] idle_breathe error: {e}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# Camera target follow — keeps cam locked on a moving subject
# ═══════════════════════════════════════════════════════════════════════════

def follow_target_to_subject(
    target,
    subject_root,
    frame_start: int,
    frame_end: int,
    height_bias: float = 0.5,
) -> None:
    """
    Make the cam-aim Empty (target) track the moving subject_root.
    The TRACK_TO constraint on the camera will then keep the camera
    pointed at the subject as it moves.

    We sample the subject's animated location each frame and copy it
    onto the target so the target rides along with the subject.
    """
    if target is None or subject_root is None:
        return

    # Sample subject motion: read its base location and any keyframed offsets
    try:
        # Snapshot the original target Z so we don't lose the height_bias offset
        original_target_z = target.location.z

        ad = getattr(subject_root, "animation_data", None)
        action = ad.action if ad else None
        if action is None:
            return

        # Build a map of (frame -> dx,dy,dz) by evaluating subject's location fcurves
        loc_curves = {0: None, 1: None, 2: None}
        for fc in _get_fcurves(action):
            if fc.data_path == "location" and fc.array_index in loc_curves:
                loc_curves[fc.array_index] = fc

        if not any(loc_curves.values()):
            return

        base_subj_x = subject_root.location.x
        base_subj_y = subject_root.location.y
        base_subj_z = subject_root.location.z

        base_tgt_x = target.location.x
        base_tgt_y = target.location.y
        base_tgt_z = target.location.z

        for frame in range(frame_start, frame_end + 1, 2):
            sx = loc_curves[0].evaluate(frame) if loc_curves[0] else base_subj_x
            sy = loc_curves[1].evaluate(frame) if loc_curves[1] else base_subj_y
            sz = loc_curves[2].evaluate(frame) if loc_curves[2] else base_subj_z

            dx = sx - base_subj_x
            dy = sy - base_subj_y
            dz = sz - base_subj_z

            target.location.x = base_tgt_x + dx
            target.location.y = base_tgt_y + dy
            target.location.z = base_tgt_z + dz

            target.keyframe_insert(data_path="location", frame=frame)

        target.location.x = base_tgt_x
        target.location.y = base_tgt_y
        target.location.z = base_tgt_z

        print(
            f"[MOTION] follow_target | target={target.name} -> subject={subject_root.name}",
            flush=True,
        )
    except Exception as e:
        print(f"[MOTION] follow_target error: {e}", flush=True)


def follow_camera_to_subject(
    cam,
    subject_root,
    frame_start: int,
    frame_end: int,
    forward_lag: float = 0.85,
) -> None:
    """
    Make the camera ride along with a moving subject (tracking shot).
    The camera maintains its starting offset to the subject and translates
    with it. forward_lag < 1 means the camera lags slightly behind, which
    feels more cinematic than perfect 1:1 tracking.
    """
    if cam is None or subject_root is None:
        return

    try:
        ad = getattr(subject_root, "animation_data", None)
        action = ad.action if ad else None
        if action is None:
            return

        loc_curves = {0: None, 1: None, 2: None}
        for fc in _get_fcurves(action):
            if fc.data_path == "location" and fc.array_index in loc_curves:
                loc_curves[fc.array_index] = fc

        if not any(loc_curves.values()):
            return

        base_subj_x = subject_root.location.x
        base_subj_y = subject_root.location.y
        base_subj_z = subject_root.location.z

        base_cam_x = cam.location.x
        base_cam_y = cam.location.y
        base_cam_z = cam.location.z

        for frame in range(frame_start, frame_end + 1, 2):
            sx = loc_curves[0].evaluate(frame) if loc_curves[0] else base_subj_x
            sy = loc_curves[1].evaluate(frame) if loc_curves[1] else base_subj_y
            sz = loc_curves[2].evaluate(frame) if loc_curves[2] else base_subj_z

            dx = (sx - base_subj_x) * forward_lag
            dy = (sy - base_subj_y) * forward_lag
            dz = (sz - base_subj_z) * forward_lag

            cam.location.x = base_cam_x + dx
            cam.location.y = base_cam_y + dy
            cam.location.z = base_cam_z + dz

            cam.keyframe_insert(data_path="location", frame=frame)

        cam.location.x = base_cam_x
        cam.location.y = base_cam_y
        cam.location.z = base_cam_z

        print(
            f"[MOTION] follow_camera | cam={cam.name} riding subject={subject_root.name} "
            f"lag={forward_lag:.2f}",
            flush=True,
        )
    except Exception as e:
        print(f"[MOTION] follow_camera error: {e}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# Tracking camera motion
# ═══════════════════════════════════════════════════════════════════════════

def _tracking_camera(
    cam,
    target,
    subject_center: tuple = (0.0, 0.0, 0.0),
    frame_start: int = 1,
    frame_end: int = 240,
    energy: float = 1.0,
    travel: float = 8.0,
) -> None:
    """Animate camera to track forward alongside a moving subject.

    The camera starts slightly behind the subject and glides forward,
    keeping pace with the subject's travel direction.  Combined with
    a TRACK_TO constraint on the target Empty, this produces a smooth
    tracking shot.
    """
    if cam is None:
        return

    total = max(1, frame_end - frame_start)
    cam_travel = travel * energy

    base_x = cam.location.x
    base_y = cam.location.y
    base_z = cam.location.z

    try:
        for frame in range(frame_start, frame_end + 1, 2):
            t = (frame - frame_start) / total
            ease = _smoothstep(t)

            # Track forward in -Y (same direction as vehicle_drive)
            cam.location.y = base_y - cam_travel * ease
            cam.keyframe_insert(data_path="location", frame=frame)

        _smooth_keyframes(cam)

        # Reset live transform
        cam.location.x = base_x
        cam.location.y = base_y
        cam.location.z = base_z

        print(
            f"[MOTION] _tracking_camera | cam={cam.name} travel={cam_travel:.1f}",
            flush=True,
        )
    except Exception as e:
        print(f"[MOTION] _tracking_camera error: {e}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# V1.3 Phase 5 — camera-driven motion profiles
# ═══════════════════════════════════════════════════════════════════════════
# These profiles animate the scene CAMERA around a static (or
# independently-animated) subject.  They all take the same signature as
# the hero-facing profiles so the dispatcher in animation_ops.animate_
# subject_group can route to them uniformly: the dispatcher passes
# `instances` (hero roots) and we transparently switch to operating on
# bpy.context.scene.camera when the style name starts with `camera_`.
#
# Each profile is a 60-line cinematographer's decision, not a generic
# math function.  The intent — arcing orbit, emotional push-in,
# scale-revealing pullback — matches the directorial vocabulary of the
# compositions that drive them.
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_camera_and_hero(bpy_module, instances):
    """Return (cam, hero_world_center) or (None, None)."""
    try:
        cam = bpy_module.context.scene.camera if bpy_module is not None else None
    except Exception:
        cam = None
    if cam is None:
        return None, None
    # Hero center: average of first instance's root-object locations
    hero_center = (0.0, 0.0, 0.0)
    if instances:
        first = instances[0] if isinstance(instances[0], list) else [instances[0]]
        if first:
            xs = [o.location.x for o in first if hasattr(o, "location")]
            ys = [o.location.y for o in first if hasattr(o, "location")]
            zs = [o.location.z for o in first if hasattr(o, "location")]
            if xs:
                hero_center = (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
    return cam, hero_center


def _camera_orbit_slow(root_objs, frame_end: int, offset: int = 0,
                       arc_degrees: float = 30.0, speed: float = 0.3) -> None:
    """Slow arcing orbit of the camera around the hero.

    The camera keeps its initial distance to the hero and sweeps through
    `arc_degrees` over the frame range, aimed at the hero via the track
    constraint a human rigger would apply manually.  Used when the scene
    wants to feel contemplative — Malick / Lubezki slow-arc.
    """
    try:
        import bpy
        import math
        cam, hero_center = _resolve_camera_and_hero(bpy, [root_objs] if isinstance(root_objs, list) else root_objs)
        if cam is None:
            print("[MOTION] _camera_orbit_slow: no camera found", flush=True)
            return

        # Relative to hero
        rx = cam.location.x - hero_center[0]
        ry = cam.location.y - hero_center[1]
        radius = max(math.sqrt(rx * rx + ry * ry), 0.5)
        start_angle = math.atan2(ry, rx)

        total = max(1, frame_end - 1)
        arc_rad = math.radians(arc_degrees) * speed
        base_z = cam.location.z

        for frame in range(1 + offset, frame_end + 1, 2):
            t = (frame - 1 - offset) / max(1, total)
            ease = _smoothstep(t)
            a = start_angle + arc_rad * ease
            cam.location.x = hero_center[0] + radius * math.cos(a)
            cam.location.y = hero_center[1] + radius * math.sin(a)
            cam.location.z = base_z
            cam.keyframe_insert(data_path="location", frame=frame)

        _smooth_keyframes(cam)
        print(
            f"[MOTION] _camera_orbit_slow | cam={cam.name} arc_deg={arc_degrees} "
            f"speed={speed} radius={radius:.2f}",
            flush=True,
        )
    except Exception as e:
        print(f"[MOTION] _camera_orbit_slow error: {e}", flush=True)


def _camera_push_in_cinema(root_objs, frame_end: int, offset: int = 0,
                           start_distance_multiplier: float = 5.0,
                           end_distance_multiplier: float = 2.0,
                           speed: float = 0.6) -> None:
    """Classic emotional push-in. Camera starts far, dollies toward the
    hero along its own current forward vector, slowing as it approaches.

    Unlike the tracking-camera profile this one does NOT fly alongside
    the subject — the hero is assumed static, and the camera simply
    closes distance.
    """
    try:
        import bpy
        import math
        cam, hero_center = _resolve_camera_and_hero(bpy, [root_objs] if isinstance(root_objs, list) else root_objs)
        if cam is None:
            print("[MOTION] _camera_push_in_cinema: no camera found", flush=True)
            return

        # Unit vector from hero → camera (camera's current axis)
        dx = cam.location.x - hero_center[0]
        dy = cam.location.y - hero_center[1]
        dz = cam.location.z - hero_center[2]
        d = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        ux, uy, uz = dx / d, dy / d, dz / d

        # Resolve start/end distances as multiples of current distance
        start_d = d * (start_distance_multiplier / max(start_distance_multiplier, 0.01))
        # Start at current location, end at `end/start` fraction of distance
        end_d = d * (end_distance_multiplier / max(start_distance_multiplier, 0.01))

        total = max(1, frame_end - 1)
        for frame in range(1 + offset, frame_end + 1, 2):
            t = (frame - 1 - offset) / max(1, total)
            ease = _smoothstep(min(1.0, t * speed + (1.0 - speed) * t))
            cur = start_d + (end_d - start_d) * ease
            cam.location.x = hero_center[0] + ux * cur
            cam.location.y = hero_center[1] + uy * cur
            cam.location.z = hero_center[2] + uz * cur
            cam.keyframe_insert(data_path="location", frame=frame)

        _smooth_keyframes(cam)
        print(
            f"[MOTION] _camera_push_in_cinema | cam={cam.name} "
            f"start_d={start_d:.2f} end_d={end_d:.2f}",
            flush=True,
        )
    except Exception as e:
        print(f"[MOTION] _camera_push_in_cinema error: {e}", flush=True)


def _camera_epic_pullback(root_objs, frame_end: int, offset: int = 0,
                          start_distance_multiplier: float = 3.0,
                          end_distance_multiplier: float = 15.0,
                          height_rise: float = 4.0) -> None:
    """Scale-revealing pullback. Camera starts near-and-low, pulls back
    and rises so by the end of the shot the hero is a speck in the
    landscape. The Empire Strikes Back / Contact closing pullback.
    """
    try:
        import bpy
        import math
        cam, hero_center = _resolve_camera_and_hero(bpy, [root_objs] if isinstance(root_objs, list) else root_objs)
        if cam is None:
            print("[MOTION] _camera_epic_pullback: no camera found", flush=True)
            return

        dx = cam.location.x - hero_center[0]
        dy = cam.location.y - hero_center[1]
        d_xy = math.sqrt(dx * dx + dy * dy) or 1.0
        ux, uy = dx / d_xy, dy / d_xy
        base_z = cam.location.z

        total = max(1, frame_end - 1)
        for frame in range(1 + offset, frame_end + 1, 2):
            t = (frame - 1 - offset) / max(1, total)
            ease = _smoothstep(t)
            mult = start_distance_multiplier + (end_distance_multiplier - start_distance_multiplier) * ease
            cam.location.x = hero_center[0] + ux * d_xy * (mult / max(start_distance_multiplier, 0.01))
            cam.location.y = hero_center[1] + uy * d_xy * (mult / max(start_distance_multiplier, 0.01))
            cam.location.z = base_z + height_rise * ease
            cam.keyframe_insert(data_path="location", frame=frame)

        _smooth_keyframes(cam)
        print(
            f"[MOTION] _camera_epic_pullback | cam={cam.name} "
            f"start_x{start_distance_multiplier} end_x{end_distance_multiplier} "
            f"rise={height_rise:.2f}",
            flush=True,
        )
    except Exception as e:
        print(f"[MOTION] _camera_epic_pullback error: {e}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# Profile registry + dispatch
# ═══════════════════════════════════════════════════════════════════════════

_MOTION_PROFILES: dict[str, callable] = {
    "vehicle_drive":        _vehicle_drive,
    "vehicle_drift":        _vehicle_drift,
    "character_walk":       _character_walk,
    "character_dance":      _character_dance,
    "idle_breathe":         _idle_breathe,
    # V1.3 Phase 5: camera-driven directorial profiles
    "camera_orbit_slow":    _camera_orbit_slow,
    "camera_push_in":       _camera_push_in_cinema,
    "camera_push_in_cinema": _camera_push_in_cinema,
    "camera_epic_pullback": _camera_epic_pullback,
}

_DIRECTORIAL_STYLES = set(_MOTION_PROFILES.keys())


def is_directorial_style(animation_style: str) -> bool:
    return animation_style in _DIRECTORIAL_STYLES


def lock_camera_to_subject(
    bpy,
    cam,
    hero,
    target_empty=None,
    frame_start: int = 1,
    frame_end: int = 240,
) -> dict:
    """Enforce full-timeline camera-subject lock.

    Real directors never leave a shot where the camera's keyframe range
    is shorter than the subject's.  If the hero has keyframes on
    frames [a..b] but the camera only covers [c..d], we extend the
    camera's coverage to match by holding the first/last pose at the
    missing endpoints.  Also ensures a TRACK_TO constraint exists as a
    belt-and-suspenders aim lock — even if the camera's keyframed
    position drifts, the rotation still points at the subject.

    Returns a dict describing what was done (used by the [CAMERA_LOCK]
    log line).
    """
    info = {
        "hero_keyframes": (0, 0),   # (first_frame, last_frame)
        "camera_keyframes": (0, 0),
        "extended": False,
        "track_constraint": "none",
    }
    if cam is None or hero is None:
        return info

    def _frame_range(obj):
        ad = getattr(obj, "animation_data", None)
        if not ad or not ad.action:
            return (0, 0)
        try:
            fcs = ad.action.fcurves
        except AttributeError:
            fcs = []
            if hasattr(ad.action, "layers") and ad.action.layers:
                _lyr = ad.action.layers[0]
                if hasattr(_lyr, "strips") and _lyr.strips:
                    _stp = _lyr.strips[0]
                    if hasattr(_stp, "channelbags") and _stp.channelbags:
                        fcs = _stp.channelbags[0].fcurves
        frames: list[int] = []
        for fc in fcs:
            for kp in fc.keyframe_points:
                try:
                    frames.append(int(kp.co.x))
                except Exception:
                    pass
        if not frames:
            return (0, 0)
        return (min(frames), max(frames))

    hero_a, hero_b = _frame_range(hero)
    cam_c, cam_d = _frame_range(cam)
    info["hero_keyframes"] = (hero_a, hero_b)
    info["camera_keyframes"] = (cam_c, cam_d)

    # If hero has animation but camera doesn't cover its full range,
    # extend the camera by holding its current pose at the missing end(s).
    if hero_a and hero_b and (cam_c or cam_d):
        want_start = min(hero_a, cam_c) if cam_c else hero_a
        want_end = max(hero_b, cam_d) if cam_d else hero_b
        # Also never go below scene.frame_start / above scene.frame_end
        want_start = min(want_start, frame_start)
        want_end = max(want_end, frame_end)

        if cam_c and want_start < cam_c:
            # Evaluate camera location at cam_c, replay as keyframe at want_start
            try:
                bpy.context.scene.frame_set(cam_c)
                bpy.context.view_layer.update()
                _loc_at_c = cam.location.copy()
                cam.location = _loc_at_c
                cam.keyframe_insert(data_path="location", frame=want_start)
                info["extended"] = True
            except Exception as e:
                print(f"[CAMERA_LOCK] extend-start failed: {e}", flush=True)

        if cam_d and want_end > cam_d:
            try:
                bpy.context.scene.frame_set(cam_d)
                bpy.context.view_layer.update()
                _loc_at_d = cam.location.copy()
                cam.location = _loc_at_d
                cam.keyframe_insert(data_path="location", frame=want_end)
                info["extended"] = True
            except Exception as e:
                print(f"[CAMERA_LOCK] extend-end failed: {e}", flush=True)

    # Ensure TRACK_TO constraint exists for belt-and-suspenders aim lock.
    _already_has_track = False
    for _con in cam.constraints:
        if _con.type == "TRACK_TO":
            _already_has_track = True
            info["track_constraint"] = "EXISTING"
            break
    if not _already_has_track:
        _aim = target_empty if target_empty is not None else hero
        try:
            _con = cam.constraints.new(type="TRACK_TO")
            _con.target = _aim
            _con.track_axis = "TRACK_NEGATIVE_Z"
            _con.up_axis = "UP_Y"
            info["track_constraint"] = "ADDED"
        except Exception as e:
            print(f"[CAMERA_LOCK] TRACK_TO add failed: {e}", flush=True)

    print(
        f"[CAMERA_LOCK] hero={hero.name!r} "
        f"hero_keyframes=[{info['hero_keyframes'][0]}..{info['hero_keyframes'][1]}] "
        f"camera_keyframes=[{info['camera_keyframes'][0]}..{info['camera_keyframes'][1]}] "
        f"extended={info['extended']} "
        f"track_constraint={info['track_constraint']}",
        flush=True,
    )
    return info


def apply_directorial_motion(
    bpy,
    scene,
    instances: list[list],
    scene_plan: dict,
    frame_start: int = 1,
    frame_end: int = 240,
    stagger_frames: int = 8,
) -> bool:
    """
    Apply directorial motion to subject instances based on scene_plan.

    For each instance, animate the SINGLE root object (not every leaf
    mesh). For vehicles, also detect and spin wheels.

    Returns True if motion was applied to at least one instance.
    """
    anim_style = scene_plan.get("animation_style", "")
    if not is_directorial_style(anim_style):
        return False

    energy = scene_plan.get("energy_multiplier", 1.0)
    profile_fn = _MOTION_PROFILES[anim_style]
    is_vehicle = anim_style.startswith("vehicle")

    print(
        f"[MOTION] applying directorial motion | style={anim_style} "
        f"energy={energy} instances={len(instances or [])}",
        flush=True,
    )

    from .animation_ops import find_animation_root, find_wheel_meshes

    applied_any = False
    animated_roots: list = []

    for idx, root_objs in enumerate(instances or []):
        offset = idx * stagger_frames
        root = find_animation_root(root_objs)
        if root is None:
            print(f"[MOTION] instance {idx}: no root found, skipping", flush=True)
            continue

        wheels = None
        if is_vehicle:
            wheels = find_wheel_meshes(root)
            if wheels:
                print(f"[MOTION] instance {idx}: detected {len(wheels)} wheel meshes", flush=True)

        profile_fn(
            root,
            frame_start=frame_start,
            frame_end=frame_end,
            energy=energy,
            stagger=offset,
            wheels=wheels,
        )
        animated_roots.append(root)
        applied_any = True

    # Stash animated roots on the scene_plan so the behavior layer can wire
    # the camera target to follow them.
    if applied_any and animated_roots:
        scene_plan["_animated_roots"] = animated_roots
        scene_plan["_primary_animated_root"] = animated_roots[0]

    return applied_any


def apply_tracking_camera_if_needed(
    cam,
    target,
    scene_plan: dict,
    subject_center: tuple = (0, 0, 0),
    frame_start: int = 1,
    frame_end: int = 240,
) -> bool:
    """
    Legacy helper. Prefer execute_behavior() which now wires camera target
    follow + camera lag automatically.
    """
    if scene_plan.get("_behavior_executed"):
        return False

    cam_style = scene_plan.get("_camera_style")
    motion_style = scene_plan.get("_motion_style")

    if cam_style in ("tracking", "follow") or motion_style in ("driving", "walking"):
        primary = scene_plan.get("_primary_animated_root")
        if primary is not None:
            follow_target_to_subject(target, primary, frame_start, frame_end)
            follow_camera_to_subject(cam, primary, frame_start, frame_end)
            return True

    return False
