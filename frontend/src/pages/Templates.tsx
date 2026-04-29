import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Loader2,
  Layers,
  AlertCircle,
  Sparkles,
  X,
  ExternalLink,
  ImageOff,
  ChevronRight,
  Heart,
  Boxes,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import {
  getAssetCounts,
  browseAssets,
  type AssetCountsResponse,
  type AssetLibraryItem,
} from '@/lib/api'

const PAGE_SIZE = 50

const CATEGORIES: { id: string; label: string; countKey?: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'character', label: 'Characters / Animals', countKey: 'character' },
  { id: 'vehicle', label: 'Vehicles', countKey: 'vehicle' },
  { id: 'environment', label: 'Environments', countKey: 'environment' },
  { id: 'prop', label: 'Props', countKey: 'prop' },
  { id: 'hdri', label: 'HDRIs', countKey: 'hdri' },
]

const CATEGORY_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  character: { bg: 'bg-[#7c5cff]/15', text: 'text-[#a78bfa]', border: 'border-[#7c5cff]/30' },
  animal:    { bg: 'bg-[#7c5cff]/15', text: 'text-[#a78bfa]', border: 'border-[#7c5cff]/30' },
  vehicle:   { bg: 'bg-[#38d9c4]/15', text: 'text-[#38d9c4]', border: 'border-[#38d9c4]/30' },
  environment: { bg: 'bg-[#ff5c8a]/15', text: 'text-[#ff5c8a]', border: 'border-[#ff5c8a]/30' },
  prop:      { bg: 'bg-[#ffc857]/15', text: 'text-[#ffc857]', border: 'border-[#ffc857]/30' },
  hdri:      { bg: 'bg-[#60a5fa]/15', text: 'text-[#60a5fa]', border: 'border-[#60a5fa]/30' },
}

const QUALITY_STYLES: Record<string, { text: string; label: string }> = {
  tested:     { text: 'text-[#38d9c4]', label: 'Tested' },
  unverified: { text: 'text-[#ffc857]', label: 'Unverified' },
  rejected:   { text: 'text-[#ff5c8a]', label: 'Rejected' },
}

const PLACEHOLDER_PALETTE = [
  '#7c5cff', '#ff5c8a', '#38d9c4', '#ffc857', '#a78bfa', '#f472b6', '#4ade80', '#60a5fa',
]

function placeholderColor(title: string): string {
  const idx = (title.charCodeAt(0) || 0) % PLACEHOLDER_PALETTE.length
  return PLACEHOLDER_PALETTE[idx]
}

export default function Templates() {
  const [counts, setCounts] = useState<AssetCountsResponse | null>(null)
  const [countsError, setCountsError] = useState<string | null>(null)

  const [category, setCategory] = useState<string>('all')
  const [items, setItems] = useState<AssetLibraryItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [detailItem, setDetailItem] = useState<AssetLibraryItem | null>(null)

  // Protect against race conditions when switching categories quickly
  const requestIdRef = useRef(0)

  // Fetch counts once
  useEffect(() => {
    getAssetCounts()
      .then((c) => setCounts(c))
      .catch((e: any) => setCountsError(e?.message || 'Failed to load counts'))
  }, [])

  // Fetch items on category change
  const loadFirstPage = useCallback(async (cat: string) => {
    const myId = ++requestIdRef.current
    setLoading(true)
    setError(null)
    setItems([])
    setOffset(0)
    setHasMore(false)
    try {
      const res = await browseAssets({ category: cat, limit: PAGE_SIZE, offset: 0 })
      if (myId !== requestIdRef.current) return
      setItems(res.items)
      setTotal(res.total)
      setOffset(res.items.length)
      setHasMore(res.has_more)
    } catch (e: any) {
      if (myId !== requestIdRef.current) return
      setError(e?.message || 'Failed to load assets')
    } finally {
      if (myId === requestIdRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadFirstPage(category)
  }, [category, loadFirstPage])

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return
    const myId = requestIdRef.current
    setLoadingMore(true)
    try {
      const res = await browseAssets({ category, limit: PAGE_SIZE, offset })
      if (myId !== requestIdRef.current) return
      setItems((prev) => [...prev, ...res.items])
      setOffset((prev) => prev + res.items.length)
      setHasMore(res.has_more)
    } catch (e: any) {
      if (myId !== requestIdRef.current) return
      setError(e?.message || 'Failed to load more')
    } finally {
      if (myId === requestIdRef.current) setLoadingMore(false)
    }
  }, [category, offset, hasMore, loadingMore])

  const grandTotal = counts?.total ?? 0
  const byCategory = counts?.by_category || {}

  const useAsset = useCallback((asset: AssetLibraryItem) => {
    const subject = asset.subject || (asset.subject_tags && asset.subject_tags[0]) || asset.title
    const prompt = `a ${subject} in an interesting scene`
    const sp = new URLSearchParams({ forced_hero_id: asset.id, prompt })
    // Plain navigation — SceneStudio's mount effect reads forced_hero_id +
    // prompt from window.location.search and pre-locks the asset.
    window.location.assign(`/studio?${sp.toString()}`)
  }, [])

  return (
    <div className="space-y-8 animate-reveal">
      {/* Header */}
      <div className="space-y-3">
        <span className="section-tag section-tag--teal font-mono text-xs">// assets</span>
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
          <div className="space-y-2">
            <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-gradient">
              Asset Library
            </h1>
            <p className="text-[#807d99]">
              {grandTotal > 0 ? (
                <>
                  <span className="text-white font-semibold">{grandTotal}</span> curated assets —
                  growing weekly
                </>
              ) : countsError ? (
                <span className="text-[#ff5c8a]">{countsError}</span>
              ) : (
                'Loading library…'
              )}
            </p>
          </div>
          <div className="hidden sm:flex items-center gap-2 px-3 py-2 rounded-xl bg-white/[0.03] border border-white/[0.05]">
            <Boxes className="w-4 h-4 text-[#a78bfa]" />
            <span className="text-xs font-mono text-[#807d99]">CC-BY licensed · drop-in ready</span>
          </div>
        </div>
      </div>

      {/* Category pills */}
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((cat) => {
          const count = cat.id === 'all' ? grandTotal : byCategory[cat.countKey || cat.id] ?? 0
          const active = category === cat.id
          return (
            <button
              key={cat.id}
              onClick={() => setCategory(cat.id)}
              className={cn(
                'px-4 py-2 rounded-full border text-sm font-medium transition-all duration-200 flex items-center gap-2',
                active
                  ? 'border-[#7c5cff]/40 bg-[#7c5cff]/10 text-white shadow-[0_0_16px_rgba(124,92,255,0.2)]'
                  : 'border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:border-white/[0.12] hover:text-white',
              )}
            >
              <span>{cat.label}</span>
              <span
                className={cn(
                  'text-[10px] font-mono px-1.5 py-0.5 rounded-md',
                  active ? 'bg-[#7c5cff]/20 text-[#a78bfa]' : 'bg-white/[0.04] text-[#4a4764]',
                )}
              >
                {count}
              </span>
            </button>
          )
        })}
      </div>

      {/* Grid */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-16 gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-[#7c5cff]" />
          <p className="text-sm font-mono text-[#4a4764]">Loading assets…</p>
        </div>
      )}

      {!loading && error && (
        <div className="flex items-start gap-3 rounded-2xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-400 max-w-2xl mx-auto">
          <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
          <div className="space-y-1">
            <div className="font-semibold">Couldn't load assets</div>
            <div className="text-xs">{error}</div>
          </div>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
          <div className="w-14 h-14 rounded-2xl bg-white/[0.03] border border-white/[0.05] flex items-center justify-center">
            <Layers className="w-6 h-6 text-[#4a4764]" />
          </div>
          <p className="text-sm text-[#807d99]">No assets in this category yet.</p>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 stagger-reveal">
            {items.map((asset) => (
              <AssetCard key={asset.id} asset={asset} onOpen={() => setDetailItem(asset)} />
            ))}
          </div>

          <div className="flex items-center justify-center">
            {hasMore ? (
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className={cn(
                  'inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border text-sm font-semibold transition-all',
                  loadingMore
                    ? 'border-white/[0.04] bg-white/[0.02] text-[#4a4764] cursor-not-allowed'
                    : 'border-white/[0.08] bg-white/[0.03] text-white hover:border-[#7c5cff]/30 hover:bg-[#7c5cff]/10',
                )}
              >
                {loadingMore ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ChevronRight className="w-4 h-4" />
                )}
                Load more
                <span className="text-[10px] font-mono text-[#4a4764]">
                  {items.length}/{total}
                </span>
              </button>
            ) : (
              <span className="text-xs font-mono text-[#4a4764]">
                Showing all {items.length} · no more results
              </span>
            )}
          </div>
        </>
      )}

      {/* Detail panel */}
      <AssetDetailPanel
        asset={detailItem}
        onClose={() => setDetailItem(null)}
        onUse={useAsset}
      />
    </div>
  )
}

function AssetCard({ asset, onOpen }: { asset: AssetLibraryItem; onOpen: () => void }) {
  const [thumbFailed, setThumbFailed] = useState(false)
  const category = asset.category || 'asset'
  const catStyle = CATEGORY_STYLES[category] || CATEGORY_STYLES.prop

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group text-left rounded-2xl overflow-hidden border border-white/[0.06] bg-[#0a0a10] hover:border-[#7c5cff]/30 hover:shadow-[0_0_18px_rgba(124,92,255,0.15)] transition-all duration-200 flex flex-col"
    >
      {/* Thumbnail */}
      <div className="aspect-square relative overflow-hidden bg-[#0a0a10]">
        {thumbFailed || !asset.thumbnail_url ? (
          <ThumbPlaceholder title={asset.title} />
        ) : (
          <img
            src={asset.thumbnail_url}
            alt={asset.title}
            loading="lazy"
            onError={() => setThumbFailed(true)}
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-[1.05]"
          />
        )}
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/70 via-black/10 to-transparent pointer-events-none" />

        {/* Category tag */}
        <div
          className={cn(
            'absolute top-2 left-2 px-2 py-0.5 rounded-full text-[10px] font-mono border',
            catStyle.bg,
            catStyle.text,
            catStyle.border,
          )}
        >
          {category}
        </div>
      </div>

      {/* Meta */}
      <div className="px-3 py-2.5 space-y-1">
        <div className="text-sm font-semibold text-white line-clamp-1">{asset.title}</div>
        <div className="flex items-center justify-between gap-2">
          {typeof asset.use_count === 'number' && asset.use_count > 0 ? (
            <span className="text-[10px] font-mono text-[#807d99] inline-flex items-center gap-1">
              <Heart className="w-2.5 h-2.5" /> used {asset.use_count} time
              {asset.use_count === 1 ? '' : 's'}
            </span>
          ) : (
            <span className="text-[10px] font-mono text-[#4a4764]">new</span>
          )}
          {QUALITY_STYLES[asset.quality] && (
            <span
              className={cn(
                'text-[10px] font-mono',
                QUALITY_STYLES[asset.quality].text,
              )}
            >
              {QUALITY_STYLES[asset.quality].label}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

function ThumbPlaceholder({ title }: { title: string }) {
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
      <span className="text-5xl font-bold opacity-90" style={{ color }}>
        {letter}
      </span>
      <ImageOff className="absolute bottom-2 right-2 w-3.5 h-3.5 text-white/20" />
    </div>
  )
}

function AssetDetailPanel({
  asset,
  onClose,
  onUse,
}: {
  asset: AssetLibraryItem | null
  onClose: () => void
  onUse: (asset: AssetLibraryItem) => void
}) {
  const [thumbFailed, setThumbFailed] = useState(false)

  useEffect(() => {
    setThumbFailed(false)
  }, [asset?.id])

  useEffect(() => {
    if (!asset) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [asset, onClose])

  const attribution = asset?.attribution
  const author = attribution?.author
  const license = attribution?.license
  const sourceUrl = attribution?.source_url || attribution?.source
  const showAuthor = author && author !== 'unknown'

  const category = asset?.category || 'asset'
  const catStyle = asset ? CATEGORY_STYLES[category] || CATEGORY_STYLES.prop : CATEGORY_STYLES.prop

  if (!asset) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[90] bg-black/60 backdrop-blur-sm animate-in fade-in-0"
        onClick={onClose}
      />

      {/* Slide-in panel */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${asset.title} details`}
        className="fixed top-0 right-0 bottom-0 z-[100] w-full max-w-md glass border-l border-white/[0.08] shadow-[-10px_0_40px_rgba(0,0,0,0.4)] flex flex-col animate-in slide-in-from-right-10"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.05]">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-[#7c5cff]" />
            <span className="text-sm font-semibold">Asset details</span>
          </div>
          <button
            onClick={onClose}
            aria-label="Close details"
            className="p-2 rounded-xl hover:bg-white/[0.05] text-[#807d99] hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-5 space-y-5">
          {/* Large thumbnail */}
          <div className="aspect-square rounded-2xl overflow-hidden border border-white/[0.06] bg-[#0a0a10] relative">
            {thumbFailed || !asset.thumbnail_url ? (
              <ThumbPlaceholder title={asset.title} />
            ) : (
              <img
                src={asset.thumbnail_url}
                alt={asset.title}
                onError={() => setThumbFailed(true)}
                className="w-full h-full object-cover"
              />
            )}
            <div
              className={cn(
                'absolute top-3 left-3 px-2.5 py-1 rounded-full text-[11px] font-mono border',
                catStyle.bg,
                catStyle.text,
                catStyle.border,
              )}
            >
              {category}
            </div>
          </div>

          {/* Title + quality */}
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-white">{asset.title}</h2>
            <div className="flex flex-wrap items-center gap-2">
              {QUALITY_STYLES[asset.quality] && (
                <Badge
                  className={cn(
                    'border text-[10px] rounded-lg font-mono',
                    QUALITY_STYLES[asset.quality].text,
                    'bg-white/[0.03] border-white/[0.06]',
                  )}
                >
                  {QUALITY_STYLES[asset.quality].label}
                </Badge>
              )}
              {typeof asset.use_count === 'number' && asset.use_count > 0 && (
                <Badge className="bg-white/[0.03] border-white/[0.06] text-[#807d99] text-[10px] rounded-lg font-mono">
                  used {asset.use_count}×
                </Badge>
              )}
              <span className="text-[10px] font-mono text-[#4a4764]">{asset.id}</span>
            </div>
          </div>

          {/* Subject + tags */}
          {(asset.subject || (asset.subject_tags && asset.subject_tags.length > 0)) && (
            <div className="space-y-2">
              <div className="text-[10px] font-mono text-[#4a4764] uppercase tracking-wider">
                Subject
              </div>
              <div className="flex flex-wrap gap-1.5">
                {asset.subject && (
                  <Badge className="bg-[#7c5cff]/10 border-[#7c5cff]/20 text-[#a78bfa] text-xs rounded-lg">
                    {asset.subject}
                  </Badge>
                )}
                {(asset.subject_tags || []).map((t) => (
                  <Badge
                    key={t}
                    className="bg-white/[0.03] border-white/[0.06] text-[#807d99] text-xs rounded-lg"
                  >
                    {t}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Visual descriptors */}
          {asset.visual_descriptors && asset.visual_descriptors.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-mono text-[#4a4764] uppercase tracking-wider">
                Visual descriptors
              </div>
              <div className="flex flex-wrap gap-1.5">
                {asset.visual_descriptors.map((d) => (
                  <Badge
                    key={d}
                    className="bg-white/[0.03] border-white/[0.06] text-[#807d99] text-xs rounded-lg"
                  >
                    {d}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Attribution */}
          <div className="space-y-2">
            <div className="text-[10px] font-mono text-[#4a4764] uppercase tracking-wider">
              Attribution
            </div>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3 text-sm">
              {showAuthor ? (
                <p className="text-[#e4e2f0]">
                  by <span className="font-semibold text-white">{author}</span>
                  {license && (
                    <>
                      {' '}— <span className="text-[#a78bfa]">{license}</span>
                    </>
                  )}
                </p>
              ) : (
                <p className="text-[#807d99]">Author unknown</p>
              )}
              {sourceUrl && typeof sourceUrl === 'string' && /^https?:\/\//.test(sourceUrl) && (
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-[#7c5cff] hover:text-[#a78bfa] mt-2"
                >
                  <ExternalLink className="w-3 h-3" /> source
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-white/[0.05] bg-white/[0.02]">
          <button
            onClick={() => onUse(asset)}
            className="w-full btn-generate px-4 py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2"
          >
            <Sparkles className="w-4 h-4" />
            Use this in a render
          </button>
        </div>
      </aside>
    </>
  )
}
