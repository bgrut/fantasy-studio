import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Search, ImageOff, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { libraryBrowse, type LibraryBrowseAsset } from '@/lib/api'

/**
 * ASSET PALETTE (2026-08-06)
 *
 * The library already existed, the edit-at-a-point API already existed, and
 * the runtime already raycasted for Inspect. What was missing was somewhere
 * to SEE what you can add and a way to put it exactly where you want it, so
 * placing a guard meant typing "place a guard here" and hoping the caster
 * picked the same word you did.
 *
 * Cards are HTML5 drag sources. The drop target is an overlay the studio
 * raises over the game iframe while a drag is live — an iframe swallows the
 * parent's drag events, so there is no way to drop "onto" the game without
 * one. See GameStudio's fs-dropat bridge for the coordinate handoff.
 */

export type PaletteAsset = {
  id: string
  subject: string
  category: string
  thumbnail_url?: string | null
}

/** Palette tabs -> library categories. The library's own vocabulary is
 *  character / environment / prop / vehicle / hdri; these are the groupings
 *  that make sense when the question is "what can I drop into a street". */
const TABS = [
  { id: 'character', label: 'Characters', cats: 'character', hint: 'people and creatures — they arrive with their behaviour' },
  { id: 'object', label: 'Objects', cats: 'prop,vehicle', hint: 'props and vehicles — a car you drop is a car you can drive' },
  { id: 'building', label: 'Buildings', cats: 'environment', hint: 'structures and set dressing placed on the ground plane' },
] as const

type TabId = (typeof TABS)[number]['id']

export default function AssetPalette({
  onDragStart,
  onDragEnd,
  disabled,
}: {
  onDragStart: (a: PaletteAsset) => void
  onDragEnd: () => void
  disabled?: boolean
}) {
  const [tab, setTab] = useState<TabId>('character')
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [assets, setAssets] = useState<LibraryBrowseAsset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const reqRef = useRef(0)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 220)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => {
    const spec = TABS.find(t => t.id === tab)!
    const seq = ++reqRef.current
    setLoading(true)
    setError(null)
    libraryBrowse({ category: spec.cats, search: debounced, page: 1, per_page: 24 })
      .then(r => {
        if (seq !== reqRef.current) return          // a newer request won
        setAssets(r.assets ?? [])
      })
      .catch(e => {
        if (seq !== reqRef.current) return
        setError(e instanceof Error ? e.message : String(e))
        setAssets([])
      })
      .finally(() => { if (seq === reqRef.current) setLoading(false) })
  }, [tab, debounced])

  const activeHint = useMemo(() => TABS.find(t => t.id === tab)!.hint, [tab])

  const handleDragStart = useCallback((a: LibraryBrowseAsset) => (e: React.DragEvent) => {
    if (disabled) { e.preventDefault(); return }
    const payload: PaletteAsset = {
      id: a.id,
      subject: (a.subject || a.id || '').replace(/_/g, ' ').trim(),
      category: a.category,
      thumbnail_url: a.thumbnail_url,
    }
    // both a custom type (so the studio can tell a palette drag from a file
    // drop) and text/plain (so the browser will start the drag at all)
    e.dataTransfer.setData('application/x-fs-asset', JSON.stringify(payload))
    e.dataTransfer.setData('text/plain', payload.subject)
    e.dataTransfer.effectAllowed = 'copy'
    onDragStart(payload)
  }, [disabled, onDragStart])

  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-1.5 flex-wrap">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              'px-2.5 py-1 rounded-full text-[11px] transition-all',
              tab === t.id
                ? 'bg-[#a78bfa]/25 text-[#d6c9ff]'
                : 'text-[#807d99] hover:text-white',
            )}
          >
            {t.label}
          </button>
        ))}
        <div className="relative ml-auto">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[#4a4764]" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="search library"
            className="w-40 pl-6 pr-2 py-1 rounded-full bg-black/30 border border-[#a78bfa]/20
                       text-[11px] text-[#d6c9ff] placeholder:text-[#4a4764]
                       focus:outline-none focus:border-[#a78bfa]/50"
          />
        </div>
      </div>

      <p className="text-[10px] text-[#4a4764]">
        {disabled
          ? 'Build or open a game first — a drop needs a world to land in.'
          : <>Drag a card onto the game. {activeHint}</>}
      </p>

      {error && (
        <p className="text-[11px] text-[#ff8fa0]">Library unavailable: {error}</p>
      )}

      <div className="relative">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/20 rounded-lg">
            <Loader2 className="w-4 h-4 animate-spin text-[#a78bfa]" />
          </div>
        )}
        <div className="grid gap-1.5 max-h-[228px] overflow-y-auto pr-1
                        [grid-template-columns:repeat(auto-fill,minmax(88px,1fr))]">
          {assets.map(a => (
            <div
              key={a.id}
              draggable={!disabled}
              onDragStart={handleDragStart(a)}
              onDragEnd={onDragEnd}
              title={a.subject || a.id}
              className={cn(
                'group rounded-lg border border-[#a78bfa]/20 bg-black/25 overflow-hidden',
                'transition-all select-none',
                disabled
                  ? 'opacity-40 cursor-not-allowed'
                  : 'cursor-grab active:cursor-grabbing hover:border-[#a78bfa]/60 hover:bg-[#a78bfa]/10',
              )}
            >
              <div className="aspect-square bg-black/40 flex items-center justify-center overflow-hidden">
                {a.thumbnail_url
                  ? <img src={a.thumbnail_url} alt="" draggable={false}
                         className="w-full h-full object-cover" />
                  : <ImageOff className="w-4 h-4 text-[#3a3750]" />}
              </div>
              <div className="px-1.5 py-1 text-[9.5px] leading-tight text-[#b8b3d0] truncate">
                {(a.subject || a.id).replace(/_/g, ' ')}
              </div>
            </div>
          ))}
          {!loading && !assets.length && !error && (
            <p className="col-span-full text-[11px] text-[#4a4764] py-4 text-center">
              Nothing in this category{debounced ? ` matching “${debounced}”` : ''} yet.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
