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

Order matters: A and B make every game *feel* finished; C makes it *theirs*;
D makes it *sellable*. Video side rides along — R-A's particle recipes and
score-overlay typography become title-card and HUD polish in film exports
(shared-enhancement rule).

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

## What we deliberately do NOT copy

Top sellers also succeed via multiplayer, live-ops, and content treadmills.
Those are platform businesses, not generator features — out of scope until
the community marketplace exists. Single-player "one more run" polish is the
highest leverage per line of code today.
