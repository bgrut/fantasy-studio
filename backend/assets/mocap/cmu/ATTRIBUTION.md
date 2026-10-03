# CMU Motion Capture Data — attribution & license

The `.bvh` files in this directory are from the **Carnegie Mellon University
Graphics Lab Motion Capture Database** (http://mocap.cs.cmu.edu/), via the
cgspeed Daz-friendly BVH conversion (Bruce Hahne), re-mirrored at
https://github.com/una-dinosauria/cmu-mocap .

## License — COMMERCIAL-SAFE ✓

Per the CMU database terms: *"This data is free for use in research projects.
You may include this data in commercially-sold products, but you may not resell
this data directly, even in converted form."*

i.e. we MAY ship motion retargeted from this data inside Fantasy Studio (a
commercial product). We may NOT sell the BVH data itself. This satisfies the
project's hard "free + commercial-safe only" constraint.

**Required acknowledgment** (must appear in product credits):
> "The motion data used in this product was obtained from mocap.cs.cmu.edu."

## NOT used: Bandai-Namco Research Motion Dataset

Considered but **excluded** — it is CC BY-NC-ND 4.0 (non-commercial,
no-derivatives), which violates the commercial-safe rule. Do not add it.

## Clip manifest (file → CMU motion label → our category)

| file        | CMU label        | category |
|-------------|------------------|----------|
| 02_01.bvh   | walk             | walk     |
| 02_02.bvh   | walk             | walk     |
| 07_01.bvh   | walk             | walk     |
| 08_01.bvh   | walk             | walk     |
| 35_01.bvh   | walk             | walk     |
| 02_03.bvh   | run/jog          | run      |
| 09_01.bvh   | run              | run      |
| 16_01.bvh   | walk/run (mixed) | run      |
| 02_05.bvh   | punch/strike     | fight    |
| 02_07.bvh   | swordplay        | fight    |
| 02_04.bvh   | jump, balance    | jump     |
| 140_06.bvh  | Idle             | idle     |
| 136_09.bvh  | Walk Crouched    | sneak    |
| 79_02.bvh   | swimming         | swim     |
| 90_16.bvh   | fall on face     | die      |

The five below the swordplay line were added 2026-09-04 from the same mirror
under the same terms. All carry the identical 31-joint CMU skeleton as the
originals, so the bone mapping above applies unchanged (verified by joint-name
comparison, not assumed).

## BVH skeleton → canonical 19-bone rig mapping (for the retargeter)

Hips→hips · LowerBack/Spine→spine · Spine1→chest · Neck/Neck1→neck · Head→head
LeftShoulder→clav_L · LeftArm→uparm_L · LeftForeArm→lowarm_L · LeftHand→hand_L
RightShoulder→clav_R · RightArm→uparm_R · RightForeArm→lowarm_R · RightHand→hand_R
LeftUpLeg→upleg_L · LeftLeg→lowleg_L · LeftFoot→foot_L
RightUpLeg→upleg_R · RightLeg→lowleg_R · RightFoot→foot_R
(LHipJoint/RHipJoint = connector bones; fingers/thumbs ignored in v1.)

## The motion-matching database (2026-10-03)

`assets/mocap/mm/mm_db.bin` is built by `tools/mmdb.py` from 111 CMU takes
(running, jogging, sprinting, turning, starting, stopping, backpedalling and
sidestepping; subjects 2, 7, 8, 9, 16, 35, 36, 41, 69, 83, 104, 127, 128,
131, 134, 136, 139, 141, 143) and 6 windows of 100STYLE (see
`../100style/ATTRIBUTION.md`). The raw CMU files, from the same cgspeed
mirror (github.com/una-dinosauria/cmu-mocap), live in `../_cmu_src/`, which
git ignores; only the retargeted database ships, inside games, never as data
for sale. The credit line above appears in every exported game's LICENSES.md.
