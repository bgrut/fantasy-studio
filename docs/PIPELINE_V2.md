# Pipeline V2 — Prompt → Photoreal 3D Video (current engine)

> **This document describes the current production pipeline (Phase 17–22, June 2026).**
> It supersedes the V1.x recipe/template system described in the original README sections,
> which remains as the procedural fallback path.

One sentence in — *"a red ferrari driving on a road"*, *"a samurai warrior standing"*,
*"an orange tabby cat walking"* — and Fantasy Studio produces a photoreal, textured,
animated 3D scene rendered to MP4. Fully local, fully commercial-safe.

## The nine stages

```
user prompt
   │
   ▼
1. SLOT EXTRACTION        Ollama LLM (gemma3/qwen3) → structured scene JSON
   │                      subject (pattern, identity_phrase, color…), scene, motion, camera
   │                      Deterministic keyword fallback if the LLM is unavailable.
   ▼
2. REFERENCE IMAGE        SDXL Base 1.0 + ControlNet-depth pose lock → clean studio
   │                      shot of the subject. identity_phrase keeps the user's exact
   │                      wording (brands/roles/styles) so a samurai is a SAMURAI.
   ▼
3. IMAGE → 3D             TRELLIS.2-4B (default since the 4/4 A/B sweep) → natively
   │                      TEXTURED GLB. Fallback chain: TripoSG → TripoSR → InstantMesh.
   │                      Each engine runs in its own isolated venv as a subprocess
   │                      (PNG in → GLB out) to avoid dependency conflicts.
   ▼
4. MESH HYGIENE           Weld-aware connected-component filter (glTF UV-seam splits
   │                      are virtually welded by quantized position) + valence-guarded
   │                      density prune — kills remesh "string" shards without punching
   │                      holes in smooth body panels.
   ▼
5. ORIENTATION GATE       Azimuth-normalize (long horizontal → Y, baked), then
   │                      silhouette-IoU against the reference over a restricted flip
   │                      set. Vehicles add wheels-down + paint-side-up texture checks.
   ▼
6. RIG + MOTION           Motion archetypes:
   │                        • legged (quadruped/biped): auto-detected skeleton, manual
   │                          nearest-bone weights, keyframed gait cycles that loop for
   │                          the full clip length
   │                        • wheeled: rigid drive + camera tracking (+wheel spin on
   │                          procedural bodies)
   │                        • celestial spin, idle breathing
   ▼
7. ENVIRONMENT            Setting-driven: OpenStreetMap city extrusion (procedural
   │                      day/night facades), AWS Terrain Tiles DEM landscapes, or the
   │                      preset library (sky/ground/mood).
   ▼
8. LIGHT + CAMERA         Framing from the real mesh bbox; key sun azimuth aligned to
   │                      the camera (subjects show their lit side); brightness floor +
   │                      exposure for PBR-textured heroes.
   ▼
9. RENDER + ENCODE        Headless Blender 5.1 (EEVEE/Cycles) over a local socket
                          bridge → PNG frames → ffmpeg MP4.
```

## Quality gates

| Gate | Catches |
|---|---|
| Silhouette-IoU orientation (24-way for generic, restricted flips for canonical meshes) | upside-down / sideways meshes, per-asset |
| Wheels-down + paint-side-up (vehicles) | flipped cars that silhouettes can't distinguish |
| Weld-aware island filter + valence-guarded density prune | string shards, floaters — without surface holes |
| Texture color fidelity (non-TRELLIS path) | washed-out colors vs the reference |
| Brightness floor + camera-aligned key light | shadow-side, underexposed renders |
| Black-frame guard + bridge health checks | GPU-starvation render failures |

## Mesh engine A/B (why TRELLIS.2 is the default)

Same prompts through both engines, full pipeline, June 2026:

| Subject | TripoSG + projection | TRELLIS.2 native |
|---|---|---|
| Dog | flat clay toy | realistic tan coat, muscle shading |
| Cat | clay, visible seams | tabby fur gradient, white paws |
| Samurai | featureless mannequin | full armor, katana, face detail |
| Ferrari | blobby SUV-like mass | glossy supercar, chrome rims |

TRELLIS.2 won 4/4. TripoSG remains the automatic fallback.

## Code map

```
backend/
├── app/orchestrator/    ~6.3k lines — the brain
│   ├── slots.py              LLM slot extraction, identity_phrase, keyword fallback
│   ├── composer.py           40+ step deterministic scene assembly + all quality gates
│   ├── motion_rig.py         gait cycles, wheeled drive (motion archetypes)
│   ├── osm_city.py           OpenStreetMap → extruded city, procedural facades
│   ├── dem_terrain.py        AWS Terrain Tiles → real-world landscapes
│   └── procedural_vehicle.py parametric car + crisp wheel attachment
├── app/asset_gen/       SDXL reference (ControlNet pose templates) + engine chain
├── app/refinement/      SDXL img2img polish
├── app/mcp/             Blender socket bridge + tool registry
├── app/api/             FastAPI endpoints
├── scripts/             engine subprocesses, installers, E2E entry points
│   ├── render_from_prompt.py   ← the one-command entry point
│   └── inference_trellis2.py   TRELLIS.2 subprocess (license-safe preprocessing)
├── venv/                main env (SDXL, diffusers 0.20.x)
├── venv_triposg/        isolated TripoSG (torch cu128)
├── venv_trellis/        isolated TRELLIS.2 (torch nightly cu128, sdpa attention)
└── vendor/              TRELLIS.2, TripoSG, TripoSR, InstantMesh + Windows build patches
```

## Hardware & platform

- **GPU**: 16 GB VRAM (tested RTX 5070 Ti / Blackwell, CUDA 12.8). TRELLIS.2 runs
  sdpa attention — flash-attn not required.
- **OS**: Windows 11 (vendored CUDA extensions patched + built with MSVC `/permissive-`;
  Linux should work with upstream setup scripts).
- **Blender**: 5.1 headless via socket bridge.
- ~6 min per clip end-to-end (dominated by TRELLIS.2 pipeline cold load — persistent
  worker is on the roadmap).

## Env vars

| Variable | Default | Purpose |
|---|---|---|
| `FS_MESH_ENGINE` | `trellis2` | force an engine: `triposg`, `triposr`, `instantmesh` |
| `FS_TRELLIS_TEXSIZE` | `2048` | texture bake size (4096 = sharper, slower) |
| `FS_ORIENT_SILHOUETTE` | `1` | reference-anchored orientation gate |
| `FS_REFTEX` / `FS_TEXFIDELITY` | `1` | texture projection / color gate (non-TRELLIS engines) |
| `FS_CONTROLNET_SCALE` | `0.35` | reference pose-lock strength |
| `FS_PROCEDURAL_VEHICLE` | `1` | vehicle mode: `0` off, `pure` box car, `1` hybrid |

## Licensing & attribution (commercial-safe by construction)

| Component | License | Note |
|---|---|---|
| TRELLIS.2 (code + weights) | MIT | default mesh engine |
| TripoSG / TripoSR | MIT | fallbacks |
| SDXL Base 1.0 | CreativeML OpenRAIL++ | reference + refinement |
| DINOv3 encoder (Meta) | DINOv3 License — commercial permitted | **attribution required: "Built with DINOv3"** |
| rembg (u2net) | MIT / Apache-2.0 | replaces TRELLIS's bundled RMBG-2.0 (non-commercial → stubbed out) |
| OpenStreetMap data | ODbL | **attribution required: "© OpenStreetMap contributors"** |
| AWS Terrain Tiles | open | elevation data |
| Blender | GPL | rendered outputs unrestricted |
| Ollama models | open weights | slot extraction |

> Ship the two attribution lines in your product credits and everything you generate is yours to sell.

---

*Built with DINOv3 · Map data © OpenStreetMap contributors*
