# The Director — Phase 31+ uplevel plan

Goal (user vision, 2026-07-02): "truly create and generate amazing high
quality videos and games from prompt directions" — level design, scene
design, and video dynamics, driven by prompts, on BOTH backends. This is the
layer that turns "a knight in a forest" into a *directed* piece: shots that
cut, levels with intent, worlds that move.

Standing rules: local/free/commercial-safe; shared enhancements land on both
backends; video pipeline never regresses (isolated modules, env-gated);
push + docs every session.

## Architecture: one DirectionSpec, two backends

```
prompt / PRD
   │  Ollama (shared client) → DirectionSpec (schema-validated, all defaulted)
   ▼
 ┌─ ShotPlan   — beats, camera per beat, framing, cuts        (video-first)
 ├─ LevelPlan  — zones, paths, landmarks, spawns, goals       (game-first)
 └─ DynamicsPlan — weather, time-of-day drift, ambient motion (BOTH)
   │
   ├─ Blender emitter: multi-shot timeline, dressed sets, particles
   └─ Game emitter: playable zones, objectives, ambient FX
```

Asset layer beneath it (SHIPPED with this commit): every generated character/
prop auto-registers into the library — **the user's creations are the
marketplace**; curated packs (Objaverse/Sketchfab era) demote to fallback.

## Phase 31 — ShotPlan: multi-shot video sequencing  ← START HERE (no GPU for logic)

The single biggest "directed" jump for video. One scene, one motion bake,
MULTIPLE cameras cut on beats.

- `app/orchestrator/shot_director.py`: prompt → ShotPlan via Ollama
  (beats: establish → medium track → close-up → resolve; per-beat camera
  mode reusing cinematography.py moves) with a deterministic default plan
  (wide 0-25% → track 25-70% → push-in 70-100%) when the LLM is down.
- Emitter: bind N cameras, keyframe scene.camera via markers (Blender's
  native cut mechanism — one render pass, real cuts, zero re-render cost).
- Gate: FS_SHOTS. Solo-hero scenes first; fights get circle+close coverage.
- Validate on CPU: markers + camera binds inspectable headless; full visual
  pass when GPU returns.

## Phase 32 — LevelPlan: level design for games

- Zones (spawn / goal / danger / scenic), paths between them (walkable
  corridors through the scatter), landmarks (big prop at a zone), objective
  placement ON the paths (fireflies along the route, not random).
- Terrain: heightfield hills from the DEM/terrain module (shared with video)
  + Rapier heightfield collider; three.js displaced-grid mesh.
- Structures: fences/walls/gates from the prop pipeline (procedural first,
  generated props when GPU returns).
- LevelPlan renders in BOTH: the game gets it playable; the video composer
  gets the same layout as set dressing — one world, filmed or played.

## Phase 33 — DynamicsPlan: scene/video dynamics

- Weather: rain/snow/fog-drift — Blender particle systems + three.js
  points/shader; leaves/dust motes for ambience.
- Time-of-day drift: sun angle + color temperature animate across the clip
  (sunset that actually sets over 12s).
- Ambient motion: prop sway (wind on trees), water shimmer planes,
  firefly/ember systems (night — already shipped, generalize).
- Physics events (games): pushable props, falling objects on trigger.

## Phase 34 — photoreal tier (GPU): Wan 2.2 VACE v2v polish over our renders
   (Apache-2.0, local; depth/pose-conditioned — see game_engine_plan.md).
## Phase 35 — audio: ambient beds + footsteps/impacts (freesound CC0 packs),
   music via local MusicGen-small (check license: CC-BY-NC — if NC, use
   licensed-safe alternatives) — license audit BEFORE integration.

## Order
31 (shot director — video's biggest visible win, buildable now) →
32 (level designer — game depth) → 33 (dynamics both) → GPU returns:
Phase 27 live-fire + 34. Marketplace UI surfacing of /api/game/library
slots in beside 31.
