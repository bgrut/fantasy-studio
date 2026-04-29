import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X,
  Search,
  ImageOff,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  RefreshCw,
  CheckCircle2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  libraryBrowse,
  type LibraryBrowseAsset,
  type LibraryBrowseResponse,
} from '@/lib/api'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * v1.3.7 — Paginated library browser. Opens from the Cast panel slot's
 * "Change" / "Browse library" affordance. Shows up to 12 cards per page
 * with substring search (server-side) and a category-tag filter for
 * environments. Selecting an asset closes the modal and emits the choice.
 */

export type LibraryBrowserChoice = {
  id: string
  title: string
  thumbnail_url?: string | null
  shape_class?: string | null
  subject?: string | null
  // v1.4 follow-up — preserve actual category since the hero browser now
  // mixes character/vehicle/prop and the caller needs to know which one
  // was picked.
  category?: string | null
}

interface Props {
  open: boolean
  /** Restrict results to one library category. Required. */
  category: 'character' | 'environment' | 'prop' | 'vehicle' | 'hdri' | string
  /** Section title shown in the header — e.g. "Pick a character". */
  title?: string
  onClose: () => void
  onChoose: (choice: LibraryBrowserChoice) => void
}

const PER_PAGE = 12
const SEARCH_DEBOUNCE_MS = 220

const PALETTE = ['#7c5cff', '#ff5c8a', '#38d9c4', '#ffc857', '#a78bfa', '#f472b6', '#4ade80', '#60a5fa']
function placeholderColor(seed: string): string {
  return PALETTE[(seed.charCodeAt(0) || 0) % PALETTE.length]
}

function prettifyAssetTitle(asset: LibraryBrowseAsset): string {
  const raw = asset.id.replace(/^lib_/, '')
  const parts = raw.split('_').filter(Boolean)
  // De-duplicate a leading subject prefix (e.g. lib_cat_cat_box_meme → cat_box_meme)
  if (parts[0] && asset.subject && parts[0].toLowerCase() === asset.subject.toLowerCase()) {
    parts.shift()
  }
  if (parts.length === 0) return asset.subject || asset.id
  return parts
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())
    .join(' ')
}

const SHAPE_CLASS_LABELS: Record<string, { label: string; text: string; bg: string; border: string }> = {
  flat_map:           { label: 'flat map',     text: 'text-[#ffc857]', bg: 'bg-[#ffc857]/10', border: 'border-[#ffc857]/30' },
  '3d_terrain':       { label: '3D terrain',   text: 'text-[#38d9c4]', bg: 'bg-[#38d9c4]/10', border: 'border-[#38d9c4]/30' },
  character_upright:  { label: 'upright',      text: 'text-[#a78bfa]', bg: 'bg-[#a78bfa]/10', border: 'border-[#a78bfa]/30' },
  character_quadruped:{ label: 'quadruped',    text: 'text-[#a78bfa]', bg: 'bg-[#a78bfa]/10', border: 'border-[#a78bfa]/30' },
}

export default function LibraryBrowser({ open, category, title, onClose, onChoose }: Props) {
  const [page, setPage] = useState(1)
  const [searchInput, setSearchInput] = useState('')
  const [searchActive, setSearchActive] = useState('')
  const [tagFilter, setTagFilter] = useState<string>('')
  const [data, setData] = useState<LibraryBrowseResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const previouslyFocused = useRef<HTMLElement | null>(null)
  const requestId = useRef(0)

  // Reset on open
  useEffect(() => {
    if (open) {
      previouslyFocused.current = document.activeElement as HTMLElement | null
      setPage(1)
      setSearchInput('')
      setSearchActive('')
      setTagFilter('')
      setData(null)
      setError(null)
    }
  }, [open, category])

  // Debounce search input
  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => {
      setSearchActive(searchInput.trim())
      setPage(1)
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [searchInput, open])

  // Scroll lock + focus restore
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
      previouslyFocused.current?.focus?.()
    }
  }, [open])

  // Esc closes
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Combine server search with optional client-side biome_hints filter
  // (because the backend's `search` already covers tags; tagFilter is a
  // user-facing convenience for canonical environment categories).
  const effectiveSearch = useMemo(() => {
    if (tagFilter && !searchActive) return tagFilter
    if (tagFilter && searchActive) return `${tagFilter} ${searchActive}`
    return searchActive
  }, [tagFilter, searchActive])

  // Fetch
  useEffect(() => {
    if (!open) return
    const myId = ++requestId.current
    setLoading(true)
    setError(null)
    libraryBrowse({
      category,
      page,
      per_page: PER_PAGE,
      search: effectiveSearch || undefined,
    })
      .then((res) => {
        if (myId !== requestId.current) return
        setData(res)
      })
      .catch((e: any) => {
        if (myId !== requestId.current) return
        setError(e?.message || 'Failed to load library')
      })
      .finally(() => {
        if (myId === requestId.current) setLoading(false)
      })
  }, [open, category, page, effectiveSearch])

  // Environment-only canonical tag filter chips
  const envTags = useMemo(
    () =>
      category === 'environment'
        ? [
            { id: '', label: 'All' },
            { id: 'desert', label: 'Desert' },
            { id: 'mountain', label: 'Mountain' },
            { id: 'forest', label: 'Forest' },
            { id: 'arctic', label: 'Arctic' },
            { id: 'ocean', label: 'Ocean' },
            { id: 'city', label: 'Urban' },
            { id: 'canyon', label: 'Canyon' },
            { id: 'studio', label: 'Studio' },
          ]
        : [],
    [category],
  )

  const totalPages = data?.pages ?? 0
  const total = data?.total ?? 0
  const headline = title || `Browse ${category}s`

  const choose = useCallback(
    (asset: LibraryBrowseAsset) => {
      onChoose({
        id: asset.id,
        title: prettifyAssetTitle(asset),
        thumbnail_url: asset.thumbnail_url ?? null,
        shape_class: asset.shape_class ?? null,
        subject: asset.subject ?? null,
        category: asset.category ?? null,
      })
    },
    [onChoose],
  )

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="bg"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-[110] bg-black/70 backdrop-blur-md"
            onClick={onClose}
          />
          {/* v1.4.3 polish — same viewport-aware sizing as CastPanel. */}
          <div
            className="fixed inset-0 z-[120] flex items-start sm:items-center justify-center p-4 overflow-y-auto pointer-events-none"
            role="dialog"
            aria-modal="true"
            aria-labelledby="lib-browser-title"
          >
            <motion.div
              key="panel"
              initial={{ opacity: 0, scale: 0.96, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ type: 'spring', bounce: 0.15, duration: 0.35 }}
              className="pointer-events-auto glass rounded-2xl w-full max-w-5xl max-h-[calc(100vh-2rem)] my-auto flex flex-col overflow-hidden border border-white/[0.08] shadow-[0_25px_60px_rgba(0,0,0,0.6)] outline-none"
            >
              {/* Header — flex-shrink-0 */}
              <div className="flex-shrink-0 flex flex-col gap-3 px-6 py-4 border-b border-white/[0.05]">
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <span className="section-tag section-tag--primary font-mono text-[10px]">// library</span>
                    <h2 id="lib-browser-title" className="text-lg sm:text-xl font-bold text-gradient mt-1">
                      {headline}
                    </h2>
                  </div>
                  <button
                    onClick={onClose}
                    aria-label="Close library browser"
                    className="p-2 rounded-xl hover:bg-white/[0.05] text-[#807d99] hover:text-white transition-colors flex-shrink-0"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <div className="flex flex-col sm:flex-row gap-2">
                  {/* v1.4 polish — search input gets the gradient-border-rotate
                      treatment when focused; subtle on rest. */}
                  <div className="relative flex-1 group">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#4a4764] group-focus-within:text-[#a78bfa] transition-colors z-10" />
                    <input
                      autoFocus
                      value={searchInput}
                      onChange={(e) => setSearchInput(e.target.value)}
                      placeholder={`Search ${category}s by name or tag…`}
                      className="relative w-full rounded-xl bg-white/[0.03] border border-white/[0.05] pl-9 pr-3 py-2.5 text-sm text-white placeholder:text-[#4a4764] focus:outline-none focus:border-[#7c5cff]/40 focus:bg-white/[0.05] focus:shadow-[0_0_0_3px_rgba(124,92,255,0.10),_0_0_24px_-6px_rgba(255,92,138,0.25)] transition-all"
                    />
                    {searchInput && (
                      <button
                        type="button"
                        onClick={() => setSearchInput('')}
                        aria-label="Clear search"
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-[#4a4764] hover:text-white hover:bg-white/[0.06] transition-colors z-10"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                  {envTags.length > 0 && (
                    <Select
                      value={tagFilter || 'all'}
                      onValueChange={(v: string) => {
                        setTagFilter(v === 'all' ? '' : v)
                        setPage(1)
                      }}
                    >
                      <SelectTrigger className="rounded-xl bg-white/[0.03] border border-white/[0.05] py-2.5 px-3 text-sm text-[#a78bfa] hover:bg-white/[0.05] hover:border-[#7c5cff]/30 font-mono min-w-[140px] h-auto">
                        <SelectValue placeholder="All" />
                      </SelectTrigger>
                      <SelectContent className="elevation-3 border-white/[0.1] rounded-xl">
                        {envTags.map((t) => (
                          <SelectItem
                            key={t.id || 'all'}
                            value={t.id || 'all'}
                            className="font-mono text-xs hover:bg-[#7c5cff]/10 focus:bg-[#7c5cff]/15 text-[#807d99] focus:text-white data-[selected]:text-[#a78bfa]"
                          >
                            {t.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              </div>

              {/* Body — min-h-0 critical for flex-1 + overflow-auto to
                  actually engage internal scroll. */}
              <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-6 py-5">
                {loading && <SkeletonGrid />}
                {!loading && error && <ErrorBlock message={error} onRetry={() => setPage((p) => p)} />}
                {!loading && data && !error && (data.assets.length === 0 ? (
                  <Empty
                    effectiveSearch={effectiveSearch}
                    onClear={() => {
                      setSearchInput('')
                      setTagFilter('')
                      setPage(1)
                    }}
                  />
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
                    {data.assets.map((a) => (
                      <Card key={a.id} asset={a} onChoose={() => choose(a)} />
                    ))}
                  </div>
                ))}
              </div>

              {/* Footer — flex-shrink-0 keeps the pagination row visible. */}
              <div className="flex-shrink-0 flex items-center justify-between gap-3 px-6 py-3 border-t border-white/[0.05] bg-white/[0.02] text-xs font-mono text-[#807d99]">
                <span>
                  {total > 0 ? (
                    <>
                      Showing{' '}
                      <span className="text-white">
                        {(data!.page - 1) * data!.per_page + 1}-
                        {Math.min(data!.page * data!.per_page, total)}
                      </span>{' '}
                      of <span className="text-white">{total}</span>
                    </>
                  ) : loading ? (
                    'Loading…'
                  ) : (
                    'No matches'
                  )}
                </span>
                <FilmstripPagination
                  page={data?.page ?? page}
                  totalPages={totalPages}
                  disabled={loading}
                  onChange={(next) => setPage(next)}
                />
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  )
}

function Card({
  asset,
  onChoose,
}: {
  asset: LibraryBrowseAsset
  onChoose: () => void
}) {
  const [thumbFailed, setThumbFailed] = useState(false)
  const title = prettifyAssetTitle(asset)
  const shape = asset.shape_class ? SHAPE_CLASS_LABELS[asset.shape_class] : null

  return (
    // v1.4 polish — lift + shadow deepen + thumb scale on hover. 180ms.
    <motion.button
      type="button"
      onClick={onChoose}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.18 }}
      className={cn(
        'group relative text-left rounded-xl overflow-hidden border transition-shadow duration-200 flex flex-col bg-[#0a0a10]',
        'border-white/[0.06] hover:border-[#7c5cff]/40',
        'hover:shadow-[0_8px_24px_-6px_rgba(0,0,0,0.5),_0_0_22px_-4px_rgba(124,92,255,0.28)]',
      )}
    >
      <div className="aspect-square bg-[#0a0a10] relative overflow-hidden">
        {thumbFailed || !asset.thumbnail_url ? (
          <Placeholder title={title} />
        ) : (
          <img
            src={asset.thumbnail_url}
            alt={title}
            loading="lazy"
            onError={() => setThumbFailed(true)}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
          />
        )}
        <div className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-black/70 via-black/20 to-transparent pointer-events-none" />
        {/* Hover-revealed Use button */}
        <div className="absolute inset-0 flex items-end justify-end p-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="px-2.5 py-1 rounded-full bg-[#7c5cff] text-white text-[10px] font-semibold shadow-[0_0_14px_rgba(124,92,255,0.6)]">
            use
          </span>
        </div>
      </div>
      <div className="px-2 py-2 space-y-1">
        <div className="flex items-center gap-1 min-w-0">
          <span className="text-[11px] sm:text-xs font-semibold text-white line-clamp-1">{title}</span>
          <Tooltip>
            <TooltipTrigger
              render={(props) => (
                <span
                  {...props}
                  aria-label={`Asset ID: ${asset.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="flex-shrink-0 inline-flex w-3 h-3 rounded-full border border-white/[0.08] bg-white/[0.02] text-[7px] font-mono text-[#3a3850] hover:text-[#807d99] hover:border-white/[0.18] cursor-help items-center justify-center transition-colors"
                >
                  ?
                </span>
              )}
            />
            <TooltipContent>
              <span className="font-mono text-[10px]">{asset.id}</span>
            </TooltipContent>
          </Tooltip>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {shape && (
            <span className={cn('text-[9px] font-mono px-1.5 py-0.5 rounded border', shape.bg, shape.text, shape.border)}>
              {shape.label}
            </span>
          )}
          {!shape && asset.subject && (
            <span className="text-[9px] font-mono text-[#4a4764] truncate">{asset.subject}</span>
          )}
        </div>
      </div>
    </motion.button>
  )
}

function Placeholder({ title }: { title: string }) {
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
      <span className="text-4xl font-bold opacity-90" style={{ color }}>{letter}</span>
      <ImageOff className="absolute bottom-1 right-1 w-3 h-3 text-white/20" />
    </div>
  )
}

// v1.4 polish — Phase 6 skeleton grid replaces the spinner. 12 brand-tinted
// shimmer cards hold the grid's exact shape so layout doesn't shift on
// content arrival.
function SkeletonGrid({ count = 12 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl overflow-hidden border border-white/[0.06] bg-[#0a0a10] flex flex-col"
        >
          <Skeleton
            className="aspect-square w-full rounded-none bg-gradient-to-br from-[#7c5cff]/[0.08] via-[#ff5c8a]/[0.06] to-[#38d9c4]/[0.05]"
            style={{ animationDelay: `${(i % 4) * 90}ms` }}
          />
          <div className="px-2 py-2 space-y-1.5">
            <Skeleton className="h-3 w-3/4 bg-white/[0.05]" />
            <Skeleton className="h-2 w-1/3 bg-white/[0.04]" />
          </div>
        </div>
      ))}
    </div>
  )
}

function Empty({
  effectiveSearch,
  onClear,
}: {
  effectiveSearch: string
  onClear: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-center max-w-sm mx-auto">
      {/* Friendly cube + magnifier illustration */}
      <div className="relative w-16 h-16 flex items-center justify-center">
        <div className="absolute inset-0 spinning-cube opacity-25" />
        <Search className="w-6 h-6 text-[#a78bfa] relative z-10" />
      </div>
      <div className="space-y-1.5">
        <p className="font-display text-base font-semibold text-white">
          {effectiveSearch ? (
            <>No assets match <em className="text-[#a78bfa] not-italic">"{effectiveSearch}"</em></>
          ) : (
            'Nothing here yet'
          )}
        </p>
        <p className="text-xs text-[#807d99]">
          {effectiveSearch
            ? 'Try another search or browse all.'
            : 'No assets in this category yet.'}
        </p>
      </div>
      {effectiveSearch && (
        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-white/[0.08] bg-white/[0.03] text-white hover:bg-[#7c5cff]/10 hover:border-[#7c5cff]/30 text-xs font-semibold transition-all hover:scale-[1.02] active:scale-[0.97]"
        >
          <X className="w-3.5 h-3.5" />
          Clear search
        </button>
      )}
    </div>
  )
}

// v1.4 polish — Phase 6 filmstrip pagination. Numbered dots that pulse on
// the active page; chevron arrows for nav. Up to 7 dots visible at once
// (windowed when totalPages > 7).
function FilmstripPagination({
  page,
  totalPages,
  disabled,
  onChange,
}: {
  page: number
  totalPages: number
  disabled: boolean
  onChange: (next: number) => void
}) {
  const visibleDots = useMemo(() => {
    if (totalPages <= 0) return []
    if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1)
    // Windowed: show first, last, current ± 1 with ellipses
    const out: (number | 'ellipsis')[] = [1]
    const start = Math.max(2, page - 1)
    const end = Math.min(totalPages - 1, page + 1)
    if (start > 2) out.push('ellipsis')
    for (let i = start; i <= end; i++) out.push(i)
    if (end < totalPages - 1) out.push('ellipsis')
    out.push(totalPages)
    return out as (number | 'ellipsis')[]
  }, [page, totalPages])

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => onChange(Math.max(1, page - 1))}
        disabled={disabled || page <= 1}
        aria-label="Previous page"
        className={cn(
          'p-1.5 rounded-lg transition-all',
          page <= 1 || disabled
            ? 'text-[#3a3850] cursor-not-allowed'
            : 'text-[#807d99] hover:text-white hover:bg-white/[0.05]',
        )}
      >
        <ChevronLeft className="w-3.5 h-3.5" />
      </button>
      <div className="flex items-center gap-1 px-1">
        {visibleDots.map((dot, i) => {
          if (dot === 'ellipsis') {
            return (
              <span key={`e${i}`} className="text-[10px] text-[#3a3850] px-1">
                …
              </span>
            )
          }
          const active = dot === page
          return (
            <button
              key={dot}
              onClick={() => onChange(dot)}
              disabled={disabled}
              aria-label={`Page ${dot}`}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'relative inline-flex items-center justify-center transition-all',
                'h-6 min-w-6 px-1.5 rounded-md text-[10px] font-mono font-semibold',
                active
                  ? 'text-white bg-gradient-to-br from-[#7c5cff] to-[#ff5c8a] shadow-[0_0_14px_-2px_rgba(255,92,138,0.55)]'
                  : 'text-[#807d99] hover:text-white hover:bg-white/[0.05]',
                disabled && 'opacity-50 cursor-not-allowed',
              )}
            >
              {active && (
                <span className="absolute inset-0 rounded-md animate-pulse bg-gradient-to-br from-[#7c5cff]/30 to-[#ff5c8a]/30" />
              )}
              <span className="relative z-10">{dot}</span>
            </button>
          )
        })}
      </div>
      <button
        onClick={() => onChange(page + 1)}
        disabled={disabled || page >= totalPages}
        aria-label="Next page"
        className={cn(
          'p-1.5 rounded-lg transition-all',
          page >= totalPages || disabled
            ? 'text-[#3a3850] cursor-not-allowed'
            : 'text-[#807d99] hover:text-white hover:bg-white/[0.05]',
        )}
      >
        <ChevronRight className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-14 gap-3 text-center max-w-md mx-auto">
      <div className="w-12 h-12 rounded-2xl bg-[#ff5c8a]/10 border border-[#ff5c8a]/20 flex items-center justify-center">
        <AlertCircle className="w-5 h-5 text-[#ff5c8a]" />
      </div>
      <p className="text-sm text-[#807d99]">{message}</p>
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] text-white hover:bg-white/[0.06] text-xs font-semibold transition-all"
      >
        <RefreshCw className="w-3 h-3" /> Retry
      </button>
    </div>
  )
}
