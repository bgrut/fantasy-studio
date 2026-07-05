# Realism Plan — "like someone is standing there"

Goal: hyper-real visuals + accurate physics on BOTH backends, from the same
one-prompt pipeline. Phased so every step lands verified (no circles): each
item ships with a regression check before the next starts.

Diagnosis anchor (2026-07-05 demo review): video car slid sideways (nose-axis
not aligned in the VIDEO motion module — game side already fixed & verified by
render), black patches (CPU-era texture holes + inverted normals + no
normal/roughness maps), samurai gait (no foot-plant IK — feet slide in
stance), "gritty" look (EEVEE fast tier, 720p, no motion blur/AO/grade).

---

## Phase R0 — The no-circles guarantee (FIRST, CPU, ~half a session)
**Regression pack**: `scripts/regression_pack.py` — renders one canonical
frame for N fixed prompts (horse meadow, car street, samurai forest, fox
night, city race game spec) into a dated contact sheet after every realism
change. Every phase below gates on "pack looks >= previous pack". This
codifies the ad-hoc frame checks that caught the fur bug and the nose flip.

## Phase R1 — CPU wins now (1-2 sessions, no GPU needed)
- **R1.1 Vehicle nose alignment, ONCE, shared**: bake the verified -90°
  alignment into the library-cast import path (composer `_try_library_hero` /
  game optimizer) so video motion AND game runtime both inherit it. Kills the
  sideways car everywhere; the render-verified method is documented in memory.
- **R1.2 Normals hygiene in the optimizer**: recalc-outside + weld pass on
  library assets (black inverted-face patches disappear under any light).
- **R1.3 Car-paint shader for video vehicles**: clearcoat + metallic +
  roughness override (the game's PMREM gloss equivalent, in Cycles/EEVEE
  terms). Masks remaining texture damage the same way it did in-game.
- **R1.4 Foot-plant IK (task #119)**: lock the stance foot to its ground
  contact during retarget (we already know contact frames from the CMU clip),
  smooth pelvis. This is THE gait fix — walk reads human immediately.
- **R1.5 The look pipeline (video)**: motion blur ON, AO ON, subtle bloom,
  AgX/filmic view transform, 3-point light rig preset per mood (key/fill/rim)
  over the HDRI, DoF from the cinematography module, 1080p at standard tier.
  Single biggest "gritty -> cinematic" jump available on CPU.
- **R1.6 Story polish**: ffmpeg crossfades + title/end cards; per-scene
  re-render button in Video Projects.

## Phase R2 — GPU day 1 (PSU arrives; the source-quality fix)
- **R2.1 Library regeneration** at TRELLIS.2 quality tier + 2K texture bakes
  + baked NORMAL maps -> black spots and blotch die at the source, for both
  backends at once (shared library).
- **R2.2 Cycles hero tiers** actually engaged (600-1200 spp + OptiX denoise),
  real SSS skin, fur systems where appropriate (guarded by the asset-hero
  gate so fur NEVER stacks on textured heroes again).
- **R2.3 Prompt-exact characters in ~1 min** (dragon, armored knight...) —
  the CPU path already works; GPU makes it interactive.

## Phase R3 — The photoreal leap (GPU; "is that a real person?")
- **R3.1 Wan 2.2 / VACE video-to-video polish tier** (Apache-2.0, local,
  commercial-safe): our render supplies EXACT identity, motion, camera and
  depth/pose control maps; the diffusion pass re-skins frames photoreal.
  Our 3D pipeline stays the controllable "bones" — this is the "someone is
  standing there" answer for VIDEO. Opt-in tier next to fast/standard.
- **R3.2 DaVinci Resolve via MCP**: timeline assembly, grade, audio bed for
  Story Director exports.
- **Games note**: real-time photorealism is bounded by three.js — the path
  there is R2 textures + normal maps + light probes now, and the
  Godot/Unreal exporters for AAA lighting when a user opts in.

## Phase R4 — Accurate physics (both sides, after R1)
- **R4.1 Game vehicles -> real rigid-body**: Rapier dynamic body + raycast
  suspension (per-wheel spring/damper), mass-based acceleration/braking,
  weight transfer, wheel spin (needs separable wheels from R2.1 regen).
  Replaces the kinematic arcade controller; same inputs, real response.
- **R4.2 Video vehicle dynamics**: body roll/pitch from the same
  spring-damper constants driven through the wheeled motion module.
- **R4.3 Shared motion-truth module**: one `motion_constants.py` (speeds,
  turn radii, gait cadence per species/vehicle class) consumed by composer
  AND game exporter — physics agreement between a video and its game.
- **R4.4 Character contact**: foot-IK terrain adherence (game runtime
  raycast per foot — after R1.4 proves the approach in Blender), simple
  hit-reaction ragdoll blend for combat.

## Order & gates
R0 -> R1 (each item = code + regression pack diff) -> [GPU arrives] -> R2 ->
R3.1 prototype on ONE Story Director film -> R4 alongside R3. Nothing in R2+
changes pipeline architecture — the spine stays prompt -> spec -> two
deterministic backends + shared library.
