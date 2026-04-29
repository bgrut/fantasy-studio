from __future__ import annotations

"""
animation_ops.py
================
Execution-layer animation module.  All public functions accept explicit
target objects so they never accidentally animate background geometry.

Public surface
--------------
animate_subject_group(bpy, root_objs_per_instance, action, mode, frame_end, stagger_frames)
    High-level dispatcher called by scene templates.  Detects rigs, uses
    NLA playback when actions exist, falls back to procedural keyframes.

apply_animation_instructions(instructions, subject_groups=None)
    Backward-compatible wrapper for the old instruction-list API.
    subject_groups: optional list-of-lists of root objects, one per instruction.
    When omitted the functions fall back to the old global-object scan
    (preserved for callers that haven't been updated yet).

Fallback motion profiles
------------------------
Each profile operates on a supplied list of root objects and a frame offset
so multiple instances can be staggered without overlap.
"""

from math import pi
from typing import Optional

# ---------------------------------------------------------------------------
# Rig / action detection helpers
# ---------------------------------------------------------------------------

def find_armatures(root_objs) -> list:
    """Return all ARMATURE objects in the hierarchy of root_objs."""
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
    """Return MESH objects that are direct roots or immediate children."""
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


def get_armature_actions(armature_obj) -> list:
    """
    Return the list of bpy.types.Action objects linked to an armature's
    animation_data, plus any actions whose name starts with the armature
    name (a common Blender convention).
    """
    actions = []
    ad = getattr(armature_obj, "animation_data", None)
    if ad and ad.action:
        actions.append(ad.action)
    # NLA tracks
    if ad:
        for track in getattr(ad, "nla_tracks", []):
            for strip in getattr(track, "strips", []):
                if strip.action and strip.action not in actions:
                    actions.append(strip.action)
    return actions


def push_action_to_nla(armature_obj, action, track_name: str = "Anim",
                        frame_start: int = 1) -> bool:
    """
    Push an existing action onto an NLA track so it plays back during render.
    Returns True on success.
    """
    try:
        ad = armature_obj.animation_data
        if ad is None:
            armature_obj.animation_data_create()
            ad = armature_obj.animation_data

        # Clear active action so NLA drives playback
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


# ---------------------------------------------------------------------------
# Fallback motion profiles
# Each profile receives:
#   objs        – list of Blender objects to keyframe (mesh roots or armatures)
#   frame_end   – last frame of the scene
#   offset      – frame offset for staggering multiple instances
# ---------------------------------------------------------------------------

def _fallback_bounce(objs, frame_end: int, offset: int = 0,
                     amplitude: float = 0.12, period: int = 20) -> None:
    """
    Small vertical bounce — believable idle for quadrupeds (cats, dogs).
    Uses a two-keyframe oscillation looped via Blender's cyclic modifier.
    """
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

            # Make it loop
            if obj.animation_data and obj.animation_data.action:
                for fc in obj.animation_data.action.fcurves:
                    if fc.data_path == "location" and fc.array_index == 2:
                        fc.modifiers.new(type="CYCLES")
        except Exception as e:
            print(f"[ANIM] _fallback_bounce error on {obj.name}: {e}", flush=True)


def _fallback_sway(objs, frame_end: int, offset: int = 0,
                   amplitude_deg: float = 8.0, period: int = 30) -> None:
    """
    Side-to-side rotation sway — used for dance fallback on unrigged characters.
    """
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
                for fc in obj.animation_data.action.fcurves:
                    if fc.data_path == "rotation_euler" and fc.array_index == 2:
                        fc.modifiers.new(type="CYCLES")
        except Exception as e:
            print(f"[ANIM] _fallback_sway error on {obj.name}: {e}", flush=True)


def _fallback_talk_nod(objs, frame_end: int, offset: int = 0,
                       amplitude_deg: float = 5.0, period: int = 18) -> None:
    """
    Gentle forward head-nod — placeholder for lip-sync on unrigged meshes.
    Rotates on X axis (pitch).
    """
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
                for fc in obj.animation_data.action.fcurves:
                    if fc.data_path == "rotation_euler" and fc.array_index == 0:
                        fc.modifiers.new(type="CYCLES")
        except Exception as e:
            print(f"[ANIM] _fallback_talk_nod error on {obj.name}: {e}", flush=True)


def _fallback_swim_arc(objs, frame_end: int, offset: int = 0,
                       travel: float = 2.0, period: int = 80) -> None:
    """
    Forward/back swim travel on Y axis with a gentle pitch oscillation.
    Used for ocean creatures when no rig/action is present.
    """
    import math
    for obj in objs:
        try:
            base_y = obj.location.y
            base_rx = obj.rotation_euler.x
            pitch = math.radians(6.0)
            half = period // 2
            f1 = 1 + offset

            # Y travel
            obj.location.y = base_y - travel
            obj.keyframe_insert(data_path="location", index=1, frame=f1)
            obj.location.y = base_y + travel
            obj.keyframe_insert(data_path="location", index=1, frame=f1 + period)

            # Pitch nose-down on forward stroke
            obj.rotation_euler.x = base_rx - pitch
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f1)
            obj.rotation_euler.x = base_rx + pitch
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f1 + half)
            obj.rotation_euler.x = base_rx - pitch
            obj.keyframe_insert(data_path="rotation_euler", index=0, frame=f1 + period)

            for curve_dp in ("location", "rotation_euler"):
                if obj.animation_data and obj.animation_data.action:
                    for fc in obj.animation_data.action.fcurves:
                        if fc.data_path == curve_dp:
                            fc.modifiers.new(type="CYCLES")
        except Exception as e:
            print(f"[ANIM] _fallback_swim_arc error on {obj.name}: {e}", flush=True)


def _fallback_turntable(objs, frame_end: int, offset: int = 0) -> None:
    """
    Single full Z rotation over frame_end frames.  Product turntable.
    """
    for obj in objs:
        try:
            obj.rotation_euler.z = 0.0
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=1)
            obj.rotation_euler.z = 2.0 * pi
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=frame_end)

            # Linear interpolation so rotation is constant-speed
            if obj.animation_data and obj.animation_data.action:
                for fc in obj.animation_data.action.fcurves:
                    if fc.data_path == "rotation_euler" and fc.array_index == 2:
                        for kp in fc.keyframe_points:
                            kp.interpolation = "LINEAR"
        except Exception as e:
            print(f"[ANIM] _fallback_turntable error on {obj.name}: {e}", flush=True)


def _fallback_glide(objs, frame_end: int, offset: int = 0,
                    travel: float = 8.0) -> None:
    """Forward glide on Y for vehicles or environment dressing."""
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


# ---------------------------------------------------------------------------
# Per-action dispatch table
# Maps action name → (profile_func, kwargs)
# Scene templates can extend this if needed.
# ---------------------------------------------------------------------------

_FALLBACK_PROFILES: dict[str, tuple] = {
    "dance":      (_fallback_sway,      {"amplitude_deg": 10.0, "period": 24}),
    "talk":       (_fallback_talk_nod,  {"amplitude_deg": 5.0,  "period": 18}),
    "swim":       (_fallback_swim_arc,  {"travel": 2.0,         "period": 80}),
    "rotate":     (_fallback_turntable, {}),
    "glide":      (_fallback_glide,     {"travel": 8.0}),
    "walk":       (_fallback_glide,     {"travel": 12.0}),
    "idle":       (_fallback_bounce,    {"amplitude": 0.02, "period": 48}),
    # Quadruped-specific — also valid for "dance" when species is feline/canine
    "bounce":     (_fallback_bounce,    {"amplitude": 0.12, "period": 20}),
}


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def animate_subject_group(
    bpy,
    instances: list[list],
    action: str,
    mode: str,
    frame_end: int = 120,
    stagger_frames: int = 8,
) -> None:
    """
    Animate a group of character/creature instances.

    Parameters
    ----------
    instances       List of root-object lists, one per imported instance.
                    e.g. [[cat1_root, cat1_armature], [cat2_root], ...]
    action          Animation action name: 'dance', 'talk', 'swim', 'rotate', 'glide'
    mode            Mode hint passed through (e.g. 'loop', 'turntable') — used for NLA naming
    frame_end       Last frame of the scene
    stagger_frames  Frame offset between consecutive instances (default 8)
    """
    print(
        f"[ANIM] animate_subject_group | action={action} mode={mode} "
        f"instances={len(instances)} stagger={stagger_frames}",
        flush=True,
    )

    for idx, root_objs in enumerate(instances):
        offset = idx * stagger_frames
        armatures = find_armatures(root_objs)
        meshes = find_mesh_roots(root_objs)

        # ── Path 1: rigged with existing actions → push to NLA ───────────
        if armatures:
            for arm in armatures:
                existing_actions = get_armature_actions(arm)
                if existing_actions:
                    pushed = push_action_to_nla(
                        arm,
                        existing_actions[0],
                        track_name=f"{action}_{idx}",
                        frame_start=1 + offset,
                    )
                    if pushed:
                        print(
                            f"[ANIM] instance {idx}: NLA playback via existing action "
                            f"'{existing_actions[0].name}'",
                            flush=True,
                        )
                        continue

            # ── Path 2: rigged but no baked action → procedural on armature roots
            print(f"[ANIM] instance {idx}: rigged but no baked action — procedural on armature", flush=True)
            _dispatch_fallback(action, armatures, frame_end, offset)

        else:
            # ── Path 3: unrigged → procedural on mesh roots ───────────────
            print(f"[ANIM] instance {idx}: unrigged — procedural fallback on meshes", flush=True)
            _dispatch_fallback(action, meshes, frame_end, offset)


def _dispatch_fallback(action: str, objs: list, frame_end: int, offset: int) -> None:
    """Look up and execute the fallback profile for the given action."""
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


# ---------------------------------------------------------------------------
# Backward-compatible instruction wrapper
# ---------------------------------------------------------------------------

def apply_animation_instructions(
    instructions: list[dict],
    subject_groups: Optional[list[list]] = None,
    frame_end: int = 120,
    stagger_frames: int = 8,
) -> None:
    """
    Backward-compatible entry point used by scene templates.

    If subject_groups is provided (list of root-obj lists, one per instruction),
    delegates to animate_subject_group with proper targeting.

    If subject_groups is None (legacy callers), falls back to the old
    global-object iteration behaviour for each action type.
    """
    for i, inst in enumerate(instructions):
        subject = inst.get("subject", "")
        action  = inst.get("action", "")
        mode    = inst.get("mode", "")

        print(f"[ANIM] instruction | subject={subject} action={action} mode={mode}", flush=True)

        if subject_groups is not None and i < len(subject_groups):
            animate_subject_group(
                None,  # bpy not needed for per-object keyframing
                subject_groups[i] if isinstance(subject_groups[i][0], list) else [subject_groups[i]],
                action=action,
                mode=mode,
                frame_end=frame_end,
                stagger_frames=stagger_frames,
            )
        else:
            # Legacy fallback: operate on all matching scene objects
            # (preserved for callers not yet updated to pass subject_groups)
            _legacy_dispatch(action, mode, frame_end)


def _legacy_dispatch(action: str, mode: str, frame_end: int) -> None:
    """
    Old global-scan behaviour, kept for backward compatibility.
    Imports bpy at call time so this module can be imported outside Blender.
    """
    try:
        import bpy as _bpy
    except ImportError:
        print("[ANIM] _legacy_dispatch: bpy not available", flush=True)
        return

    if action == "rotate" and mode == "turntable":
        targets = [o for o in _bpy.data.objects if o.type == "MESH"]
        _fallback_turntable(targets, frame_end)

    elif action == "dance":
        # Prefer armatures; fall back to meshes
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
