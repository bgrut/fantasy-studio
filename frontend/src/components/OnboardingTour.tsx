import React, { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'

/**
 * F2 — First-time onboarding tooltip tour. Runs once per browser (tracked in
 * localStorage). Targets existing DOM elements by data-tour-id so it's
 * decoupled from the surrounding components.
 */

type TourStep = {
  id: string
  targetAttr: string // value of data-tour-id
  title: string
  body: string
  placement?: 'bottom' | 'top' | 'right' | 'left'
}

const STEPS: TourStep[] = [
  {
    id: 'prompt',
    targetAttr: 'prompt-input',
    title: 'Type anything cinematic',
    body: 'AI handles camera, lighting, and direction. Try "a cat on top of mountains."',
    placement: 'bottom',
  },
  {
    id: 'cinematic-ai',
    targetAttr: 'cinematic-ai-toggle',
    title: 'Cinematic AI Direction',
    body: 'V1.3 — smart scene routing. Keep it on for best results.',
    placement: 'left',
  },
  {
    id: 'cast-scene',
    targetAttr: 'generate-btn',
    title: 'Cast your own scene',
    body:
      "Hit Generate — you'll see a Cast panel to pick the character and " +
      "environment. Override AI's choices anytime.",
    placement: 'bottom',
  },
]

const STORAGE_KEY = 'fs.onboarding.v1.done'

export default function OnboardingTour() {
  const [stepIdx, setStepIdx] = useState<number>(0)
  const [active, setActive] = useState<boolean>(false)
  const [ready, setReady] = useState<boolean>(false)

  // Decide once on mount whether to run the tour
  useEffect(() => {
    let done = true
    try {
      done = localStorage.getItem(STORAGE_KEY) === '1'
    } catch {}
    if (!done) setActive(true)
  }, [])

  // Delay activation a beat so target elements have mounted
  useEffect(() => {
    if (!active) return
    const t = setTimeout(() => setReady(true), 400)
    return () => clearTimeout(t)
  }, [active])

  const finish = () => {
    try {
      localStorage.setItem(STORAGE_KEY, '1')
    } catch {}
    setActive(false)
  }

  const skip = finish

  const step = STEPS[stepIdx]

  // Compute target rect for positioning. Recompute on resize/scroll while
  // active so the tooltip tracks its anchor.
  const [rect, setRect] = useState<DOMRect | null>(null)
  useLayoutEffect(() => {
    if (!active || !ready || !step) return
    const find = () =>
      document.querySelector(
        `[data-tour-id="${step.targetAttr}"]`,
      ) as HTMLElement | null
    const update = () => {
      const el = find()
      if (el) setRect(el.getBoundingClientRect())
      else setRect(null)
    }
    update()
    const iv = setInterval(update, 300) // handle late-mounted targets
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      clearInterval(iv)
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [active, ready, step])

  // Scroll the target into view when the step changes
  useEffect(() => {
    if (!active || !ready || !step) return
    const el = document.querySelector(
      `[data-tour-id="${step.targetAttr}"]`,
    ) as HTMLElement | null
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [stepIdx, active, ready, step])

  // Esc skips the tour
  useEffect(() => {
    if (!active) return
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') skip()
    }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [active])

  const tooltipStyle = useMemo<React.CSSProperties>(() => {
    if (!rect) return { visibility: 'hidden' }
    const placement = step?.placement || 'bottom'
    const pad = 12
    const w = 300
    const h = 140 // rough; tooltip has flexible height
    let top = rect.bottom + pad
    let left = rect.left + rect.width / 2 - w / 2
    if (placement === 'top') {
      top = rect.top - h - pad
      left = rect.left + rect.width / 2 - w / 2
    } else if (placement === 'right') {
      top = rect.top + rect.height / 2 - h / 2
      left = rect.right + pad
    } else if (placement === 'left') {
      top = rect.top + rect.height / 2 - h / 2
      left = rect.left - w - pad
    }
    // Clamp to viewport
    const vw = window.innerWidth
    const vh = window.innerHeight
    left = Math.max(12, Math.min(vw - w - 12, left))
    top = Math.max(80, Math.min(vh - h - 12, top))
    return {
      position: 'fixed',
      top,
      left,
      width: w,
      zIndex: 200,
    }
  }, [rect, step?.placement])

  if (!active) return null

  return (
    <AnimatePresence>
      {ready && step && rect && (
        <>
          {/* Spotlight halo */}
          <motion.div
            key={`halo-${step.id}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="pointer-events-none fixed z-[190] rounded-xl ring-2 ring-[#38d9c4]/80 shadow-[0_0_30px_rgba(56,217,196,0.45)]"
            style={{
              top: rect.top - 6,
              left: rect.left - 6,
              width: rect.width + 12,
              height: rect.height + 12,
            }}
          />
          {/* Tooltip card */}
          <motion.div
            key={`tip-${step.id}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ type: 'spring', bounce: 0.2, duration: 0.3 }}
            style={tooltipStyle}
            className="glass rounded-2xl border border-[#38d9c4]/40 shadow-[0_20px_50px_rgba(0,0,0,0.5)]"
          >
            <div className="px-4 py-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-[#38d9c4]">
                    {stepIdx + 1} / {STEPS.length}
                  </span>
                  <h4 className="text-sm font-semibold text-white">{step.title}</h4>
                </div>
                <button
                  onClick={skip}
                  className="text-[#4a4764] hover:text-white text-[10px] font-mono"
                >
                  skip
                </button>
              </div>
              <p className="text-xs text-[#807d99] leading-relaxed">{step.body}</p>
              <div className="flex items-center justify-end gap-2 pt-1">
                {stepIdx > 0 && (
                  <button
                    onClick={() => setStepIdx((i) => Math.max(0, i - 1))}
                    className="px-2.5 py-1 rounded-lg text-[10px] font-mono border border-white/[0.08] bg-white/[0.03] text-[#807d99] hover:text-white hover:bg-white/[0.06]"
                  >
                    back
                  </button>
                )}
                {stepIdx < STEPS.length - 1 ? (
                  <button
                    onClick={() => setStepIdx((i) => i + 1)}
                    className={cn(
                      'px-3 py-1 rounded-lg text-[10px] font-mono font-semibold',
                      'btn-generate',
                    )}
                  >
                    next →
                  </button>
                ) : (
                  <button
                    onClick={finish}
                    className={cn(
                      'px-3 py-1 rounded-lg text-[10px] font-mono font-semibold',
                      'btn-generate',
                    )}
                  >
                    got it
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
