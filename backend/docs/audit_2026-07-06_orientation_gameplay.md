# Heavy Audit — Orientation & Gameplay (2026-07-06)

User-reported failures: dragon rolls onto its side on input, whale pivots at
the tail and barely moves, knight lying down, rivals launching at t=0, no
pre-game instructions. This audit traced them to two root causes and fixed
the *classes*, not the instances.

## Root cause A — stacked runtime orientation heuristics

Orientation was being "fixed" in three different places (mesh import, bake,
and per-frame runtime guards in `main.js.tpl`). Each new guard was tuned on
one asset and false-positived on the next: the vertical-mesh guard
(`ey > 1.25*max(ex,ez)`) written for a lying-down mesh fired on the
*correctly upright* dragon and rolled it 90° the moment input arrived. That
is why fixes kept "going in circles" — heuristics stack, verification doesn't.

**Fix: orientation is now verified once, at bake time, and never guessed at
runtime.**

- `bake.optimize_asset` gained a `pattern` arg and runs the composer's
  silhouette gate (`_orient_hero_by_reference`) on every asset: renders 24
  axis-aligned candidate orientations of the actual mesh, scores each by
  silhouette IoU against the SDXL reference image, keeps the best, with
  `upright_biped` / `wheels_down` constraints per pattern. The reference
  image is ground truth; the result is baked into the GLB.
- Because orientation now precedes texture projection, the reference photo
  projects onto the *correct* facing — better color coverage for free.
- `main.js.tpl`: ALL orientation heuristics removed. The runtime keeps
  exactly one transform: `alignLongAxis` for drive/swim (nose = +X, verified
  by Blender axis renders 2026-07-05, see `game-vehicle-orientation` memory).
- `prepModel` now centers the pivot vertically for max-dim-normalized
  heroes (whales/vehicles) — fixes the whale rotating about its tail.

**Verified**: dragon, whale, knight re-baked through the gate
(IoU 0.60 / 0.40 / 0.37, best of 24) and render-checked from fixed axes:
dragon upright wings spread, whale horizontal belly-down, knight standing.
`knight_anim.glb` was dropped so the next build re-rigs from the corrected
static.

**Rule going forward**: never add a runtime orientation guard. If an asset
faces wrong, the bake gate failed — fix it there, where the reference image
can arbitrate.

## Root cause B — no pre-game UX

Games dropped the player straight into a live world: races launched rivals
at t=0, controls were only discoverable by pressing keys.

**Fix: universal START overlay** in the runtime template — every game opens
with title, objective list, and mode-specific controls (walk/drive/fly/swim)
plus a START button. The world idles as a live backdrop; inputs and NPC
mission logic are dead until Start. Races begin their 3-2-1-GO countdown
only after Start, and neither rivals nor player throttle engage until GO.
Verified in a fresh export: `startbtn` / `startCountdown` / `gameStarted` /
`raceGo` all present, `node --check` clean.

## Also fixed

- Aquatic speeds: swim cruise 4→6 m/s, burst 10→14 (whale "didn't move").

## Honest gaps (not regressions — unbuilt modules)

- **Wing flap** (dragon) — Phase 20 flying module (#117): procedural
  wing-bone flap cycle. Until then flyers hover/bank without flapping.
- **Swim gait** (whale body undulation) — aquatic module (#116).
- **Biped foot-plant IK** (#119) — next focused session; knight now *stands*
  correctly, gait polish is this task.
- **Full-body texture wrap + car black splotches** — single-view projection
  covers side-facing surfaces only; the real fix is GPU-day library regen at
  TRELLIS quality (`scripts/gpu_day1.py`, ready to run).
