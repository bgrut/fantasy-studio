# World-Class Plan — from "it works" to "people can't stop using it"

Brainstorm 2026-07-04. Standing rules apply: local/free/commercial-safe, both
backends move together, no regressions, ship + push every session.

## 1. Game modes: don't build genres — build VERBS

The unlock for "RPG, sports, war, a squirrel with a gun doing missions" is NOT
N genre templates. It's a small set of composable MECHANIC VERBS the extractor
mixes per prompt. Genres fall out of combinations:

| Verb | What it adds | Effort |
|---|---|---|
| collect | ✅ shipped | — |
| reach (goal/beacon) | ✅ shipped | — |
| **missions** | objective SEQUENCE + quest log HUD ("1. find the key → 2. reach the tower") | S — highest leverage |
| **combat** | enemy AI states (chase/attack), health bars, player attack (melee swing / projectile), hit feedback, lose state | M — second |
| survive/avoid | hazards, timer, damage zones | S (falls out of combat) |
| race | checkpoints + timer + best time | S |
| score | physics ball + goal triggers (soccer MVP) | S (Rapier dynamic body) |
| talk | NPC dialogue lines (Ollama-written, text bubbles) | S — the RPG feel |

Genre = recipe: **RPG** = missions+talk+combat · **war/fighting** = combat+survive ·
**sports** = score · **"squirrel with a gun"** = casting(squirrel) + combat(ranged)
+ missions. The extractor already understands subjects/objectives — it learns
verbs the same way. Lose states + retry give games STAKES (win screens alone
don't make a game).

Build order: missions → combat → talk → score/race. After combat, ~80% of
"literally anything random" prompts resolve to a playable loop.

## 2. Video: from scenes to STORIES

Phase 31 gave one scene cinematic cuts. The next level is the **Story
Director**: prompt → Ollama writes a 3-act beat sheet (scene list: setting,
action, camera mood, character emotional beat) → pipeline renders each scene
(actor cache keeps the SAME hero across scenes — continuity is already free) →
Video Projects auto-assembles with transitions + title card + credits.
**"Type a story, get a short film."** Nobody has this locally.

Supporting pieces:
- **Action vocabulary**: CMU has hundreds more clips (jumps, dances, stumbles,
  sits, climbs) — grow CATALOG so beats can say "she collapses" and mean it.
- **Dialogue**: text overlays/subtitles now (Ollama-written); local TTS later —
  license-audit first (Piper TTS = MIT ✅ candidate).
- **Transitions**: crossfade/dip-to-black in the ffmpeg assembly (one filter).
- **Fight choreography beats** (Phase 23 fight system + shot director circle
  coverage = action scenes with cuts).

## 3. Quality/detail — what we can do BEFORE the GPU (and after)

CPU-now (each is a visible step-change):
- **Normal-map baking in the decimator**: bake the 500k-tri TRELLIS detail
  into a normal map ON the 45k game mesh (Blender bake, CPU). Game characters
  keep sculpt-level detail at game cost. Single biggest character-quality win.
- **Real sky + grass**: three.js Sky shader (sun-linked) + instanced shader
  grass (100k blades are cheap) — kills the "flat green plane" look forever.
- **Post FX in game**: SSAO + bloom + vignette (three.js postprocessing,
  vendored) — instant "graded" look.
- **PBR ground/prop materials**: PolyHaven CC0 texture packs (normal/rough/AO)
  for grounds and props — both backends.
- **Dense instanced forests**: InstancedMesh scatter (500 trees at 60fps).
- **Video**: Cycles quality tier is CPU-capable for stills/short clips
  (patience tier); film grain + color grade LUT in the ffmpeg export.

GPU day-1 (already queued): TRELLIS quality tier + 2K texture bakes, generate-
anything casting, Cycles hero renders, **Wan 2.2 VACE photoreal pass** (the
Higgsfield-class jump), upright-fix validation + shot-director facing e2e.

## 4. Adoption mechanics (what makes people COME BACK and SHARE)

- **Share codes**: a level/film is fully described by (prompt, seed, verbs) —
  a ~100-char string. "Try my level: FS1-a fox…-#987376" pasted anywhere
  rebuilds it locally. Zero hosting, viral by text. Trivial to build, huge.
- **Remix**: gallery of seed prompts with one-click "remix" (change the hero,
  keep the level). The TikTok loop: see it → remix it → share yours.
- **One-click itch.io publish** (they have an API/butler CLI) + vertical
  9:16 game recording export for TikTok demos.
- **Starter packs**: 5 curated genre recipes on the home screen (RPG quest,
  soccer match, squirrel ops, night hunt, road trip film).
- **The demo video that markets itself**: one take — type a sentence, SAME
  world comes out as a film AND a playable game, then export both. That's the
  category-defining clip; nothing free does this.

## 5. Recommended sequence

1. **Missions + combat verbs** (games get purpose + stakes; CPU-now)
2. **Story Director** (multi-scene screenplay → auto-assembled film; CPU logic
   now, full glory on GPU)
3. **Quality pack** (normal-map bake, sky+grass+postFX, PBR grounds; CPU-now)
4. **GPU lands** → generation casting everywhere, photoreal tier, quality tiers
5. **Share codes + starter packs + itch publish** (adoption layer)
6. Unreal adapter (Phase 29) once the above is polished — arrive on AAA turf
   with a full product, not a demo.
