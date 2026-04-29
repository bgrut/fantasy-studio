"""
Motion library — applies pre-recorded Mixamo-style FBX animations to any
imported humanoid armature.

Expected on-disk layout:
    assets/motion_library/humanoid/<action>.fbx

apply_motion(hero_objects, action, scene) finds the armature among the
hero objects, imports the motion FBX, steals its Action, and assigns that
Action to the hero armature. Keyframes are rescaled to fit the scene's
frame range so the motion doesn't run past the render.

All failures fall back to returning False so the caller can try other
animation strategies (procedural swim, etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOTION_DIR = PROJECT_ROOT / "assets" / "motion_library" / "humanoid"


# Action name -> filename. Keep lowercase; get_motion_file lowercases input.
ACTION_MAP: dict[str, str] = {
    "walking":       "walking.fbx",
    "walk":          "walking.fbx",
    "running":       "running.fbx",
    "run":           "running.fbx",
    "idle":          "idle.fbx",
    "standing":      "idle.fbx",
    "jumping":       "jumping.fbx",
    "jump":          "jumping.fbx",
    "dancing":       "dancing_hip_hop.fbx",
    "dance":         "dancing_hip_hop.fbx",
    "waving":        "waving.fbx",
    "wave":          "waving.fbx",
    "sitting":       "sitting.fbx",
    "sit":           "sitting.fbx",
    "fighting":      "fighting.fbx",
    "punching":      "punching.fbx",
    "kicking":       "kicking.fbx",
    "falling":       "falling.fbx",
    "climbing":      "climbing.fbx",
    "swimming":      "swimming.fbx",
    "crawling":      "crawling.fbx",
    "rolling":       "rolling.fbx",
    "cooking":       "cooking.fbx",
    "writing":       "writing.fbx",
    "typing":        "typing.fbx",
}

_HUMANOID_BONE_HINTS = ("spine", "hip", "pelvis", "head", "neck",
                        "shoulder", "arm", "leg")


def get_motion_file(action: str) -> Path | None:
    """Look up the FBX for `action`. Returns the path if it exists on disk,
    else None (the user may not have downloaded every motion)."""
    if not action:
        return None
    key = str(action).strip().lower()
    fname = ACTION_MAP.get(key)
    if not fname:
        return None
    path = MOTION_DIR / fname
    return path if path.exists() else None


def has_motion(action: str) -> bool:
    """True iff the on-disk FBX is present for this action."""
    return get_motion_file(action) is not None


def find_humanoid_armature(hero_objects: Iterable):
    """Return the first armature among `hero_objects` that looks humanoid
    (has at least a couple of bones matching common humanoid names)."""
    best = None
    best_hits = 0
    for obj in hero_objects or []:
        if getattr(obj, "type", None) != "ARMATURE":
            continue
        bones = getattr(getattr(obj, "data", None), "bones", None)
        if not bones:
            continue
        bone_names = " ".join(b.name.lower() for b in bones)
        hits = sum(1 for hint in _HUMANOID_BONE_HINTS if hint in bone_names)
        if hits >= 2 and hits > best_hits:
            best = obj
            best_hits = hits
    # Fallback: if nothing scored >=2 but an armature exists, take the first.
    if best is None:
        for obj in hero_objects or []:
            if getattr(obj, "type", None) == "ARMATURE":
                return obj
    return best


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


def _rescale_action(action, target_start: int, target_end: int) -> None:
    """Scale every fcurve so its first/last keyframe map to
    [target_start, target_end]. Preserves motion shape but fits the shot."""
    _fcs = _get_fcurves(action)
    if not _fcs:
        return

    all_x = [kp.co.x for fc in _fcs for kp in fc.keyframe_points]
    if not all_x:
        return
    src_start, src_end = min(all_x), max(all_x)
    src_span = src_end - src_start
    dst_span = target_end - target_start
    if src_span <= 0 or dst_span <= 0:
        return
    scale = dst_span / src_span

    for fc in _fcs:
        for kp in fc.keyframe_points:
            kp.co.x = target_start + (kp.co.x - src_start) * scale
            # Also scale handles so the curve shape survives.
            kp.handle_left.x  = target_start + (kp.handle_left.x  - src_start) * scale
            kp.handle_right.x = target_start + (kp.handle_right.x - src_start) * scale


def apply_motion(bpy, hero_objects: Iterable, action: str,
                 frame_start: int = 1, frame_end: int | None = None) -> bool:
    """Import the FBX for `action` and assign its animation to the hero
    humanoid armature. Returns True on success, False otherwise."""
    motion_path = get_motion_file(action)
    if motion_path is None:
        return False

    target_armature = find_humanoid_armature(hero_objects)
    if target_armature is None:
        print(f"[MOTION] no humanoid armature among heroes for '{action}'", flush=True)
        return False

    # Snapshot existing armatures so we can identify newly imported ones.
    before_armatures = {o.name for o in bpy.data.objects if o.type == "ARMATURE"}

    try:
        bpy.ops.import_scene.fbx(filepath=str(motion_path))
    except Exception as e:
        print(f"[MOTION] FBX import failed for {motion_path.name}: {e}", flush=True)
        return False

    imported_armatures = [
        o for o in bpy.data.objects
        if o.type == "ARMATURE" and o.name not in before_armatures
    ]
    if not imported_armatures:
        print(f"[MOTION] import produced no armature: {motion_path.name}", flush=True)
        return False

    src_armature = imported_armatures[0]
    src_anim = getattr(src_armature, "animation_data", None)
    src_action = getattr(src_anim, "action", None)
    if src_action is None:
        print(f"[MOTION] imported armature has no action: {src_armature.name}", flush=True)
        _cleanup_imported(bpy, imported_armatures)
        return False

    if frame_end is None:
        frame_end = int(getattr(bpy.context.scene, "frame_end", 120))
    _rescale_action(src_action, int(frame_start), int(frame_end))

    if target_armature.animation_data is None:
        target_armature.animation_data_create()
    target_armature.animation_data.action = src_action

    _cleanup_imported(bpy, imported_armatures)
    print(f"[MOTION] applied '{action}' ({motion_path.name}) to {target_armature.name}", flush=True)
    return True


def _cleanup_imported(bpy, imported_armatures) -> None:
    """Remove the temporary imported armatures + their mesh children so
    the scene only contains the hero(es) + their re-targeted motion."""
    to_remove = []
    for arm in imported_armatures:
        for child in list(arm.children):
            to_remove.append(child)
        to_remove.append(arm)
    for obj in to_remove:
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass
