# Game Success Blueprint — what top games do, and what our outputs need

The question: users can build levels — how do the outputs become games people
*want to play* (and eventually sell)? This maps what the best-selling PC and
console games consistently do, against what our pipeline emits today.

## Why top sellers succeed (the recurring anatomy)

Looking across the perennial best-sellers — Minecraft, GTA V, Stardew Valley,
Terraria, Elden Ring, Mario Kart, Vampire Survivors, Balatro — genre varies
wildly but five properties repeat:

1. **A legible core loop in the first 30 seconds.** The player always knows
   what to do next and why (mine → craft → build; drive → race → win). Nothing
   sells a bad first minute.
2. **Feedback for everything ("juice").** Every action answers: sound, flash,
   number, particle. This is the cheapest quality signal there is — indie
   megahits (Vampire Survivors, Balatro) are 90% feedback craft on simple loops.
3. **Progression you can feel.** Numbers go up, abilities unlock, the world
   opens. Sessions end with "one more run" hooks.
4. **Identity & ownership.** Your island, your character, your save. Players
   sell each other on games where *their* story is visible.
5. **Friction-free session shape.** Instant restart, clear fail states,
   save/resume. Death without a retry button kills retention.

## Scorecard: our exports today

| Pillar | Status | Gap |
|---|---|---|
| Core loop legibility | ✅ good | START overlay + quest log + objectives already do this |
| Feedback / juice | 🟡 begun | **Sound landed 2026-07-06** (WebAudio, zero assets). Still missing: pickup particles, hit flash on player, screen shake, damage numbers |
| Progression | ❌ missing | No score, no timer, no medals, no unlocks. A run has no "how well did I do?" |
| Identity / ownership | 🟡 seeded | Library + My Game levels are the seed; needs save states, naming, sharing |
| Session shape | 🟡 partial | Win/lose screens exist; needs instant Restart button, best-time/score memory (localStorage) |

## The plan (each step is small, all runtime-template work — no GPU needed)

- **R-A "Juice pack"**: pickup burst particles, player hit flash + brief
  screenshake, floating "+1" on collect, race position pops. (template only)
- **R-B "Score & medals"**: every game gets a score (time for races, collect
  streaks, kills) + bronze/silver/gold thresholds on the win screen +
  best-score memory in localStorage. Instant Restart button on win/lose.
- **R-C "Ownership"**: name-your-save, per-game best times shown on the
  START overlay ("your best: 1:42"), one-click share/export zip (exists).
- **R-D "Marketplace readiness"**: the asset library + heading/orientation
  facts + Git LFS already form the technical seed. What sales need: game
  thumbnails, a title screen with author credit, and the community section.

- **R-ITER "Edit this game"** (benchmark response, high priority): a follow-up
  prompt box on a built game patches the existing GameSpec via the LLM and
  re-exports — deterministic assembly + cached assets means edits land in
  seconds. This is the single feature that closes the gap with Summer Engine's
  conversational loop, and our architecture is already shaped for it.

Order matters: A and B make every game *feel* finished; C makes it *theirs*;
D makes it *sellable*; ITER makes it *craftable* — the difference between a
generator and an engine. Video side rides along — R-A's particle recipes and
score-overlay typography become title-card and HUD polish in film exports
(shared-enhancement rule).

## Competitive benchmark: Summer Engine (summerengine.com)

The closest quality competitor on the game side: an AI-native layer over
Godot 4 that turns a prompt into a real engine project (scene tree, GDScript,
art, audio) and — their defining feature — lets every FOLLOW-UP prompt edit
the SAME project conversationally. Free desktop app, cloud AI for heavy
generation, exports everywhere with full ownership.

**Where they beat us today, and the counter for each:**

| Their edge | Our counter (woven into the plan) |
|---|---|
| Conversational iteration on one game | **R-ITER (new, jumps the queue)**: keep the GameSpec, feed follow-up prompts as SPEC DELTAS ("add a boss" → LLM patches entities; "make it night" → sky field) and re-export. Our exports are deterministic and assets are cached, so an edit rebuilds in SECONDS — we can out-iterate a cloud round-trip. |
| Generated music + sfx | Synth sfx landed (R-A). Music: procedural WebAudio ambient loops now; local MusicGen-class model on GPU day. |
| Real-engine project output | We already have a Godot 4 exporter (Phase 28) — promote it from adapter to first-class "own your project" story. |
| Arbitrary mechanics via generated scripts | Their flexibility is unverified (broken scripts ship). Ours is a verified verb library — narrower but never broken. Path: grow verbs, then LLM-authored "mechanic modules" that must pass the headless play-probe before shipping. Reliability IS the quality difference users feel. |
| 2D games | Out of scope near-term; our wedge is 3D worlds + the video twin. |

**Where we beat them (press these):** 100% local generation (their AI is
cloud); one prompt drives BOTH a game and a film from the same asset library;
real mocap gaits; real-city OSM maps; verified asset pipeline (orientation
gates, play-probes) so outputs work every time; browser-playable zero-install
exports.

## Marketplace infrastructure (how sharing actually works)

The product is local-first; the *community* cannot be. Sharing needs a small
always-on service — but we get there in three honest steps, each shippable:

1. **Bundles (no server, works today).** Everything shareable is already a
   file: assets are GLB + reference PNG + heading-fact, games are
   self-contained `dist/` zips, videos are MP4s. Step 1 is an export/import
   bundle format (`.fsbundle` = zip + manifest.json with kind, pattern,
   heights, license, author) and an "Import bundle" button. Users share via
   Discord/itch/anywhere. Zero infra, and it forces us to define the manifest
   the marketplace will need anyway.
2. **Community registry (one small API).** A hosted FastAPI + object storage
   (S3-compatible) service: upload bundle, browse/search, download. The
   desktop app polls it for the "community feels alive" feed (new this week,
   trending). The app stays fully functional offline — the registry is
   additive, never required. Auth starts as simple accounts; payments later
   via a storefront layer (Stripe or itch-style) once moderation exists.
3. **Live presence (later).** Comments, ratings, creator pages, revenue
   share. Only after 1–2 prove demand.

Key principle: the local library IS the marketplace's unit of exchange. The
orientation gate + heading facts + license manifest mean a downloaded asset
drops into anyone's library and just works — that's the moat.

## Parity rules (so no side falls behind)

- Every game-feel feature maps to a video twin: juice particles → title-card
  and collectible glints in films; score typography → film HUD/lower-thirds;
  personal bests → per-project render history. Frontend surfaces each new
  capability the same week it lands in the pipeline.

## Depth & breadth strategy (decided 2026-07-07)

Benchmarks calibrated against Rosebud AI as well as Summer Engine. Rosebud's
model: the LLM writes arbitrary game code — maximum genre breadth, no
verification gate, so a large share of creations are broken. Decisions:

1. **Never adopt free codegen.** Our identity is "it always works." Breadth
   comes from **grammar expansion** instead: each new deterministic element
   (jump/platform controller, switches/doors/keys, enemy waves, checkpoints/
   laps) multiplies the composable game space while every output still passes
   the gates. Cadence: ~one archetype per round alongside distribution work.
2. **Depth ceiling is the Godot off-ramp, not our engine.** Hours-long
   complex games are Godot/Unity territory; our story is "fastest on-ramp to
   game-making, with a real off-ramp to Godot." Target: 15–30 min games with
   real arcs via missions + narrative + grammar, not 10-hour epics.
3. **Perceived quality beats mechanic count.** The ladder that closes the
   Rosebud gap: sound ✅ → juice ✅ → medals/replay hooks ✅ → **narrative
   layer ✅ (2026-07-07: LLM-written intro + win_text — content, not code,
   can't break a build)** → adaptive performance ✅ (fps governor sheds
   resolution → bloom → shadow updates; no more lag on weak iGPUs) →
   grammar expansion (next).
4. **Distribution before depth.** "Made with Fantasy Studio" stamp ships in
   every export (START screen + persistent corner badge — the game IS the
   ad). Next: shareable links (bundles → registry per the marketplace
   ladder), touch controls audit for phone players (stick + attack button
   exist; verify on real mobile), showcase set.
5. **Future option, parked:** LLM-authored behavior scripts in a tiny
   sandboxed DSL, statically checked by the verify gate — Rosebud-ish
   expressiveness inside our safety model. Revisit after the marketplace.

## What we deliberately do NOT copy

Top sellers also succeed via multiplayer, live-ops, and content treadmills.
Those are platform businesses, not generator features — out of scope until
the community marketplace exists. Single-player "one more run" polish is the
highest leverage per line of code today.
