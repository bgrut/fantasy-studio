# Roadmap

## Vision

Fantasy Studio is becoming the **AI cinematographer for everyone who isn't an expert Blender artist**. Our north star is making single-subject cinematic shots feel inevitable — type a prompt, get a film-quality clip, own the source. From there we expand outward to scene composition, character animation, and ultimately Unreal Engine quality output.

The bet underneath: AI directs real tools, it doesn't replace them. Diffusion video burns money on every render and produces output you can't direct. Fantasy Studio costs electricity, gives you the `.blend` file, and lets you re-light, re-frame, re-render forever.

Timelines below are aspirational and depend on traction post-launch. Treat the version numbers as ordering, not deadlines.

---

## Now (V1.0 — Mid-May 2026 launch)

What ships at the public launch:

- **Single-subject cinematic shots** — animals, vehicles, characters in environments
- **Local LLM director** (Gemma 3 12B via Ollama) with deterministic rule-based fallback
- **15 cinematic recipes** + layered template system (env / comp / lighting / animation / ambient / post)
- **Four render tiers** (Quick Preview / Polished / High Quality / Final Cinematic)
- **Cycles + Eevee** rendering selected per tier
- **316-asset curated launch library** with V1.2 healer applied
- **Objaverse + Sketchfab fallback** when the library doesn't have the requested subject
- **MP4 + `.blend` + GIF + PNG sequence + credits.txt** output package
- **Cast panel manual override**, scene controls, refine panel
- **Pipeline trace logging** + `[HERO_VERIFY]` 7-check render gate
- **Public docs**, BSL 1.1 license, GitHub repo

---

## Next (V1.1 – V1.4 — post-launch, ~8 weeks)

The Plan B "build quality in parallel" priorities. These are the things that turn V1's good single-subject renders into great ones, while keeping the multi-subject V2 roadmap honest.

- **Hero animation library** — pre-baked walk / run / fly cycles per character archetype, swapped in based on subject_type. No more static renders for "horse galloping" or "eagle flying"
- **Ground contact + shadow integration** — proper shadow casters that match hero motion, contact points that align with terrain raycasts
- **Expanded camera language vocabulary** — more pre-baked moves per scene archetype (push-in variants, whip-pans, dolly-zooms, low-orbit refinements)
- **Library expansion sprint** — 316 → 600+ curated assets, focusing on gaps (more animal variety, vehicle classes, environment regions)
- **Matcher tuning rounds** — additional alias map entries from real-world prompt logs, biased pruning of low-scoring partial-tag matches
- **Frontend polish** — empty-state showcase carousel, prompt suggestion chips for verified-working scenes, better cast panel filtering
- **Render time reduction** — Eevee Next sample tuning, optimized HDRI loading, skipped recompute where possible

---

## Soon (V1.5 – V1.9 — ~3-6 months)

Capability expansion before V2's hard-mode work:

- **Cloud render tier** — Fantasy Studio runs the LLM director locally and ships the prepared `.blend` to a render farm for users without a local GPU. Eevee tiers stay local; Cycles tiers can offload
- **Sound effects + ambient audio** — recipe-driven SFX library, ambient layers that match the environment (wind for arctic, engine for vehicle)
- **Voice prompt input** — speech-to-text → director, mobile-friendly capture
- **Sharing / portfolio features** — render gallery on user profile, shareable scene URLs, embed codes
- **Patreon-only premium templates** — high-end recipes with extra layers (volumetric atmospherics, cinema-grade post grades) gated behind the support tier
- **Scene presets** — save your favorite controls combo as a one-click profile
- **Asset pinning** — "use this hero across my next 5 prompts" to lock subject identity for series work

---

## Future (V2.0+ — ~6-12 months)

The hard-mode features that need real architecture work:

- **🛒 Marketplace launch** — creator asset sales with Stripe Connect, 80% revenue share to creators, automated quality healing on upload, attribution tracking and royalty distribution. The contributor pipeline that's already taking shape becomes a real economy
- **🎭 Multi-subject scene composition** — character holding props, multiple interacting subjects, action verb library. The big one. Requires action grammar (subject + verb + object), proximity/contact solving, multi-armature compatibility
- **🎬 Character consistency across scenes** — the same hero looks the same across a 10-shot sequence. Asset locking + identity tags + consistent lighting profiles
- **🎥 AI Director v2** — treatment → casting → blocking canvas. Brief the model on a *story*, get a *sequence*, not a clip
- **🎮 Unreal Engine renderer backend** — same recipe JSON, different executor. Pixel quality jumps significantly
- **📐 Multi-shot sequence generation** — 3 cuts of the same scene from different angles, edited together

---

## Eventual (V3+)

The post-product-market-fit ambitions:

- **Real-time iteration via WebGPU previews** — sub-second feedback while typing the prompt
- **Community-driven recipe library** — recipes curated and rated by the community, surfaced through the dispatcher with reputation weighting
- **Plugin system for custom layers** — third parties write Python layers that compose into recipes, distributed through the marketplace
- **Multi-language director** — Gemma → Llama / Qwen / region-tuned models for non-English prompts
- **Mobile capture → desktop render** — shoot reference on your phone, render at home

---

## What we're explicitly NOT doing

- **Diffusion video generation** — different bet, different team. Plenty of great tools already exist there
- **Pure 3D editing UX** — Spline, Womp, and Blender itself are already great at that. Fantasy Studio is for when you don't want to learn a 3D editor
- **Closed-source / cloud-only deployment** — local-first is non-negotiable. Cloud render is opt-in tier, not a replacement
- **Surveillance / facial recognition / deepfake** integrations — outside the moral envelope of the project

---

## How priorities get set

Inputs in rough order of weight:

1. **Render quality regressions** — anything breaking existing canary prompts is highest priority
2. **Plan B priorities** — single-subject quality compounds; we ship Now and Next before getting clever
3. **User feedback from waitlist + Discord** — the actual prompt patterns people try
4. **Marketplace runway** — features that unblock the marketplace economy land in V2 ahead of the longer-tail V3 list
5. **Personal interest** — solo dev project; if I'm not excited to ship it, it slips

---

## Open questions / pending decisions

- Should V1.5 cloud render tier ship as managed (FantasyLab AI hosts) or BYO-API-key (user provides Modal / RunPod credentials)?
- Marketplace revenue share: 80/20 vs. 70/30? Need to model the floor at low SKU volumes
- Multi-subject V2: greedy approach (compose at scene-build time) vs. structural approach (action grammar in the LLM director). Probably both, sequenced

If you have strong feelings on any of these, open a [GitHub Discussion](https://github.com/bgrut/fantasy-studio/discussions).
