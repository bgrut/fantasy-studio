# Showcase MP4s

V1.4.2 launch-frame — pre-rendered hero clips that run as the auto-cycling
carousel in the Studio's empty Output panel.

## Files expected

Drop the four `.mp4` files at these exact paths:

| File | Prompt that produced it |
|---|---|
| `polar-bear.mp4` | `a polar bear in the arctic` |
| `ferrari.mp4` | `a ferrari racing at sunset` |
| `horse-mountain.mp4` | `a horse galloping through mountains` |
| `eagle-canyon.mp4` | `an eagle soaring over a canyon` |

Add or replace clips by editing `src/lib/showcase.ts` (no SceneStudio changes
needed).

## Format guidance

- **Aspect ratio**: 9:16 (TikTok / vertical) — same shape as live renders
- **Duration**: 4–5 s. The carousel cycles every 4.5 s and crossfades over
  600 ms, so keep the MP4 close to that to avoid mid-clip cuts
- **Codec**: H.264 baseline profile, AAC audio (or muted), MP4 container
- **Resolution**: 720×1280 minimum, 1080×1920 ideal. Compress to ~2–4 MB
  per clip — these load on every page visit, so weight matters
- **Mood**: silent or near-silent. The carousel autoplays muted, so audio
  doesn't matter, but keep the visuals self-contained
- **Loop-friendly**: the clip loops while in view, so a smooth start/end
  helps. If the render has a hard cut at the end, trim it slightly

## Graceful fallback

If any clip fails to load (404, codec mismatch, network error), the
carousel skips that slot. If **all four** clips fail, the carousel returns
null and the Studio falls back to its existing empty state ("Your scene
will appear here" + nudge chip). This means you can ship the carousel code
before the MP4s exist — it's invisible until the files are dropped in.

## Click behavior

Clicking any clip copies its prompt into the Studio's input field. The
user can then hit Generate to reproduce the showcase render with their
own cast / scene control overrides.
