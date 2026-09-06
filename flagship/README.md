# Crystal Works — 3D incremental automation

Flagship prototype. Runs standalone in a browser; no build step.

    cd flagship && python -m http.server 8123
    open http://127.0.0.1:8123/

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
    1 2 3 4 5     miner / belt / smelter / hub / erase
    TAB           overhead build view (routing a junction from eye level is
                  genuinely worse than seeing it from above)

## Recipes

    miner    on a crystal node only        1 crystal per tick
    smelter  2 crystals -> 1 ingot         3 ticks to cook
    hub      banks anything                crystal 1, ingot 6

Node scarcity is why belts exist. The recipe is why belts have to MEET
somewhere rather than just run to the hub.

## Next

- Splitter / merger, the first real routing puzzle
- Upgrade tree: tick rate, belt speed, miner yield
- Save/load, then the Steam packaging path from the brief
