/**
 * v1.4 polish — motion vocabulary.
 *
 * Three timing curves, three durations. Use these everywhere instead of
 * ad-hoc `transition-all duration-200` so motion language stays consistent.
 *
 * The CSS-side mirrors live in src/index.css under :root (--motion-fast,
 * --motion-std, --motion-dramatic, --ease-out-soft, --ease-in-out-snap).
 *
 * Sound effects deferred to V1.5 (4 SFX: tick/swoosh/chime/whoosh; Settings
 * toggle default-off; max 30% volume; sourced from licensed library).
 */
import type { Transition } from 'framer-motion'

// ── Easings (cubic-bezier control points) ─────────────────────────────
export const EASE_OUT_SOFT: [number, number, number, number] = [0.16, 1, 0.3, 1]
export const EASE_IN_OUT_SNAP: [number, number, number, number] = [0.83, 0, 0.17, 1]

// ── Durations (seconds — framer-motion uses seconds) ──────────────────
export const MOTION_FAST = 0.15 // micro: 150ms
export const MOTION_STD = 0.28 // standard: 280ms
export const MOTION_DRAMATIC = 0.6 // dramatic: 600ms

// ── Spring presets ────────────────────────────────────────────────────
export const SPRING_BOUNCY: Transition = {
  type: 'spring',
  stiffness: 300,
  damping: 20,
  mass: 0.7,
}

export const SPRING_SETTLE: Transition = {
  type: 'spring',
  stiffness: 220,
  damping: 26,
  mass: 0.8,
}

// ── Common framer-motion transition presets ───────────────────────────
export const TRANSITION_FAST: Transition = {
  duration: MOTION_FAST,
  ease: EASE_OUT_SOFT,
}

export const TRANSITION_STD: Transition = {
  duration: MOTION_STD,
  ease: EASE_OUT_SOFT,
}

export const TRANSITION_SNAP: Transition = {
  duration: MOTION_STD,
  ease: EASE_IN_OUT_SNAP,
}

export const TRANSITION_DRAMATIC: Transition = {
  duration: MOTION_DRAMATIC,
  ease: EASE_OUT_SOFT,
}

// ── Stagger helper ────────────────────────────────────────────────────
/** 80ms stagger between children, total entrance choreography <1.2s. */
export const STAGGER_DELAY_S = 0.08
