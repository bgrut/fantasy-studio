# Performance pass

Measured on 2026-09-18 with `backend/tools/shotgate/perfpass.mjs`: headless Chrome on the d3d11 ANGLE backend,
frame-rate limit off, 1280 by 760 at device pixel ratio 1, forty seconds a phase.

GPU: `ANGLE (NVIDIA, NVIDIA GeForce RTX 5070 Ti (0x00002C05) Direct3D11 vs_5_0 ps_5_0, D3D11)`

| phase | what | fps | p50 ms | p95 ms | worst ms | draw calls | triangles | occlusion | tier |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| fresh start | the starter line, first person | 365.3 | 2.6 | 4 | 8.8 | 101 | 52,902 | on | ultra |
| built factory | 299 belts and 16 machines | 333.4 | 2.8 | 4.3 | 8.5 | 128 | 153,078 | on | ultra |
| overhead | TAB, the planning screen | 286.3 | 3.2 | 4.9 | 10.4 | 233 | 161,736 | on | ultra |
| the works minute | sparks, seam waves, racing sweeps | 230.2 | 4.5 | 5.6 | 12.4 | 128 | 153,078 | on | ultra |
| no occlusion | the built factory, ?ao=0 | 252.1 | 4 | 4.9 | 10.3 | 97 | 151,198 | off | ultra |
| performance tier | the built factory, ?q=performance | 219.9 | 4.5 | 5.4 | 10.8 | 127 | 153,026 | on | performance |

The frame rate is raw throughput with the limit off; a player sees it capped at the display rate. The 95th-percentile frame time is the number that matters for smoothness: under 16.7 ms is a solid sixty.
## Reading

Written after the pass of 2026-09-18, the second pass, with the warm-up in place.

- **Nothing is close to the line.** The slowest phase is the performance tier at 220 fps with a 95th-percentile frame of 5.4 ms; a sixty-hertz frame is 16.7 ms. The heaviest view by draw calls is the overhead at 233 calls, and it runs at 286 fps.
- **The worst frame in any phase is 12.4 ms.** The first pass had a 300 ms frame at the first sale and 60 to 80 ms after each reload. Tracing found the main thread blocked on a buffer update while the GPU process ran a 350 ms task: on the d3d11 backend the driver builds a shader's executable at its first draw, per program and per vertex layout, and every GL command waits behind it. renderer.compile links programs but does not draw, so it did not help. The warm-up now draws every geometry with every material once at boot, everything visible and unculled, into an eight-pixel target under the reveal. backend/tools/shotgate/fhitch.mjs proves the window across the first sale and the first flight on every check; the probes that found it (hitchprobe, hitchmode, hitchtrace2, hitchgl) stay beside the gates.
- **The occlusion pass has no measurable cost at this resolution.** The phase without it is not faster than the built factory with it; the difference between phases is smaller than the card's own clock changes between phases. It stays on.
- **The performance tier changes nothing here** because the pass runs at device pixel ratio 1 already; on a laptop at ratio 2 the tier halves the pixels drawn, which is where its saving is.
- **Pass to pass, the numbers move by a third** (the fresh start read 243 fps on the first pass and 365 on the second) as the card's clocks settle, so compare phases within one pass and trust the frame-time percentiles more than the averages.
