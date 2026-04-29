import React, { useState } from 'react'
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { Check } from 'lucide-react'

/**
 * v1.4 polish — Phase 7 swatch + hex color picker. Replaces native
 * <input type="color"> for visual cohesion. 8 brand-aligned swatches plus a
 * free hex input. Post-launch we can swap in `react-colorful` if real users
 * request a full picker; for now this covers 95% of use.
 */

export interface ColorSwatchPickerProps {
  value: string
  onChange: (hex: string) => void
  label: string
  tooltip?: string
}

// Brand-aligned palette: pink → purple → teal → amber → green → red → black/white
const BRAND_SWATCHES: { value: string; name: string }[] = [
  { value: '#7c5cff', name: 'Studio Purple' },
  { value: '#ff5c8a', name: 'Studio Pink' },
  { value: '#38d9c4', name: 'Studio Teal' },
  { value: '#ffc857', name: 'Amber' },
  { value: '#a78bfa', name: 'Lavender' },
  { value: '#60a5fa', name: 'Sky' },
  { value: '#4ade80', name: 'Mint' },
  { value: '#0EA5E9', name: 'Cerulean' },
]

const HEX_RE = /^#([0-9a-f]{6})$/i

export default function ColorSwatchPicker({
  value,
  onChange,
  label,
  tooltip,
}: ColorSwatchPickerProps) {
  const [hex, setHex] = useState(value)
  const [open, setOpen] = useState(false)

  // Keep local hex synced when external value changes
  React.useEffect(() => {
    setHex(value)
  }, [value])

  const isValidHex = HEX_RE.test(hex)
  const normalize = (raw: string) => {
    const v = raw.trim()
    if (!v.startsWith('#')) return `#${v}`
    return v
  }
  const commitHex = () => {
    const norm = normalize(hex)
    if (HEX_RE.test(norm)) {
      onChange(norm)
      setHex(norm)
    } else {
      // Revert to current value on invalid hex
      setHex(value)
    }
  }

  const trigger = (
    <PopoverTrigger
      render={(props) => (
        <button
          {...props}
          aria-label={`${label} color picker`}
          className="w-8 h-8 rounded-lg border border-white/[0.08] bg-transparent cursor-pointer transition-all hover:scale-105 hover:border-white/30 active:scale-95 relative overflow-hidden"
          style={{
            background: `linear-gradient(135deg, ${value} 0%, ${value} 100%)`,
            boxShadow: `0 0 12px -2px ${value}66, inset 0 1px 0 rgba(255,255,255,0.15)`,
          }}
        />
      )}
    />
  )

  return (
    <Popover open={open} onOpenChange={setOpen}>
      {tooltip ? (
        <Tooltip>
          <TooltipTrigger render={(props) => <span {...props}>{trigger}</span>} />
          <TooltipContent side="top" className="max-w-[240px]">
            {tooltip}
          </TooltipContent>
        </Tooltip>
      ) : (
        trigger
      )}

      <PopoverContent
        side="top"
        sideOffset={8}
        className="w-[260px] elevation-3 border-white/[0.1] rounded-xl"
      >
        <div className="space-y-3">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] font-mono uppercase tracking-wider text-[#a78bfa]">
              {label}
            </span>
            <span className="font-mono text-[10px] text-[#4a4764]">
              swatch + hex
            </span>
          </div>

          {/* 4×2 swatch grid */}
          <div className="grid grid-cols-4 gap-2">
            {BRAND_SWATCHES.map((sw) => {
              const selected = sw.value.toLowerCase() === value.toLowerCase()
              return (
                <Tooltip key={sw.value}>
                  <TooltipTrigger
                    render={(props) => (
                      <button
                        {...props}
                        type="button"
                        onClick={() => {
                          onChange(sw.value)
                          setHex(sw.value)
                        }}
                        aria-label={sw.name}
                        className={cn(
                          'relative w-full aspect-square rounded-lg cursor-pointer transition-all',
                          'hover:scale-110 hover:shadow-[0_0_14px_-2px_currentColor]',
                          selected
                            ? 'ring-2 ring-white/80 ring-offset-2 ring-offset-[#0e0e16]'
                            : 'ring-1 ring-white/[0.08] hover:ring-white/30',
                        )}
                        style={{
                          backgroundColor: sw.value,
                          color: sw.value,
                          boxShadow: selected
                            ? `0 0 18px -2px ${sw.value}aa, inset 0 1px 0 rgba(255,255,255,0.18)`
                            : `inset 0 1px 0 rgba(255,255,255,0.12)`,
                        }}
                      >
                        {selected && (
                          <Check className="absolute inset-0 m-auto w-3.5 h-3.5 text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.6)]" />
                        )}
                      </button>
                    )}
                  />
                  <TooltipContent side="top">
                    <span className="font-mono text-[10px]">
                      <span className="text-white">{sw.name}</span>
                      <span className="text-[#807d99] ml-1.5">{sw.value}</span>
                    </span>
                  </TooltipContent>
                </Tooltip>
              )
            })}
          </div>

          {/* Hex input */}
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-[#4a4764] uppercase tracking-wider">
              Custom hex
            </label>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-[#4a4764]">#</span>
              <input
                type="text"
                value={hex.startsWith('#') ? hex.slice(1) : hex}
                onChange={(e) => setHex(`#${e.target.value.replace(/^#/, '')}`)}
                onBlur={commitHex}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    commitHex()
                  }
                }}
                maxLength={6}
                placeholder="7c5cff"
                aria-label="Hex color value"
                spellCheck={false}
                className={cn(
                  'flex-1 rounded-md border bg-white/[0.04] px-2 py-1.5 text-xs font-mono uppercase tracking-wider focus:outline-none transition-colors',
                  isValidHex
                    ? 'border-white/[0.08] text-white focus:border-[#7c5cff]/50'
                    : 'border-[#ff5c8a]/30 text-[#ff5c8a] focus:border-[#ff5c8a]/60',
                )}
              />
              {/* Live preview swatch */}
              <div
                className="w-7 h-7 rounded-md border border-white/[0.08] flex-shrink-0"
                style={{
                  backgroundColor: isValidHex ? hex : 'transparent',
                  boxShadow: isValidHex
                    ? `0 0 8px -2px ${hex}aa`
                    : 'none',
                }}
              />
            </div>
            {!isValidHex && (
              <p className="text-[10px] font-mono text-[#ff5c8a]">
                6-digit hex, e.g. 7c5cff
              </p>
            )}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
