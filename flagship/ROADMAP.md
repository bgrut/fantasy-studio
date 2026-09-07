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

Measured: ~960 value/min after three upgrades, 60fps, no runtime errors.

---

## 1. Multi-sided gravity grid — **the differentiator, and the hard one**

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

## 2. Prestige meltdown — **cheapest viral moment on the list**

Pause the sim, convert every instance matrix into a particle with outward
velocity and gravity, collapse the factory, award tokens.

We already have the two hard parts: everything is in `InstancedMesh` (so the
transforms are already in one buffer) and the engine side of this project has
shipped physics-driven destruction before. Mostly a render-mode switch. High
spectacle, low structural risk. Good candidate to do *alongside* item 1.

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

1. **Multi-sided gravity grid** while the mechanic count is still low
2. **Prestige meltdown** — spectacle, and it reuses the instance buffers
3. **Filter tile** (item 4, done without a parser) + more recipes
4. **Market ticker** — gives the recipes a reason to differ
5. Revisit **Chronos** only if 3 and 4 give it something to bite on

## Also outstanding

- Merger fairness: two belts into one currently resolve by grid order
- Save / load
- Art uplift — placeholder boxes; the Kenney space kit (already vendored in
  `backend/assets/props`, CC0) is the right visual language for this
- Levels / progression frame: goals, unlocks, a reason to expand
- Steam packaging path (Tauri), per the brief
