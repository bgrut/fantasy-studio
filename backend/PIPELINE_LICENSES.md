# What the generation pipeline runs on, and what each part allows

Audited 2026-09-25 by reading the code that calls each model (`app/asset_gen`,
`app/game_export/generate.py`, `app/api/game.py`, `scripts/inference_trellis2.py`,
`app/refinement/refiner.py`) and the licence files of the vendored and cached
weights. The question is one question: can a game made with this be sold. The
answer for every part actually called is yes, with the notes below.

| stage | model or tool | licence | commercial use |
|---|---|---|---|
| the reference image | Stable Diffusion XL base 1.0 (stabilityai) | CreativeML Open RAIL++-M | yes; the licence forbids specific harmful uses, not selling |
| depth for the reference | controlnet-depth-sdxl-1.0 (diffusers), Intel DPT-large, Depth-Anything-V2-Small | OpenRAIL++, Apache-2.0, Apache-2.0 | yes |
| the VAE | sdxl-vae-fp16-fix (madebyollin) | MIT | yes |
| image to 3D | TRELLIS and TRELLIS.2 (Microsoft), TripoSG (VAST), TripoSR (Stability and Tripo), InstantMesh (Tencent ARC), zero123plus (sudo-ai) | MIT, MIT, MIT, MIT, Apache-2.0, Apache-2.0 | yes |
| TRELLIS's image encoder | DINOv2 (Meta) | Apache-2.0 | yes |
| background removal inside TRELLIS.2 | briaai RMBG-2.0 | non-commercial | **not used**: `scripts/inference_trellis2.py` stubs it out by design and cuts the subject out with rembg (MIT; u2net weights Apache-2.0) before the pipeline sees the image |
| the cut-out | rembg + u2net | MIT, Apache-2.0 | yes |
| rig and animation | Blender auto-rig (own code), CMU Motion Capture Database clips in `assets/mocap/cmu` | GPL (the tool, not its output), CMU: free for any use, citation asked | yes |
| optional Mixamo clips | `assets/animations/mixamo` holds a README only | Adobe terms: use in your own products, no redistribution of the files | a user may drop their own in; **the studio must not ship them** |
| the judge | CLIP ViT-B/32 (OpenAI) | MIT | yes |
| the refiner's depth hint | MiDaS via lllyasviel/Annotators | MIT | yes |
| the director | Gemma 3 via Ollama | Gemma Terms of Use | yes, with Google's use restrictions |
| the runtime | three.js, N8AO, Rapier | MIT, CC0, Apache-2.0 | yes |
| fonts | Bricolage Grotesque, Instrument Sans, DM Mono | SIL OFL 1.1 | yes |

Cached but not called by any code path: DINOv3 (custom licence), Depth-Anything-V2-Base,
sentence-transformers mpnet. They can be deleted from the Hugging Face cache without effect.

Rules this file exists to keep:

- A model with a non-commercial licence never enters a code path, even as a
  convenience. RMBG is the precedent: stubbed at the boundary, with the reason
  in the comment.
- Anything a user drops in under their own licence (Mixamo) stays out of the
  repository and out of the packaged studio.
- A new model is added to this table in the same commit that first calls it.
