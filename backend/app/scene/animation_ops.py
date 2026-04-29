from __future__ import annotations

from math import pi
from typing import Optional


def _get_fcurves(action):
    """Get fcurves from an Action, compatible with old and new Blender APIs."""
    if action is None:
        return []
    try:
        fc = action.fcurves
        if fc is not None:
            return fc
    except AttributeError:
        pass
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


def find_armatures(root_objs) -> list:
    result = []
    seen: set[str] = set()

    def walk(obj) -> None:
        if obj is None or obj.name in seen:
            return
        seen.add(obj.name)
        if getattr(obj, "type", None) == "ARMATURE":
            result.append(obj)
        for child in getattr(obj, "children", []):
            walk(child)

    for obj in root_objs:
        walk(obj)
    return result


def find_mesh_roots(root_objs) -> list:
    result = []
    seen: set[str] = set()

    def walk(obj) -> None:
        if obj is None or obj.name in seen:
            return
        seen.add(obj.name)
        if getattr(obj, "type", None) == "MESH":
            result.append(obj)
        for child in getattr(obj, "children", []):
            walk(child)

    for obj in root_objs:
        walk(obj)
    return result


def find_animation_root(root_objs):
    """
    Find the single best object to keyframe so that the WHOLE imported asset
    moves coherently — i.e. the topmost ancestor that owns the asset's
    transform.

    Priority:
      0. Any object tagged ``is_hero_root`` (set by import_glb_as_hero_group
         and _dedup_blend_roots) — this is explicitly the hero root and
         bypasses every heuristic.
      1. Top-most ARMATURE in the hierarchy (best for rigged characters).
      2. Top-most parentless ancestor among the root_objs themselves.
      3. The single common parent of all root_objs, if they share one.
      4. The first object in root_objs (last-resort fallback).

    Animating this single object — rather than every leaf mesh — is what
    makes the entire car/character translate and rotate as one unit.
    """
    if not root_objs:
        return None

    # 0. Explicit hero-root tag wins — downstream dedup + import set this
    # on the surviving Sketchfab scene root so motion targets the right
    # object even when the hierarchy has multiple candidates.
    for obj in root_objs:
        cursor = obj
        while cursor is not None:
            if cursor.get("is_hero_root", False):
                return cursor
            cursor = getattr(cursor, "parent", None)

    # 1. Prefer an armature if any object in the hierarchy is/has one
    arms = find_armatures(root_objs)
    if arms:
        # Pick the one with no parent or whose parent is not also an armature
        top = arms[0]
        cursor = top
        while getattr(cursor, "parent", None) is not None:
            cursor = cursor.parent
        return cursor

    # 2. Walk every supplied root upward to its true top-level ancestor
    candidates = []
    for obj in root_objs:
        cursor = obj
        while getattr(cursor, "parent", None) is not None:
            cursor = cursor.parent
        if cursor is not None and cursor not in candidates:
            candidates.append(cursor)

    # If they all share a single top ancestor → use it
    if len(candidates) == 1:
        return candidates[0]

    # If there are multiple top-level ancestors but one is an EMPTY parent of
    # the others, prefer it
    for cand in candidates:
        if getattr(cand, "type", None) == "EMPTY":
            return cand

    # 3. Otherwise just pick the first true root
    if candidates:
        return candidates[0]

    return root_objs[0]


_WHEEL_NAME_HINTS = (
    "wheel", "tire", "tyre", "rim", "rotor", "brake", "hub",
    "Wheel", "Tire", "Tyre", "Rim", "Rotor", "Brake", "Hub",
    "WHEEL", "TIRE", "TYRE", "RIM",
)


def find_wheel_meshes(root_obj) -> list:
    """
    Walk the descendants of root_obj looking for mesh objects whose names
    suggest they are wheels/tires. Returns a list of those meshes so we can
    apply per-wheel rotation in vehicle motion profiles.
    """
    if root_obj is None:
        return []

    found: list = []
    seen: set[str] = set()

    def walk(obj) -> None:
        if obj is None or obj.name in seen:
            return
        seen.add(obj.name)
        name = obj.name or ""
        if getattr(obj, "type", None) == "MESH" and any(h in name for h in _WHEEL_NAME_HINTS):
            found.append(obj)
        for child in getattr(obj, "children", []):
            walk(child)

    walk(root_obj)
    return found


def get_world_location(obj):
    """Return the world-space location of obj as a tuple, ignoring any
    keyframes — uses matrix_world translation."""
    if obj is None:
        return (0.0, 0.0, 0.0)
    try:
        m = obj.matrix_world
        return (m.translation.x, m.translation.y, m.translation.z)
    except Exception:
        return (
            getattr(obj.location, "x", 0.0),
            getattr(obj.location, "y", 0.0),
            getattr(obj.location, "z", 0.0),
        )


def get_armature_actions(armature_obj) -> list:
    actions = []
    ad = getattr(armature_obj, "animation_data", None)
    if ad and ad.action:
        actions.append(ad.action)
    if ad:
        for track in getattr(ad, "nla_tracks", []):
            for strip in getattr(track, "strips", []):
                if strip.action and strip.action not in actions:
                    actions.append(strip.action)
    return actions


def push_action_to_nla(armature_obj, action, track_name: str = "Anim", frame_start: int = 1) -> bool:
    try:
        ad = armature_obj.animation_data
        if ad is None:
            armature_obj.animation_data_create()
            ad = armature_obj.animation_data

        ad.action = None

        track = ad.nla_tracks.new()
        track.name = track_name
        strip = track.strips.new(action.name, frame_start, action)
        strip.action_frame_start = action.frame_range[0]
        strip.action_frame_end = action.frame_range[1]
        strip.use_auto_blend = False
        print(
            f"[ANIM] NLA push | arm={armature_obj.name} action={action.name} "
            f"frames={action.frame_range[0]:.0f}-{action.frame_range[1]:.0f}",
            flush=True,
        )
        return True
    except Exception as e:
        print(f"[ANIM] NLA push failed: {e}", flush=True)
        return False


def _fallback_bounce(objs, frame_end: int, offset: int = 0, amplitude: float = 0.12, period: int = 20) -> None:
    for obj in objs:
        try:
            base_z = obj.location.z
            f1 = 1 + offset
            f2 = f1 + period // 2

            obj.location.z = base_z
            obj.keyframe_insert(data_path="location", index=2, frame=f1)
            obj.location.z = base_z + amplitude
            obj.keyframe_insert(data_path="location", index=2, frame=f2)
            obj.location.z = base_z
            obj.keyframe_insert(data_path="location", index=2, frame=f2 + period // 2)

            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path == "location" and fc.array_index == 2:
                        fc.modifiers.new(type="CYCLES")
        except Exception as e:
            print(f"[ANIM] _fallback_bounce error on {obj.name}: {e}", flush=True)


def _fallback_sway(objs, frame_end: int, offset: int = 0, amplitude_deg: float = 8.0, period: int = 30) -> None:
    import math
    amp = math.radians(amplitude_deg)
    for obj in objs:
        try:
            base_rz = obj.rotation_euler.z
            f1 = 1 + offset
            f2 = f1 + period // 2
            f3 = f2 + period // 2

            obj.rotation_euler.z = base_rz - amp
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=f1)
            obj.rotation_euler.z = base_rz + amp
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=f2)
            obj.rotation_euler.z = base_rz - amp
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=f3)

            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path == "rotation_euler" and fc.array_index == 2:
                        fc.modifiers.new(type="CYCLES")
        except Exception as e:
            print(f"[ANIM] _fallback_sway error on {obj.name}: {e}", flush=True)


def _fallback_dance(
    objs,
    frame_end: int,
    offset: int = 0,
    amplitude_deg: float = 14.0,
    bob_amplitude: float = 0.18,
    period: int = 18,
) -> None:
    """
    Rhythmic dance motion (Round 9 Pillar 1C):
      • Z-rotation sway (hip swing) at ``period`` frames/cycle.
      • Vertical bob at half the sway period, so each sway crosses the
        beat with a down-step — like a real weight shift.
      • Small X-tilt to avoid the robotic feel of pure yaw.

    All three axes use CYCLES modifiers so the animation loops without
    needing explicit keyframes for every beat across ``frame_end``.
    """
    import math
    amp_z = math.radians(amplitude_deg)
    amp_x = math.radians(amplitude_deg * 0.35)
    half = max(1, period // 2)
    quarter = max(1, period // 4)
    for obj in objs:
        try:
            base_z_loc = obj.location.z
            base_rz = obj.rotation_euler.z
            base_rx = obj.rotation_euler.x

            f0 = 1 + offset
            # ── Z-rotation sway ─────────────────────────────────────────
            obj.rotation_euler.z = base_rz - amp_z
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=f0)
            obj.rotation_euler.z = base_rz + amp_z
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=f0 + half)
            obj.rotation_euler.z = base_rz - amp_z
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=f0 + period)

            # ── Vertical bob (twice the sway frequency) ─────────────────
            bob_half = max(1, half // 2)
            obj.location.z = base_z_loc
            obj.keyframe_insert(data_path="location", index=2, frame=f0)
            obj.location.z = base_z_loc + bob_amplitude
            obj.keyframe_insert(data_path="location", index=2, frame=f0 + bob_half)
            obj.location.z = base_z_loc
            obj.keyframe_insert(data_path="location", index=2, frame=f0 + half)

            # ── Subtle forward/back tilt offset by a quarter beat ───────
            obj.rotation_euler.x = base_rx - amp_x
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f0 + quarter)
            obj.rotation_euler.x = base_rx + amp_x
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f0 + quarter + half)

            # Loop everything with CYCLES so it carries to frame_end.
            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path in ("rotation_euler", "location"):
                        # Only loop the axes we actually keyed.
                        if (
                            (fc.data_path == "rotation_euler" and fc.array_index in (0, 2))
                            or (fc.data_path == "location" and fc.array_index == 2)
                        ):
                            fc.modifiers.new(type="CYCLES")
        except Exception as e:
            print(f"[ANIM] _fallback_dance error on {obj.name}: {e}", flush=True)


def _fallback_talk_nod(objs, frame_end: int, offset: int = 0, amplitude_deg: float = 5.0, period: int = 18) -> None:
    import math
    amp = math.radians(amplitude_deg)
    for obj in objs:
        try:
            base_rx = obj.rotation_euler.x
            f1 = 1 + offset
            f2 = f1 + period // 2
            f3 = f2 + period // 2

            obj.rotation_euler.x = base_rx
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f1)
            obj.rotation_euler.x = base_rx + amp
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f2)
            obj.rotation_euler.x = base_rx
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f3)

            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path == "rotation_euler" and fc.array_index == 0:
                        fc.modifiers.new(type="CYCLES")
        except Exception as e:
            print(f"[ANIM] _fallback_talk_nod error on {obj.name}: {e}", flush=True)


def _fallback_swim_arc(objs, frame_end: int, offset: int = 0, travel: float = 2.0, period: int = 80) -> None:
    import math
    for obj in objs:
        try:
            base_y = obj.location.y
            base_rx = obj.rotation_euler.x
            pitch = math.radians(6.0)
            half = period // 2
            f1 = 1 + offset

            obj.location.y = base_y - travel
            obj.keyframe_insert(data_path="location", index=1, frame=f1)
            obj.location.y = base_y + travel
            obj.keyframe_insert(data_path="location", index=1, frame=f1 + period)

            obj.rotation_euler.x = base_rx - pitch
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f1)
            obj.rotation_euler.x = base_rx + pitch
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f1 + half)
            obj.rotation_euler.x = base_rx - pitch
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f1 + period)

            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path in ("location", "rotation_euler"):
                        fc.modifiers.new(type="CYCLES")
        except Exception as e:
            print(f"[ANIM] _fallback_swim_arc error on {obj.name}: {e}", flush=True)


def _fallback_turntable(objs, frame_end: int, offset: int = 0) -> None:
    for obj in objs:
        try:
            base_rz = obj.rotation_euler.z
            obj.rotation_euler.z = base_rz
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=1)
            obj.rotation_euler.z = base_rz + 2.0 * pi
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=frame_end)

            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path == "rotation_euler" and fc.array_index == 2:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
        except Exception as e:
            print(f"[ANIM] _fallback_turntable error on {obj.name}: {e}", flush=True)


def _fallback_glide(objs, frame_end: int, offset: int = 0, travel: float = 8.0) -> None:
    for obj in objs:
        try:
            base_y = obj.location.y
            obj.location.y = base_y - travel * 0.5
            obj.keyframe_insert(data_path="location", index=1, frame=1)
            obj.location.y = base_y + travel * 0.5
            obj.keyframe_insert(data_path="location", index=1, frame=frame_end)
            obj.location.y = base_y
        except Exception as e:
            print(f"[ANIM] _fallback_glide error on {obj.name}: {e}", flush=True)


def _fallback_fly_soar(
    objs,
    frame_end: int,
    offset: int = 0,
    travel: float = 12.0,
    base_altitude: float = 3.0,
    altitude_amp: float = 1.2,
    bank_deg: float = 8.0,
    period: int = 60,
) -> None:
    """
    Bird / flyer motion: forward travel + sinusoidal altitude + lateral
    bank. Designed for eagles, dragons, anything soaring over a landscape.
    """
    import math
    bank = math.radians(bank_deg)
    for obj in objs:
        try:
            base_x = obj.location.x
            base_y = obj.location.y
            base_rz = obj.rotation_euler.z

            f0 = 1 + offset
            f_end = max(f0 + 1, frame_end)

            # Forward travel (Y axis).
            obj.location.y = base_y - travel * 0.5
            obj.keyframe_insert(data_path="location", index=1, frame=f0)
            obj.location.y = base_y + travel * 0.5
            obj.keyframe_insert(data_path="location", index=1, frame=f_end)

            # Altitude sine wave.
            half = max(1, period // 2)
            quarter = max(1, period // 4)
            f = f0
            lift = 0
            while f <= f_end:
                phase = ((f - f0) % period) / float(period)
                obj.location.z = base_altitude + altitude_amp * math.sin(phase * math.tau)
                obj.keyframe_insert(data_path="location", index=2, frame=f)
                f += quarter
                lift += 1
            if lift < 2:
                obj.location.z = base_altitude
                obj.keyframe_insert(data_path="location", index=2, frame=f_end)

            # Lateral bank (z-rotation), phase-shifted so banks don't align
            # with altitude peaks — feels like natural flight path.
            f = f0
            while f <= f_end:
                phase = (((f - f0) + half) % period) / float(period)
                obj.rotation_euler.z = base_rz + bank * math.sin(phase * math.tau)
                obj.keyframe_insert(data_path="rotation_euler", index=2, frame=f)
                f += half

            # Make travel linear, sinusoidal curves keep their bezier tangents.
            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path == "location" and fc.array_index == 1:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
        except Exception as e:
            print(f"[ANIM] _fallback_fly_soar error on {obj.name}: {e}", flush=True)


def _fallback_gallop(
    objs,
    frame_end: int,
    offset: int = 0,
    travel: float = 12.0,
    bob_amp: float = 0.18,
    period: int = 12,
    pitch_deg: float = 4.0,
) -> None:
    """
    Horse / large-quadruped gallop: strong forward travel + tall vertical
    bob + forward-back pitch. Period is short because gallop gait has a
    rapid 4-beat cadence.
    """
    import math
    pitch = math.radians(pitch_deg)
    for obj in objs:
        try:
            base_y = obj.location.y
            base_z = obj.location.z
            base_rx = obj.rotation_euler.x

            f0 = 1 + offset
            f_end = max(f0 + 1, frame_end)

            # Linear forward travel.
            obj.location.y = base_y - travel * 0.5
            obj.keyframe_insert(data_path="location", index=1, frame=f0)
            obj.location.y = base_y + travel * 0.5
            obj.keyframe_insert(data_path="location", index=1, frame=f_end)

            # Vertical bob: apex at each stride peak.
            f = f0
            step = max(1, period // 4)
            i = 0
            while f <= f_end:
                phase = (i % 4) / 4.0
                obj.location.z = base_z + bob_amp * max(0.0, math.sin(phase * math.tau))
                obj.keyframe_insert(data_path="location", index=2, frame=f)
                f += step
                i += 1

            # Pitch forward on the downbeat.
            f = f0
            i = 0
            half = max(1, period // 2)
            while f <= f_end:
                obj.rotation_euler.x = base_rx + (pitch if i % 2 == 0 else -pitch * 0.5)
                obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f)
                f += half
                i += 1

            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path == "location" and fc.array_index == 1:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
        except Exception as e:
            print(f"[ANIM] _fallback_gallop error on {obj.name}: {e}", flush=True)


def _fallback_vehicle_glide(objs, frame_end: int, offset: int = 0, travel: float = 6.0) -> None:
    import math
    lean = math.radians(1.8)
    for obj in objs:
        try:
            base_y = obj.location.y
            base_rz = obj.rotation_euler.z

            f1 = max(1, 1 + offset)
            f2 = frame_end

            obj.location.y = base_y - travel * 0.5
            obj.rotation_euler.z = base_rz - lean
            obj.keyframe_insert(data_path="location", index=1, frame=f1)
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=f1)

            obj.location.y = base_y + travel * 0.5
            obj.rotation_euler.z = base_rz + lean
            obj.keyframe_insert(data_path="location", index=1, frame=f2)
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=f2)

            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path in ("location", "rotation_euler"):
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"

            obj.location.y = base_y
            obj.rotation_euler.z = base_rz
        except Exception as e:
            print(f"[ANIM] _fallback_vehicle_glide error on {obj.name}: {e}", flush=True)


_FALLBACK_PROFILES: dict[str, tuple] = {
    "dance": (_fallback_dance, {"amplitude_deg": 14.0, "bob_amplitude": 0.18, "period": 18}),
    "talk": (_fallback_talk_nod, {"amplitude_deg": 5.0, "period": 18}),
    "swim": (_fallback_swim_arc, {"travel": 2.0, "period": 80}),
    "rotate": (_fallback_turntable, {}),
    "glide": (_fallback_glide, {"travel": 8.0}),
    "vehicle_glide": (_fallback_vehicle_glide, {"travel": 6.0}),
    "bounce": (_fallback_bounce, {"amplitude": 0.12, "period": 20}),
}


def _dispatch_fallback(action: str, objs: list, frame_end: int, offset: int) -> None:
    if not objs:
        print(f"[ANIM] _dispatch_fallback: no objects for action={action}", flush=True)
        return

    entry = _FALLBACK_PROFILES.get(action)
    if entry is None:
        print(f"[ANIM] _dispatch_fallback: no profile for action='{action}', skipping", flush=True)
        return

    profile_func, kwargs = entry
    try:
        profile_func(objs, frame_end=frame_end, offset=offset, **kwargs)
    except Exception as e:
        print(f"[ANIM] _dispatch_fallback error: action={action} {e}", flush=True)


def animate_subject_group(
    bpy,
    instances,
    action,
    mode=None,
    frame_start=1,
    frame_end=120,
    stagger_frames=0,
    scene_plan: Optional[dict] = None,
    **kwargs,
):
    # ── Check if directorial motion system should handle this ─────────
    if scene_plan:
        try:
            from .directorial_motion import is_directorial_style, apply_directorial_motion
            anim_style = scene_plan.get("animation_style", "")
            if is_directorial_style(anim_style):
                applied = apply_directorial_motion(
                    bpy, None, instances,
                    scene_plan,
                    frame_start=frame_start,
                    frame_end=frame_end,
                    stagger_frames=stagger_frames,
                )
                if applied:
                    print(f"[ANIM] routed to directorial motion: {anim_style}", flush=True)
                    return
        except ImportError:
            pass  # directorial_motion not available, fall through

    for idx, root_objs in enumerate(instances or []):
        offset = idx * stagger_frames
        armatures = find_armatures(root_objs)
        meshes = find_mesh_roots(root_objs)

        nla_pushed = False
        if armatures:
            for arm in armatures:
                existing_actions = get_armature_actions(arm)
                if existing_actions:
                    pushed = push_action_to_nla(
                        arm,
                        existing_actions[0],
                        track_name=f"{action}_{idx}",
                        frame_start=frame_start + offset,
                    )
                    if pushed:
                        print(
                            f"[ANIM] instance {idx}: NLA playback via existing action '{existing_actions[0].name}'",
                            flush=True,
                        )
                        nla_pushed = True
                        break

        if nla_pushed:
            continue
        elif armatures:
            print(f"[ANIM] instance {idx}: rigged but no baked action -> procedural on armature", flush=True)
            _dispatch_fallback(action, armatures, frame_end, offset)
        else:
            print(f"[ANIM] instance {idx}: unrigged -> procedural fallback on meshes", flush=True)
            _dispatch_fallback(action, meshes, frame_end, offset)


def apply_animation_instructions(
    instructions: list[dict],
    subject_groups: Optional[list[list]] = None,
    frame_start: int = 1,
    frame_end: int = 120,
    stagger_frames: int = 8,
) -> None:
    for i, inst in enumerate(instructions):
        subject = inst.get("subject", "")
        action = inst.get("action", "")
        mode = inst.get("mode", "")

        print(f"[ANIM] instruction | subject={subject} action={action} mode={mode}", flush=True)

        if subject_groups is not None and i < len(subject_groups):
            group = subject_groups[i]
            animate_subject_group(
                None,
                group if isinstance(group[0], list) else [group],
                action=action,
                mode=mode,
                frame_start=frame_start,
                frame_end=frame_end,
                stagger_frames=stagger_frames,
            )
        else:
            _legacy_dispatch(action, mode, frame_end)


def _legacy_dispatch(action: str, mode: str, frame_end: int) -> None:
    try:
        import bpy as _bpy
    except ImportError:
        print("[ANIM] _legacy_dispatch: bpy not available", flush=True)
        return

    if action == "rotate" and mode == "turntable":
        targets = [o for o in _bpy.data.objects if o.type == "MESH"]
        _fallback_turntable(targets, frame_end)
    elif action == "dance":
        targets = [o for o in _bpy.data.objects if o.type == "ARMATURE"]
        if not targets:
            targets = [o for o in _bpy.data.objects if o.type == "MESH"]
        _fallback_sway(targets, frame_end)
    elif action == "talk":
        targets = [o for o in _bpy.data.objects if o.type in ("ARMATURE", "MESH")]
        _fallback_talk_nod(targets, frame_end)
    elif action == "swim":
        targets = [o for o in _bpy.data.objects if o.type == "MESH"]
        _fallback_swim_arc(targets, frame_end)
    elif action == "glide":
        targets = [o for o in _bpy.data.objects if o.type == "MESH"]
        _fallback_glide(targets, frame_end)


# ═══════════════════════════════════════════════════════════════════════════
# Behavior-driven animation dispatch
# ═══════════════════════════════════════════════════════════════════════════

# Maps desired action to keywords for matching baked animation names
_ACTION_KEYWORDS: dict[str, list[str]] = {
    "walking": ["walk", "walking", "walk_cycle", "locomotion"],
    "running": ["run", "running", "sprint", "jog", "gallop"],
    "idle": ["idle", "stand", "breathing", "rest", "wait"],
    "dancing": ["dance", "dancing", "groove", "hip_hop"],
    "sitting": ["sit", "sitting", "seated"],
    "swimming": ["swim", "swimming", "float"],
    "driving": ["drive", "driving"],
    "flying": ["fly", "flying", "glide", "soar"],
    "jumping": ["jump", "jumping", "leap"],
    "attacking": ["attack", "bite", "swipe", "fight", "combat"],
    "talking": ["talk", "talking", "speak"],
}

# Default fallback profile mapping for action → animation style
_ACTION_TO_FALLBACK: dict[str, str] = {
    "walking": "glide",
    "running": "glide",
    "idle": "bounce",
    "dancing": "dance",
    "sitting": "bounce",
    "swimming": "swim",
    "driving": "vehicle_glide",
    "flying": "glide",
    "jumping": "bounce",
    "talking": "talk",
    "turntable": "rotate",
}


_IDLE_KEYWORDS = ("idle", "tpose", "t_pose", "t-pose", "rest", "default", "stand")


# Baked animation names that are actively WRONG for a given requested
# action. Sketchfab characters routinely ship with one baked clip — often
# "Sleep" or "Idle" — that has nothing to do with what the user asked for.
# When the prompt says "dancing" and the only baked clip is "Sleep", we'd
# rather play nothing baked (and let procedural drive) than play a sleep
# loop and claim it's a dance. Matched via substring against the baked
# action name.
_INCOMPATIBLE_BAKED_ACTIONS: dict[str, tuple[str, ...]] = {
    "dancing": ("sleep", "sleeping", "idle", "sit", "lying", "lie", "rest", "dead", "death"),
    "dance":   ("sleep", "sleeping", "idle", "sit", "lying", "lie", "rest", "dead", "death"),
    "running": ("sleep", "sleeping", "idle", "sit", "lying", "lie", "rest", "dead", "death"),
    "run":     ("sleep", "sleeping", "idle", "sit", "lying", "lie", "rest", "dead", "death"),
    "walking": ("sleep", "sleeping", "lying", "lie", "rest", "dead", "death"),
    "walk":    ("sleep", "sleeping", "lying", "lie", "rest", "dead", "death"),
    "fighting": ("sleep", "sleeping", "idle", "sit", "lying", "lie", "rest", "dead", "death"),
    "attacking": ("sleep", "sleeping", "idle", "sit", "lying", "lie", "rest", "dead", "death"),
    "flying":  ("sleep", "walk", "run", "idle", "sit", "lying", "lie", "rest", "dead", "death"),
    "fly":     ("sleep", "walk", "run", "idle", "sit", "lying", "lie", "rest", "dead", "death"),
    "jumping": ("sleep", "sleeping", "lying", "lie", "dead", "death"),
    "swimming": ("sleep", "sleeping", "walk", "run", "dead", "death"),
    "performing": ("sleep", "sleeping", "dead", "death"),
}


def _is_compatible_baked_action(requested_action: str, baked_action_name: str) -> bool:
    """Return False when the baked clip is a well-known bad match for the
    requested action (e.g. a "Sleep" clip when the user asked for "dancing").
    Used to reject matches that would render a static subject and pretend
    it's performing the requested behavior.
    """
    bad = _INCOMPATIBLE_BAKED_ACTIONS.get((requested_action or "").lower(), ())
    if not bad:
        return True
    name_lower = (baked_action_name or "").lower()
    return not any(term in name_lower for term in bad)


def _match_baked_action(available_actions: list, desired_action: str):
    """
    Find the best matching baked animation for the desired action.
    Returns the Action object, or None.

    Round 10 Pillar D change
    ------------------------
    Previously this function returned ``available_actions[0]`` as a
    fallback when no keyword matched. Sketchfab dogs ship with an
    "Idle_01" action at index 0, so every "dog running" prompt rendered
    a stationary dog. We now return None when the user asked for a
    specific *motion* action and nothing in the baked set contains a
    motion keyword — procedural glide/bounce will take over and actually
    translate the hero forward.

    A soft fallback to idle is still allowed when the user asked for an
    idle action (idle / sit / stand / rest), so static shots don't lose
    baked subtleties like breathing.
    """
    if not available_actions:
        return None

    desired_lower = (desired_action or "").lower()
    keywords = _ACTION_KEYWORDS.get(desired_lower, [desired_lower] if desired_lower else [])

    # First pass: look for a keyword match in the baked action names.
    for action in available_actions:
        action_lower = action.name.lower()
        for keyword in keywords:
            if keyword and keyword in action_lower:
                if _is_compatible_baked_action(desired_lower, action.name):
                    return action
                print(
                    f"[ANIM] rejecting baked match {action.name!r} for "
                    f"{desired_action!r} — incompatible action content",
                    flush=True,
                )

    # Second pass: if the user asked for an idle-ish action and we
    # didn't find a direct match, accept any idle/t-pose clip.
    idle_requests = {"idle", "sitting", "sit", "standing", "resting", "rest", "stand", ""}
    if desired_lower in idle_requests:
        for action in available_actions:
            if any(k in action.name.lower() for k in _IDLE_KEYWORDS):
                return action
        # No idle-named clip either — fall through to first action so
        # we at least show the rig breathing for an idle shot.
        return available_actions[0]

    # Motion was requested but no baked motion match. Return None so
    # procedural motion can drive the rig instead of an idle loop.
    first_name = available_actions[0].name if available_actions else "<none>"
    print(
        f"[ANIM] no baked match for desired={desired_action!r}; "
        f"baked actions start with {first_name!r} — deferring to procedural",
        flush=True,
    )
    return None


def _determine_forward_axis(root_objs) -> str:
    """
    Determine which axis is 'forward' for a vehicle/asset.
    Returns 'Y' or 'X'.
    """
    wheels = find_wheel_meshes(root_objs[0]) if root_objs else []
    if len(wheels) >= 2:
        xs = [w.location.x for w in wheels]
        ys = [w.location.y for w in wheels]
        spread_x = max(xs) - min(xs) if xs else 0
        spread_y = max(ys) - min(ys) if ys else 0
        return "Y" if spread_x > spread_y else "X"
    return "Y"  # default forward axis


def _animate_wheel_rotation(wheels: list, frame_end: int, speed: float = 1.0) -> None:
    """Spin wheel meshes around their local X axis."""
    for wheel in wheels:
        try:
            wheel.rotation_euler.x = 0
            wheel.keyframe_insert(data_path="rotation_euler", index=0, frame=1)
            wheel.rotation_euler.x = speed * 6.28 * (frame_end / 24.0)
            wheel.keyframe_insert(data_path="rotation_euler", index=0, frame=frame_end)
            if wheel.animation_data and wheel.animation_data.action:
                for fc in _get_fcurves(wheel.animation_data.action):
                    if fc.data_path == "rotation_euler" and fc.array_index == 0:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
        except Exception as e:
            print(f"[ANIM] wheel rotation failed for {wheel.name}: {e}", flush=True)


def _animate_vehicle(root_objs: list, action: str, frame_end: int) -> None:
    """Animate a vehicle: forward motion + optional wheel spin."""
    anim_root = find_animation_root(root_objs)
    if not anim_root:
        return

    # Determine forward axis and apply motion
    forward_axis = _determine_forward_axis(root_objs)
    speed_map = {"driving": 1.0, "racing": 1.5, "cruising": 0.6, "drifting": 1.2}
    speed = speed_map.get(action.lower(), 1.0)
    travel = 8.0 * speed

    _fallback_vehicle_glide([anim_root], frame_end, travel=travel)

    # Spin wheels if found
    wheels = find_wheel_meshes(anim_root)
    if wheels:
        _animate_wheel_rotation(wheels, frame_end, speed=speed)
        print(f"[ANIM] vehicle: {len(wheels)} wheels spinning, speed={speed}", flush=True)


def _fallback_walk_cycle(
    objs,
    frame_end: int,
    offset: int = 0,
    travel: float = 6.0,
    bob_amplitude: float = 0.05,
    sway_deg: float = 2.5,
    lean_deg: float = 3.0,
    step_period_frames: int = 18,
) -> None:
    """
    Richer walk cycle: forward travel (linear), a sine-bob per step,
    hip sway (rotation around Y), and a subtle forward lean. Used for
    walking/running characters when no baked/Mixamo clip is available.
    """
    import math
    for obj in objs:
        try:
            base_x = obj.location.x
            base_y = obj.location.y
            base_z = obj.location.z
            base_rx = obj.rotation_euler.x
            base_ry = obj.rotation_euler.y

            f0 = 1 + offset
            f_end = max(f0 + 1, frame_end)

            # 1. Forward travel (linear interpolation set after keyframes).
            obj.location.y = base_y - travel * 0.5
            obj.keyframe_insert(data_path="location", index=1, frame=f0)
            obj.location.y = base_y + travel * 0.5
            obj.keyframe_insert(data_path="location", index=1, frame=f_end)

            # 2. Forward lean — one pose, held for the whole shot.
            obj.rotation_euler.x = base_rx + math.radians(lean_deg)
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f0)
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f_end)

            # 3. Step bob + hip sway sampled per step.
            step_count = max(4, int((f_end - f0) / max(4, step_period_frames // 2)))
            frames_per_sample = max(1, (f_end - f0) // step_count)
            sway_rad = math.radians(sway_deg)
            for i in range(step_count + 1):
                fr = f0 + i * frames_per_sample
                if fr > f_end:
                    fr = f_end
                # Bob: abs-sine so both up and down read as footfalls.
                bob = abs(bob_amplitude * math.sin(i * math.pi))
                obj.location.z = base_z + bob
                obj.keyframe_insert(data_path="location", index=2, frame=fr)
                # Sway alternates left/right.
                sway = sway_rad * math.sin(i * math.pi * 0.5)
                obj.rotation_euler.y = base_ry + sway
                obj.keyframe_insert(data_path="rotation_euler", index=1, frame=fr)

            # 4. Linear interpolation on the forward Y fcurve so speed is
            # constant — bezier easing on a walk makes it drift in / out.
            if obj.animation_data and obj.animation_data.action:
                for fc in _get_fcurves(obj.animation_data.action):
                    if fc.data_path == "location" and fc.array_index == 1:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
        except Exception as e:
            print(f"[ANIM] _fallback_walk_cycle error on {obj.name}: {e}", flush=True)


def _animate_creature(root_objs: list, action: str, frame_end: int, has_armature: bool) -> None:
    """Animate a living creature (animal/humanoid)."""
    action_lower = action.lower()
    if action_lower in ("walking", "running", "walk", "run", "jogging", "jog", "sprint", "sprinting"):
        is_fast = action_lower in ("running", "run", "jogging", "jog", "sprint", "sprinting")
        speed = 1.8 if is_fast else 1.0
        targets = find_armatures(root_objs) or find_mesh_roots(root_objs)
        _fallback_walk_cycle(
            targets, frame_end,
            travel=7.0 * speed,
            bob_amplitude=0.08 * speed,
            sway_deg=3.0 if is_fast else 2.0,
            lean_deg=6.0 if is_fast else 3.0,
            step_period_frames=10 if is_fast else 18,
        )
    elif action_lower in ("galloping", "gallop"):
        targets = find_armatures(root_objs) or find_mesh_roots(root_objs)
        _fallback_gallop(targets, frame_end, travel=14.0, bob_amp=0.22, period=12)
    elif action_lower in ("flying", "fly", "soaring", "soar"):
        targets = find_armatures(root_objs) or find_mesh_roots(root_objs)
        _fallback_fly_soar(
            targets, frame_end,
            travel=14.0, base_altitude=3.5, altitude_amp=1.2, bank_deg=10.0, period=50,
        )
    elif action_lower in ("swimming", "swim", "diving", "dive"):
        targets = find_armatures(root_objs) or find_mesh_roots(root_objs)
        # Give it real travel so a dolphin actually swims — not just bobs.
        _fallback_swim_arc(targets, frame_end, travel=5.0, period=50)
    elif action_lower in ("dancing", "dance"):
        targets = find_armatures(root_objs) or find_mesh_roots(root_objs)
        _fallback_dance(
            targets, frame_end,
            amplitude_deg=14.0, bob_amplitude=0.18, period=18,
        )
    elif action_lower in ("idle", "sitting", "sit", "standing", "stand"):
        targets = find_armatures(root_objs) or find_mesh_roots(root_objs)
        _fallback_bounce(targets, frame_end, amplitude=0.04, period=40)
    else:
        # Generic fallback
        fallback_key = _ACTION_TO_FALLBACK.get(action_lower, "bounce")
        targets = find_armatures(root_objs) or find_mesh_roots(root_objs)
        _dispatch_fallback(fallback_key, targets, frame_end, 0)


def animate_by_behavior(
    bpy_module,
    instances: list[list],
    manifest: dict,
    frame_start: int = 1,
    frame_end: int = 120,
    stagger_frames: int = 8,
) -> bool:
    """
    Top-level behavior-driven animation dispatch.

    Reads asset metadata from the manifest to choose the right animation
    approach:
      1. If the asset has baked animations that match → use them
      2. Otherwise → procedural animation based on asset_type + action

    Returns True if animation was applied, False otherwise.
    """
    if not instances:
        return False

    asset_type = str(manifest.get("hero_asset_type", "")).lower()
    action = str(manifest.get("action", "idle")).lower()
    has_armature = bool(manifest.get("hero_has_armature", False))
    has_animations = bool(manifest.get("hero_has_animations", False))

    print(
        f"[ANIM] animate_by_behavior: type={asset_type} action={action} "
        f"armature={has_armature} baked_anims={has_animations} "
        f"instances={len(instances)}",
        flush=True,
    )

    # Motion actions that REQUIRE forward translation — even when a
    # baked rig animation was pushed, we still run the procedural glide
    # because most Sketchfab "run" clips cycle in place without root
    # motion, and the user's prompt ("dog running in park") implies
    # travel. For non-motion actions we let baked win cleanly.
    _MOTION_ACTIONS = {
        "walking", "walk", "running", "run", "sprinting", "sprint",
        "driving", "drive", "racing", "race", "flying", "fly",
        "swimming", "swim",
    }
    needs_translation = action in _MOTION_ACTIONS

    for idx, root_objs in enumerate(instances):
        offset = idx * stagger_frames
        baked_pushed = False

        # Priority 1: Use baked animations from the model
        if has_animations or has_armature:
            armatures = find_armatures(root_objs)
            for arm in armatures:
                existing_actions = get_armature_actions(arm)
                if existing_actions:
                    best = _match_baked_action(existing_actions, action)
                    if best:
                        pushed = push_action_to_nla(
                            arm, best,
                            track_name=f"behavior_{idx}",
                            frame_start=frame_start + offset,
                        )
                        if pushed:
                            baked_pushed = True
                            print(
                                f"[ANIM] instance {idx}: baked action "
                                f"'{best.name}' for '{action}'",
                                flush=True,
                            )
                            break

        # Priority 2a (Round 4): Motion library — user-curated FBX
        # retargeting from assets/motion_library/humanoid/. Checked
        # before animation_library so a user can drop in their own
        # replacement clip and have it win. Humanoid + rigged only.
        if not baked_pushed and asset_type in ("character", "humanoid") and has_armature:
            try:
                from app.scene.motion_library import apply_motion, has_motion
                if has_motion(action):
                    if apply_motion(
                        bpy_module, root_objs, action,
                        frame_start=frame_start + offset,
                        frame_end=frame_end,
                    ):
                        print(
                            f"[ANIM] instance {idx}: motion_library '{action}' applied",
                            flush=True,
                        )
                        baked_pushed = True
            except Exception as e:
                print(f"[ANIM] motion_library attempt failed (non-fatal): {e}", flush=True)

        # Priority 2b: Mixamo animation library. Only attempted for
        # humanoid characters with a rig and when a baked action didn't
        # already cover the request. A library hit wins over procedural.
        if not baked_pushed and asset_type in ("character", "humanoid") and has_armature:
            try:
                from app.scene.animation_library import (
                    apply_mixamo_animation,
                    has_mixamo_animation,
                )
                if has_mixamo_animation(action):
                    mixamo_speed = 1.4 if action in ("running", "run", "sprint", "sprinting") else 1.0
                    if apply_mixamo_animation(root_objs, action, speed=mixamo_speed):
                        print(
                            f"[ANIM] instance {idx}: Mixamo '{action}' applied",
                            flush=True,
                        )
                        baked_pushed = True  # treat same as baked for downstream logic
            except Exception as e:
                print(f"[ANIM] Mixamo attempt failed (non-fatal): {e}", flush=True)

        # Priority 3: Type-specific procedural animation. Skipped when
        # baked/Mixamo won cleanly (no motion required) to avoid
        # fighting the NLA. For motion requests we layer a root-level
        # glide on top so the creature actually travels across the ground.
        if baked_pushed and not needs_translation:
            continue

        if baked_pushed and needs_translation:
            # Just add root translation; don't re-key full cycles.
            targets = find_armatures(root_objs) or find_mesh_roots(root_objs)
            speed = 1.5 if action in ("running", "run") else 0.8
            _fallback_glide(targets, frame_end, offset=offset, travel=6.0 * speed)
            print(
                f"[ANIM] instance {idx}: baked '{action}' + procedural root glide",
                flush=True,
            )
            continue

        # At this point no baked/Mixamo match stuck — procedural will drive.
        # Strip whatever action Blender auto-assigned on import (e.g. the
        # cat_02.blend's "Sleep" action) so it doesn't keep playing under
        # the procedural dance/run/etc. keyframes we're about to lay down.
        if asset_type in ("animal", "character", "humanoid"):
            try:
                for arm in find_armatures(root_objs):
                    ad = getattr(arm, "animation_data", None)
                    if ad and ad.action is not None:
                        print(
                            f"[ANIM] clearing residual action {ad.action.name!r} "
                            f"on {arm.name} so procedural {action!r} can drive",
                            flush=True,
                        )
                        ad.action = None
            except Exception as e:
                print(f"[ANIM] residual action clear failed (non-fatal): {e}", flush=True)

        if asset_type == "vehicle":
            _animate_vehicle(root_objs, action, frame_end)
        elif asset_type in ("animal", "character", "humanoid"):
            _animate_creature(root_objs, action, frame_end, has_armature)
        elif asset_type in ("product", "prop", "prop_small", "prop_medium"):
            meshes = find_mesh_roots(root_objs)
            _fallback_turntable(meshes, frame_end)
        else:
            # Generic: gentle turntable or bounce
            meshes = find_mesh_roots(root_objs)
            if meshes:
                _fallback_bounce(meshes, frame_end, offset=offset)

    return True
