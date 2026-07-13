# Changelog

All notable changes to Fantasy Studio are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0 versions are internal milestones during the constraint sprint leading to public early access and the V1.0 launch. They're documented here transparently — Fantasy Studio has never been a stealth project.

---

## [Unreleased]

### Added — Phase 60+61: 1:1 reference texturing + new game genres (2026-07-11)
- **Texture v2 (`texture_v2.py`, FS_TEX_V2 default on)** — kills the
  "half-stretched face/body" on CPU-generated heroes. The v1 flat side
  projection mapped face/chest/rump onto a thin strip of photo pixels; v2
  bakes a smart-UV atlas (numpy rasterizer, no Cycles), keeps the photo where
  the surface faced the reference camera, and pyramid-inpaints the smear
  zones (~20% of the surface on bear/cat). Verified by front-render A/B:
  streak bands gone; flanks stay 1:1 with the reference. Companion fix:
  skin v2's geodesic graph is now WELDED BY POSITION so atlas UV-seam vertex
  splits can't fragment it (the harness caught a cat morph regression from
  exactly that — fixed, all gates pass).
- **Battle royale (`eliminate` objective)** — "battle royale / last one
  standing / eliminate all rivals" spawns hostile rivals of the player's own
  kind plus a SHRINKING STORM ZONE (translucent wall + ground ring, closes
  over 150 s, 1 HP/s outside). Win = all rivals down. Verified live in
  browser: 3 rivals, quest "Last one standing — eliminate 3 rivals 0/3",
  zero errors.
- **Sports (`score` objective)** — "soccer / score N goals" spawns an arcade
  ball (gravity, bounce, rolling drag, world-bounds), walk into it to kick
  (Shift = power), goalposts at the level goal, GOAL! burst + counter, win at
  N. Verified live in browser: "Score 2 goals — 0/2", ball physics running
  clean during play.
- Both genres wired end-to-end: spec Literal, LLM grammar + keyword fallback
  (works with Ollama down), runtime, quest log/HUD. Style/view snapshot
  re-baselined for the intended runtime change; morph gate untouched.
- **Godot multiplayer starting point** — every Godot export now ships
  MULTIPLAYER_GUIDE.md: the 5-step Godot 4 high-level networking path
  (ENetMultiplayerPeer, MultiplayerSpawner/Synchronizer, per-peer authority,
  server-authoritative mission RPCs) mapped to this project's player.gd/
  mission.gd structure. Honest scope: web builds stay single-player; Godot
  is the multiplayer route.

### Added — Phase 57+58: orientation telemetry + gated retopo keystone (2026-07-11)
- **Phase 57 (orientation)**: auto-fix was REJECTED BY EVIDENCE — two
  independent geometric leg-gap detectors false-positived on known-good rigs
  (one flipped a correct polar bear twice; caught by visual render checks,
  file restored + re-verified). Ships as detection-only telemetry
  (`verify_glb_orientation`, FS_ORIENT_VERIFY, off by default) + a visual QA
  tool (`scripts/_render_pose_check.py`). Orientation stays guaranteed where
  it is provable: the bake-time 24-view silhouette gate vs the reference +
  feet-down/head-up priors + rig-cache mtime invalidation.
- **Phase 58 (retopo keystone, FS_RETOPO=1 opt-in)**: `app/game_export/
  retopo.py` — voxel remesh (manifold/watertight/shard-fusing, density-guarded)
  + hygiene pass + largest-island filter + best-effort QuadriFlow + UV/material
  transfer, inserted before rigging in both anim bakes; failure restores the
  original mesh. HONEST FINDINGS: Blender 5.1's QuadriFlow rejects the
  voxel-remeshed TRELLIS heroes ("needs manifold/consistent normals") even at
  0 non-manifold verts / 1 island / consistent normals — probed exhaustively
  (symmetry off, triangulated, mesh-doctor); a cube passes in the same
  session. Voxel-only keystone measured MIXED on the harness: bear 0.702→0.668
  (better), cat 0.613→0.749 (worse), fox 0.320→1.725 (fur is hundreds of
  legitimate alpha-strip shells — island filter + voxel destroy them).
  Therefore OPT-IN ONLY; library keeps the Phase 54 rigs. Upgrade path:
  standalone instant-meshes (BSD-3) or newer Blender + per-pattern gating —
  GPU-day. Bridge ops learned: quadriflow needs a long-timeout call (420 s);
  never read_factory_settings through the bridge (kills the addon socket).

### Added — Phase 53+54: quality harness + quadruped skin v2 (morphing fix, part 1) (2026-07-11)
- **Quality harness** (`scripts/quality_harness.py`): the regression gate for all
  character/scene quality work. `morph` mode measures p95 EDGE STRETCH on the
  animated library rigs via headless Blender — wrong-bone skinning weights
  stretch edges between limbs, so this is the "morphing" defect as a number.
  `styles` mode hashes fixed-seed exports per style/view preset to catch drift.
  Baselines live in `renders/quality_baseline/` (gitignored); `--compare`
  fails on any regression, so every quality change is proven, not eyeballed.
- **Quadruped skin v2** (`app/game_export/skin_v2.py`, flag `FS_SKIN_V2`,
  default on, per-step auto-fallback to the untouched Euclidean path):
  1. *Same-side/same-end constraints* — a left-leg bone can never claim a
     clearly-right-side vertex (ported from the proven biped mocap skin).
  2. *Geodesic surface distance* for leg bones — pure numpy+heapq multi-source
     Dijkstra over the mesh edge graph (bridge Python has no scipy). Surface
     distance makes the inner thigh "far" from the other leg even though it is
     physically near — the root cause of cross-limb weight bleed.
  3. *Laplacian weight smoothing* + max-4-influence clamp.
- **Measured (harness, p95 edge stretch, lower=better):**
  polar_bear 0.934 → 0.702 (−25%) · cat 0.737 → 0.613 (−17%) ·
  fox 0.698 → 0.320 (−54%) · man 0.481 (untouched biped path, unchanged).
  Visual A/B mid-run confirms: legs read as legs instead of sheared sheets.
- Re-baked cat/fox/polar_bear rigs promoted to the library; every future
  quadruped bake gets v2 automatically. Remaining stretch is the thin
  triangle-soup leg geometry itself — that is the QuadriFlow retopo keystone's
  job (next phase).

### Fixed — Phase 53: rig cache invalidates when its static mesh is re-baked (2026-07-08)
- **The bug (why the bear STILL looked upside-down after Phase 52)**: the game
  player uses the RIGGED `<kind>_anim.glb`, not the static library mesh.
  `ensure_playable` returned the cached `_anim.glb` whenever it merely EXISTED,
  with no freshness check — so after Phase 52 re-baked the static polar bear
  feet-down, the game kept loading the older `polar_bear_anim.glb` that had been
  rigged from the belly-up mesh. Fix corrected the source, cache served the
  stale derivative.
- **Fix (scalable, all rigged assets)**: `ensure_playable` now serves the cached
  rig ONLY if its mtime is ≥ the static mesh it was rigged from; otherwise it
  re-rigs. Any future static re-bake (orientation, texture, mesh re-roll) now
  auto-invalidates the derived animation — no more stale rigs shipping silently.
- Regenerated `polar_bear_anim.glb` from the fixed static → verified feet-down,
  standing (12-bone quad rig, idle/attack/walk/run). `bake.py` compiles clean.
- NOTE: existing GAME BUILDS bundle a COPY of the rig in their dist/, so a game
  built before this fix must be REBUILT to pick up the corrected bear.

### Fixed — Phase 52: quadruped feet-down orientation prior (2026-07-08)
- **The bug**: the generated polar bear shipped BELLY-UP in-game (legs in the
  air) at silhouette IoU 0.34. Root cause: the 24-view silhouette orientation
  gate had geometric up/down priors for BIPEDS (head-up) and VEHICLES
  (wheels-down), but NONE for quadrupeds — and the 2D silhouette centre-of-mass
  tiebreak can't tell a chunky animal's back from its belly (both outlines look
  nearly identical), so a belly-up pick sailed through.
- **Fix (scalable, all quadrupeds)**: added a `quad_feet_down` geometric prior
  to `_orient_hero_by_reference`, mirroring the biped one. After the silhouette
  pick + azimuth-normalize, it measures the LEG-GAP (belly clearance between the
  front/back leg pairs along the body axis, and the left/right leg split across
  it) in the bottom vs top Z-slabs. If the leg-gap is at the TOP, the animal is
  belly-up → roll 180° about Y (the body long axis), preserving the heading the
  silhouette already chose. Reference-independent; fixes bear, dog, horse,
  tiger, etc. — not a per-asset override. Wired in `bake.py` for
  `pattern == "quadruped"`.
- Verified: re-baked the polar bear (raw mesh cached) → renders standing
  feet-down, head forward. `composer.py` + `bake.py` compile clean.
- KNOWN (GPU-day, not this fix): the fur texture is still single-view baked, so
  off-camera faces show brown/tan patches — the real fix is multi-view texturing
  (needs a GPU). Tracked separately.

### Fixed — Phase 51: hero casting never crosses species (2026-07-08)
- **The bug**: "a polar bear that must defeat 3 knights to reach the sacred
  igloo" spent ~30-60 min attempting to generate the bear on CPU, the attempt
  failed, and the casting ladder silently fell back to `library.resolve("man")`
  — a human who, in a `defeat` mission, spawns holding a sword. The player got
  a man-with-a-sword instead of a polar bear, and nothing was saved to the
  library. Root cause: the failure fallback degraded the hero to a completely
  different SPECIES.
- **Fix 1 — honest same-species stand-in**: new `library.nearest(kind, pattern)`
  returns the closest asset of the SAME category, so an un-buildable quadruped
  degrades to a quadruped (polar bear → wolf), a vehicle to a vehicle, an
  aquatic to a whale — NEVER a man. Both blind `resolve("man")` fallbacks in
  the player-casting ladder now route through it, with a loud, self-healing
  note: "Couldn't build 'polar bear' yet — needs a GPU; cast 'wolf' as a
  stand-in; re-run once your GPU is in to get the real one."
- **Design intent preserved**: the generate-then-place path stays PRIMARY and
  is always attempted — CPU generation works (~25-30 min once, then cached; the
  cat and fox were both born this way). The `nearest()` stand-in fires ONLY on
  a genuine generation failure, so a hero is never a man-with-a-sword, but the
  normal flow is still "not in library → generate → place." (An earlier draft
  of this fix wrongly gated generation behind a GPU; reverted.)
- Verified: `nearest()` maps polar bear/grizzly/tiger → wolf, ferrari → car,
  dolphin → whale, cat → cat; TripoSR confirmed available in the backend venv;
  both edited files compile clean.
- **Fix 3 — a bridge hiccup no longer discards a generated mesh**: root-cause
  of THIS report was not generation at all — the SDXL+TripoSR mesh generated
  fine (cached), but the final "optimize to game budget" step (which needs the
  Blender bridge) failed because the bridge was down/deadlocked, so the whole
  build fell back to a stand-in. `ensure_asset` now catches an optimize failure
  and registers the RAW generated mesh as a raw library entry, so the CORRECT
  species plays immediately and `resolve()` auto-optimizes it (orientation +
  texture projection + decimation) the moment the bridge is healthy again.

### Docs — Phase 50: README rewrite, front-and-center game engine (2026-07-08)
- **Rewrote `README.md` to lead with what Fantasy Studio IS today**: a
  local-first, no-code desktop app that turns one sentence into a playable 3D
  game OR a cinematic video. Games are now front-and-center (previously the
  README was video-first and barely mentioned the game side).
- **New "game engine" section** covers the full loop that shipped in Phases
  42–49: prompt → playable game, real-time Inspector (hover to identify,
  click-to-place with Point/Line tools), honored rules + the Truth Table,
  user-picked style presets, 2D/3D view presets, walk-in destinations, level
  projects, and the Community Marketplace share link. Added a "Share it"
  section (marketplace / zip / Godot 4 export with parity).
- **Removed every stale reference**: all "Mid-May 2026 launch" banners/FAQ
  answers replaced with an honest "public early access, active development"
  status; the old `python scripts/export_game.py` CLI framing and the
  "single-subject V1 only" positioning are gone.
- **Kept the strong positioning**: local / deterministic / you-own-it /
  render-not-diffusion, the comparison table (now with a games row), honest
  GPU-day constraints, acknowledgments, and BSL 1.1 license.
- Also fixed the "Mid-May 2026" note in this changelog's own preamble.

### Fixed — Phase 49: WebGL resilience, full-viewport canvas, mobile HUD (2026-07-08)
- **"Error creating WebGL context" (constrained Chrome)**: the game asked for
  a WebGL context with no fallback, so Chrome refused when its global context
  limit was hit (many tabs) or hardware acceleration was off. Now it tries
  three configs (high-perf → default → low-power, all with
  `failIfMajorPerformanceCaveat:false` so software rendering is allowed); if
  all fail it shows a helpful message ("close some tabs or enable hardware
  acceleration") with a Retry button instead of a dead end. Verified by
  forcing getContext to return null: the recovery UI + Retry appear.
- **Firefox/desktop black gap**: the canvas is now pinned to fill the
  viewport (`width/height:100%`, `setSize(...,false)` so resizes don't
  overwrite it) plus a post-layout re-fit. Verified: canvas matches
  innerWidth/innerHeight exactly.
- **Mobile HUD overlap**: a `max-width:640px` breakpoint truncates the title
  to one line and moves the objective/hearts to the bottom, so the long
  title no longer collides with them. Verified at 375px: title one line,
  zero overlap.

### Fixed — Shared games: "click a level, nothing loads" (2026-07-08)
- **Root cause**: the worker served a directory URL (the hub `/g/:id`, or a
  level `/g/:id/levels/lvl_N/dist`) WITHOUT a trailing slash as a plain 200.
  With no trailing slash the browser resolves the hub's relative card links
  one path level too high (`levels/lvl_1/dist/` → `/g/levels/lvl_1/dist/`),
  which 404s — the published game's level cards led nowhere.
- **Fix**: the worker now 301-redirects any extension-less directory URL to
  add the trailing slash (standard web-server behavior), so relative links
  always resolve against the canonical directory. Applies to game hubs,
  nested level dirs, and character pages. Verified: `/g/:id` → 301 →
  `/g/:id/` (200 hub), level dirs and `/c/:id` redirect too, all files and
  the API unaffected. **Fixes already-published games server-side — no
  re-publish needed.** The game files themselves were always byte-perfect
  (confirmed identical to local); this was purely a navigation bug.

### Fixed — Texture warm-fill: the gray "unwrapped" patches are gone (2026-07-08)
- Root cause audited in a neutral-light viewer: side-projection baking
  leaves off-axis texels (haunches, back, chest) as desaturated gray smears —
  the "texture doesn't wrap the character" look. New
  `scripts/warmfill_texture.py` recolors those texels toward the asset's own
  fur palette (hue+sat transfer, luminance kept; whites/darks protected;
  rigs and animations untouched — only the embedded texture bytes change).
- Applied to the demo trio (cat, wolf, dog + animated variants; originals
  in `assets/library/_pre_warmfill/`). Verified in-viewer (haunches read as
  soft fur, not gray plastic) and in-game (wolves close-up with intact
  detailed faces). True multi-view texture baking remains the GPU-day
  upgrade; this closes most of the visual gap on CPU.

### Fixed — Character faces + forest depth + style/view edit protection (2026-07-08)
- **No more half-cut-off faces**: generated character meshes are open shells,
  and single-sided rendering showed holes through heads/ears at grazing
  angles. Player, NPC and placed-creature materials now render DoubleSide —
  the CPU-tier fix until GPU-day watertight meshes.
- **Forests stopped being plastic**: scatter props get per-instance color
  variation (±8% tone, seeded) — every tree reads as an individual. (The
  flat look was the low-poly asset tier by design, not a lighting bug;
  textured photoreal props are a GPU-day upgrade.)
- **Style + view are sacred during edits**: the base game's style/view carry
  forward through every LLM edit; only explicit words ("make it horror",
  "make it top-down") may change them. Verified: an edit rebuild preserved
  style=default view=3d while adding health packs and keeping placed cats.

### Added — Phase 48: Quality uplevel — living placements, structure flavors, sky life (2026-07-08)
- **Placed creatures are ALIVE**: placements resolve to the already-baked
  animated variant when one exists and play their idle clip — a cat placed
  at the shelter breathes instead of freezing in bind pose. Never triggers
  a bake; uses only what's cached. `__game.placed()` reports `alive`.
- **Goal structures have flavor**: "reach the castle" builds a stone keep
  with four cone-capped corner towers and a parapet; "reach the lighthouse"
  adds a striped light column with a lamp visible for miles. Everything
  else keeps the warm cottage. All walk-in, all verified.
- **Sky life**: day-family skies get 7 drifting soft clouds and a wheeling
  bird flock (canvas sprites, near-zero cost, seeded per world). Horror
  skies stay dead quiet, as they should.

### Added — Phase 47: The goal is a PLACE — walk-in buildings + creative-prompt readiness (2026-07-08)
- **Walk-in goal structures**: when a reach objective names a structure
  ("reach the cat shelter", "the cabin", "the lighthouse" — 20 nouns), a
  real building stands at the goal instead of the abstract beacon: open
  doorway facing the approach path, warm windows, a lit hearth inside, a
  glowing welcome mat, wall colliders with the doorway open — you win by
  STEPPING INSIDE. Verified: outside the wall = no win, through the door =
  win.
- **The keyword fallback speaks every verb**: an Ollama hiccup used to
  degrade rich prompts to an empty stroll (the cat-with-9-lives prompt lost
  ALL its objectives). The fallback now parses collect/defeat/survive/reach
  + hostile mentions ("avoid the hostile wolves") deterministically — every
  prompt yields a playable mission on both extraction paths.
- **"9 lives" → 9 HP**: numbers the user writes are game facts.
- **Generic collectibles never stall**: "food"/"supplies"/"treasures" render
  as glowing pickups instantly with a note pointing at the specific-noun
  path ("fish", "bones") — no more accidental 35-minute generation.
- Friendlier note when the AI imagines a creature that isn't in the library.
- Verified end-to-end on the cat demo prompt: cat cast, 9 hearts, 6 food
  pickups, hostile wolf, GOLD win inside the shelter.

### 🚀 THE COMMUNITY IS LIVE (2026-07-08)
- The first Fantasy Studio hub is deployed at
  `fantasy-studio-share.fantasy-labai.workers.dev` and baked in as the
  app's DEFAULT community — every install browses it with zero setup
  (`FS_COMMUNITY_HUB` env overrides for private hubs).
- **First publishes, verified from the public internet**: the Winterfang
  game (108 files, plays in a plain browser at /g/3d3b5801/) and the wolf
  character (installable into any library). Feed, playback and per-level
  URLs all confirmed live.
- Fixes shaken out by the real deployment: directory-style URLs now fall
  back to index.html in the worker (level pages 404'd); per-file upload
  retries with backoff (large GLBs hit transient TLS resets).

### Added — Phase 46: Community Marketplace + share worker v2 + privacy policy + Godot parity (2026-07-08)
- **Community Marketplace** (replaces the template marketplace page): browse
  the community feed, ▶ play shared games in-app, install shared characters
  straight into your library (they become castable kinds), and publish your
  own games/characters behind an explicit consent checkbox. Includes a
  6-step in-app setup wizard for the one-time Cloudflare wiring.
- **Share worker v2** (infra/share-worker): community feed (feed/index.json,
  capped 500), character publishing + serving (/c/:id/), unpublish
  (DELETE /api/items/:id), CORS. Games and characters share one
  create→upload→publish flow.
- **Backend share bridge** (app/api/share.py): the publish token lives
  server-side only (renders/share_config.json, local); endpoints for
  status/config/feed/publish game/publish character/install character.
  Config saving verifies the worker actually answers before persisting.
- **PRIVACY.md**: the local-first promise (no telemetry, local AI), exactly
  what Publish uploads, CC-BY-4.0 sharing terms, content rules, removal
  path, third-party attribution requirements.
- **Godot export parity (Phase 46)**: placed items spawn as primitive props
  with colliders (fence/campfire/building/sign/book/chest/rock/beacon);
  rules are HONORED (safe zones hold hostiles at the glow's edge,
  blocks_enemies pushes NPCs out, hurt zones drain 1 HP/s); books/signs are
  readable with E; top-down/side orthographic views; styles map to
  environment color grading (horror adds fog). STEAM_GUIDE updated with the
  parity list and honest approximation notes. Verified structurally on a
  spec with fences+rules+side view.

### Added — Phase 45: 2D view presets — top-down + side-scroller (2026-07-08)
- **View chips** next to the style chips: 🧊 3D · 🗺️ Top-down 2D ·
  🎞️ Side-scroller. User-selected like styles, never LLM-guessed; edits can
  switch deterministically ("make it top-down").
- **Top-down** = orthographic overhead camera (the 2D-Zelda feel), wheel
  zooms the map, world-aligned WASD. Pairs beautifully with 👾 Pixel style.
- **Side-scroller** = orthographic side camera locked to one lane: A/D run,
  Space jumps, terrain becomes the platforming. Gameplay honestly projected
  to the lane — goal, collectibles, health packs land on it and creatures
  drift onto it, so every objective stays reachable. Verified: ran +3.6m on
  the lane (z locked at 0), jumped +1.9m, fox-runs-to-cabin frame reads as
  a real platformer.
- Fog pushed out by the ortho camera standoff in 2D views (the whole world
  used to sit inside the fog band). Inspect/picking/free-fly all work in
  both views. Same world, three games.

### Added — Phase 44: Style presets, the Line tool, rule chips + the Truth Table (2026-07-08)
- **Style presets (user-selected, never LLM-guessed)**: 🎬 Photoreal ·
  🖍️ Cartoon (cel bands + ink outlines) · 🌸 Anime (soft cel + bloom) ·
  🕯️ Horror (midtone crush + grain + closing fog) · 👾 Pixel (chunky
  low-res + posterize) · 📐 Low-poly (flat shading). Picked as chips BEFORE
  building; one GLOBAL post/render pack applies coherently to the whole
  game — hero, props, terrain — unlike per-asset stylers. Edits can also
  switch styles deterministically ("make it horror"). Verified visually:
  cartoon (outlined fox + fence) and horror (crushed dark + grain).
- **📏 Line tool**: Inspect gains Point/Line modes. Two clicks define a run;
  "place a fence here" tiles 2m segments A→B with correct heading — a new
  procedural fence prop ships (posts + rails; wall/railing/hedge/barrier
  alias to it). Purpose clauses parse ("a fence TO BLOCK THE DOGS" = fence).
  Verified: 6 segments along a 12m line, blocks_enemies auto-on.
- **Rule chips**: click a placed item in Inspect → toggle 🔥 safe zone ·
  🚧 blocks enemies · ⚡ hurts on touch. Every chip is an HONORED runtime
  behavior (fence line held a hunting dog out — 2.76m minimum approach —
  and it correctly flanked the open ends; cursed rock drained 1 HP/s).
  Toggles are fully deterministic (no LLM), re-export in seconds.
- **📜 The Truth Table**: one panel listing every rule the game actually
  enforces — hero stats, mission steps, hostile behavior ranges, placed-item
  rules, rewards — derived from the resolved spec, so nothing listed is
  decorative. The "auditable game" vision, rendered.

### Added + Fixed — Props tell the truth, Inspect free-fly, biped birds (2026-07-08)
- **Placed props are real game rules**: campfires (and beacons) are SAFE
  ZONES — hostiles fear the light: they will not enter the glow, and back
  off to its edge while you stand inside. A sign that says "stay near the
  fire" is now mechanically TRUE. Verified: fast hostile held 9m from the
  fire for 9s, zero damage. (First brick of the rules engine — richer
  honored-rule vocabularies ride the grammar roadmap.)
- **Inspect free-fly camera**: while Inspecting, WASD/arrows pan the EDITOR
  CAMERA across the world (hero stays put, slightly wider framing) — scout
  any hill, click, place. No more walking the hero around to reach spots.
  Verified: camera panned 40m, player moved 0.00m, distant pick landed.
- **Penguins have two legs**: the body-type classifier had cached
  penguin=quadruped, so its SDXL reference was drawn "standing on all four
  legs" — that's where the extra legs came from. Flightless upright birds
  (penguin/ostrich/emu/kiwi/dodo) now hard-classify as bipeds; stale cache
  purged. Regenerating the penguin asset itself is one ~35-min CPU pass
  (or minutes on GPU day).

### Fixed — Demo-feedback round: combat feel, inspect freeze, hero cast, placement trust (2026-07-08)
- **Combat feel**: melee reach 2.3→3.2m, swing arc widened, and AIM ASSIST —
  the swing snaps toward the marked target. A red diamond MARKER floats over
  the nearest hostile in reach, so you always know who the hit lands on.
  Verified headless: off-angle attack at 2.9m kills in one press.
- **Inspect = soft freeze**: while Inspecting, enemies stop, damage stops and
  the run/survive clocks hold (shifted on exit, same math as pause) — you
  can't die mid-edit. Camera, player and rendering stay live. Verified:
  adjacent hostile frozen 2.5s, zero damage.
- **Subject is the hero**: "a wolf roaming the mountains" once cast a FOX
  with a wandering wolf NPC. If the extracted player noun never appears in
  the prompt, the first prompt noun that resolves in the library takes over
  (its duplicate non-hostile entity is dropped) — with a visible note.
- **Placement trust**: placed items never stack (a new item landing on an
  earlier one is nudged ~2m aside — the sign-inside-the-campfire report);
  "place a X here" without a clicked spot is now caught in the studio with
  a helpful message instead of letting the LLM guess coordinates; Inspect
  mode survives rebuilds (only stale picks clear).

### Fixed — Explicit words beat the AI's pick for sky/weather edits (2026-07-08)
- "make it a starry night" once came back as `sky="space"` (airless glare +
  the grade's dark-palette lift = washed-out daylight, not night). Two-layer
  class fix: (a) sky normalization handles multiword values ("starry night",
  "night sky", "moonlit") and falls back to token scanning; (b) in the edit
  path, when the change TEXT literally names a sky or weather (night, dusk,
  snow, rain, …), that deterministically overrides whatever the LLM chose —
  with a visible note ("your words beat the AI's pick"). Verified by
  replaying the exact failing edit: sky=night, 4 health packs.

### Fixed — Inspect-mode ergonomics + prompt-chip scrunch (2026-07-07)
- **Screen jumped upward in Inspect mode**: every arrow press refocused the
  game iframe, and plain `focus()` scrolls the page to the element. All
  programmatic focus now uses `preventScroll` — the studio never jumps.
- **Camera drag restored while Inspecting**: dragging orbits the camera like
  normal play; a STILL click (moves < 6px between down and up) is what picks.
  You can look around freely and still select exactly what you mean.
  (Applies to games built/opened after this change — opening a level tile
  or applying any edit re-exports with the new runtime.)
- **Prompt idea chips scrunched**: truncated multi-column pills (full text
  on hover) instead of ten full-width rows — the level tiles and player sit
  a scroll higher.

### Added — Phase 43: Level tiles + scene tiles — the Inspector methodology everywhere (2026-07-07)
- **Level tiles (game)**: the levels dropdown is now the hub's level-select
  cards, live in the studio. Click a tile → that level re-exports in seconds
  and opens in the player — play it, Inspect it, edit it. A **Save to level N**
  button writes the edited game back into the SAME tile (one evolving level,
  not accumulating copies). New endpoints:
  `POST /api/game/projects/{pid}/levels/{i}/open`, `PUT .../levels/{i}`.
- **Scene tiles (video)**: 🎬 scenes panel with per-scene ▶ Watch (in-app
  player — scenes were already served under /outputs), ✎ **Change** ("make it
  a snowy night" → Ollama rewrites the scene prompt, the full pipeline
  re-renders it, the mp4 swaps in place with live status on the tile), and
  ✕ remove. `POST /api/video/projects/{pid}/scenes/{i}/edit`. A failed
  re-render never touches the original scene.
- **Video export buttons fixed** (same WebView2 bug class as the game side):
  "Watch film" plays in an in-app player, "Show mp4 in folder" opens
  Explorer at the file (`POST /api/video/projects/{pid}/reveal`).

### Added — Phase 42: Inspector mode — visually build the game in real time (2026-07-07)
- **Picking bridge**: toggle 🎯 Inspect over the running game — hover
  identifies anything under the cursor (wolf · hostile · speed 3), click
  selects a spot or thing. The game raycasts and reports world coordinates
  to the studio via postMessage; standalone exports keep the bridge inert.
- **Click-to-place**: with a selection active, "place a book here that says
  'follow the river'" is DETERMINISTIC — no LLM round-trip, the item lands
  at the exact clicked coordinates in seconds. Longer edits still go through
  the LLM patcher, which now receives the selection as context ("here"/"this"
  mean the clicked spot) with a coordinate safety net.
- **placed_items in the spec**: procedural props render instantly (book,
  sign, chest, building, rock, beacon, campfire + aliases like house/torch/
  scroll); any other noun resolves through the same casting ladder as
  entities — placed items are always user-invited, so unknown nouns may
  generate (once, then cached).
- **Interact verb**: placed items with text are READABLE — proximity prompt
  ("E — read the sign"), press E, a panel shows the hint/lore. Books with
  hints, trail signs, notes: games can now teach and tell stories.
- Verified end-to-end: headless probes (5 props placed, E-panel text exact,
  picks report coords + identity tags) AND the full studio loop (build →
  Inspect → click ground → "place a sign here that says…" → sign at the
  clicked spot with readable text, 16 checks passed).

### Fixed — Export buttons did nothing in the desktop app (2026-07-07)
- **Root cause**: both post-export actions were plain `<a>` links. The
  desktop shell (WebView2) ignores `target="_blank"` (no new-window handler)
  and has no browser download UI, so "Play it" and "Download zip" silently
  no-oped. Same bug class as the old open-in-tab fullscreen link.
- **▶ Play it** now plays the exported game (hub + level select + all
  levels) right inside the studio in an embedded player, with Fullscreen
  and Close — better than a new tab anyway. Verified end-to-end: export →
  play → hub renders → level 1 launches with a live canvas.
- **⬇ Show zip in folder** replaces the download link: a new
  `POST /api/game/projects/{id}/reveal` opens Explorer with the exported
  zip selected (path-guarded to the projects dir). That's the
  desktop-native version of "download" — the file is already on disk.

### Fixed + Added — White-screen recovery, health packs, difficulty edits (2026-07-07)
- **White-screen root cause**: NOT a build bug — WebView2 caps live WebGL
  contexts, and after many game loads the new canvas silently gets none
  (HTML UI keeps working, canvas shows the white page). The exact "broken"
  build rendered perfectly when re-verified. Two-layer fix: games detect
  `webglcontextlost` and self-reload with an honest message; the studio
  iframe is keyed per game so old contexts release.
- **Health packs**: `world.health_packs` — heart pickups on the ground
  restore 1 HP (politely don't consume at full health). "add health packs"
  works in prompts AND edits.
- **Difficulty edits**: the edit bar understands "make it harder/easier" —
  hostile speed/count/hp and player HP adjust through the existing schema.

### Fixed — Texture polish push: white-wash + stretch on NPC bodies (2026-07-07)
- **Root cause 1 — wrong interpreter**: the batch re-bakes ran under system
  Python (no PIL), so subject-bbox detection silently fell back to
  "whole image" and mapped background margins onto bodies. All library kinds
  re-baked under the venv interpreter (correct bbox).
- **Root cause 2 — silhouette bleed**: up/back-facing surfaces sample pixels
  at the photo's silhouette edge where the white studio background bleeds in
  (the washed wolf spine). New `_fill_reference_background`: background
  pixels are replaced by their nearest subject color (iterative masked
  dilation), so UV overreach samples fur, never white. Cached per-ref as
  `*_fill.png`; graceful skip when PIL is absent.
- Stale `_anim` rigs dropped for re-baked kinds — they re-rig from the
  improved bodies (with foot ground-plant) on next use.

### Added — Motion session: foot ground-plant + airborne body language (2026-07-07)
- **Foot ground-plant (#119)**: every mocap bake now evaluates the finished
  clip and keys the ROOT height so feet neither sink below ground nor hover —
  penetration always corrected, float pulled down gently (capped so run
  flight-phases survive). Root-only correction: bone curves untouched, so it
  cannot introduce limb bugs by construction (the three historical retarget
  bugs live in bone space and stay fixed). Knight + fox re-baked;
  render-verified across the walk cycle: clean stride, separate legs, feet
  planted with contact shadows. Known polish left: faint elbow smear on
  armor (skin falloff — GPU-day item).
- **Airborne body language**: walking characters tilt back on a jump's rise
  and lean into the fall — the cheap half of jump articulation until a jump
  clip joins the CMU catalog.

### Added — Godot-for-Steam enrichment + style coherence + game shell (2026-07-07)
- **Godot export is a real GAME now**: the emitted Godot 4.3 project carries
  the full mission system (collect/defeat/reach/survive with quest log +
  progress), hostile AI with player health and win/lose/retry, spawned
  collectibles and goal beacon, survive waves, jump, the narrative intro
  overlay, and the Made-with credit. Every export includes **STEAM_GUIDE.md**
  — the honest step-by-step from "open in Godot" through export templates,
  Steamworks ($100 app fee), GodotSteam, and SteamPipe upload. (Structurally
  verified; full `godot --headless --import` validation runs wherever a Godot
  binary exists — none on this machine.)
- **Art-direction coherence (style system v1)**: a whole-frame color grade
  pulls every element toward the sky palette's mood + scatter props get
  albedo-nudged toward the same tint at load — photoreal heroes and low-poly
  props finally share one look. Consistency is the cheapest "looks expensive"
  trick in games.
- **Game shell**: Esc pause menu — Resume, Sound ON/OFF, Restart. Pausing
  freezes movement, NPCs, the run clock AND survive timers (play-verified:
  4.5m moved → frozen at 0.00 during pause → clean resume).

### Fixed + Added — Pickup lag spike, rival gaits, SURVIVE verb (2026-07-07)
- **Pickup lag spike KILLED (Reddit report)**: every collectible carried its
  own PointLight, and removing a light recompiles every shader in the scene —
  a ~1s freeze per pickup on iGPUs. Replaced with a shared additive glow
  sprite: visually identical, free to remove.
- **Race rivals animate**: rivals resolved the static mesh ("{kind}_anim" was
  never a registry key) — the gliding fox. Rivals now cast through
  ensure_playable, same as every other NPC.
- **Collect labels generate their own mesh**: "collect 6 fireflies" produces
  firefly meshes even when no matching entity was cast — the label is a noun
  like any other. Ambient nouns (snow, rain, fog, stars…) never generate.
- **Grammar verb 2 — SURVIVE**: "survive 90 seconds against the wolf waves" →
  live countdown in the quest log, escalating waves every 20s from a DORMANT
  pre-built hostile pool (no mid-game loading hitches — same philosophy as
  the glow-sprite fix), "Wave N!" pops. Play-verified headlessly: timer
  counts, waves wake on schedule (pool 7→5 at t=20s), step advances on
  survival. Needs at least one hostile; drops honestly otherwise.

### Added — Narrative layer, adaptive performance, Made-with stamp (2026-07-07)
- **Narrative layer**: the LLM now writes a 1-2 line quest intro (START
  screen, set like game flavor text) and a victory line (win screen) for
  every game — content, not code, so it can't break a build. "Collect 6
  fireflies" becomes "The fireflies have scattered across the frozen wood…"
- **Adaptive performance governor**: sustained sub-28fps sheds cost tiers
  automatically — resolution first, then bloom, then frozen shadow updates —
  instead of letting the game lag. Never oscillates back mid-run.
- **"⚡ MADE WITH FANTASY STUDIO" stamp**: on the START screen and as a
  persistent corner badge — it travels with every exported zip, so every
  shared game advertises the product.
- **Strategy locked in the blueprint** (vs Rosebud AI + Summer Engine):
  breadth via verified grammar expansion, never free codegen; depth via the
  Godot off-ramp; distribution before depth; sandboxed-DSL behaviors parked.

### Added — R-B medals + R-ITER "Edit this game" (2026-07-06)
- **Medals**: 🥇/🥈/🥉 on the win screen, judged against a par time computed
  from the actual level geometry (spawn → collect points → goal distance at
  cruise speed) — the same fair formula for every game class.
- **R-ITER — conversational game editing** (the Summer Engine answer): every
  built game gets an "Edit this game…" bar. A follow-up prompt patches the
  existing GameSpec via the local LLM and re-exports — SAME seed, so it's the
  same world with your change applied; cached assets make the rebuild itself
  take seconds. Verified end-to-end: "make it night time with snow falling"
  on a fox meadow → sky=night, weather=snow, identical seed/world, in 120 s
  total (~90 s of that is CPU LLM inference — GPU day makes the loop ~10 s).
  Specs persist to disk (spec_full.json) so games stay editable across
  restarts.

### Added — R-A juice pack + marketplace architecture (2026-07-06)
- **Juice**: gold particle burst + floating "+1 label · n/count" on every
  pickup, red burst on kills, decaying screen shake when the player takes
  damage. Verified headlessly: full pearl run → win screen showed
  "time 0:34 — new personal best!", zero console errors.
- **Marketplace architecture** documented in the blueprint: (1) `.fsbundle`
  export/import (no server — assets/games/videos as manifest-carrying zips),
  (2) hosted community registry API (browse/search/feed; app stays fully
  offline-capable), (3) presence/payments only after demand is proven. The
  orientation gate + heading facts + license manifest make downloaded assets
  drop-in — that's the moat. Parity rule recorded: every game-feel feature
  ships a video twin.

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
