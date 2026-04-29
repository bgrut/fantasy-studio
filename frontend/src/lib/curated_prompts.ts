/**
 * V1.4.2 launch-frame — curated, verified prompt set.
 *
 * These are the marketing demo prompts. Each one has produced an excellent
 * render in production, so suggesting them sets correct user expectations
 * AND showcases what the product can do.
 *
 * Add or remove without touching SceneStudio: this list is the single
 * source of truth.
 *
 * Brandon — drop new verified prompts here. Aim for 12-15 total. The
 * SceneStudio shows 7-9 randomly per page load.
 */

export const CURATED_PROMPTS: string[] = [
  // ── Verified at launch ────────────────────────────────────────────
  'a polar bear in the arctic',
  'a ferrari racing at sunset',
  'a horse galloping through mountains',
  'a rhino in the desert',
  'a cow in a meadow',
  'an eagle soaring over a canyon',
  'a deer in a misty forest',
  'a porsche in the desert',
  // ── V1.3 showcase prompts (already validated against the cinematic
  //    template_v2 recipe pool) ─────────────────────────────────────
  'a cat on top of mountains',
  'a dragon flying over a castle',
  'a bear in an alpine meadow',
  'a wolf in a snowy forest',
  'a cheetah running across the savanna',
  // ── Brandon: add 4-7 more verified prompts here ──────────────────
]

/**
 * How many chips to display at once on the Studio hero. Spec: 7-9.
 * 8 sits perfectly in two rows on desktop, three on mobile.
 */
export const PROMPT_CHIP_COUNT = 8

/**
 * Fisher-Yates shuffle that picks N from the curated set, deterministic
 * for the lifetime of the page (so chips don't churn between renders).
 */
export function pickPrompts(n: number = PROMPT_CHIP_COUNT): string[] {
  const arr = [...CURATED_PROMPTS]
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr.slice(0, Math.min(n, arr.length))
}
