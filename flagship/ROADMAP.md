# Crystal Works / Voxel Forge — roadmap

Working notes on the five differentiators from the Voxel Forge brief, ordered
by *value per unit of risk* rather than by the order they were written. Each
one is judged on the same two questions: does it make a five-second video
someone stops scrolling for, and can it be built without destabilising what
already works.

Nothing here is a promise. Where I think an idea is weaker than it sounds, it
says so.

---

## Shipped

| | what it proves |
|---|---|
| grid + tick + belts | the loop: mine, move, deliver |
| first person | standing in a factory beats arranging one |
| smelter | belts solve "these must meet", not just "that is far" |
| splitter | routing becomes a decision, not a drawing |
| upgrades | the number climbs, and spending it makes it climb faster |
| **built by the studio** | a prompt produces this game, not a hand-run file |
| **multi-sided gravity grid** | the differentiator: belts and gravity wrap a cube |
| **prestige meltdown** | the factory is thrown into the sky for a permanent core |
| **three minerals + forge** | an alloy no single face can make: a reason to cross |
| **filter tile** | routing by ore type, configured from the crosshair |
| **market ticker** | the hub pays a live price, so what to make is a decision |
| **chronos rift** | borrowed ore on a clock, and a storm if you miss it |
| **studio inspect** | the factory answers the studio's picking bridge |
| **demo is generated** | the standalone build IS the studio's output |
| **save / load** | a factory survives closing the tab |
| **collision + fair mergers** | machines are solid; a merge stopped eating items |
| **progression frame** | goals unlock machines in the order that teaches them |
| **art pass** | conveyors that convey, icons in the bar, a sky to float in |
| **lighting pass** | bloom, a graded composite, particles, a lit silhouette |
| **grounding pass** | real cast shadows, contact shadows, curved belt corners |
| **material pass** | an environment to reflect, baked occlusion, rim light, detail |
| **UI pass** | tool icons that ARE the machines, rendered at boot |
| **presence pass** | a tool in your hands, jams that read, seams that flex, one HUD |
| **depletion** | seams thin under a rig and grow back, so placement is a decision |
| **the reveal** | the worldlet shown before control is handed over; again on arrival |
| **weather** | ash on Ember, snow on Frostline, spores on Verdant, dust at home |
| **sound** | six synthesised layers, no assets; wakes on the first click, M mutes |
| **the panel** | read by shape: a hero number, a sparkline, icon chips, bars, pips |
| **the world, finished** | the meltdown pulls to orbit; hubs carry the price board; each world has its own ground |
| **refinements** | prices read from a 1.0 baseline; belts belong to their world; a title with weight; idle motion |
| **the prompt's mood** | world zero reads its own words when no palette was committed; unlocks are the families home is not |
| **unlockable worlds** | four places to put the factory, bought with cores |
| **the chain, twelve deep** | rates are HELD, not reached; rewards are machines, caps, or capabilities, derived from the tier on load |
| **capabilities** | Frostline needs the heated drill, Verdant the spore scrubber, the Drift the whole chain; cores only buy the trip |
| **creative** | chosen at world creation (`?creative=1`, or "new world"); its own save; all open, free, nothing runs out |
| **spores** | Verdant's pressure: an unfiltered belt clogs every few seconds; a filter within 3 tiles shields the belts around it |
| **the machine skin** | one shared panel map (seams, rivets, wear) on every machine; glow moved to the lamps; the sun made the key |
| **the companion** | a planet or moon in every sky, cratered or banded by hash noise, lit from the sun's side, drawn in the sky shader |
| **lanes** | every fifth grid line is a lit strip in the world's edge colour, one instanced mesh for six faces |
| **seams are lights** | each seam owns its glow: a dark-glass body, an additive core and a pool on the ground that all follow its richness |
| **items** | ore is a two-crystal chunk that spins; a refined product is a chamfered, stamped, metallic bar lying flat along its belt; the glow follows the instance colour |
| **particles** | smoke has a seeded lobed edge and dims as it swells; sparks carry a gravity along their face, arc, and cool white to red |
| **frames, finished** | the forge, splitter and filter get the cap, posts, bands and lips the smelter, rig and hub got |
| **the ghost is the machine** | the placement preview is the machine's own silhouette with a lit edge, green where it can go and red where it cannot |
| **lamps light the ground** | every lit lamp pools its light on the deck: orange under a cooking smelter, pink under a forge, gold breathing under a hub, the ore's colour under an open rift |
| **worlds show their sky** | each world row carries a swatch of its sky and edge colour; locked rows are dimmer places |
| **the grade** | a lift / gamma / gain curve and a saturation per mood in the composite, so the same furnace reads as a different object on each world |
| **the handover** | the reveal eases position and orientation into the first-person pose over its last fifth instead of cutting |
| **sound for the light** | a rig ticks per crystal pitched by the ore, a smelter clanks as an ingot leaves, a spore strike thuds; all throttled |
| **shadows that reach** | the contact ramp holds to a tile out and the decals are a fifth wider, so an unlit face grounds its machines at any grid size |
| **a palette that agrees** | a committed palette's sky and fog win only when they belong to the prompt's own family; the mood's win otherwise |
| **weight** | the body lags the intent: the camera leans into starts and out of stops, dips on a landing by how hard it was, and rolls an edge crossing with weight |
| **ambience** | a second layer in the air per family: motes in the light at home, embers off the cinder, breath on the ice, fireflies over the green |
| **the overhead** | TAB opens over the face you stand on with your heading up the screen; the tread glows and every machine pools its colour, a city at night |
| **machine skin** | one shared panel map (seams, rivets, a lip, wear) on every machine; glow moved from the paint to the lamps; sun made the key (3.1 over 0.95 hemi / 0.85 fill); a frame on the smelter |
| **the companion** | a planet or moon low in every world's sky, shaded from the sun's side with a terminator and an atmosphere rim, drawn in the sky shader; one fixed direction so it is a landmark |
| **lanes** | every fifth grid line is a faint lit strip in the world's edge colour; the far plane widened to 1400 so the sky dome no longer clips from orbit |
| **the starter line always exists** | seedLine grows a seam at the head of the first clear run when the scatter left none; `?grid=` and `?seed=` debug overrides let a gate prove it by size |
| **factory reads as factory** | the pipeline holds prompts that name a production system to the factory genre, deterministically, before the 25-minute hero path can start |

Measured on a prompt-built export: 40x40x6 grid, 40 nodes, 180 value/min,
9 ingots in 12s, 18 draw calls, no console errors. The player walks top ->
south with up [0,0,-1] and never leaves the surface; a crystal on a belt at
the top face's edge arrives on the next face. 19/19 cube-grid properties pass
against an extract of the shipping template, not against the library copy.

---

## ~~1. Multi-sided gravity grid~~ — SHIPPED 2026-09-07

Walk over the edge of a floating cube and the world rotates under you; belts
wrap around the corner and keep running.

**Why it is first on merit:** it is the only item on the list that is both
genuinely novel in this genre AND immediately legible in a silent five-second
video. Satisfactory and Foundry are flat-ground games. Shapez is a detached
top-down board. A first-person camera tumbling around the underside of a
planetoid is the whole viral funnel in one shot.

**Why it is expensive:** the simulation is currently a 2D array. Faces need
their own coordinate frames, `getAdjacentTile` has to resolve across an edge
into a different frame with a different up-vector, and every belt matrix needs
re-basing. This is not a feature bolted on; it replaces the spatial core.

**Sequencing:** build it against the *existing* mechanics before adding more.
Porting one face's worth of belts and smelters is a week; porting five
mechanics' worth afterwards is a month.

**What it actually cost:** the simulation no longer knows the shape of the
world — it asks `stepTile` what is next to a tile, and that is the only place
an edge exists. Everything that stands on the surface goes through one seating
rule, so a belt arrow, a smelter and the build ghost cannot disagree about
which way is up. Three bugs, none of which threw an error: a two-pass edge
loop that crossed and immediately crossed back (the re-seat has to happen
*inside* the loop), a spawn offset the wrong way along the face's v axis that
pinned the player to the clamp so W did nothing at all, and a Tab orbit framed
for a flat island that sat *inside* the worldlet.

## ~~2. Prestige meltdown~~ — SHIPPED 2026-09-07

Pause the sim, convert every instance matrix into a particle with outward
velocity and gravity, collapse the factory, award tokens.

We already have the two hard parts: everything is in `InstancedMesh` (so the
transforms are already in one buffer) and the engine side of this project has
shipped physics-driven destruction before. Mostly a render-mode switch. High
spectacle, low structural risk. Good candidate to do *alongside* item 1.

**As built:** machines are not deleted, they are thrown — each build group is
detached, given an outward velocity and a tumble, and pulled back by the
worldlet so it arcs rather than simply leaving. Cores multiply everything the
hub banks by 45% each, which has to be steep enough that melting a good
factory beats keeping it or the prestige is a button nobody presses twice.
Two timing bugs worth remembering: the first pass threw debris at 9-25 m/s and
the whole factory left the frame inside 300ms, and re-seeding the starter line
inside `meltdown()` meant the collapse and the rebuild were the same frame, so
neither read. The replacement line now arrives when the old one has landed.

## ~~3. Galactic market ticker~~ — SHIPPED 2026-09-07

A random-walk price per product, and a launch pad that sells at the live rate.

Small to build. Its real value is not the spectacle — it is that it gives the
player a *reason to choose what to produce*, which is the thing a one-recipe
factory currently lacks. Pairs naturally with more recipes.

**As built:** four traded goods (three ingots and the alloy) on a mean-reverting
random walk between 0.55 and 1.85, and the hub pays the live rate. Mean
reversion matters more than it sounds: without it a long session parks every
price against a rail and the market quietly switches itself off. Raw ore always
sells at base, so the market rewards refining rather than hoarding.

The three mechanics now close a loop: the market says which good is worth
making, the filter is how you re-route production to make it, and the forge
means the best-paying good may need ore from a face you have not built on yet.

## ~~4. Scriptable logic belts~~ — SHIPPED 2026-09-07, as a filter tile

Route items by rule: `if (item.purity > 80) OUTPUT_A else OUTPUT_B`.

The brief's market read is right — there is a real gap for a logic/programming
factory game, and Shapez players are exactly that audience. But shipping a
`eval`-style script box first is a mistake:

- an arbitrary-code text field is a security and save-corruption problem the
  moment anyone shares a factory blueprint
- typing JavaScript into a first-person game breaks the immersion this build
  just spent its time earning
- most players bounce off a blank text box

Better shape: a **filter/condition tile** the player configures from a short
menu (by item type, then later by a property). Same decision space, no parser,
no immersion break. A raw script mode can come later for the audience that
wants it, once there are properties worth branching on.

**As built:** point at a filter, press F, and the gate on it changes colour to
whichever ore now passes — the setting is readable from across the face rather
than from a tooltip. Matching ore carries straight on, everything else leaves
out of the side. It deliberately does NOT fall back to the other output when
the chosen one is full: an item that takes the wrong exit because the right one
was busy is a filter that has silently stopped filtering, and the player would
have no way to see it happen. Shipped after the minerals, not before, because
a filter with one item type to sort is a belt.

Also fixed on the way: items sitting on a splitter were never drawn at all, so
a backed-up splitter looked empty.

## ~~5. Chronos paradox loop~~ — SHIPPED 2026-09-07, as a debt with a clock

Buffer 10s of item history, replay it as ghosts, and storm if the player
cannot repay the exact items in time.

The most complex item on the list and the least legible. It needs several
systems that do not exist yet (item identity over time, a debt ledger, a
failure state with area effects) and its appeal is hard to read in a video —
"ghost ore you must repay" takes a paragraph to explain, which is the opposite
of the funnel.

Not a bad idea; a bad *early* idea. Revisit once there are properties, filters
and a market, because it needs all three to mean anything.

**As built, once those three existed:** the debt is the good idea; the ghosts
are the part that takes a paragraph to explain, which is the opposite of the
funnel. So a rift lends you six of whichever ore the market currently pays most
for, pays the loan out onto your belts one tile at a time like a miner, and
puts the amount and the deadline on the HUD. Feed it back through the same ring
and it settles at a premium. Miss the deadline and it throws every machine
within three tiles into the sky — the meltdown's debris path, aimed at you
rather than chosen by you. It only accepts back exactly what it lent, which is
what makes the filter tile the instrument for repaying one.

One fairness bug worth remembering: the countdown originally started when the
rift opened, so a rift whose output belt was blocked demanded repayment of ore
it had never handed over, then blew up the factory for not returning it. The
clock starts when the loan lands.

---

## Suggested order

1. ~~Multi-sided gravity grid~~ — shipped
2. ~~Prestige meltdown~~ — shipped
3. ~~Filter tile~~ and ~~more recipes~~ — shipped
4. ~~Market ticker~~ — shipped
5. ~~Chronos~~ — shipped, as a debt with a clock rather than replayed ghosts

All five differentiators from the brief are in, and the factory now saves.
What is left is the Tauri/Steam packaging path.

## Worlds

Cores were a multiplier and nothing else, so prestige was a number going up. A
world is the other half of the trade — melt the factory down enough times and
somewhere new opens, which gives the meltdown a destination.

| world | cores | needs |
|---|---|---|
| whatever the prompt asked for | 0 | — |
| the first family home is not | 2 | — (warm) / heated drill (cold) / spore scrubber (green) |
| the second | 5 | same rule, by family |
| The Long Drift (void) | 3 | the whole chain walked |

The three unlockables are the families the home world is not, so a warm prompt
offers frost, verdant and the drift. Cores buy the trip; the capability makes
it survivable, and the chain hands the capabilities out.

Deliberately DATA: a world is a row of sky, fog, ground, grid, stars and a
price, so adding one is an edit to that table and nothing else. Ore colours are
excluded on purpose — they are how a belt is read at a glance, and re-learning
them per world would be a tax on travelling.

The progression chain, for reference — ordered so each unlock lands when the
previous one has made it mean something, and so that finding the cube is a
goal rather than a hope:

| tier | goal | reward |
|---|---|---|
| 1 | bank 40 value | SPLITTER |
| 2 | hold 400 a minute for 20s | OVERCLOCK cap 8 |
| 3 | stand on a second face | FORGE |
| 4 | forge one alloy | FILTER |
| 5 | run three rigs on three seams | RICH SEAMS cap 8 |
| 6 | hold 1200 a minute for 30s | CHRONOS RIFT |
| 7 | sell an alloy above 1.20 | HOT FURNACE cap 6 |
| 8 | bank 400 value | MELTDOWN |
| 9 | earn a core | HEATED DRILL (Frostline opens) |
| 10 | hold 3000 a minute for 30s | SPORE SCRUBBER (Verdant opens) |
| 11 | repay a rift | STABLE RIFT (cores worth a quarter more) |
| 12 | reach three cores | THE LONG DRIFT opens |

A rate goal's timer runs only while the rate is at or over the target and
resets the instant it is not: the starter line alone earns ~210/min at level
zero, so 120 would have been a total wearing a costume. Rewards are never
saved — `applyRewards()` re-derives caps and capabilities from the tier index
on every load, so an old save cannot carry a stale cap.

## Checking both at once

The demo is generated from the studio runtime, so they can only disagree if the
generator was not re-run. One command checks that and then runs all four gates
against each:

    cd flagship && python -m http.server 8790     # serve the demo
    python backend/tools/factory_check.py --job <id>

### Materials

Three things that are not more polygons and matter more than polygons:

- **An environment to reflect.** metalness with no environment map makes a
  surface DARKER, not shinier — raising it on the ground plating turned the
  floor black. A PMREM built from a two-stop gradient (an HDRI would be a
  megabyte of asset for a look three colours wide) fixed that and turned out to
  be the single biggest lighting upgrade available: every standard material
  gets a soft directional bounce instead of flat lambert. Tinted per world, so
  a red planet does not have neutral grey machines standing on it.
- **Baked occlusion.** Machines are merged into one geometry at boot, which is
  the moment to write an occlusion ramp into their vertex colours — dark where
  they meet the ground and under downward faces. Plus a per-part tint, so one
  material carries a recessed door, a plinth and a panel without a second draw
  call.
- **A rim light**, a fresnel pushed into emissive so the bloom outlines every
  machine. Use `normal`, never `vNormal`: a flatShading material has no vNormal
  varying, so referencing it fails to compile on exactly the materials most
  likely to be flat shaded.

### Rendering

The post pipeline is written by hand rather than pulled from three's addons —
the standalone demo vendors exactly one file and keeping it that way means the
demo cannot break in a way the studio build does not. Scene into a target,
bright pass, two blur pairs, then a composite that adds the bloom in linear
light, tone maps, tints the shadows toward the world's own fog colour and
closes a vignette.

The second trap, in the same family: a directional light's shadow camera sits
AT the light looking at its target, so anything farther from the target than
the light is behind the camera and casts nothing. The sun was 58 units out on a
world whose corners are at 69 — measured, ground luminance across a smelter's
base read 109/110/110/110/106, perfectly flat. Every distance in the light rig
is a multiple of HALF now.

Even fixed, one directional light only shadows three of six faces, so every
machine also carries a contact shadow of its own. It is tuned against the real
one: the first version darkened a quarter as much, which left a machine on the
underside floating next to an identical machine on top that did not.

The first trap: three applies tone mapping and sRGB encoding **only
when rendering to the canvas**. Render into a target and you get raw linear
values, and compositing those straight to the screen produces a nearly black
world that looks exactly like a lighting bug and is not one. The art gate now
reads a floor pixel and asserts it is lit.

Twelve gates, run against each — the three newest cover depletion, the
reveal/weather/sound beat, and grounding.

The bug this file keeps producing, so it is written down: a `const` or `let`
declared after a hoisted function that touches it AT BOOT. `scatterSpots`,
`AUDIO`, and the intro clock all threw a temporal-dead-zone error the first
time — each because something that runs during the starter-line seed or the
first render reached forward. Everything a boot-time path touches now lives in
one block near the top, next to the scene handles.

Nine gates, run against each: the core loop and cube walk, the rift, the studio
inspect bridge, save/load, collision and merge losslessness, the goal chain, the
art (icons, instancing, a scrolling tread, a drawn sky), a draw-call budget for
a 250-machine factory, and world unlocking.

## Also outstanding

- Art uplift — placeholder boxes; the Kenney space kit (already vendored in
  `backend/assets/props`, CC0) is the right visual language for this
- Levels / progression frame: goals, unlocks, a reason to expand
- Steam packaging path (Tauri), per the brief
