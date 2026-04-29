/**
 * V1.4.2 launch-frame — client-side prompt complexity heuristic.
 *
 * Detects three classes of prompts that are likely outside current capability
 * and SOFTLY signals to the user. The user can still hit Generate; the
 * detection just sets expectations and offers proven alternatives.
 *
 * 1. Multi-subject — more than 2 noun phrases joined by "and" / "with".
 *    "a cat AND a dog" → multi-subject. Hard to render well in V1.
 * 2. Blocked brand/character names — copyrighted IP not in our asset library.
 *    Maintained client-side; refine post-launch as new requests come in.
 * 3. Complex action phrases — "holding", "wearing", "carrying", "riding".
 *    These imply complex character interactions / props the rigging
 *    pipeline can't reliably produce yet.
 *
 * NEVER blocks. Only surfaces a soft info pill above Generate.
 */

// ── Brand / character names not in our asset library ───────────────────
// Lower-cased; matched as whole words against the prompt.
const BLOCKED_NAMES: string[] = [
  // Sesame / kids' TV
  'elmo', 'big bird', 'cookie monster', 'oscar the grouch',
  // Disney / Pixar
  'mickey', 'minnie', 'donald duck', 'goofy', 'pluto',
  'buzz lightyear', 'woody', 'olaf', 'elsa', 'anna',
  'wall-e', 'wall e',
  // Nintendo
  'mario', 'luigi', 'peach', 'bowser', 'yoshi', 'zelda', 'link',
  'pikachu', 'charizard', 'eevee', 'mewtwo',
  // Marvel / DC
  'spiderman', 'spider-man', 'iron man', 'thor', 'hulk', 'captain america',
  'batman', 'superman', 'wonder woman', 'flash', 'aquaman',
  // Other commonly-requested IP
  'sonic', 'kirby', 'bart simpson', 'homer simpson', 'spongebob',
  'patrick star', 'shrek', 'snoopy', 'garfield',
  // Generic celebrity asks
  'taylor swift', 'kanye', 'drake', 'beyonce', 'rihanna',
]

// ── Complex action verbs that imply specific character interactions ────
const COMPLEX_ACTIONS: string[] = [
  'holding', 'wearing', 'carrying', 'riding', 'hugging',
  'kissing', 'fighting', 'shaking hands', 'high-fiving', 'high fiving',
  'eating', 'drinking', 'reading', 'writing', 'cooking',
  'playing guitar', 'playing piano',
]

export type PromptAdvice = {
  ok: boolean
  /** Short user-facing reason. Null when ok. */
  reason?: string
  /** Which heuristic class fired (for telemetry / debugging). */
  kind?: 'blocked-name' | 'multi-subject' | 'complex-action'
}

export function analyzePrompt(prompt: string): PromptAdvice {
  const text = (prompt || '').toLowerCase().trim()
  if (!text) return { ok: true }

  // 1. Blocked names — substring match wrapped in word boundaries
  for (const name of BLOCKED_NAMES) {
    if (containsWholeWord(text, name)) {
      return {
        ok: false,
        kind: 'blocked-name',
        reason: `${capitalize(name)} isn't in our asset library yet.`,
      }
    }
  }

  // 2. Multi-subject — count "and" / "with" joins. 2+ joins suggests
  //    chaining 3+ subjects, which the renderer struggles with.
  const joinMatches = text.match(/\b(and|with)\b/g) || []
  if (joinMatches.length >= 2) {
    return {
      ok: false,
      kind: 'multi-subject',
      reason: 'I work best with single-subject cinematic scenes.',
    }
  }

  // 3. Complex actions
  for (const action of COMPLEX_ACTIONS) {
    if (containsWholeWord(text, action)) {
      return {
        ok: false,
        kind: 'complex-action',
        reason: `Complex actions like "${action}" can look unnatural in V1.`,
      }
    }
  }

  return { ok: true }
}

function containsWholeWord(haystack: string, needle: string): boolean {
  // Escape regex specials in the needle, then match as a whole-word sequence.
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`\\b${escaped}\\b`, 'i')
  return re.test(haystack)
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
