# Performance pass

Measured on 2026-09-17 with `backend/tools/shotgate/perfpass.mjs`: headless Chrome on the d3d11 ANGLE backend,
frame-rate limit off, 1280 by 760 at device pixel ratio 1, forty seconds a phase.

GPU: `ANGLE (NVIDIA, NVIDIA GeForce RTX 5070 Ti (0x00002C05) Direct3D11 vs_5_0 ps_5_0, D3D11)`

| phase | what | fps | p50 ms | p95 ms | worst ms | draw calls | triangles | occlusion | tier |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| fresh start | the starter line, first person | 243.1 | 4.1 | 5.1 | 300 | 102 | 52,970 | on | ultra |
| built factory | 299 belts and 16 machines | 216 | 4.6 | 5.7 | 10.4 | 130 | 153,186 | on | ultra |
| overhead | TAB, the planning screen | 178.5 | 5.6 | 6.8 | 11.2 | 234 | 161,736 | on | ultra |
| the works minute | sparks, seam waves, racing sweeps | 211 | 4.7 | 6 | 17.2 | 127 | 153,026 | on | ultra |
| no occlusion | the built factory, ?ao=0 | 252.8 | 3.9 | 4.9 | 80.9 | 96 | 151,146 | off | ultra |
| performance tier | the built factory, ?q=performance | 222.9 | 4.5 | 5.4 | 60.1 | 128 | 153,078 | on | performance |

The frame rate is raw throughput with the limit off; a player sees it capped at the display rate. The 95th-percentile frame time is the number that matters for smoothness: under 16.7 ms is a solid sixty.
## Reading

Written after the pass of 2026-09-17.

- **Nothing is close to the line.** The heaviest phase is the overhead at 178 fps with a 95th-percentile frame of 6.8 ms; a sixty-hertz frame is 16.7 ms. On this card the demo has roughly two and a half times the headroom it needs in its worst view.
- **The occlusion pass costs about 0.7 ms a frame** (built factory 4.6 ms at p50 against 3.9 ms without it) and 34 draw calls. It stays on: that is a twentieth of the budget for the contact shadow under every machine.
- **The overhead is the expensive view**, not the works' minute. Its 234 calls are the planning screen's rate labels and the full face of machines in one frustum. The works' minute adds particles, not draws.
- **The performance tier changes nothing here** because the pass runs at device pixel ratio 1 already; on a laptop at ratio 2 the tier halves the pixels drawn, which is where its saving is.
- **The worst frames are hitches, not load.** A 300 ms frame in the first phase and 80 ms after a reload are one-off stalls (shader compiles as the first machine of a kind appears, the first play of a sound), not a frame rate. A warm-up that touches every material during the reveal would take them out of play; noted for a later round.
