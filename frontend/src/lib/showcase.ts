/**
 * V1.4.2 launch-frame — empty-state showcase carousel config.
 *
 * Each entry is one of our 4 hero render demos. The MP4 lives in
 * /public/showcase/ and is referenced as a relative URL.
 *
 * Click behavior: clicking a clip copies its `prompt` into the Studio's
 * input field, ready for a one-tap render.
 *
 * Graceful fallback: if a clip's MP4 fails to load, the carousel skips
 * it. If ALL clips fail, the carousel returns null and SceneStudio
 * renders its standard empty state instead.
 *
 * Brandon — drop pre-rendered .mp4 files at the paths below. See
 * /public/showcase/README.md for guidance on aspect ratio + duration.
 */

export type ShowcaseClip = {
  id: string
  /** Absolute URL path to the MP4 in /public/showcase/. */
  src: string
  /** The exact prompt that produced this render — copied to input on click. */
  prompt: string
  /** Display label shown over the clip. Usually the prompt without the leading article. */
  label: string
}

export const SHOWCASE_CLIPS: ShowcaseClip[] = [
  {
    id: 'polar-bear',
    src: '/showcase/polar-bear.mp4',
    prompt: 'a polar bear in the arctic',
    label: 'Polar bear · arctic',
  },
  {
    id: 'ferrari',
    src: '/showcase/ferrari.mp4',
    prompt: 'a ferrari racing at sunset',
    label: 'Ferrari · sunset',
  },
  {
    id: 'horse-mountain',
    src: '/showcase/horse-mountain.mp4',
    prompt: 'a horse galloping through mountains',
    label: 'Horse · mountain pass',
  },
  {
    id: 'eagle-canyon',
    src: '/showcase/eagle-canyon.mp4',
    prompt: 'an eagle soaring over a canyon',
    label: 'Eagle · canyon',
  },
]

/** How long each clip plays before crossfading to the next. */
export const SHOWCASE_CLIP_DURATION_MS = 4500

/** Crossfade overlap window. Subtle, not abrupt. */
export const SHOWCASE_CROSSFADE_MS = 600
