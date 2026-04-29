Mixamo Animation Library
========================

Drop Mixamo FBX files into this folder to give humanoid characters
professional-quality animations at render time. The Blender pipeline
picks them up automatically through `app/scene/animation_library.py`.

How to get the files
--------------------
1. Sign in to https://www.mixamo.com with a free Adobe ID.
2. Pick an animation. In the download dialog choose:
   - Format:      FBX Binary
   - Skin:        Without Skin
   - Frames/sec:  30
   - Keyframe:    Reduced
3. Save to this folder using EXACTLY the filenames below.

Required filenames (case-sensitive)
-----------------------------------
Locomotion:
  walking.fbx
  running.fbx
  jogging.fbx
  sprinting.fbx
  sneaking.fbx

Performance:
  idle.fbx
  dancing_hip_hop.fbx
  waving.fbx
  clapping.fbx
  jumping.fbx

Actions:
  fighting_punch.fbx
  fighting_kick.fbx
  falling.fbx
  sitting_down.fbx
  looking_around.fbx

How it's used
-------------
`animate_by_behavior` in `app/scene/animation_ops.py` calls
`apply_mixamo_animation` when:
  - the hero has an ARMATURE
  - `hero_asset_type` is character / humanoid
  - the current `action` matches a filename above
  - the .fbx actually exists here

If any of those checks fail it falls back to procedural animation
(the `_animate_creature` / `_fallback_*` path) — so missing files
never break a render, they just downgrade it.
