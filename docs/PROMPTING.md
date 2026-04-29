# Prompting Guide

How to write prompts that produce great Fantasy Studio renders. Sets honest expectations on what V1 does well, where the constraint sprint stops, and where V2 picks up.

> The TL;DR: **`[single hero] [doing simple action] in [environment]`** is the pattern. Everything else is decoration.

---

## The supported pattern

> **`[single hero] [doing simple action] in [environment]`**

That's it. This is the V1 sweet spot, designed deliberately. Examples that hit it perfectly:

- *"a polar bear walking through the arctic"*
- *"a horse galloping in the desert"*
- *"an eagle flying through the canyon"*
- *"a ferrari racing at sunset"*

Why it works: the LLM director maps each piece cleanly to a recipe slot:

- `[single hero]` → `subject` and `subject_type` → matcher and `forced_hero_id`
- `[doing simple action]` → `animation_style` → which animation layer composes in
- `[environment]` → `environment` and `forced_environment_id` → which env asset and lighting preset

Add cinematic adjectives sparingly — they help, but the core grammar is what matters.

---

## What works exceptionally well

### Wildlife in environments

```text
a polar bear walking through the arctic at sunset
a horse galloping through mountain pass
an eagle flying through a canyon at golden hour
a deer standing in a misty forest
a tiger walking through tall grass
a rhinoceros in the savanna at dawn
```

### Vehicles in environments

```text
a ferrari racing at sunset
a bmw racing through the desert
a porsche in a showroom at night
a jeep climbing a mountain road
a sports car cruising through the city at night
```

### Single characters in environments

```text
a robot walking through a futuristic city at night
a knight standing on a castle wall at sunset
a samurai walking through a bamboo forest
```

### Simple actions

The animation library handles these well:

- `running`, `walking`, `galloping`, `flying`, `standing`, `racing`
- `cruising` (vehicles), `drifting` (vehicles)
- `idle` / `still` (cinematic close-ups)

### Time-of-day modifiers

These swap the lighting preset cleanly:

- `at sunset` / `at golden hour` → `golden_hour_warm` or `sunset_landscape`
- `at sunrise` / `at dawn` → similar but cooler
- `at night` → `automotive_night` or `cinematic_3point` with low key
- `during a storm` → adjust mood, dim sun, add dust ambient

---

## What doesn't work yet (V2 roadmap)

### Multiple subjects

```text
❌ Elmo and a friend skateboarding
❌ a knight fighting a dragon
❌ two cars drag racing
```

V1 builds one hero. The action verb library doesn't yet handle subject-subject interaction. The scene complexity guardrail (V1.4.2) catches these prompts and gives a friendly handoff explaining V2 is the right home.

**V2 plan**: action grammar in the LLM director (`(subject, verb, object)` triples) plus proximity/contact solving for placement.

### Held objects

```text
❌ a robot holding a sword
❌ a person carrying a torch
❌ a knight with a shield
```

V1 doesn't solve for prop attachment. The hero lands in the scene at its authored position; props don't follow.

**V2 plan**: arm-tip raycast → prop position, with simple parent-of-hand binding.

### Specific named characters

```text
❌ Mickey Mouse running
❌ Elmo skateboarding
❌ Pikachu in the forest
```

This is partly an IP issue and partly a library issue. We don't curate trademarked characters and the matcher won't auto-fetch them from Objaverse. If you ingest a custom asset of your own creation that happens to look like X, the system has no way to tell it apart from a non-IP asset — but we're not going to ship those by default.

### Complex action chains

```text
❌ a horse jumping over a fence then galloping through the desert
❌ a car drifting then crashing into a wall
❌ a robot walking up to a door, opening it, and going through
```

V1 is single-action per render. Sequencing is V2/V3.

**V2 plan**: multi-shot sequence generation. V1.5+ may add a "scene transitions" feature for connecting two single-action renders.

### Specific framing requests

```text
⚠️ shot from above
⚠️ low angle close-up
⚠️ over-the-shoulder
```

These *partially* work — the camera director picks one of `tracking_low`, `push_in`, `low_orbit`, `wide_establishing`, etc. — but the mapping is approximate. For exact framing, use the **scene controls** to pick a camera mode directly.

---

## Prompt patterns that produce great results

### Pattern 1 — Subject + environment + time of day

```text
a polar bear in the arctic at sunset
a ferrari in the desert at golden hour
a deer in the forest at dawn
```

The simplest pattern. Lighting + environment auto-pick rarely miss.

### Pattern 2 — Subject + action + environment

```text
a horse galloping through the desert
an eagle flying through the canyon
a wolf running across the snow
```

Adds animation. The animation library has cycles for most common verbs.

### Pattern 3 — Cinematic descriptor + subject + environment

```text
epic ferrari racing through desert canyon
moody horse standing in misty forest
dramatic eagle soaring through stormy mountains
```

The descriptors (`epic`, `moody`, `dramatic`, `intimate`) shift mood, post grade, and energy. They're decorations, not requirements.

### Pattern 4 — Hero + cinematic adjective + environment

```text
a sleek porsche in a luxury showroom
a majestic tiger in lush jungle
a vintage truck in a dusty desert town
```

Adjectives bias asset selection toward matching tags. `sleek` favors metallic finishes; `vintage` favors weathered models; `majestic` shifts camera framing slightly.

---

## Prompt patterns that struggle

These won't crash, but they'll produce generic / fall-back output:

### "Make me a video of..."

```text
⚠️ make me a video of a horse running
⚠️ create a scene with a polar bear
```

The director ignores meta-instructions and parses what's after. `a horse running` is fine on its own — drop the meta.

### Branded products

```text
⚠️ a Coca-Cola can on a beach
⚠️ a McDonald's burger floating
```

Brand-specific assets aren't in the library. Generic versions ("a soda can on a beach", "a burger floating") work but won't have brand fidelity.

### Abstract or surreal scenes

```text
⚠️ existential dread visualized
⚠️ the concept of nostalgia
```

V1 is concrete subject-environment. Abstract prompts fall back to whatever the LLM director makes of them, often producing a generic landscape.

### Specific weather descriptions

```text
⚠️ a horse in the desert with three sandstorms
⚠️ a ferrari in light rain at exactly 6:42 PM
```

Weather influences mood/lighting at a high level. Specific numbers (three storms, exact time) don't propagate to the renderer.

---

## Tier and tone modifiers

Adjectives that shift the directorial output:

| Modifier | Effect |
|---|---|
| `cinematic` | Larger format target_fill (~55%), `cinematic_graded` post |
| `dramatic` | Higher light contrast, deeper shadows, low-orbit camera |
| `epic` | Wide establishing camera, environment scale up, atmospheric layer added |
| `intimate` | Tighter framing (target_fill ~70%), softer lighting |
| `moody` | Lower exposure, cool color grade, denser atmosphere |
| `golden hour` | Warm sun + warm fill, low sun angle, long shadows |
| `night` | Automotive_night lighting, dimmer ambient, hero rim light |
| `realistic` | Less stylized post grade |
| `stylized` | More aggressive color grade, possibly tilt-shift |

You can stack modifiers: `epic dramatic ferrari racing through desert canyon at sunset` works fine.

---

## Iteration patterns

### When to use cast panel manual override

- The matcher returned the right *kind* of asset but wrong *variant* (white horse vs. brown horse)
- You're doing series work and need the same exact hero across multiple shots
- Auto-pick chose an asset you know is broken / low-quality

### When to use scene controls

- You want a specific camera angle the director didn't pick
- You want a specific lighting preset
- You're locking in a duration for time-aligned series work
- You're branding the render with specific colors

### When to use refine panel

- The render is *close* to right but needs a directional nudge ("more dramatic", "lower the camera")
- You're pushing toward a target mood iteratively
- The framing is fine but the *energy* feels off

### When to start over

- The matcher picked the wrong subject entirely (file a bug if you think it's our fault)
- The recipe choice doesn't fit (try rephrasing — `epic` and `dramatic` favor different recipes than `intimate`)
- The output is fundamentally wrong-shaped — multi-subject prompt that V1 can't handle

---

## The honest constraints

V1 ships single-subject because:

1. **Single-subject covers 80% of indie creator demand** — wildlife, vehicle, character-in-environment is what TikTok / YouTube / marketing actually need
2. **Multi-subject is genuinely hard** — action grammar + proximity solving + multi-rig compatibility is V2's headline feature
3. **A constrained tool that nails one thing beats a sprawling tool that's mediocre at many** — we'd rather ship great single-subject renders than okay multi-subject ones

The constraint isn't a limitation we're hiding. It's a positioning we're being explicit about. V2 multi-subject is on the [roadmap](../ROADMAP.md) and is the next major feature.

---

## Pro tips

### Use the prompt suggestion chips

The empty-state carousel (V1.4.2) is curated. Every chip has been validated to render well. Use them as templates for your own prompts.

### Watch the matcher logs

Every render prints:

```text
[MATCHER] picked=horse (score=1.00, exact_subject) runner_up=horse (score=1.00)
```

If `picked` is right but feels like a coincidence, you're getting lucky. If it's wrong, file a bug — the alias map gets tuned with real-world data.

### Save your winners

When a prompt + cast + controls combo produces something great, save:

- The prompt (verbatim)
- The cast assets (their `id`s in the manifest)
- The recipe (`[TEMPLATE_V2] DISPATCH selected recipe='X'`)
- The scene controls

You can replicate any render later. V1.5 will add a "save preset" feature; for now, copy-paste into a notes file.

### Iterate at Quick Preview

Five Quick Previews to nail the prompt + cast + framing, then one Polished or HQ for the final. Don't burn 3-minute Cycles renders on prompt iteration.

### When in doubt, simpler

If a prompt isn't working, try the simplest version of it:

```text
"epic majestic dramatic golden ferrari racing through misty desert canyon at sunset"
                            ↓ simplify ↓
"a ferrari racing in the desert at sunset"
```

Modifiers stack, but the base grammar is what carries the render.

---

## Examples gallery

See **[GALLERY.md](GALLERY.md)** for real renders with their prompts and recipes side-by-side.

---

## Questions or new pattern shares?

- **GitHub Discussions** — the best place to share a prompt pattern that surprised you. We add the best to this guide
- **Discord** — coming soon for launch
- **TikTok / YouTube** — DM for non-technical questions
