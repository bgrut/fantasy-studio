# Humanoid Motion Library

Drop Mixamo-style humanoid FBX files into this directory. The names below
match `ACTION_MAP` in `app/scene/motion_library.py` — if a file is missing,
the motion system silently falls back to the procedural animator.

## Required filenames

| Filename              | Maps from keys               |
|-----------------------|------------------------------|
| `walking.fbx`         | walking, walk                |
| `running.fbx`         | running, run                 |
| `idle.fbx`            | idle, standing               |
| `jumping.fbx`         | jumping, jump                |
| `dancing_hip_hop.fbx` | dancing, dance               |
| `waving.fbx`          | waving, wave                 |
| `sitting.fbx`         | sitting, sit                 |
| `fighting.fbx`        | fighting                     |
| `punching.fbx`        | punching                     |
| `kicking.fbx`         | kicking                      |
| `falling.fbx`         | falling                      |
| `climbing.fbx`        | climbing                     |
| `swimming.fbx`        | swimming                     |
| `crawling.fbx`        | crawling                     |
| `rolling.fbx`         | rolling                      |
| `cooking.fbx`         | cooking                      |
| `writing.fbx`         | writing                      |
| `typing.fbx`          | typing                       |

## How to obtain from Mixamo

1. Go to https://www.mixamo.com/ (free Adobe account required).
2. Pick **any** humanoid character — the rig is what matters.
3. Search the animation name, select it.
4. Click **Download** with:
   - Format: `FBX Binary (.fbx)`
   - Skin: `Without Skin`
   - Frames per Second: `30`
   - Keyframe Reduction: `none`
5. Rename the download to match the table above and drop it here.

Files are imported only when the corresponding action is requested, so you
can add them incrementally. Missing files are logged once and skipped.
