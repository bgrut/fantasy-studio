# Crystal Works — 3D incremental automation

Flagship demo. Runs standalone in a browser; no build step.

    cd flagship && python -m http.server 8123
    open http://127.0.0.1:8123/

## This directory is GENERATED

`factory.js` and `index.html` are built from the studio's own factory runtime:

    python backend/tools/flagship_build.py          # rewrite the demo
    python backend/tools/flagship_build.py --check  # fail if it is stale

Do not edit them — edit
`backend/app/game_export/runtime/factory.js.tpl` and re-run the builder.

The demo used to be its own file, and within a week of the cube grid, the
meltdown, the minerals, the filter and the market landing in the studio it was
601 lines behind with nobody noticing. Keeping two copies "in parallel" is a
discipline, and disciplines lapse. This way a feature cannot exist in one and
not the other, because there is only one source — and the demo doubles as the
honest proof of the claim on the box: what you play here IS what a prompt
produces. Both are run against the same gate
(`backend/tools/shotgate/fact.mjs`, `URL=` to point it at either).

## What is proven

The core conversion the genre lives on: manual clicking becomes a machine that
runs without you. Mine, move, deliver, watch the number climb.

Measured in a headless browser: 1 miner, 5 belts, a hub, ore 0 -> 11 in nine
seconds at 120/minute, 3 items in transit, 60fps, no runtime errors.

## Shape

- `cells[x][z]` is the whole simulation. Type, direction, and at most one item.
- A tick collects every legal move FIRST and commits after. Moving in place
  would let one item ride an entire belt line in a single tick, depending on
  iteration order.
- Items on belts are not meshes. One `InstancedMesh` carries every crystal in
  the world; the frame writes matrices into it. A thousand items on a hundred
  belts is one draw call.
- Items render BETWEEN their tile and the next, interpolated on the tick
  fraction, so discrete grid motion reads as smooth travel — and a blocked
  item sits still, which is what makes a jam legible.
- Miners may only stand on crystal nodes. Scarcity is the whole reason belts
  exist; without it you would just put a miner on the hub.

## Controls

    WASD          walk        Shift  run        Space  jump
    click         lock the pointer / look
    hold LMB      sweep your view to draw a belt line
    1..6          miner / belt / smelter / splitter / hub / erase
    TAB           overhead build view (routing a junction from eye level is
                  genuinely worse than seeing it from above)

## Recipes

    miner    on a crystal node only        1 crystal per tick
    smelter  2 crystals -> 1 ingot         3 ticks to cook
    splitter accepts from any side        sends each item out a different
                                          side in turn
    hub      banks anything                crystal 1, ingot 6

Node scarcity is why belts exist. The recipe is why belts have to MEET
somewhere rather than just run to the hub.

## Upgrades

    Z  OVERCLOCK     everything runs faster    6 levels
    X  RICH SEAMS    crystals worth more       6 levels
    C  HOT FURNACE   smelters cook quicker     4 levels

Costs scale 2.3-2.8x per level. Buttons light up the moment you can afford
them, because watching the number cross a threshold IS the loop.

## Next

See ROADMAP.md for the Voxel Forge differentiators, ordered by value per unit
of risk rather than by the order they were written.

- Merger fairness (two belts into one currently resolve by grid order)
- Upgrade tree: tick rate, belt speed, miner yield
- Save/load, then the Steam packaging path from the brief
