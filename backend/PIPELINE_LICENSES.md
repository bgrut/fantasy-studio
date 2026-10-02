# What the generation pipeline runs on, and what each part allows

Audited 2026-09-25 by reading the code that calls each model (`app/asset_gen`,
`app/game_export/generate.py`, `app/api/game.py`, `scripts/inference_trellis2.py`,
`app/refinement/refiner.py`) and the licence files of the vendored and cached
weights. Re-audited 2026-09-30, which found four non-commercial parts in code
paths this file had called clean; they are out, and the table below is what
runs now. The question is one question: can a game made with this be sold.

| stage | model or tool | licence | commercial use |
|---|---|---|---|
| the reference image | Stable Diffusion XL base 1.0 (stabilityai) | CreativeML Open RAIL++-M | yes; the licence forbids specific harmful uses, not selling |
| depth for the reference | controlnet-depth-sdxl-1.0 (diffusers), Intel DPT-hybrid-MiDaS and DPT-large | OpenRAIL++, Apache-2.0, Apache-2.0 | yes |
| the VAE | sdxl-vae-fp16-fix (madebyollin) | MIT | yes |
| image to 3D | TRELLIS.2 (Microsoft), then TripoSR (Stability and Tripo) | MIT, MIT | yes |
| TRELLIS.2's texture bake | `scripts/_permissive_raster.py`, a PyTorch rasteriser registered as `nvdiffrast` | own code (BSD-licensed PyTorch underneath) | yes; NVIDIA's nvdiffrast is **never imported** (see below) |
| TRELLIS.2's image encoder | DINOv3 ViT-L/16 (Meta) | DINOv3 License | yes; Meta claims no rights in outputs; "Built with DINOv3" is credited in the README; military, weapons and surveillance uses are forbidden |
| TRELLIS (v1, splats only)'s image encoder | DINOv2 (Meta) | Apache-2.0 | yes |
| background removal inside TRELLIS.2 | briaai RMBG-2.0 | non-commercial | **not used**: `scripts/inference_trellis2.py` stubs it out by design and cuts the subject out with rembg (MIT; u2net weights Apache-2.0) before the pipeline sees the image |
| the cut-out | rembg + u2net | MIT, Apache-2.0 | yes |
| rig and animation | Blender auto-rig (own code), CMU Motion Capture Database clips in `assets/mocap/cmu` | GPL (the tool, not its output), CMU: free for commercial products, credit line required | yes; every exported game's LICENSES.md carries CMU's credit line |
| optional Mixamo clips | `assets/animations/mixamo` holds a README only | Adobe terms: use in your own products, no redistribution of the files | a user may drop their own in; **the studio must not ship them** |
| the judge | CLIP ViT-B/32 (OpenAI) | MIT | yes |
| the refiner's depth hint | MiDaS via lllyasviel/Annotators | MIT | yes |
| the director | Gemma 3 via Ollama | Gemma Terms of Use | yes, with Google's use restrictions |
| the runtime | three.js, N8AO, Rapier, gaussian-splats-3d | MIT, CC0, Apache-2.0, MIT | yes |
| fonts | Bricolage Grotesque, Instrument Sans, DM Mono; the skins' faces (2026-10-01, from github.com/google/fonts with the owner's approval): Cinzel, IM Fell English, Share Tech Mono, Bebas Neue, Bangers, Fredoka, Creepster, Russo One, Lora, Josefin Sans; Special Elite | SIL OFL 1.1; Special Elite Apache-2.0 | yes; licence files beside each in `vendor/fonts` |
| props | Kenney kits (Nature, Space, Fantasy Town, Graveyard, Survival, Castle, Pirate, Blocky Characters), Poly Haven models and HDRIs | CC0 | yes; licence files in `assets/props/LICENSES` and `assets/library/LICENSES` |
| city streets | OpenStreetMap data | ODbL 1.0 | yes, with the credit every city game's LICENSES.md carries |
| asset search (video pipeline) | Sketchfab, Objaverse | per object | **CC0 objects only** since 2026-09-30; an object with an unreadable licence is refused |
| desktop build | Tauri 2 and its Rust crates; Steamworks bindings; Valve's steam_api64.dll (Steam build only) | MIT, Apache-2.0, MPL-2.0, Unicode-3.0; MIT/Apache-2.0; Valve's SDK agreement | yes; notices generated into THIRD_PARTY_NOTICES.md; the DLL exception approved by the owner 2026-09-29 |

## Removed 2026-09-30

| part | where it was | why it went |
|---|---|---|
| nvdiffrast (NVIDIA Source Code License) | the texture bake of every TRELLIS.2 model (`o_voxel/postprocess.py`), and InstantMesh | "may be used non-commercially": replaced by `scripts/_permissive_raster.py`, matched against nvdiffrast on a real atlas (99.8% of texels covered alike, the same triangle on 99.6%, positions within a millionth of the model's size) |
| TripoSG's RMBG-1.4 and diso | TripoSG, second in the game chain | RMBG-1.4 is "non-commercial use"; diso is CC BY-NC 4.0; its NOTICE carries Tencent Hunyuan community terms. TripoSG left the chain: TRELLIS.2 falls back to TripoSR |
| InstantMesh + zero123plus | the video pipeline's cinematic tier | nvdiffrast inside, and zero123plus weights of unverified licence: the cinematic tier uses TRELLIS.2 |

Models made before these changes went through nvdiffrast (every TRELLIS.2 model)
and possibly TripoSG (before 2026-09-25, when TRELLIS.2 was failing over to it).
The library records no engine per model, so which ones cannot be told apart;
regenerating a model (`tools/regen.py <kind>`) puts it through the current chain.

Cached but not called by any code path: Depth-Anything-V2-Small and -Base,
sentence-transformers mpnet, RMBG-1.4 under `vendor/TripoSG/pretrained_weights`.
They can be deleted without effect.

The zero123plus and InstantMesh weights and the unused SDXL copies (the two
single-file checkpoints and the OpenVINO exports) were deleted from the cache
on 2026-10-01 with the owner's approval.

## Who owns what

- **What users make is theirs.** The studio's LICENSE (BSL 1.1) grants every
  output (games, characters, models, textures, music, text) free of any
  restriction, and the runtime copied into an exported game under MIT. Each
  exported game's LICENSES.md says so and carries the MIT text.
- **The studio is the owner's to sell.** BSL keeps anyone else from offering
  Fantasy Studio, or a modified copy, as a paid product or hosted service, and
  the owner may sell it however they choose, a subscription included.

## Before selling Fantasy Studio as a subscription

Every part above allows a paid service. What each one asks of the operator:

| part | what selling it as a service requires |
|---|---|
| SDXL and its ControlNet (OpenRAIL++-M) | the terms of service carry the licence's use restrictions (its Attachment A) and bind subscribers to them; outputs stay the subscriber's |
| Gemma 3 (Gemma Terms of Use) | the terms of service carry Google's Prohibited Use Policy and a copy of, or link to, the Gemma terms; the model is not offered to subscribers as a general chatbot |
| DINOv3 (DINOv3 License) | "Built with DINOv3" stays visible in the product's credits; a copy of the licence ships with the studio; no military, weapons or surveillance customers |
| Blender scripts (`scripts/*.py` run inside Blender) | none while the studio runs on the owner's servers. A downloadable studio carrying them should license those scripts as GPL-3.0-or-later, since they use Blender's GPL API; they talk to the rest of the studio only through files and a socket, so the studio itself stays BSL |
| CMU motion | none beyond the credit line every game already carries |
| brand-named library models (ferrari, corvette, ford f-150) | a trademark risk for subscribers who sell their games; renaming them to generic kinds (sports car, pickup) before launch removes it |

Rules this file exists to keep:

- A model with a non-commercial licence never enters a code path, even as a
  convenience. RMBG-2.0 and nvdiffrast are the precedents: stubbed or replaced
  at the boundary, with the reason in the comment.
- Anything a user drops in under their own licence (Mixamo) stays out of the
  repository and out of the packaged studio.
- A new model is added to this table in the same commit that first calls it.
