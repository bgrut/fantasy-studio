import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Sparkles, User, Mountain, Wand2, ImageOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { SPRING_BOUNCY, EASE_OUT_SOFT, MOTION_STD } from '@/lib/motion'

export type InlineCastSlot = {
  id: string
  title: string
  thumbnail_url?: string | null
} | null

interface Props {
  hero: InlineCastSlot
  env: InlineCastSlot
  /** Empty-state CTA — opens the full Cast panel (prompt-aware re-pick). */
  onCast: () => void
  /** Per-slot Change — opens the paginated library browser for that slot. */
  onChangeHero?: () => void
  onChangeEnv?: () => void
  disabled?: boolean
  /** When true, render a "Cast modified — re-render to apply" pill. */
  modified?: boolean
}

const PALETTE = ['#7c5cff', '#ff5c8a', '#38d9c4', '#ffc857', '#a78bfa', '#f472b6', '#4ade80', '#60a5fa']
function placeholderColor(seed: string): string {
  return PALETTE[(seed.charCodeAt(0) || 0) % PALETTE.length]
}

export default function InlineCastStrip({
  hero,
  env,
  onCast,
  onChangeHero,
  onChangeEnv,
  disabled,
  modified,
}: Props) {
  const empty = !hero && !env

  return (
    <div className="max-w-2xl mx-auto space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] text-[#807d99] uppercase tracking-wider">Cast</span>
        {empty ? (
          <span className="text-[11px] font-mono text-[#4a4764]">
            AI will pick from the library based on your prompt, or pick yourself.
          </span>
        ) : (
          <AnimatePresence>
            {modified && (
              <Tooltip>
                <TooltipTrigger
                  render={(props) => (
                    <motion.span
                      {...props}
                      key="cast-modified-pill"
                      initial={{ opacity: 0, x: 30 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 30 }}
                      transition={{ duration: MOTION_STD, ease: EASE_OUT_SOFT }}
                      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-[#ffc857]/30 bg-[#ffc857]/10 text-[10px] font-mono text-[#ffc857] cursor-help"
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-[#ffc857] shadow-[0_0_6px_rgba(255,200,87,0.7)]" />
                      Cast modified — re-render to apply
                    </motion.span>
                  )}
                />
                <TooltipContent side="left" className="max-w-[240px]">
                  You changed a cast slot after the last render. Hit Generate to render with the updated cast.
                </TooltipContent>
              </Tooltip>
            )}
          </AnimatePresence>
        )}
      </div>

      <div className="glass rounded-2xl px-3 py-3 border border-white/[0.05]">
        {empty ? (
          <div className="flex items-center gap-3">
            <div className="spinning-cube opacity-30" />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-white">Auto-pick from prompt</div>
              <div className="text-[11px] font-mono text-[#4a4764] truncate">
                Let the director cast both, or override below.
              </div>
            </div>
            <button
              type="button"
              onClick={onCast}
              disabled={disabled}
              className={cn(
                'inline-flex items-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-sm transition-all',
                disabled
                  ? 'bg-white/[0.04] text-[#4a4764] cursor-not-allowed'
                  : 'btn-generate',
              )}
            >
              <Wand2 className="w-4 h-4" />
              Cast scene
            </button>
          </div>
        ) : (
          // v1.4 polish — spring-bouncy reveal when slots populate. Each slot
          // overshoots slightly then settles. Keyed on slot.id so swapping
          // cast members re-triggers the bounce.
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <motion.div
              key={`hero-${hero?.id || 'empty'}`}
              initial={{ opacity: 0, y: 18, scale: 0.94 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={SPRING_BOUNCY}
            >
              <Slot
                kind="hero"
                label="Character"
                Icon={User}
                accent="#a78bfa"
                slot={hero}
                onChange={onChangeHero || onCast}
                disabled={disabled}
              />
            </motion.div>
            <motion.div
              key={`env-${env?.id || 'empty'}`}
              initial={{ opacity: 0, y: 18, scale: 0.94 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ ...SPRING_BOUNCY, delay: 0.06 }}
            >
              <Slot
                kind="env"
                label="Environment"
                Icon={Mountain}
                accent="#38d9c4"
                slot={env}
                onChange={onChangeEnv || onCast}
                disabled={disabled}
              />
            </motion.div>
          </div>
        )}
      </div>
    </div>
  )
}

function Slot({
  label,
  Icon,
  accent,
  slot,
  onChange,
  disabled,
}: {
  kind: 'hero' | 'env'
  label: string
  Icon: React.ComponentType<any>
  accent: string
  slot: InlineCastSlot
  onChange: () => void
  disabled?: boolean
}) {
  const [thumbFailed, setThumbFailed] = useState(false)

  return (
    // v1.4.1 audit — relative positioning so the Change button can overlay
    // top-right without consuming flex space the title needs.
    <div className="group relative flex items-center gap-3 rounded-xl border border-white/[0.05] bg-white/[0.02] px-2.5 py-2.5 pr-3">
      {/* Thumbnail */}
      <div
        className="flex-shrink-0 w-12 h-12 rounded-lg overflow-hidden relative"
        style={{ background: '#0a0a10' }}
      >
        {slot && !thumbFailed && slot.thumbnail_url ? (
          <img
            src={slot.thumbnail_url}
            alt={slot.title}
            onError={() => setThumbFailed(true)}
            className="w-full h-full object-cover"
          />
        ) : (
          <Placeholder slot={slot} accent={accent} />
        )}
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-1.5">
          <Icon className="w-3 h-3 flex-shrink-0" style={{ color: accent }} />
          <span
            className="text-[10px] font-mono uppercase tracking-wider"
            style={{ color: accent }}
          >
            {label}
          </span>
        </div>
        {/* v1.4.1 audit — line-clamp-2 instead of truncate so titles like
            "Car Free Model By Omega" wrap to a 2nd line instead of cutting
            at the ellipsis. break-words so long single-word titles also wrap. */}
        <div className="flex items-start gap-1.5 min-w-0">
          <span className="text-xs font-semibold text-white leading-tight line-clamp-2 break-words">
            {slot ? slot.title : 'Not cast'}
          </span>
          {slot && (
            <Tooltip>
              <TooltipTrigger
                render={(props) => (
                  <span
                    {...props}
                    aria-label={`Asset ID: ${slot.id}`}
                    className="flex-shrink-0 inline-flex w-3.5 h-3.5 rounded-full border border-white/[0.08] bg-white/[0.02] text-[8px] font-mono text-[#3a3850] hover:text-[#807d99] hover:border-white/[0.18] cursor-help items-center justify-center transition-colors mt-0.5"
                  >
                    ?
                  </span>
                )}
              />
              <TooltipContent>
                <span className="font-mono text-[10px]">{slot.id}</span>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      {/* v1.4.1 audit — Change button overlaid top-right so it doesn't eat
          flex space when hidden. Title gets the full row to wrap into. */}
      <button
        type="button"
        onClick={onChange}
        disabled={disabled}
        aria-label={`Change ${label.toLowerCase()}`}
        className={cn(
          'absolute top-1.5 right-1.5 z-10',
          'inline-flex items-center justify-center gap-1 px-2 py-1 rounded-md text-[10px] font-semibold',
          'opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity',
          'border border-white/[0.1] bg-[rgba(14,14,22,0.85)] backdrop-blur-sm text-[#a78bfa]',
          'hover:bg-[#7c5cff]/20 hover:text-white hover:border-[#7c5cff]/40',
          disabled && 'opacity-30 cursor-not-allowed',
        )}
      >
        <Sparkles className="w-2.5 h-2.5" />
        Change
      </button>
    </div>
  )
}

function Placeholder({
  slot,
  accent,
}: {
  slot: InlineCastSlot
  accent: string
}) {
  if (!slot) {
    return (
      <div
        className="w-full h-full flex items-center justify-center"
        style={{ background: 'linear-gradient(135deg, #12121e, #0a0a10)' }}
      >
        <ImageOff className="w-5 h-5 text-white/15" />
      </div>
    )
  }
  const color = placeholderColor(slot.title)
  const letter = (slot.title.trim().charAt(0) || '?').toUpperCase()
  return (
    <div
      className="w-full h-full flex items-center justify-center"
      style={{
        backgroundImage: `linear-gradient(135deg, ${color}33, ${color}11)`,
        backgroundColor: '#12121e',
      }}
    >
      <span className="text-xl font-bold" style={{ color: accent }}>
        {letter}
      </span>
    </div>
  )
}
