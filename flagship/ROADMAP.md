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

## 3. Galactic market ticker — **cheap, and it earns its keep**

A random-walk price per product, and a launch pad that sells at the live rate.

Small to build. Its real value is not the spectacle — it is that it gives the
player a *reason to choose what to produce*, which is the thing a one-recipe
factory currently lacks. Pairs naturally with more recipes.

## 4. Scriptable logic belts — **strong idea, wrong first implementation**

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

## 5. Chronos paradox loop — **park it**

Buffer 10s of item history, replay it as ghosts, and storm if the player
cannot repay the exact items in time.

The most complex item on the list and the least legible. It needs several
systems that do not exist yet (item identity over time, a debt ledger, a
failure state with area effects) and its appeal is hard to read in a video —
"ghost ore you must repay" takes a paragraph to explain, which is the opposite
of the funnel.

Not a bad idea; a bad *early* idea. Revisit once there are properties, filters
and a market, because it needs all three to mean anything.

---

## Suggested order

1. ~~Multi-sided gravity grid~~ — shipped
2. ~~Prestige meltdown~~ — shipped
3. **Filter tile** (item 4, done without a parser) + more recipes
4. **Market ticker** — gives the recipes a reason to differ
5. Revisit **Chronos** only if 3 and 4 give it something to bite on

## Also outstanding

- Merger fairness: two belts into one currently resolve by grid order
- Nothing on the five new faces yet: the cube is walkable and belts wrap, but
  the game gives no reason to go there. Ore density per face, or a recipe that
  only exists on one side, is the cheapest fix
- The player walks through machines; there is no collision
- Save / load
- Art uplift — placeholder boxes; the Kenney space kit (already vendored in
  `backend/assets/props`, CC0) is the right visual language for this
- Levels / progression frame: goals, unlocks, a reason to expand
- Steam packaging path (Tauri), per the brief
