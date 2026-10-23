# Roadmap

## Vision

**Anyone can make any game they can imagine, by describing it.** Not a template with the words swapped: a sentence becomes *its own* game, the world it names, the hero it is about, the thing to do there, looking like a small studio made it by hand. A thousand sentences should give a thousand games that do not look alike.

Fantasy Studio runs on your own computer, costs nothing per game, and gives you something you keep editing and can take to a real engine. Video (cinematic Blender renders) remains a second mode of the same studio.

Timelines are aspirational; treat the order as the plan, not the dates.

---

## Now (1.3, October 2026)

What works today:

- **Sentence → playable 3D game** in about a minute, on Windows, no graphics card required for Game mode
- **Purpose-built worlds** for what people ask for: giant rooms at a tiny hero's scale, the sea floor, islands in the sky, surfing beaches, backyards, parks, villages, harbours, frontier towns, monasteries, castles, graveyards, jungle temples, sunken cities, Venice, a Colosseum, railway lines, Cappadocia, orbit, the Moon and Mars, real cities from OpenStreetMap, and walk-in interiors
- **Heroes** generated once and cached (SDXL → TRELLIS.2), auto-rigged and moved by motion matching; animals with measured gaits; vehicles built in code (cars, karts, rover, locomotive, ships, balloons, boards); mounts, flyers, swimmers
- **Genres from the sentence:** adventure, tower defence, platformer, murder mystery, sea battle, racing, surfing, snowball fights, ghost hunts, city builder, and the factory game (the flagship, *Crystal Works*)
- **Weather and light:** rain, snowstorms, fog, hurricanes, every hour of the day; shadows, ambient occlusion, multisampling, photo-scanned materials
- **A maker per game:** typefaces (95 families), colour scheme, frame, minimap style, mark and narrator, chosen per build
- **Inspect & edit** by pointing and typing; **share** by link, zip, or Godot 4 export
- **One-click Windows installer** with checksummed downloads
- **A benchmark** that builds 24 everyday sentences and has a local vision model judge each against its sentence, so progress is a number, not a feeling

---

## Next (the coming weeks)

- **Closer on the first build.** Keep finding sentences the engine reads wrong (the stress tests run a dozen new kinds at a time) and give each missing kind of place, vehicle or play its own builder. Open now: a Viking longship you sail, herding (cattle, sheep), skate and BMX tricks, horse riding with a rider in the saddle
- **Character fidelity:** sharper faces and hands on generated people, cleaner first generations, more drawn characters for drawn styles
- **Start-up smoothness:** fewer shader-compile stutters in the first seconds of a new world
- **Code-signed installer** (Azure Trusted Signing), and the model library moved to its own asset repository so downloads stay fast
- **Benchmark:** raise the share of games the judge passes, prompt by prompt

## Soon (the next few months)

- **Mobile:** play shared games well on a phone (touch controls exist; layout and performance next)
- **Multiplayer for shared games:** a friend joins your world from a link
- **Sound per world:** ambience and music that follow the place and the weather (a music bed exists for the factory game)
- **Longer games:** chains of levels with a story through them, built from a paragraph instead of a sentence
- **Mac support**

## Later

- **Community worlds and characters** you can browse, remix and cast in your own games
- **Character consistency across a whole series** of games
- **Voice prompting**
- **Unreal or Godot-native rendering backends** for the highest-end look

---

## What we're not doing

- **Cloud-only.** Local-first is not negotiable; anything online is opt-in (publishing, sharing).
- **Diffusion video.** Video mode renders real Blender scenes you own.
- **Deepfakes, surveillance, facial recognition.**

## How priorities get set

1. **Regressions** in the gates (98 automated checks run before every change ships)
2. **What sentences people try and how far off the first build is**
3. **The benchmark's most common judged defect**
4. **What makes games feel handmade and different from each other**

Questions or strong opinions: open a [GitHub Discussion](https://github.com/bgrut/fantasy-studio/discussions).
