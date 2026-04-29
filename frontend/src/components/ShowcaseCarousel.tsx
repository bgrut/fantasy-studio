import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import {
  SHOWCASE_CLIPS,
  SHOWCASE_CLIP_DURATION_MS,
  SHOWCASE_CROSSFADE_MS,
  type ShowcaseClip,
} from '@/lib/showcase'
import { Sparkles } from 'lucide-react'
import { EASE_OUT_SOFT } from '@/lib/motion'

/**
 * V1.4.2 launch-frame — auto-cycling showcase carousel for the Studio's
 * empty Output panel.
 *
 * Behavior:
 *   • Auto-plays muted, looped, vertical clips
 *   • Crossfades between clips every SHOWCASE_CLIP_DURATION_MS (~4.5s)
 *   • Click any clip → copies its prompt into the prompt input
 *   • If a clip's MP4 fails to load, it's skipped on subsequent cycles
 *   • If ALL clips fail, returns null so SceneStudio falls back to its
 *     standard empty state
 *
 * Built to work seamlessly when /public/showcase/*.mp4 files exist AND
 * to disappear cleanly when they don't.
 */

interface Props {
  /** Called with the clicked clip's prompt — caller wires this to setTopic. */
  onSelectPrompt: (prompt: string) => void
  /** Override the clip set for testing. Defaults to SHOWCASE_CLIPS. */
  clips?: ShowcaseClip[]
  /** Rendered when no clip can play (all failed to load, or 0 configured). */
  fallback?: React.ReactNode
}

export default function ShowcaseCarousel({
  onSelectPrompt,
  clips = SHOWCASE_CLIPS,
  fallback = null,
}: Props) {
  // Track which clips have failed to load, so the cycler skips them.
  const [failedIds, setFailedIds] = useState<Set<string>>(new Set())
  const [activeIdx, setActiveIdx] = useState(0)

  const playableClips = useMemo(
    () => clips.filter((c) => !failedIds.has(c.id)),
    [clips, failedIds],
  )

  // Cycle every SHOWCASE_CLIP_DURATION_MS, advancing through playable clips.
  useEffect(() => {
    if (playableClips.length <= 1) return
    const id = setInterval(() => {
      setActiveIdx((i) => (i + 1) % playableClips.length)
    }, SHOWCASE_CLIP_DURATION_MS)
    return () => clearInterval(id)
  }, [playableClips.length])

  // Clamp activeIdx if a clip got removed (failed to load).
  useEffect(() => {
    if (activeIdx >= playableClips.length && playableClips.length > 0) {
      setActiveIdx(0)
    }
  }, [activeIdx, playableClips.length])

  const handleClipError = useCallback((id: string) => {
    setFailedIds((prev) => {
      if (prev.has(id)) return prev
      const next = new Set(prev)
      next.add(id)
      return next
    })
  }, [])

  // Graceful fallback: every clip failed (or there are no clips). Render
  // the caller-provided fallback instead.
  if (playableClips.length === 0) return <>{fallback}</>

  const current = playableClips[activeIdx]
  if (!current) return <>{fallback}</>

  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-3 px-4 py-3">
      {/* Crossfading video stack */}
      <div className="relative w-full flex-1 min-h-0 max-w-[280px] sm:max-w-[320px] mx-auto rounded-xl overflow-hidden bg-[#070710]">
        <AnimatePresence>
          <motion.button
            key={current.id}
            type="button"
            onClick={() => onSelectPrompt(current.prompt)}
            initial={{ opacity: 0, scale: 1.02 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{
              duration: SHOWCASE_CROSSFADE_MS / 1000,
              ease: EASE_OUT_SOFT,
            }}
            className="absolute inset-0 cursor-pointer group"
            aria-label={`Use prompt: ${current.prompt}`}
          >
            <video
              src={current.src}
              autoPlay
              loop
              muted
              playsInline
              preload="metadata"
              onError={() => handleClipError(current.id)}
              className="w-full h-full object-cover"
            />
            {/* Hover overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/65 via-transparent to-transparent pointer-events-none" />
            <div className="absolute inset-x-0 bottom-0 px-3 pb-2.5 pt-6 flex flex-col gap-1 pointer-events-none">
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#a78bfa]">
                {current.label}
              </span>
              <p className="text-xs sm:text-sm font-medium text-white/95 line-clamp-2">
                "{current.prompt}"
              </p>
            </div>
            {/* Tap-to-use affordance — only visible on hover */}
            <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-[rgba(14,14,22,0.85)] backdrop-blur-sm border border-white/[0.1] text-[10px] font-semibold text-[#a78bfa]">
                <Sparkles className="w-2.5 h-2.5" />
                use prompt
              </span>
            </div>
          </motion.button>
        </AnimatePresence>
      </div>

      {/* Dot indicators — clickable */}
      {playableClips.length > 1 && (
        <div className="flex items-center justify-center gap-1.5">
          {playableClips.map((c, i) => {
            const isActive = i === activeIdx
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => setActiveIdx(i)}
                aria-label={`Show: ${c.label}`}
                className={cn(
                  'h-1.5 rounded-full transition-all',
                  isActive
                    ? 'w-6 bg-gradient-to-r from-[#7c5cff] to-[#ff5c8a] shadow-[0_0_8px_-1px_rgba(255,92,138,0.6)]'
                    : 'w-1.5 bg-white/20 hover:bg-white/40',
                )}
              />
            )
          })}
        </div>
      )}

      {/* Subtle subline — explains the carousel is examples, not "your" render */}
      <p className="text-[10px] font-mono text-[#4a4764] text-center">
        Tap any clip to use its prompt
      </p>
    </div>
  )
}
