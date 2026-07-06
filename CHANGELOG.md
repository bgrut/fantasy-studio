# Changelog

All notable changes to Fantasy Studio are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0 versions are internal milestones during the constraint sprint leading to public V1.0 launch (Mid-May 2026). They're documented here transparently — Fantasy Studio has never been a stealth project.

---

## [Unreleased]

### Added — Game-feel pass 1: sound + timers + the success blueprint (2026-07-06)
- **Every game has SOUND**: WebAudio-synthesized (zero asset files, zero
  network) — pickup chime, attack whoosh, kill thud, hurt sting, race
  countdown beeps + GO, win fanfare, lose fall. Activated by the START click
  so browser autoplay policy is satisfied by design.
- **Every win answers "how well?"**: run timer on the win screen, personal
  best remembered per game (localStorage), "new personal best!" callouts,
  your best time shown on the START screen, and a Play-again button.
- **Success blueprint**: `backend/docs/game_success_blueprint.md` maps what
  perennial best-sellers do (legible loop, juice, progression, ownership,
  session shape) to a concrete runtime-template roadmap (R-A juice pack →
  R-B score/medals → R-C ownership → R-D marketplace readiness).
- **Library-wide orientation trust**: dog, monkey, penguin, samurai re-baked
  through the orientation gate (render-verified upright + textured); the cat
  was a pre-pipeline Sketchfab asset with no reference to verify against —
  retired and regenerated from scratch through the modern pipeline.

### Fixed — Reliability triple: wolf autopsy findings (2026-07-06)
- **Blender bridge self-heal**: the headless Blender behind the bridge dies
  sometimes (flaky iGPU driver); every asset bake after that failed silently —
  the wolf took 40 CPU-minutes to generate and then vanished because the bake
  couldn't reach Blender. Bakes now detect a dead bridge, relaunch the headless
  instance, and retry; animated-rig bakes fall back to the static mesh rather
  than dropping the character. Wolf re-baked and registered (library = 14).
- **Zombie job self-heal**: jobs left "rendering" by a crash/restart sat in the
  pipeline monitor forever (the ghost "horse galloping across a sunny meadow"
  was a demo-film job orphaned YESTERDAY — nothing was actually rendering).
  On startup, any in-flight-marked job is now honestly failed with a reason.
- **Collectibles are the real thing**: the dragon game generated a "fire flame"
  mesh for 30 minutes and then spawned generic orbs anyway. Collect objectives
  now carry the generated asset into the game — flames look like flames,
  pearls like pearls (emissive-lifted so they read at night); orbs are only
  the fallback when no mesh exists.

### Added — Breadth pass: procedural motion, alien worlds, rewards (2026-07-06)
- **Wings flap and whales undulate — no rig needed**: fly/swim heroes deform in
  the vertex shader (wing flap grows toward the wingtips; a traveling nose→tail
  body wave for swimmers), keyed off geometry so it works for ANY generated
  creature. Amplitude follows speed — gentle at idle, full when moving, extra
  on climb/dive. Verified in-browser: dragon flies mid-flap over the peaks,
  whale swims with a live tail wave, zero shader errors. (The full bone-based
  motion library #116/#117 still lands later for ground gaits — this makes
  every flyer/swimmer alive TODAY.)
- **Six new world classes**: mars (butterscotch haze, rust rock fields, no
  grass), moon/space (airless black sky, hard sun, gray craters), castle
  (stone yard, braziers), ruins, cave, jungle — each with terrain amplitude,
  scatter recipe, and sky palette. Extractor maps "on mars" → mars sky + rust
  ground automatically; new sky moods `mars`/`space`/`dusk`.
- **Rewards**: "the winner gets a banana" → the win screen says so. New
  `reward` field extracted from any prompt.
- **Prop sanity**: monkeys/penguins/bottles/crates get real-world default
  sizes; unknown static props default small instead of person-sized.
- **Sample prompts refreshed** to show the breadth: dragons over mountains,
  whale pearl dives, mars duels with rewards, knight-vs-knight races, a
  penguin on the moon — plus the proven classics.

### Fixed — Spawn-embedded-in-terrain (the REAL "doesn't move" root cause) (2026-07-06)
- **Whale/dragon couldn't move because they spawned INSIDE the terrain**: spawn
  height assumed flat ground, so on mountain (16 m amplitude) or seabed worlds
  the physics capsule started embedded and the character controller blocked
  every move — keys turned the body, camera orbited, position froze. Spawn,
  teleport, and fall-respawn are now terrain-aware (`spawnHeight(x,z)`): flyers
  start airborne (+6 m), swimmers start mid-water clear of the seabed.
  Play-verified headlessly on 16 m mountain terrain (dragon: 24 m straight in
  4 s) and 6 m seabed (whale: 18 m cruise + 3.2 m C-dive).
- **Race rivals are the player's own kind** — foxes race foxes, whales race
  whales; a "race" verb never conjures phantom cars again. Rival speed scales
  to the player's for foot races.
- **Every noun generates, not just the player**: entities and props missing
  from the library now go through the same image→3D pipeline as the hero
  (created once, cached forever, honest progress notes). Extractor-verified on
  wild prompts: "cat fighting a monkey on mars" → cat (library) + monkey
  (generates); "monkey hitting bottles in a castle" → monkey + bottle both
  generate. Generic humans (npc/guy/guard/villager) alias to the man rig.

### Changed — Control feel + camera polish, self-tested headlessly (2026-07-06)
- **"Inverted controls" root-caused and fixed**: heroes spawned facing the
  camera (modelYaw 0), so the first input whipped them 180° and the whole
  first turn read backwards; heroes now spawn facing away. Turn damping was
  also linear on angles — crossing the ±π seam turned 270° the wrong way —
  now angle-aware (always the short way). Verified with the new headless QA
  hook (`window.__game.state`): straight-line W, short-way turns, C-dive.
- **Pro camera**: mouse-wheel zoom (0.45×–2.6×) and auto-recenter — the camera
  swings back behind the player while moving so you can see into turns, and
  yields for 3 s after a manual drag-look.
- **Dragon auto-liftoff**: a flyer moving along the ground catches air instead
  of dragging its belly across terrain.
- **Pickup radius scales with hero size** (an 8 m whale no longer needs to hit
  a 1.4 m bullseye to collect a pearl).
- **Per-asset heading facts**: `assets/library_heading.json` (data, not
  heuristics) feeds `player.yaw_offset_deg` for meshes whose nose sign differs.
- **Git LFS**: `backend/assets/library/*.glb` tracked via LFS going forward —
  also the path for community-shared assets.

### Changed — Heavy audit: bake-time orientation + pre-game UX (2026-07-06)
- **Orientation is now VERIFIED at bake time, never guessed at runtime**: every
  generated asset runs the 24-orientation silhouette gate (render each candidate,
  score IoU against the SDXL reference image, bake the winner; upright-biped /
  wheels-down constraints per pattern). All runtime orientation heuristics were
  removed from the game runtime — they stacked and false-positived (the
  vertical-mesh guard rolled the *correctly upright* dragon on input). The only
  runtime transform left is the render-verified nose-forward alignment for
  drive/swim. Dragon, whale, knight re-baked through the gate and render-verified
  upright from fixed axes. See `backend/docs/audit_2026-07-06_orientation_gameplay.md`.
- **Universal START overlay**: every game now opens with its title, objectives,
  and mode-specific controls plus a START button; the world idles as a live
  backdrop and nothing moves until Start. Race countdowns (3-2-1-GO) begin after
  Start — rivals and player throttle both hold for GO.
- **Whale actually swims**: max-dim-normalized heroes now pivot at their center
  (was tail), and aquatic speeds raised to 6 m/s cruise / 14 m/s burst.

### Added — Phase 37: real-city maps + world detail pack (2026-07-05)
- **REAL CITIES in games**: prompts naming a city (New York, London, Tokyo, Paris,
  Chicago, San Francisco) now build the actual district from OpenStreetMap — the
  same OSM fetch/parse the video pipeline has used since Phase 19.5, now shared.
  Real building footprints extrude into a single merged mesh (per-building tint,
  box colliders); real streets are painted as asphalt into the ground texture.
  World grows to 360 m to hold a real district; buildings never block the mission
  path, spawn, or goal. Attribution: © OpenStreetMap contributors (ODbL).
- **World detail pack (all prompts)**: 1024px painted ground (soft tonal blotches,
  bare-dirt patches, fine speckle) with a worn trail drawn along the level path;
  tree SPECIES variants (oak / pine / birch + bush understory) built procedurally
  and mixed per setting recipe — shared with the video dressing pass; undergrowth
  tufts stay plant-green on brown forest floors.
- **Vehicles drive nose-first**: long-axis auto-alignment for drive-mode players
  and rival vehicle NPCs (generated car GLBs lie along X; runtime forward is +Z) —
  fixes the "car hovers sideways" bug. Suspension feel: pitch under accel/brake,
  roll into turns. (Wheel spin needs separable wheel meshes — queued for GPU day.)

### Added — Phase 38: Story Director — one prompt → a FILM (2026-07-05)
- **Story Film tier** in Scene Studio: Ollama plans a 3-act beat sheet
  (`story_director.py` — same subject wording in every scene for actor-cache
  continuity; deterministic fallback plan when Ollama is down), each scene
  renders through the SAME slot pipeline as single renders (strictly
  sequential — iGPU-safe), scenes land in a **Video Project** as they finish
  (partial progress survives; re-order/extend in the UI), and the finished
  film auto-exports via the project's ffmpeg concat.
- API: `POST /api/story` (render), `POST /api/story/plan` (beat-sheet preview,
  no rendering), `GET /api/story/jobs/{id}`. Progress rides the render_jobs
  table (`__story__` rows) → pipeline bar, Gallery, Insights.

### Fixed — game polish round (2026-07-05, same commit)
- **Night scenes: the hero is always readable** — camera-parented moonlit
  fill (lights whatever you look at, any orbit angle) + "moonlit hero" grade
  (the player's own texture doubles as a faint emissive map, so dark-furred /
  dark-armored characters don't vanish). Verified on the snowy-night fox.
- **Environment reflections everywhere**: an irradiance map baked from the
  same procedural sky (PMREM) — car paint finally reads as paint (the
  blotchiness was flat lighting as much as the texture; full texture regen
  still queued for GPU day).
- **Race rules are visible**: glowing orange gates every ~6 waypoints along
  the route, a checkered finish banner at the goal, and drive-mode HUD
  instructions ("W throttle · S brake/reverse · A/D steer · Shift boost —
  follow the orange gates to the checkered finish"). All derived from the
  level path — works for any race in any world.

### Fixed/Added — Phase 37.1: street-pinned racing + facades + blade grass (2026-07-05)
- **Nose direction verified by rendering** (not eyeballed): the alignment sign
  was flipped once from an ambiguous follow-cam screenshot; now the car/truck
  GLBs were Blender-rendered from known axes — car nose is +X (−90° align),
  truck already lies nose-+Z (no rotation). Comment in the runtime warns
  against re-flipping without renders.
- **Races run on REAL streets**: Dijkstra route through the OSM road graph
  (longest chain from the district center, resampled to ~10 m waypoints); the
  whole district shifts so the route starts at the player spawn. Rivals line
  up on a starting grid beside the player facing down the street and follow
  the route (verified: all 5 rivals at 0.0 m from the street polyline through
  the full race). Goal + collectibles pin to the route; OSM cities are dead flat.
- **Procedural building facades on every building**: extrusions split into
  walls/roofs; walls get a metre-scaled window-grid texture with a matching
  emissive map (a fraction of windows glow) — no assets, works for any city.
- **Grass is blades, not rectangles**: tapered to a tip, bowed, random lean,
  dark-rooted vertical shading; skips building interiors.
- **Vehicle paint**: glossier material response (roughness 0.38 / metalness
  0.28) masks most of the CPU-era texture blotchiness; true fix is the GPU
  texture-tier regeneration on day 1.

### Added — Phase 26/26.5: playable game export (2026-07-02)
- **New output backend**: `backend/app/game_export/` turns a prompt or PRD into a
  playable, self-contained three.js web game (offline; vendored three.js r170 MIT +
  Rapier 0.14 Apache-2.0). CLI: `python scripts/export_game.py --prompt "..."`.
- Ollama GameSpec extractor (shared LLM client with the video slot extractor) with
  keyword + default fallbacks; every export runs a static verify gate (structure,
  libs, JS syntax, GLB skins/animation clips).
- CPU-Blender animation-set bake: idle/walk/run CMU mocap retargeted IN-PLACE onto
  named glTF animations (reuses the Tier A+B auto-rig + voxel-proxy skinning).
- NPC entities (wander/follow AI), collectible objectives with HUD + win screen,
  physics character controller, boundary walls, third-person camera.
- SHARED world-dressing: procedural tree/rock/lamp prop library scattered in games
  AND in Blender video scenes (background ring; night scenes get firefly motes).
- Asset library manifest (`assets/library.json`) + GLB decimation for game-budget
  NPC assets (494k → 40k tris).
- Docs: `backend/docs/game_engine_plan.md` (Godot adapter next; Unreal opt-in later).

### Added — Phase 34: Game Projects (2026-07-03)
- **Build a whole game, not just levels**: 'Add to my game' collects finished
  builds into a named project; **Export game** emits ONE self-contained build —
  hub menu (level select), per-level next-level progression on win, back-to-menu
  link — playable in-app instantly and downloadable as a zip for itch.io/static
  hosting. Levels re-export from their RESOLVED specs (exact, no LLM re-roll).
- Player casting accuracy: prompts star the RIGHT character — species-correct
  rig+animations bake on first use (quadruped trot gait / biped mocap set).

### Added — Phase 30: Studio game mode + desktop app (2026-07-02)
- **Game/Video mode chooser** in the Studio: game mode = prompt → Ollama GameSpec →
  built + verified + **embedded playable** in the app (~30-60s, no GPU needed).
- Backend: `POST /api/game/export` (background job), `GET /api/game/jobs/{id}`,
  `GET /api/game/health`, `/games` static mount serving built games.
- **Tauri 2 desktop shell** (`desktop/`, Aurora pattern): native Fantasy Studio
  window, `launch.ps1` single-terminal dev launcher (backend + vite + window).
  Installer bundling (PyInstaller sidecar) on the roadmap.
- Also: Phase 28 Godot 4 export adapter (headless-validated) and Phase 27
  on-demand asset generation glue (GPU-gated, first live run when GPU returns).

### Planned for V1.0.0 launch (Mid-May 2026)
- Public source release under BSL 1.1
- Marketing website live at [fantasylab.ai](https://fantasylab.ai)
- Patreon launch with premium recipe / asset tier
- Discord community open
- Curated launch gallery (50+ hero renders)
- Onboarding video series

---

## [1.4.6] - 2026-04-30

### Fixed
- **Runtime usage stats no longer drift into tracked `library.json`.** Pre-V1.4.6, every render bumped `use_count` and `last_rendered_ts` on the live `library.json`, producing a meaningless per-render git diff and leaking personal usage stats into the public repo
- New `backend/app/services/library_stats.py` module owns the gitignored `backend/app/data/library_stats.json` per-user counters file. Atomic writes (tmp + replace), thread-safe bumps, idempotent merge-back-onto-entries on read
- `library_curator.promote_asset` now routes use_count bumps to `library_stats.bump_use_count` instead of mutating the library file. New-entry creation initializes stats at 1 in the stats file rather than baking it into library.json
- `library_curator._load_library` and `app/api/library.py::_load_all_entries` overlay stats onto returned entries automatically — readers (browse pagination, match scoring, asset_agent diversity rotation) keep working with no surface changes
- One-shot migration script `backend/scripts/migrate_stats.py` extracts existing counters out of library.json into stats.json. Idempotent. Backs up library.json before mutating

### Changed
- `backend/app/data/asset_library.json` is now gitignored. It's an auto-grown ledger of every fetched asset (`asset_logger.log_asset`) — runtime ledger by design, not curated content. New users get a fresh empty file on first fetch; Brandon's local copy stays useful
- `backend/.gitignore` extended for `library_stats.json`, `library_stats.json.bak_*`, `asset_library.json`, `asset_library.json.bak_*`

### Migration notes
- Run `python backend/scripts/migrate_stats.py` once on existing installs to split historical counters out of library.json. The script writes a `library.json.bak_v146_premigration_<ts>` backup automatically
- Re-running is a no-op once the migration completes (no runtime fields left to strip)

---

## [1.4.3] - 2026-04

### Fixed
- Cast panel viewport sizing — content no longer cut off on standard 13"–14" laptop displays
- Surfaced `.blend` source file export alongside MP4 in the render output panel (previously buried in the file system)

---

## [1.4.2] - 2026-04

### Added
- Curated prompt suggestions surfacing verified-working scenes in the prompt entry empty state
- Scene complexity guardrail — gentle handoff for prompts the V1 single-subject pipeline can't render well, with explicit "this works in V2" messaging
- Empty-state showcase carousel of pre-rendered hero clips so first-touch visitors see what good output looks like before committing to a render

---

## [1.4.1.1] - 2026-04

### Fixed
- **Critical**: duplicate hero asset overlay in vehicle renders. Some `.blend` files (notably `bmw_01.blend`) ship two complete LOD copies under sibling `Sketchfab_model` parents. V1.3.5 transactional dedup correctly merged the parent EMPTYs but the matrix-restore preserved the loser sub-tree's world transforms, leaving identical mesh twins at full authored scale alongside the LAYOUT-scaled keeper. Result was a dual-car render
- Added `[LOD_CLEANUP]` pass post-`[FORCED_HERO_TAG]` that signature-indexes the `is_forced_hero` set `(vert_count, face_count, rounded_world_dims_xyz)` and `hide_render`s any untagged `is_hero` mesh with an exact signature match. Originals preserved (not deleted) for debugging
- Generated `vehicle_lod_audit.json` flagging 13 vehicles in suspicious size band as candidates for the same failure mode

---

## [1.4.1] - 2026-04

### Changed
- Asset scale floor lowered from 0.3m → 0.2m at the HERO_VERIFY gate (`bbox_sane` check). 20cm heroes (small bird, mouse, gem) are legitimate
- `_hero_scale_normalize` inner band: `target * 0.35` → `target * 0.20`. Vehicles in character-scale environments (20–35% band) now render at authored size instead of being force-rescaled up
- `_hero_scale_normalize` outer floor: 0.05m → 0.02m
- `[FORCE_FIX]` trust band: `0.1m..50m` → `0.02m..50m`; TINY trigger likewise
- HERO_VERIFY abort message updated to read `expected 0.2-50m`

### Added
- Library refresh pass — regenerated 14 missing thumbnails, audited 314 entries for empty tags / placeholder subjects (zero found)
- `library_refresh_report.json` and `library_triage_report.json` in `app/data/` documenting state at refresh time
- Triage queue surfaces 14 broken-path entries, 2 unsupported-format HDRIs, 1 heavy-blend timeout for human review

---

## [1.4.0] - 2026-04

### Added
- Frontend "Change cast" library browser with category filters
- Cast panel manual override across hero / environment / prop slots
- ZIP archive ingestion in `tools/downloads_ingestor.py` — Sketchfab and Poly Haven downloads land as `.zip`; the watcher now extracts to `assets/_ingest_staging/`, locates the primary 3D file, delegates to the existing single-file ingest, and quarantines the archive to `_ingest_completed/` or `_ingest_failed/`
- Backfill banner at watcher startup processes pending downloads before steady-state polling
- Nested-archive failure cases surface in `_ingest_failed/` with sibling `.error.txt` traces

### Fixed
- Watcher loop crash on Windows: `glob("*.zip")` and `glob("*.ZIP")` returned the same files (case-insensitive FS), causing the second iteration to crash on `src.stat()` after the first moved the file. Deduped the glob result via `dict.fromkeys` and added a defensive `src.exists()` check pre-stability-probe

---

## [1.3.7] - 2026-04

### Changed
- Library matcher confidence threshold lowered 0.5 → 0.30 (V1.3.6 was over-defensive; legitimate matches were being filtered)
- Subject normalization: 45-entry alias map (plurals → singular, `car` → `vehicle`, `animal` → `character`) plus stopword filter (`a`, `an`, `the`, `of`, …) so `"an elephant"` and `"elephants"` and `"elephant"` all hit the same bucket
- Scoring rubric tightened: 1.0 exact subject (post-normalization) / 0.85 exact tag / 0.40–0.75 partial subject substring / 0.30–0.60 partial tag substring
- Exact-subject short-circuit: top match with score ≥ 0.99 restricts the diversity rotation to exact-only candidates so an *elephant* prompt never falls through to *rhinoceros*
- `[MATCHER]` log line on every pick: `picked=… (score=…, exact_subject) runner_up=… (score=…)` for debug traceability
- BMW orientation overrides updated `[90, 0, 0]` → `[180, 0, 0]` for both `lib_registry_bmw_01` and `lib_bmw_bmw_bmw_m_motorsport_gt_racing` (full flip on X)

### Fixed
- Prompt `"a horse in the desert"` and `"a horse"` now produce identical matches (article stripping)

---

## [1.3.6] - 2026-04

### Added
- Hidden hero-cluster primitive cleanup: post-`[FORCED_HERO_TAG]` sweep of `is_hero=True && !is_forced_hero` MESH objects, hiding low-poly + sphere-like rig-control "orbs" (the `Object_35` chrome sphere in `horse.glb`)
- Per-asset orientation override: `import_rotation_xyz` field in `library.json` applied at import time, with `[ASSET_ORIENT_OVERRIDE]` log
- Two BMW entries flagged with the override
- Library matcher confidence threshold of 0.5 introduced (later lowered in V1.3.7)
- Auto-pick env min-score gate: prompts like *"horse in the mountain"* no longer collapse onto whatever env scores 8 from shape bonus alone

### Fixed
- ENV_PRESET running on top of forced-environment imports caused dual styling (e.g. desert preset color cast over a placed mountain asset). ENV_PRESET now skipped when `forced_environment_id` is set

---

## [1.3.5] - 2026-03

### Fixed
- BLEND_DEDUP triple-write per child invalidated Object refs → StructRNA crash → builder fallback to placeholder scene. Replaced with a 5-phase transactional flow (gather → reparent → settle → restore-matrix → validate → delete) with abort-on-validation-failure
- Vehicle orientation gate: rotate -90°X only when Z is the longest axis. Skip for asset_type `vehicle`. Stops low-and-wide cars getting flipped on import
- Multi-hit raycast for terrain placement: prefers top-facing surface normals (z > 0.1) so heroes don't land on the side of a dune
- Library reclassification: `lib_desert_desert_landscape` shape_class `flat_map` → `3d_terrain`
- HERO_VERIFY gained two structural checks: `oriented_correctly` (hard-fails when bbox.max_axis is wrong for the asset type), `grounded` (warn-only)

---

## [1.3.4] - 2026-03

### Added
- `[FORCED_HERO_TAG]` pre-pass: walks descendants of every `is_hero_root` and stamps `is_forced_hero=True` on mesh descendants within 10m of origin. Replaces fragile per-importer tagging
- `_format_hero_verify_abort` formatter in `app/blender_runner.py` parses `[HERO_VERIFY] ABORT:` and surfaces a structured user-facing error to the API instead of leaking DeprecationWarnings

### Fixed
- CAMERA_DIRECTOR_FINAL static placement was being overridden by tracking keyframes. Now `animation_data_clear()` runs before the director writes, then tracking/orbit re-bakes anchored to the director origin

---

## [1.3.3] - 2026-03

### Added
- HERO_VERIFY render gate: 5 structural checks (`has_hero_tag`, `bbox_sane`, `in_frustum`, `fill_ok`, `not_primitive`) before any frame is rendered
- Closed-loop fill solver in camera director: `distance = hero_h / (2 * target_fill * tan(fov_v/2))`. Subject-fill is now a target, not a guess

---

## [1.3.2] - 2026-03

### Added
- `app/services/camera_director.py` as the single source of truth for hero camera placement
- `_apply_director_to_camera` writer-attempt guard: any post-director write is logged and rejected if it deviates beyond a 0.1m tolerance

---

## [1.3.1] - 2026-03

### Fixed
- Vehicle hero shrink: `_enforce_scale` now skips the shrink path when `_looks_like_vehicle` returns True. Stops BMWs from being scaled from 4.8m to 1.7m when their library `category` happens to be `character/medium`

---

## [1.3.0] - 2026-03

### Added
- Template System v2: 15 named recipes + 16 base/env/comp/lighting/anim/ambient/post layers + weighted dispatcher + executor. Recipes are pure JSON; the executor walks them. Renderer-agnostic by design (Unreal / Godot future possible)
- `app/services/variant_pool.py`: subject-filtered diversity picker that returns None on empty filter (instead of silently picking a wrong-subject random asset)
- Curated injector and prop fetcher gated on `forced_hero_id` so manual cast picks aren't second-guessed

---

## [1.2.0] - 2026-02

### Added
- V1.2 asset healer: `app/services/asset_healer.py` runs once on ingest, computes `orientation_fix_rotation_euler`, `ground_offset_z`, `shape_class`, `provisional_ready`, persists to `library.json`. Originals never modified
- 232 library assets healed and registered in `library.json` at this version

---

## [1.1.0] - 2026-01

### Added
- Recipe-based pipeline foundation
- Asset registry with library matching against subject + tags
- Cycles + Eevee tier selection at render time
- Pipeline trace logging (`[PIPELINE] +N.NNNs STAGE_NAME` markers)
- HDRI library + procedural sky fallback

---

## [1.0.0] - TBD (Mid-May 2026)

- Initial public release under BSL 1.1
- 316-asset curated launch library
- 15 recipes + composable layer system
- Four render tiers (Quick Preview / Polished / High Quality / Final Cinematic)
- Local LLM director (Gemma 3 12B via Ollama) with deterministic fallback
- MP4 + `.blend` + GIF + PNG sequence + `credits.txt` output package
- Frontend cast panel + scene controls + refine panel
- Public docs at github.com/bgrut/fantasy-studio
- Marketing site at fantasylab.ai

[Unreleased]: https://github.com/bgrut/fantasy-studio/compare/v1.4.6...HEAD
[1.4.6]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.6
[1.4.3]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.3
[1.4.2]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.2
[1.4.1.1]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.1.1
[1.4.1]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.1
[1.4.0]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.4.0
[1.3.7]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.7
[1.3.6]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.6
[1.3.5]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.5
[1.3.4]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.4
[1.3.3]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.3
[1.3.2]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.2
[1.3.1]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.1
[1.3.0]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.3.0
[1.2.0]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.2.0
[1.1.0]: https://github.com/bgrut/fantasy-studio/releases/tag/v1.1.0
