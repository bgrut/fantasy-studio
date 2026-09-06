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

## Next

- Smelter (2 crystal -> 1 ingot) so the belt has a REASON beyond distance
- Splitter / merger, the first real routing puzzle
- Upgrade tree: tick rate, belt speed, miner yield
- Save/load, then the Steam packaging path from the brief
