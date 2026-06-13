# Phase 24 — Standard Humanoid Skeleton + Mocap Motion Library (scoping)

Status: **assessment / not yet built.** Author pass 2026-06-13.

## 1. The decision in one line

**Yes — for bipeds, move off hand-authored procedural motion to a standard
humanoid skeleton + retargeted motion-capture library.** It is the only path
that scales to "hundreds of moves that look real," and there is a free,
commercial-safe data source (CMU / Bandai-Namco BVH). Keep procedural motion for
animals and vehicles (it already looks good there). This is **additive, not a
revert.**

## 2. Why procedural motion hit a wall (the evidence)

The samurai cut "was not physically realistic." That is not a bug to patch — it
is the ceiling of the approach. Each procedural action is hand-authored math
(sine-driven joints, world-space arc aiming). Two structural problems:

1. **It does not scale.** Every new move (dance, kick, eat, wave, parry…) is
   bespoke trig. Hundreds of moves = hundreds of hand-tuned functions. Never
   happening, and never consistent.
2. **It is not physically real.** Real motion has weight, anticipation,
   follow-through, balance — emergent properties of a body, not of a sine wave.
   Fortnite emotes look real because they **are** real: captured human
   performance retargeted onto the character. That is the model to copy.

Procedural is the *right* tool for things with simple, regular kinematics
(wheels rolling, a 4-leg trot, idle breathing). It is the wrong tool for
expressive human performance.

## 3. Target architecture

```
prompt → scene graph (action slot)  ──►  motion catalog lookup (named/random)
                                              │
TRELLIS mesh ──► AUTO-RIG to canonical skeleton ──► RETARGET BVH clip ──► bake → render
```

Four new pieces (each independently testable):

### 3a. Canonical humanoid skeleton
One fixed bone hierarchy (~23 deform bones: hips, spine×2, chest, neck, head,
clavicle/upper/fore/hand ×2, thigh/shin/foot/toe ×2). This is the retarget
*target* and never changes. (Hands stay coarse v1 — no finger bones.)

### 3b. Auto-rig: fit the canonical skeleton to an arbitrary TRELLIS mesh
The hard part. TRELLIS meshes vary (A-pose, T-pose, armor, fused props). Plan,
all local/free:
- **Landmark fit** (extend what we already do): we already detect the arm band,
  leg bands, head, hip/chest heights, L/R split. Use those to place the
  canonical skeleton at the mesh's real proportions.
- **Weights via proxy bone-heat + data-transfer**: voxel-remesh a watertight
  proxy, run Blender's automatic (bone-heat) weights on the proxy, then
  Data-Transfer the weights onto the real mesh. (Bone-heat fails on
  non-watertight/self-intersecting meshes — the proxy is the fix. This is the
  plan we sketched earlier.)
- Reuse the existing T-pose/A-pose + orientation handling.

### 3c. Retargeter: CMU/Bandai BVH → canonical skeleton
- BVH loader (Blender imports BVH natively).
- **Bone-name map** CMU→canonical + **rest-pose alignment** (CMU is a specific
  T/A-pose; align bind poses so a CMU "arm down" maps to our "arm down").
- Copy world-space bone rotations frame by frame; scale root translation by the
  hip-height ratio so feet don't slide/float.
- Deterministic, no ML, no paid addon. (Rokoko/Auto-Rig-Pro are the paid
  shortcuts; we write the mapping ourselves — same idea, free.)

### 3d. Motion catalog
- Curate K clips per named action (walk, run, idle, dance×N, sword-fight,
  punch, kick, sit, jump, wave, …), tagged by theme.
- Scene-graph `action` slot → catalog entry, or **random pick within a
  category** (the "Fortnite random emote" idea you liked).
- Clips are small BVH files vendored in-repo. Two-actor actions (duel) = a pair
  of clips (CMU has sparring/martial-arts captures).

## 4. Licensing — verified, fits the hard rule

**"free + commercial-safe only."** Verified this pass:

- **CMU Graphics Lab Mocap DB** (~2,600 clips): *"you may include this data in
  commercially-sold products, but you may not resell this data directly."* i.e.
  ship it inside our product = fine; sell the BVH itself = not. Requires an
  acknowledgment line. **✓ usable.**
- **Bandai-Namco Research Motion Dataset** (~3,000 clips, BVH, walks/runs/
  fights/dances, Blender viewer script): free, permissive. **✓ usable** (verify
  exact terms per release before vendoring).

Action: before vendoring any clip, record its source + license in the
attribution list (same discipline as OSM/DINOv3). Avoid AMASS wholesale (mixes
research-only datasets).

Sources:
- http://mocap.cs.cmu.edu/  •  https://www.cgchannel.com/2022/05/download-3000-free-mocap-moves-from-bandai-namco-research/

## 5. Risks & mitigations (this is a real build, be honest)

| Risk | Mitigation |
|---|---|
| Auto-rig weights fail on messy meshes | Proxy remesh + data-transfer; fall back to current procedural rig if bind QA fails (no regression) |
| Retarget proportion mismatch → foot slide/float | Hip-height root scaling + optional foot-plant IK pass |
| CMU bind pose ≠ our bind pose | One-time rest-pose alignment in the bone map |
| Fused props (sheathed sword, armor) skinned wrong | Weight from proxy of the *body*; props ride nearest bone |
| Big effort, uncertain payoff | **Validation gate (below) before investing in the full catalog** |

## 6. Phased plan (gated, no big-bang, nothing reverts)

- **P0 Canonical skeleton + auto-rig** on the existing man/samurai/robot meshes.
  Exit: clean bind, mesh deforms without tearing on a hand-posed test.
- **P1 Retarget ONE CMU walk** onto the man. **GATE: it must beat the current
  procedural walk** side-by-side. If it loses, stop and keep procedural — cheap
  failure.
- **P2 Retargeter hardening** (root motion → travel, foot-plant, looping).
- **P3 Motion catalog** (named categories + random pick) wired to the scene
  graph `action` slot.
- **P4 Two-actor interactions** (duel = paired clips on the face-off staging we
  already built).
- Procedural animals/vehicles untouched the entire time. The motion system is
  swapped *behind* the scene-graph `action` slot, so multi-actor / mounts /
  dressing keep working unchanged.

## 7. Keep in view (parallel quality track — distinct from motion)

These are **mesh-quality** problems, independent of the motion library:
- **#125 fused spikes/barnacles** (the ferrari "strings"): surface-fused, so the
  island/rope filters miss them. Needs a fused-spike detector (thin high-aspect
  protrusions far from the local surface) and/or a re-roll trigger on low orient
  IoU. Recurs on bad TRELLIS rolls — must be solved for "cars stay clean."
- **Front-face melt on profile-referenced subjects** (cat): TRELLIS hallucinates
  the front face from a side-only reference. Needs a 3/4 reference or face
  repair. (Bipeds get front refs, so cleaner — but the samurai face can still
  melt at angles.)

Recommendation: run the motion-library build and a small mesh-quality pass in
parallel, since they touch different code.

## 8. Vision check

"Anything a user types should come out correctly," everything moves seamlessly,
nothing reverts. This plan: bipeds gain a deep, realistic, scalable move set
(the Fortnite-emote model); animals/vehicles keep what works; the scene graph is
the unchanged front door (`action` slot just resolves to a better motion
source). It directly advances the vision rather than patching the procedural
ceiling.
```
```
