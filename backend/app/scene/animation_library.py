"""
Mixamo animation library — applies pre-made humanoid animation clips
(downloaded from https://www.mixamo.com as FBX, "Without Skin", 30fps)
to any rigged humanoid armature in the scene.

This is intentionally imported lazily from animation_ops.py so that
`bpy` is only required at call-time (tests / CI can still import the
asset pipeline without a Blender environment).

Setup (one-time, manual):
    1. Sign in to Mixamo with a free Adobe ID.
    2. Download each clip listed in ACTION_TO_ANIM below.
       - Format: FBX Binary
       - Skin: Without Skin
       - Keyframe: 30fps
    3. Drop the .fbx files into ``assets/animations/mixamo/`` next to
       this repo's other asset folders.

If a file is missing, the applier logs a clear hint and returns False
so the caller can fall back to procedural animation.
"""
from __future__ import annotations

from pathlib import Path

# Absolute so Blender (which runs as a subprocess with unknown CWD)
# can always find it.
ANIM_DIR = Path(
    r"C:/Users/bgrut/Desktop/FantasyAI/blender-studio-backend/assets/animations/mixamo"
)

# Map action words (lowercase) to Mixamo FBX filenames.
ACTION_TO_ANIM: dict[str, str] = {
    # Locomotion
    "walking":   "walking.fbx",
    "walk":      "walking.fbx",
    "running":   "running.fbx",
    "run":       "running.fbx",
    "jogging":   "jogging.fbx",
    "jog":       "jogging.fbx",
    "sprinting": "sprinting.fbx",
    "sprint":    "sprinting.fbx",
    "sneaking":  "sneaking.fbx",
    "crouching": "sneaking.fbx",
    # Performance
    "idle":      "idle.fbx",
    "standing":  "idle.fbx",
    "dancing":   "dancing_hip_hop.fbx",
    "dance":     "dancing_hip_hop.fbx",
    "waving":    "waving.fbx",
    "wave":      "waving.fbx",
    "clapping":  "clapping.fbx",
    "jumping":   "jumping.fbx",
    "jump":      "jumping.fbx",
    # Actions
    "fighting":  "fighting_punch.fbx",
    "punching":  "fighting_punch.fbx",
    "kicking":   "fighting_kick.fbx",
    "falling":   "falling.fbx",
    "sitting":   "sitting_down.fbx",
    "sit":       "sitting_down.fbx",
    "looking":   "looking_around.fbx",
}


def has_mixamo_animation(action: str) -> bool:
    """True if we have a Mixamo FBX for this action on disk."""
    anim_file = ACTION_TO_ANIM.get((action or "").lower())
    if not anim_file:
        return False
    return (ANIM_DIR / anim_file).exists()


def apply_mixamo_animation(hero_objects, action: str, speed: float = 1.0) -> bool:
    """
    Import a Mixamo FBX, rip its action off the imported armature, and
    assign that action to our hero armature. Cleans up the imported
    helper objects so nothing extra lingers in the scene.

    Returns True if the animation was applied, False otherwise (no
    armature, no file on disk, or Blender import failure).

    `hero_objects` is the flat list of objects for one hero instance.
    `speed` scales keyframe timing: 2.0 = twice as fast, 0.5 = half.
    """
    try:
        import bpy  # type: ignore
    except Exception as e:
        print(f"[ANIM_LIB] bpy unavailable: {e}", flush=True)
        return False

    # 1. Find a humanoid armature in the hero objects.
    armature = None
    for obj in hero_objects:
        if getattr(obj, "type", None) == 'ARMATURE':
            armature = obj
            break
    if not armature:
        print("[ANIM_LIB] no armature on hero — cannot apply Mixamo clip", flush=True)
        return False

    # 2. Resolve the FBX file.
    anim_file = ACTION_TO_ANIM.get((action or "").lower())
    if not anim_file:
        print(f"[ANIM_LIB] no Mixamo mapping for action '{action}'", flush=True)
        return False
    anim_path = ANIM_DIR / anim_file
    if not anim_path.exists():
        print(
            f"[ANIM_LIB] missing Mixamo FBX: {anim_path}\n"
            f"[ANIM_LIB] download from https://www.mixamo.com and place in {ANIM_DIR}",
            flush=True,
        )
        return False

    # 3. Import the FBX and grab the new armature / action.
    before = {obj.name for obj in bpy.data.objects}
    try:
        bpy.ops.import_scene.fbx(filepath=str(anim_path))
    except Exception as e:
        print(f"[ANIM_LIB] FBX import failed ({anim_path.name}): {e}", flush=True)
        return False

    after = {obj.name for obj in bpy.data.objects}
    new_names = after - before
    if not new_names:
        print("[ANIM_LIB] FBX imported but produced no new objects", flush=True)
        return False

    imported_armature = None
    for name in new_names:
        obj = bpy.data.objects.get(name)
        if obj and obj.type == 'ARMATURE':
            imported_armature = obj
            break

    applied = False
    try:
        if not imported_armature or not imported_armature.animation_data or not imported_armature.animation_data.action:
            print("[ANIM_LIB] imported FBX has no action on its armature", flush=True)
        else:
            imported_action = imported_armature.animation_data.action
            # Give the action a traceable name so it's easy to debug in the
            # outliner / manifest.
            imported_action.name = f"mixamo_{anim_file.replace('.fbx', '')}"

            if not armature.animation_data:
                armature.animation_data_create()
            armature.animation_data.action = imported_action

            # Optional speed scale on the keyframe timeline.
            if speed and speed != 1.0 and speed > 0:
                inv = 1.0 / speed
                from .directorial_motion import _get_fcurves
                for fc in _get_fcurves(imported_action):
                    for kp in fc.keyframe_points:
                        kp.co.x *= inv
                        kp.handle_left.x *= inv
                        kp.handle_right.x *= inv

            applied = True
            print(
                f"[ANIM_LIB] applied Mixamo '{anim_file}' to {armature.name} "
                f"(speed={speed})",
                flush=True,
            )
    finally:
        # 4. Clean up every object the FBX brought in — the hero keeps
        #    the action, but we don't want the stock Mixamo mannequin in
        #    the render.
        for name in new_names:
            obj = bpy.data.objects.get(name)
            if obj is None or obj is armature:
                continue
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception as e:
                print(f"[ANIM_LIB] cleanup failed for {name}: {e}", flush=True)

    return applied
