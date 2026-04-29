# User Guide

Everything you need to go from "just installed" to "shipping cinematic shots regularly".

> If you haven't installed yet, start with [INSTALL.md](../INSTALL.md).

---

## Getting started

### Your first render

> *Screenshot: prompt entry with cast panel populated — `.github/assets/guide-first-render.png`*

1. Open the app at <http://localhost:3000>
2. In the prompt box, type: **`a polar bear in the arctic at sunset`**
3. The cast panel auto-populates: hero (polar bear), environment (arctic), and a derived recipe (`hero_ocean_horizon` or similar)
4. Pick **Quick Preview** for your first render — fastest feedback (~30 seconds)
5. Click **Generate**
6. Watch the pipeline log stream in the side panel
7. When you see `[PIPELINE] +XXs RENDER_COMPLETE`, the MP4 plays in the preview pane

You now have:
- An **MP4** (download button)
- A **.blend** file (the source — yours forever)
- A **GIF** (for social posts)
- A **PNG sequence** (for editing in After Effects / Premiere / Resolve)
- A **credits.txt** noting any Sketchfab/Poly Haven attribution

---

## Writing good prompts

### The supported pattern

> **`[single hero] [doing simple action] in [environment]`**

This is the V1 sweet spot. Examples:

- ✅ "a polar bear walking through the arctic at sunset"
- ✅ "a horse galloping through the desert"
- ✅ "an eagle flying through the canyon"
- ✅ "a ferrari racing at sunset"
- ✅ "a deer standing in a forest at golden hour"
- ✅ "a porsche in a desert showroom"

The director picks recipe, lighting, camera, and animation from this minimal grammar. Add cinematic adjectives sparingly — they help, but the core grammar is what matters.

### What doesn't work yet (V2 roadmap)

- ❌ **Multiple subjects**: "Elmo and a friend skateboarding" — multi-subject composition is V2
- ❌ **Held objects**: "robot holding a sword" — needs proximity/contact solving (V2)
- ❌ **Specific named characters**: "Mickey Mouse running" — IP/library limitation
- ❌ **Complex action chains**: "horse jumping over a fence then galloping" — single-action V1

If you ask for one of these, the **scene complexity guardrail** (V1.4.2) gives you a gentle handoff explaining that V1 is single-subject and pointing at supported patterns.

Deep dive in **[PROMPTING.md](PROMPTING.md)**.

---

## Choosing a render tier

| Tier | When to use | Time | Engine |
|---|---|---|---|
| **Quick Preview** | Iterating on prompt or cast — getting the framing right | ~30s | Eevee, 16 samples |
| **Polished** | Sharing on social, internal review, casual portfolio | ~60s | Eevee + post effects |
| **High Quality** | YouTube, paid client work, online portfolio | ~3m | Cycles, 128 samples |
| **Final Cinematic** | The hero shot in your reel, big-budget pitches | ~10m+ | Cycles, 512+ samples |

The same scene file produces all four — pick the tier at render time.

> *Screenshot: tier selector — `.github/assets/guide-tier-selector.png`*

**Iteration loop suggestion**: 5 Quick Previews to nail the prompt + cast + framing, then one Polished or HQ for the final.

---

## Using the cast panel

The cast panel shows what the AI cast for your prompt before you render. You can override any slot.

> *Screenshot: cast panel with hero + environment slots — `.github/assets/guide-cast-panel.png`*

### When to override

- ✅ The auto-pick is the right *kind* of asset but wrong *variant* (got "white horse" wanted "brown horse")
- ✅ You want to use a specific asset you ingested yourself
- ✅ You're doing series work and need the same hero across multiple shots
- ❌ The auto-pick is wrong on subject (matcher bug — file an issue with the trace log)

### Using "Change cast"

1. Click **Change cast** next to the hero or environment slot
2. The library browser opens with category filters (character / vehicle / environment / prop)
3. Search by subject or browse thumbnails
4. Click an asset to swap; cast panel updates immediately
5. Render with the manual pick

The matcher tracks your manual picks and won't second-guess them — `forced_hero_id` is set in the manifest and downstream auto-pick logic respects it.

---

## Scene controls

The scene controls panel exposes the directorial knobs the AI usually picks for you. Override any or all.

> *Screenshot: scene controls panel — `.github/assets/guide-scene-controls.png`*

### Controls available

- **Lighting preset** — `sunset_landscape`, `golden_hour_warm`, `automotive_night`, `cinematic_3point`, etc. Pulled from `app/templates_v2/lighting/`
- **Camera mode** — `tracking_low`, `push_in`, `low_orbit`, `wide_establishing`. From `app/templates_v2/compositions/`
- **Duration** — 6s / 8s / 12s / 16s
- **Brand color** — primary + accent (used in any UI overlays)
- **Template** — pin a specific recipe (overrides dispatcher scoring)

When you change a control, the manifest updates and a re-render uses the new value. The same scene assembles with new directorial intent.

---

## Refining a scene

The refine panel lets you push the render in a direction with natural language, without rebuilding from scratch.

> *Screenshot: refine panel — `.github/assets/guide-refine-panel.png`*

### Patterns that work

- **"Make it more dramatic"** — bumps lighting contrast, deepens shadows
- **"Lower the camera"** — adjusts the camera Z down by ~30%
- **"Golden hour"** — swaps to `golden_hour_warm` lighting preset
- **"Tighter on the subject"** — increases target_fill from 55% → 70%
- **"Wider"** — drops target_fill, pulls camera back
- **"More moody"** — applies cinematic post grade

The refine panel routes the natural-language phrase through the LLM director with the current manifest as context, so it knows what it's adjusting.

### Patterns that are noisy

- **"Make it 5% bluer"** — too specific; refine works in semantic, not numeric, deltas
- **"Add a second character"** — multi-subject is V2; this won't do anything useful
- **"Use my logo"** — brand color works, but logo overlay is a future feature

---

## Render variations

Want to see the same prompt rendered 3 different ways? Use the **Sweep N variations** option.

> *Screenshot: sweep panel — `.github/assets/guide-sweep.png`*

- 3 variations × Quick Preview = ~90 seconds, three different LLM director outputs for the same prompt
- Useful when you can't decide between framing options
- Each variation gets its own MP4 + .blend

---

## Exporting

Every render produces all four exports automatically. Pick what fits your workflow:

| Format | Best for | Size |
|---|---|---|
| **MP4** | Social, YouTube, embedding | ~5–20 MB for 12s |
| **GIF** | Quick share, Slack, Discord | ~10–50 MB |
| **PNG sequence** | Importing to After Effects, Premiere, Resolve as an image sequence | ~50–200 MB |
| **`.blend`** | Re-editing in Blender, locking the scene for series work, learning from the AI's choices | ~50–500 MB |

The **`.blend` is your superpower**. Open it in Blender, swap a light, change the HDRI, re-render with motion blur — all without re-running the AI pipeline.

---

## Editing in Blender (advanced)

If you know Blender, the `.blend` export unlocks the full toolchain:

1. Open `outputs/blender_render_<timestamp>/scene.blend` in Blender 5.1+
2. The scene is fully assembled — hero, env, lights, cameras, post nodes
3. Common edits:
   - Adjust light energy / color
   - Change camera focal length
   - Swap HDRI
   - Re-time animations
   - Add subjects manually (V1's auto-direct is single-subject, but Blender doesn't care)
4. Re-render in Blender natively (`Render → Render Animation`)

This is the "yours to keep" angle of Fantasy Studio — the AI hands you a real Blender scene, not a black-box pixel buffer.

---

## Tips & tricks

### Productive iteration loop

1. Quick Preview to validate the cast and framing
2. If wrong asset → Change cast manually
3. If wrong framing → tweak scene controls or refine ("lower the camera")
4. If lighting feels off → swap lighting preset or refine ("more dramatic")
5. Once happy → re-render at Polished or HQ for the final

Most users get to "looks great" in 3–5 Quick Previews.

### Use the prompt suggestions

The empty-state prompt suggestion chips (V1.4.2) are pre-validated to render well. Click one to see what good output looks like before forming your own.

### Save winners as scene presets

(Coming in V1.5) Save your "this looks great" controls combo as a one-click preset for future prompts.

### Keep the trace log

When something renders well, save the `pipeline_trace.log` and the `manifest_<ts>.json`. They show exactly what the AI did, and you can replicate it on a new prompt by manually setting the same controls.

### Lean on the deterministic fallback

If Ollama is laggy, Fantasy Studio's deterministic director takes over. It's less creative but very fast and 100% reproducible. For series work where you need consistency, the deterministic path is your friend.

### Watch the matcher logs

Every render prints `[MATCHER] picked=… (score=…) runner_up=…`. If the runner-up is what you wanted, override via the cast panel. If both picks look wrong, file a bug — alias map tuning is ongoing.

---

## Common gotchas

- **No Sketchfab token = limited asset variety** — without a free Sketchfab API token, the fallback fetcher only uses Objaverse. Set up the token from [INSTALL.md](../INSTALL.md) for the full asset library experience
- **First Cycles render compiles shaders** — 2–5 minutes the first time per session, fast after
- **GPU VRAM matters** — heavy hero meshes (50–100 MB .blend) plus envs can OOM at 8 GB. Drop to Quick Preview tier
- **Asset cache is huge** — Objaverse fallback fills `assets/cache/` quickly. Clear periodically
- **Renders aren't 100% deterministic across machines** — same prompt + same library will produce visually identical output on the same hardware, but Cycles uses GPU-driver-specific math

---

## Where to get more help

- **[PROMPTING.md](PROMPTING.md)** — prompt engineering deep-dive
- **[GALLERY.md](GALLERY.md)** — what good output looks like
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — when things go wrong
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how the pipeline actually works
- **GitHub Discussions** — design questions, prompt-pattern shares
- **Discord** — coming soon for launch
