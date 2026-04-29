import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X,
  Sparkles,
  Loader2,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  ImageOff,
  User,
  Mountain,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { libraryMatch, type LibraryMatchHit } from '@/lib/api'
import LibraryBrowser, { type LibraryBrowserChoice } from './LibraryBrowser'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import { SPRING_BOUNCY } from '@/lib/motion'

export type CastChoice = {
  id: string
  title: string
  thumbnail_url?: string | null
  shape_class?: string | null
}

interface CastPanelProps {
  open: boolean
  prompt: string
  onClose: () => void
  onConfirm: (hero: CastChoice | null, env: CastChoice | null) => void
  /** Optional initial selection (so opening the panel from the inline strip
   * preselects what the user previously cast). */
  initialHeroId?: string | null
  initialEnvId?: string | null
}

type SectionKey = 'hero' | 'env'

const PLACEHOLDER_PALETTE = [
  '#7c5cff', '#ff5c8a', '#38d9c4', '#ffc857', '#a78bfa', '#f472b6', '#4ade80', '#60a5fa',
]

function placeholderColor(seed: string): string {
  const idx = (seed.charCodeAt(0) || 0) % PLACEHOLDER_PALETTE.length
  return PLACEHOLDER_PALETTE[idx]
}

function assetTitle(hit: LibraryMatchHit): string {
  // Strip the "lib_" + category-ish prefix and title-case what's left.
  const raw = hit.id.replace(/^lib_/, '')
  const parts = raw.split('_').filter(Boolean)
  // Drop a leading duplicate of the subject (e.g. "lib_cat_cat_box_meme" → "cat_box_meme")
  if (parts[0] && hit.subject && parts[0].toLowerCase() === hit.subject.toLowerCase()) {
    parts.shift()
  }
  if (parts.length === 0) return hit.subject || hit.id
  return parts
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())
    .join(' ')
}

const SHAPE_CLASS_STYLES: Record<string, { label: string; text: string; bg: string; border: string }> = {
  flat_map: {
    label: 'flat map',
    text: 'text-[#ffc857]',
    bg: 'bg-[#ffc857]/10',
    border: 'border-[#ffc857]/30',
  },
  '3d_terrain': {
    label: '3D terrain',
    text: 'text-[#38d9c4]',
    bg: 'bg-[#38d9c4]/10',
    border: 'border-[#38d9c4]/30',
  },
  character_upright: {
    label: 'upright',
    text: 'text-[#a78bfa]',
    bg: 'bg-[#a78bfa]/10',
    border: 'border-[#a78bfa]/30',
  },
  character_quadruped: {
    label: 'quadruped',
    text: 'text-[#a78bfa]',
    bg: 'bg-[#a78bfa]/10',
    border: 'border-[#a78bfa]/30',
  },
}

export default function CastPanel({
  open,
  prompt,
  onClose,
  onConfirm,
  initialHeroId,
  initialEnvId,
}: CastPanelProps) {
  const [heroes, setHeroes] = useState<LibraryMatchHit[]>([])
  const [envs, setEnvs] = useState<LibraryMatchHit[]>([])
  const [selectedHero, setSelectedHero] = useState<string | null>(null)
  const [selectedEnv, setSelectedEnv] = useState<string | null>(null)
  const [userPickedHero, setUserPickedHero] = useState(false)
  const [userPickedEnv, setUserPickedEnv] = useState(false)
  const [focusedSection, setFocusedSection] = useState<SectionKey>('hero')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // v1.3.7 — paginated library browser. When a section's "Browse library"
  // button is clicked, opens the modal scoped to that category.
  const [browserCategory, setBrowserCategory] = useState<SectionKey | null>(null)

  useEffect(() => {
    if (initialHeroId) setSelectedHero(initialHeroId)
    if (initialEnvId) setSelectedEnv(initialEnvId)
  }, [initialHeroId, initialEnvId])

  // When the browser confirms a choice, append it to the current section's
  // hits list (so it shows as a card) and select it.
  const handleBrowserChoose = useCallback(
    (choice: LibraryBrowserChoice) => {
      const synthHit: LibraryMatchHit = {
        id: choice.id,
        // v1.4 follow-up — preserve the asset's real category (vehicle/prop
        // are now allowed in the hero slot, not just character).
        category: choice.category || (browserCategory === 'hero' ? 'character' : 'environment'),
        subject: choice.subject || undefined,
        shape_class: choice.shape_class || undefined,
        subject_tags: [],
        biome_hints: [],
        score: 9999,
        thumbnail_url: choice.thumbnail_url || undefined,
        path: undefined,
      }
      if (browserCategory === 'hero') {
        setHeroes((prev) =>
          prev.find((h) => h.id === choice.id) ? prev : [synthHit, ...prev],
        )
        setSelectedHero(choice.id)
        setUserPickedHero(true)
      } else if (browserCategory === 'env') {
        setEnvs((prev) =>
          prev.find((e) => e.id === choice.id) ? prev : [synthHit, ...prev],
        )
        setSelectedEnv(choice.id)
        setUserPickedEnv(true)
      }
      setBrowserCategory(null)
    },
    [browserCategory],
  )

  const containerRef = useRef<HTMLDivElement | null>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)

  const load = useCallback(async () => {
    if (!prompt.trim()) return
    setLoading(true)
    setError(null)
    setHeroes([])
    setEnvs([])
    setSelectedHero(null)
    setSelectedEnv(null)
    setUserPickedHero(false)
    setUserPickedEnv(false)
    try {
      const [h, e] = await Promise.all([
        // v1.4 follow-up — hero slot accepts character + vehicle + prop
        // (anything that's NOT environment or HDRI). Comma-separated
        // categories supported by /api/library/match (Wave-D).
        libraryMatch({ q: prompt.trim(), category: 'character,vehicle,prop', limit: 12 }),
        libraryMatch({ q: prompt.trim(), category: 'environment', limit: 12 }),
      ])
      setHeroes(h.hits || [])
      setEnvs(e.hits || [])
      // Prefer caller-supplied initial selections when present in the match
      // results; otherwise fall back to the top-scored hit.
      const heroInitial =
        (initialHeroId && h.hits?.find((x) => x.id === initialHeroId)?.id) ||
        h.hits?.[0]?.id ||
        null
      const envInitial =
        (initialEnvId && e.hits?.find((x) => x.id === initialEnvId)?.id) ||
        e.hits?.[0]?.id ||
        null
      setSelectedHero(heroInitial)
      setSelectedEnv(envInitial)
    } catch (err: any) {
      setError(err?.message || 'Failed to load cast matches')
    } finally {
      setLoading(false)
    }
  }, [prompt])

  useEffect(() => {
    if (open) {
      previouslyFocused.current = document.activeElement as HTMLElement | null
      load()
    }
  }, [open, load])

  // Focus restore on close
  useEffect(() => {
    return () => {
      if (!open && previouslyFocused.current) {
        previouslyFocused.current.focus?.()
      }
    }
  }, [open])

  // Scroll lock
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  const canRender = Boolean(selectedHero && selectedEnv)
  const bothEmpty = !loading && !error && heroes.length === 0 && envs.length === 0

  const handleConfirm = useCallback(() => {
    if (!canRender) return
    const heroHit = heroes.find((h) => h.id === selectedHero)
    const envHit = envs.find((e) => e.id === selectedEnv)
    const heroChoice: CastChoice | null = heroHit
      ? {
          id: heroHit.id,
          title: assetTitle(heroHit),
          thumbnail_url: heroHit.thumbnail_url ?? null,
          shape_class: heroHit.shape_class ?? null,
        }
      : null
    const envChoice: CastChoice | null = envHit
      ? {
          id: envHit.id,
          title: assetTitle(envHit),
          thumbnail_url: envHit.thumbnail_url ?? null,
          shape_class: envHit.shape_class ?? null,
        }
      : null
    onConfirm(heroChoice, envChoice)
  }, [canRender, selectedHero, selectedEnv, heroes, envs, onConfirm])

  // Keyboard: Escape / Enter / Tab / arrows
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key === 'Enter') {
        if (canRender && !loading && !error) {
          e.preventDefault()
          handleConfirm()
        }
        return
      }
      if (e.key === 'Tab') {
        e.preventDefault()
        setFocusedSection((s) => (s === 'hero' ? 'env' : 'hero'))
        return
      }
      if (
        e.key === 'ArrowLeft' ||
        e.key === 'ArrowRight' ||
        e.key === 'ArrowUp' ||
        e.key === 'ArrowDown'
      ) {
        const list = focusedSection === 'hero' ? heroes : envs
        if (list.length === 0) return
        e.preventDefault()
        const currentId = focusedSection === 'hero' ? selectedHero : selectedEnv
        const dir =
          e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : -1
        const idx = list.findIndex((h) => h.id === currentId)
        const next =
          idx < 0
            ? dir > 0
              ? 0
              : list.length - 1
            : (idx + dir + list.length) % list.length
        const nextId = list[next].id
        if (focusedSection === 'hero') {
          setSelectedHero(nextId)
          setUserPickedHero(true)
        } else {
          setSelectedEnv(nextId)
          setUserPickedEnv(true)
        }
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [
    open,
    onClose,
    focusedSection,
    heroes,
    envs,
    selectedHero,
    selectedEnv,
    canRender,
    loading,
    error,
    handleConfirm,
  ])

  const heroTitle = useMemo(() => {
    const h = heroes.find((x) => x.id === selectedHero)
    return h ? assetTitle(h) : null
  }, [heroes, selectedHero])

  const envTitle = useMemo(() => {
    const e = envs.find((x) => x.id === selectedEnv)
    return e ? assetTitle(e) : null
  }, [envs, selectedEnv])

  const selectHero = useCallback((id: string) => {
    setSelectedHero(id)
    setUserPickedHero(true)
    setFocusedSection('env')
  }, [])

  const selectEnv = useCallback((id: string) => {
    setSelectedEnv(id)
    setUserPickedEnv(true)
  }, [])

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-[90] bg-black/70 backdrop-blur-md"
            onClick={onClose}
          />

          {/* v1.4.3 polish — outer wrapper supports vertical scroll on
              ultra-short viewports (landscape phones); items-start on mobile
              so the header is always visible from the top. */}
          <div
            className="fixed inset-0 z-[100] flex items-start sm:items-center justify-center p-4 overflow-y-auto pointer-events-none"
            role="dialog"
            aria-modal="true"
            aria-labelledby="castpanel-title"
          >
            <motion.div
              key="panel"
              ref={containerRef}
              tabIndex={-1}
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ type: 'spring', bounce: 0.15, duration: 0.35 }}
              className="pointer-events-auto glass rounded-2xl w-full max-w-5xl max-h-[calc(100vh-2rem)] my-auto flex flex-col overflow-hidden border border-white/[0.08] shadow-[0_25px_60px_rgba(0,0,0,0.6)] outline-none"
            >
              {/* Header — flex-shrink-0 so the Render button always stays
                  visible even when body content is tall. */}
              <div className="flex-shrink-0 flex items-start gap-4 px-6 py-5 border-b border-white/[0.05]">
                <div className="flex-1 space-y-1.5">
                  <span className="section-tag section-tag--primary font-mono text-[10px]">
                    // cast your scene
                  </span>
                  <h2
                    id="castpanel-title"
                    className="text-lg sm:text-xl font-bold text-gradient"
                  >
                    Pick character + environment
                  </h2>
                  <p className="text-xs sm:text-sm text-[#807d99]">
                    Rendering:{' '}
                    <em className="text-[#a78bfa] not-italic font-medium">"{prompt}"</em>
                    <span className="hidden sm:inline ml-2 text-[11px] font-mono text-[#4a4764]">
                      · Tab to switch section · ← → select · Enter to render · Esc to cancel
                    </span>
                  </p>
                </div>
                <button
                  onClick={onClose}
                  aria-label="Close cast panel"
                  className="p-2 rounded-xl hover:bg-white/[0.05] text-[#807d99] hover:text-white transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Body — min-h-0 lets the body shrink below its intrinsic
                  content height so internal scroll engages properly. Without
                  it, flex-1 forces the parent past its max-h cap and the
                  footer gets pushed off-screen (the bug we're fixing). */}
              <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-6 py-5 space-y-6">
                {loading && <LoadingState />}

                {!loading && error && (
                  <ErrorState message={error} onRetry={load} />
                )}

                {!loading && !error && bothEmpty && (
                  <EmptyState prompt={prompt} />
                )}

                {!loading && !error && !bothEmpty && (
                  <>
                    <CastSection
                      kind="hero"
                      index={1}
                      title="Character"
                      Icon={User}
                      accent="#a78bfa"
                      focused={focusedSection === 'hero'}
                      onFocus={() => setFocusedSection('hero')}
                      hits={heroes}
                      selectedId={selectedHero}
                      userPicked={userPickedHero}
                      onSelect={selectHero}
                      onBrowse={() => setBrowserCategory('hero')}
                    />
                    <CastSection
                      kind="env"
                      index={2}
                      title="Environment"
                      Icon={Mountain}
                      accent="#38d9c4"
                      focused={focusedSection === 'env'}
                      onFocus={() => setFocusedSection('env')}
                      hits={envs}
                      selectedId={selectedEnv}
                      userPicked={userPickedEnv}
                      onSelect={selectEnv}
                      onBrowse={() => setBrowserCategory('env')}
                    />
                  </>
                )}
              </div>

              {/* Footer — flex-shrink-0 locks the Render button row so it
                  can't get squashed when body content is tall. */}
              <div className="flex-shrink-0 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 px-6 py-4 border-t border-white/[0.05] bg-white/[0.02]">
                <div className="text-[11px] font-mono text-[#4a4764] sm:max-w-[50%] truncate">
                  {canRender && heroTitle && envTitle ? (
                    <>
                      Rendering with{' '}
                      <span className="text-[#a78bfa]">{heroTitle}</span> on{' '}
                      <span className="text-[#38d9c4]">{envTitle}</span>
                    </>
                  ) : (
                    <>Tab switches · Enter renders · Esc cancels</>
                  )}
                </div>
                <div className="flex gap-2 sm:gap-3">
                  <button
                    onClick={onClose}
                    className="sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-semibold border border-white/[0.08] bg-white/[0.03] text-[#807d99] hover:bg-white/[0.06] hover:text-white transition-all"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleConfirm}
                    disabled={!canRender || loading || Boolean(error)}
                    className={cn(
                      'flex-1 sm:flex-initial inline-flex items-center justify-center gap-2 px-5 sm:px-6 py-3 rounded-xl font-semibold text-sm transition-all',
                      !canRender || loading || error
                        ? 'bg-white/[0.04] text-[#4a4764] cursor-not-allowed'
                        : 'btn-generate',
                    )}
                  >
                    <Sparkles className="w-4 h-4" />
                    Render Scene
                    <span className="text-[11px] font-mono opacity-75">↵</span>
                  </button>
                </div>
              </div>
            </motion.div>
          </div>

          {/* v1.4 follow-up — hero browser now spans character + vehicle +
              prop (anything except environment / hdri). Title reflects the
              wider net so users understand the pool. */}
          <LibraryBrowser
            open={browserCategory !== null}
            category={browserCategory === 'env' ? 'environment' : 'character,vehicle,prop'}
            title={browserCategory === 'env' ? 'Browse environments' : 'Browse characters & vehicles'}
            onClose={() => setBrowserCategory(null)}
            onChoose={handleBrowserChoose}
          />
        </>
      )}
    </AnimatePresence>
  )
}

function CastSection({
  kind,
  index,
  title,
  Icon,
  accent,
  focused,
  onFocus,
  hits,
  selectedId,
  userPicked,
  onSelect,
  onBrowse,
}: {
  kind: SectionKey
  index: number
  title: string
  Icon: React.ComponentType<any>
  accent: string
  focused: boolean
  onFocus: () => void
  hits: LibraryMatchHit[]
  selectedId: string | null
  userPicked: boolean
  onSelect: (id: string) => void
  onBrowse: () => void
}) {
  return (
    <section
      onClick={onFocus}
      className={cn(
        'rounded-2xl p-4 sm:p-5 transition-all duration-200 border',
        focused
          ? 'bg-white/[0.02]'
          : 'bg-transparent border-white/[0.04]',
      )}
      style={
        focused
          ? {
              borderColor: `${accent}66`,
              boxShadow: `0 0 24px ${accent}20`,
            }
          : undefined
      }
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4" style={{ color: accent }} />
          <h3 className="text-base sm:text-lg font-semibold text-white">
            <span style={{ color: accent }} className="font-mono mr-2">
              {index}.
            </span>
            {title}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-[#4a4764]">
            {hits.length} match{hits.length === 1 ? '' : 'es'}
          </span>
          {/* v1.3.7 — open the paginated library browser scoped to this category */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onBrowse()
            }}
            aria-label={`Browse all ${title.toLowerCase()}s in the library`}
            className="px-2.5 py-1 rounded-full text-[10px] font-mono font-semibold border border-white/[0.08] bg-white/[0.03] text-[#a78bfa] hover:bg-[#7c5cff]/15 hover:text-white hover:border-[#7c5cff]/30 transition-all"
          >
            Browse library
          </button>
        </div>
      </div>

      {hits.length === 0 ? (
        <div className="rounded-xl border border-white/[0.05] bg-white/[0.02] px-4 py-6 text-center text-sm text-[#807d99]">
          No {title.toLowerCase()} matches — we'll let AI fall back.
        </div>
      ) : (
        <AssetGrid
          hits={hits}
          selectedId={selectedId}
          userPicked={userPicked}
          accent={accent}
          kind={kind}
          onSelect={onSelect}
        />
      )}
    </section>
  )
}

function AssetGrid({
  hits,
  selectedId,
  userPicked,
  accent,
  kind,
  onSelect,
}: {
  hits: LibraryMatchHit[]
  selectedId: string | null
  userPicked: boolean
  accent: string
  kind: SectionKey
  onSelect: (id: string) => void
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2 sm:gap-3">
      {hits.map((hit, i) => (
        <AssetCard
          key={hit.id}
          hit={hit}
          selected={selectedId === hit.id}
          // "AI pick" visual indicator = backend returned this at index 0 (top score)
          isAutoPick={i === 0}
          userPicked={userPicked && selectedId === hit.id}
          accent={accent}
          kind={kind}
          onSelect={() => onSelect(hit.id)}
        />
      ))}
    </div>
  )
}

function AssetCard({
  hit,
  selected,
  isAutoPick,
  userPicked,
  accent,
  kind,
  onSelect,
}: {
  hit: LibraryMatchHit
  selected: boolean
  isAutoPick: boolean
  userPicked: boolean
  accent: string
  kind: SectionKey
  onSelect: () => void
}) {
  const [thumbFailed, setThumbFailed] = useState(false)
  const title = assetTitle(hit)
  const shape = hit.shape_class ? SHAPE_CLASS_STYLES[hit.shape_class] : null

  // v1.4 polish — Phase 6 selected state. User-picked card gets the
  // rotating gradient-border treatment from Phase 3 (premium feel) plus a
  // spring-in checkmark badge.
  const frameClass = userPicked
    ? 'gradient-border-rotate border border-transparent shadow-[0_8px_30px_-8px_rgba(0,0,0,0.6),_0_0_28px_-2px_rgba(255,92,138,0.45)]'
    : selected
      ? 'border border-white/20'
      : 'border border-white/[0.06] hover:border-white/[0.15] hover:shadow-[0_8px_22px_-6px_rgba(0,0,0,0.5),_0_0_18px_-4px_rgba(124,92,255,0.22)]'

  const frameStyle: React.CSSProperties = {}
  if (selected && !userPicked) {
    frameStyle.borderColor = `${accent}80`
    frameStyle.boxShadow = `0 0 18px ${accent}33`
  }

  return (
    <motion.button
      type="button"
      onClick={onSelect}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.18 }}
      className={cn(
        'group relative text-left rounded-xl overflow-hidden transition-shadow duration-200',
        'flex flex-col bg-[#0a0a10]',
        frameClass,
      )}
      style={frameStyle}
      aria-pressed={selected}
      data-user-picked={userPicked || undefined}
      data-auto-pick={isAutoPick || undefined}
    >
      {/* AI pick badge */}
      {isAutoPick && (
        <div
          className={cn(
            'absolute top-1.5 left-1.5 z-10 px-1.5 py-0.5 rounded-full text-[9px] font-semibold flex items-center gap-1 transition-all',
            userPicked ? 'opacity-60' : 'opacity-100',
          )}
          style={{
            background: accent,
            color: '#0a0a10',
            boxShadow: `0 0 10px ${accent}66`,
          }}
        >
          <Sparkles className="w-2.5 h-2.5" /> AI
        </div>
      )}

      {/* v1.4 polish — spring-bouncy checkmark scales in on selection */}
      <AnimatePresence>
        {userPicked && (
          <motion.div
            key="userpicked-pill"
            initial={{ opacity: 0, scale: 0.4 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.5 }}
            transition={SPRING_BOUNCY}
            className="absolute top-1.5 right-1.5 z-10 px-1.5 py-0.5 rounded-full bg-[#ff5c8a] text-white text-[9px] font-semibold flex items-center gap-1 shadow-[0_0_12px_rgba(255,92,138,0.7)]"
          >
            <CheckCircle2 className="w-2.5 h-2.5" /> Pick
          </motion.div>
        )}
      </AnimatePresence>

      {/* Thumbnail */}
      <div className="aspect-square bg-[#0a0a10] relative overflow-hidden">
        {thumbFailed || !hit.thumbnail_url ? (
          <ThumbnailPlaceholder title={title} />
        ) : (
          <img
            src={hit.thumbnail_url}
            alt={title}
            loading="lazy"
            onError={() => setThumbFailed(true)}
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
          />
        )}
        <div className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-black/70 via-black/20 to-transparent pointer-events-none" />
      </div>

      {/* Meta */}
      <div className="px-2 py-2 space-y-1">
        <div className="flex items-center gap-1 min-w-0">
          <span className="text-[11px] sm:text-xs font-semibold text-white line-clamp-1">
            {title}
          </span>
          {/* v1.4 polish — debug ID via tooltip, not native title */}
          <Tooltip>
            <TooltipTrigger
              render={(props) => (
                <span
                  {...props}
                  aria-label={`Asset ID: ${hit.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="flex-shrink-0 inline-flex w-3 h-3 rounded-full border border-white/[0.08] bg-white/[0.02] text-[7px] font-mono text-[#3a3850] hover:text-[#807d99] hover:border-white/[0.18] cursor-help items-center justify-center transition-colors"
                >
                  ?
                </span>
              )}
            />
            <TooltipContent>
              <span className="font-mono text-[10px]">{hit.id}</span>
            </TooltipContent>
          </Tooltip>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {shape && (
            <span
              className={cn(
                'text-[9px] font-mono px-1.5 py-0.5 rounded border',
                shape.bg,
                shape.text,
                shape.border,
              )}
            >
              {shape.label}
            </span>
          )}
          {!shape && hit.subject && (
            <span className="text-[9px] font-mono text-[#4a4764] truncate">
              {hit.subject}
            </span>
          )}
        </div>
      </div>
    </motion.button>
  )
}

function ThumbnailPlaceholder({ title }: { title: string }) {
  const color = placeholderColor(title)
  const letter = (title.trim().charAt(0) || '?').toUpperCase()
  return (
    <div
      className="w-full h-full flex items-center justify-center relative"
      style={{
        backgroundImage: `linear-gradient(135deg, ${color}33, ${color}11)`,
        backgroundColor: '#12121e',
      }}
    >
      <span className="text-4xl font-bold opacity-90" style={{ color }}>
        {letter}
      </span>
      <ImageOff className="absolute bottom-1 right-1 w-3 h-3 text-white/20" />
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3">
      <Loader2 className="w-6 h-6 animate-spin text-[#7c5cff]" />
      <p className="text-sm font-mono text-[#4a4764]">Casting scene…</p>
    </div>
  )
}

function EmptyState({ prompt }: { prompt: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 gap-4 text-center max-w-md mx-auto">
      <div className="w-14 h-14 rounded-2xl bg-[#ffc857]/10 border border-[#ffc857]/20 flex items-center justify-center">
        <AlertCircle className="w-6 h-6 text-[#ffc857]" />
      </div>
      <div className="space-y-2">
        <h3 className="text-base font-semibold text-white">
          No library matches for <em className="text-[#a78bfa] not-italic">"{prompt}"</em>
        </h3>
        <p className="text-sm text-[#807d99]">
          Hit <em className="not-italic text-white/80">Cancel</em> and try a more specific prompt,
          or render anyway — the AI will fall back to its own search.
        </p>
      </div>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 gap-4 text-center max-w-md mx-auto">
      <div className="w-14 h-14 rounded-2xl bg-[#ff5c8a]/10 border border-[#ff5c8a]/20 flex items-center justify-center">
        <AlertCircle className="w-6 h-6 text-[#ff5c8a]" />
      </div>
      <div className="space-y-1">
        <h3 className="text-base font-semibold text-white">Couldn't load cast</h3>
        <p className="text-sm text-[#807d99]">{message}</p>
      </div>
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-white/[0.08] bg-white/[0.03] text-white hover:bg-white/[0.06] text-sm font-semibold transition-all"
      >
        <RefreshCw className="w-3.5 h-3.5" /> Retry
      </button>
    </div>
  )
}
