# Fantasy Studio → Playable Games (Phase 26+)

Goal: extend Studio from "prompt → cinematic video" to "prompt/PRD → playable
game", mimicking the Fable-style autonomous build (a detailed PRD handed to the
agent, which runs long and emits a working 3D browser game) — but with our
unfair advantage: **we don't start from thin air.** Studio already produces the
hard parts (real 3D assets, rigged characters, mocap motion, environments,
scene graph). A game is those same ingredients plus an interactive runtime.

Hard constraint (unchanged): local, free, commercial-safe. Licensing per layer:

| Layer | Choice | License | Commercial |
|---|---|---|---|
| Web runtime | three.js | MIT | yes |
| Physics | Rapier (rapier3d-compat) | Apache-2.0 | yes |
| Assets | our own TRELLIS.2/SDXL output | MIT/ours | yes (CMU mocap credit) |
| Desktop engine | Godot 4 | MIT | yes |
| Unreal Engine | OPTIONAL adapter | proprietary EULA (free, 5% royalty > $1M) | yes, but NOT open source — user opt-in only |

Unreal note: you can make money with it, but it fails the "open source" half of
our rule. Godot is the open-source engine of record; Unreal is an optional
export adapter the user explicitly enables and accepts the EULA for.

## Architecture: one IR, many backends

The composer's scene graph becomes a canonical intermediate representation.
Backends consume it:

```
prompt/PRD → GameSpec (Ollama extract, schema-validated)
                │
                ├─ video backend (EXISTING — untouched, zero-regression)
                ├─ web game backend (three.js)       ← Phase 26 (build NOW)
                ├─ Godot backend (.tscn + glTF)      ← Phase 28
                └─ Unreal backend (glTF + Remote Py) ← Phase 29 (opt-in)
```

New code lives in `app/game_export/` — **no edits to composer.py paths**, so
the video pipeline cannot regress. Feature-gated `FS_GAME`.

## Phase 26 — three.js web-game MVP (buildable + testable NOW, no dGPU)

Why now: the runtime is pure JS/HTML (browser runs on iGPU), existing GLB
assets are on disk from prior runs, and Blender headless animation-bake/export
is CPU-only. Only NEW asset generation (SDXL/TRELLIS CUDA) waits for the GPU.

Deliverable: **"walkable park"** — our man in a park environment, third-person
camera, WASD/gamepad movement driving idle/walk/run mocap animations, ground
collision. Opens as `dist/index.html` fully offline.

Modules:
- `app/game_export/spec.py` — `GameSpec` (pydantic): player{asset,controller,
  speed,anims}, camera{mode,distance}, world{ground,sky,scatter[]},
  entities[]{asset,behavior,spawn}, objectives[]{type,target,count},
  controls, ui{hud}. Everything defaulted; a bare prompt still yields a game.
- `app/game_export/bake.py` — Blender headless (CPU): import hero GLB →
  reuse `mocap_retarget` autorig/retarget for a CLIP SET (idle, walk, run) →
  export ONE animated glTF with named actions. (Video path bakes one clip into
  the scene; games need a switchable animation library on the character.)
- `app/game_export/web_exporter.py` — GameSpec + baked assets → `dist/`:
  index.html, `vendor/three.module.js` + `vendor/rapier.js` (VENDORED +
  pinned, never CDN — local-first, reproducible), `game.js` from templates.
- `app/game_export/runtime/` — hand-written, tested JS templates (NOT
  LLM-generated at export time — determinism = no errors): scene bootstrap,
  AnimationMixer state machine (idle↔walk↔run blend), character controller
  (capsule + Rapier), third-person follow cam, touch fallback.
- `scripts/export_game.py "<prompt or prd.md path>"` — CLI entry.

Validation harness (the "without error" guarantee):
- `renders/_ab/verify_game.py` — serves dist/, drives a headless browser:
  zero console errors, all assets 200, player moves ≥ N units on synthetic
  input, FPS floor. Runs on iGPU. Every export must pass before we call it done.

## Phase 26.5 — PRD → GameSpec (the "Fable from a single PRD" front-end)

- `app/game_export/extractor.py` — Ollama (gemma3:12b, JSON mode) maps a short
  prompt OR a long PRD document onto GameSpec. Schema-validated; on validation
  failure, ONE corrective re-ask, then deterministic defaults (never emit a
  broken spec).
- Agentic build loop (mimics "let it run long"): extract → resolve/generate
  assets → bake → export → run verify_game → on failure, patch spec/params and
  retry (bounded). This is our existing composer philosophy — deterministic
  templates + LLM only at the semantic edge — which is exactly why our games
  won't be one-shot-lucky like pure codegen.

## Phase 27 — full pipeline integration (GPU required)

- Prompt with no existing assets → TRELLIS.2 generates hero/props → auto-rig →
  bake anim set → export. "any game a user types comes out correctly."
- Multi-entity: NPCs with wander/chase behaviors from mocap clips; vehicles
  drivable via the wheeled module; collectibles/goals from objectives[].
- Environment upgrade: reuse OSM city / DEM terrain / park presets as playable
  worlds (the TikTok street scene = our city dressing, playable).
- First GPU test session also validates the pending biped upright fix
  (commit 3e45302) + reruns the paused regression prompts (car_city rerun;
  horse strings + cat face polish tracked separately).

## Phase 28 — Godot adapter (open-source desktop engine)

- Emit a Godot 4 project: glTF assets + generated `.tscn` scenes + small
  GDScript templates (CharacterBody3D controller, camera, spawner). Godot is
  MIT — ships desktop/mobile builds, monetizable, zero royalty.
- Same GameSpec, same assets — only the emitter differs.

## Phase 29 — Unreal adapter (OPTIONAL, user opt-in)

- Path: glTF import + UE Python Remote Execution to assemble a level, retarget
  anims to UE5 Manny via IK Rig, spawn a GameMode. Heavy install, proprietary
  EULA, 5% royalty > $1M — surfaced to the user before enabling. Not part of
  the default pipeline.

## Shared-enhancement rule (user directive 2026-07-02)

Anything built for games that would also improve VIDEO scenes must flow back to
the Blender/video side. Both backends read the same IR, so this is structural:
- **World dressing** (scattered trees/props/paths for playable parks & streets)
  → the same scatter manifest upgrades video environments (currently too bare).
- **Animation library bake** (idle/walk/run sets per character) → video multi-
  shot sequencing can switch actions mid-scene instead of one clip per video.
- **Level-of-detail + collision proxies** → faster video preview renders.
The reverse also holds: video-side realism work (Cycles materials, HDRI, SSS)
carries into game exports via the baked glTF textures.

## Order of work while GPU is down

1. Scaffold `app/game_export/` (spec, exporter, runtime templates, CLI).
2. Vendor three.js + Rapier (pinned versions, license files copied).
3. Bake anim-set GLB from an EXISTING hero via CPU Blender; build walkable-park
   dist; pass verify_game in browser (iGPU).
4. Phase 26.5 extractor + build loop against existing assets.
5. GPU returns → Phase 27 + the deferred validations above.
