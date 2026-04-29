import React, { useEffect, useMemo, useState } from 'react'
import {
  Download,
  Eye,
  Play,
  Search,
  Calendar,
  VideoIcon,
  Loader2,
  FileImage,
  FileArchive,
  Film,
  ExternalLink,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Link } from '@tanstack/react-router'
import { formatDistanceToNow } from 'date-fns'
import { listRenderJobs, runExport, type ExportFormat, type ExportResult } from '@/lib/api'
import { cn } from '@/lib/utils'
import { recipeDisplayName } from '@/lib/recipes'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select'

type SortMode = 'newest' | 'oldest' | 'template'

export default function Outputs() {
  const [outputs, setOutputs] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortMode>('newest')
  const [filterTemplate, setFilterTemplate] = useState<string>('')

  const fetchOutputs = async () => {
    try {
      const data = await listRenderJobs()
      const completeJobs = (data.jobs || []).filter((j) => j.status === 'complete' && j.output_url)
      setOutputs(completeJobs)
    } catch (error) {
      console.error('Failed to fetch outputs:', error)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchOutputs()
    const interval = setInterval(fetchOutputs, 5000)
    return () => clearInterval(interval)
  }, [])

  // B1 — derive per-template counts so the filter dropdown shows "name (count)"
  // sorted descending. Stays in sync as the library grows.
  const templateCounts = useMemo(() => {
    const counts = new Map<string, number>()
    outputs.forEach((o) => {
      const name = o.template_name || 'auto'
      counts.set(name, (counts.get(name) || 0) + 1)
    })
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
  }, [outputs])
  const templateNames = useMemo(
    () => templateCounts.map(([name]) => name),
    [templateCounts],
  )

  const filteredOutputs = useMemo(() => {
    let result = outputs.filter((o) =>
      String(o.project_name || '').toLowerCase().includes(search.toLowerCase()) ||
      String(o.template_name || '').toLowerCase().includes(search.toLowerCase()) ||
      String(o.topic || '').toLowerCase().includes(search.toLowerCase())
    )
    if (filterTemplate) {
      result = result.filter((o) => o.template_name === filterTemplate)
    }
    if (sort === 'oldest') {
      result = [...result].reverse()
    } else if (sort === 'template') {
      result = [...result].sort((a, b) => (a.template_name || '').localeCompare(b.template_name || ''))
    }
    return result
  }, [outputs, search, sort, filterTemplate])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-3">
          <Loader2 className="w-6 h-6 animate-spin text-[#7c5cff] mx-auto" />
          <p className="text-sm font-mono text-[#4a4764]">Loading gallery...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8 animate-reveal">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-3">
          <span className="section-tag section-tag--primary font-mono text-xs">// gallery</span>
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-gradient">Render Gallery</h1>
          <p className="text-[#807d99] max-w-xl">
            All completed renders. Preview, download, and export in multiple formats.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge className="bg-[#7c5cff]/10 text-[#a78bfa] border-[#7c5cff]/20 px-3 py-1.5 rounded-xl text-xs font-mono">
            {outputs.length} renders
          </Badge>
        </div>
      </div>

      {/* Search + Filter bar */}
      <div className="glass rounded-2xl p-2 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#4a4764]" />
          <input
            placeholder="Search renders..."
            className="w-full bg-transparent pl-12 pr-4 py-3 text-sm text-white placeholder:text-[#4a4764] focus:outline-none focus-glow rounded-xl"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2 px-2">
          {/* Sort */}
          <div className="flex items-center gap-1 bg-white/[0.02] rounded-xl border border-white/[0.05] p-0.5">
            {(['newest', 'oldest', 'template'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSort(s)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-[10px] font-mono font-medium transition-all',
                  sort === s
                    ? 'bg-[#7c5cff]/15 text-[#a78bfa] border border-[#7c5cff]/20'
                    : 'text-[#4a4764] hover:text-white'
                )}
              >
                {s}
              </button>
            ))}
          </div>
          {/* Template filter — B1 with counts. v1.4 Wave C: ui/select.tsx
              for design-system cohesion (no native <select> visible). */}
          {templateNames.length > 1 && (
            <Select
              value={filterTemplate || 'all'}
              onValueChange={(v: string) => setFilterTemplate(v === 'all' ? '' : v)}
            >
              <SelectTrigger className="bg-white/[0.02] border border-white/[0.05] rounded-xl px-3 py-1.5 text-xs text-[#807d99] hover:border-[#7c5cff]/30 hover:bg-white/[0.04] font-mono h-auto min-w-[180px]">
                <SelectValue placeholder="All templates" />
              </SelectTrigger>
              <SelectContent className="elevation-3 border-white/[0.1] rounded-xl">
                <SelectItem
                  value="all"
                  className="rounded-md hover:bg-[#7c5cff]/10 focus:bg-[#7c5cff]/15 font-mono text-xs"
                >
                  All templates ({outputs.length})
                </SelectItem>
                {templateCounts.map(([name, count]) => (
                  <SelectItem
                    key={name}
                    value={name}
                    className="rounded-md hover:bg-[#7c5cff]/10 focus:bg-[#7c5cff]/15 font-mono text-xs"
                  >
                    {name} ({count})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      {filteredOutputs.length === 0 ? (
        <div className="glass rounded-2xl py-20 text-center card-hover relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-[#7c5cff]/[0.02] to-transparent" />
          <div className="relative z-10">
            <div className="spinning-cube mx-auto mb-6 opacity-40" style={{ width: 40, height: 40 }} />
            <h3 className="text-xl font-bold text-white mb-2">No renders yet</h3>
            <p className="text-[#807d99] max-w-sm mx-auto mb-6">
              Type a prompt to create your first cinematic video. Completed renders will appear here.
            </p>
            <Link to="/studio" className="inline-flex items-center gap-2 btn-generate px-6 py-3 rounded-xl font-semibold text-sm">
              Go to Studio
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 stagger-reveal">
          {filteredOutputs.map((output) => (
            <div key={output.id} className="glass rounded-2xl overflow-hidden card-hover group flex flex-col">
              {/* Video preview */}
              <div className="aspect-video md:aspect-[9/16] relative overflow-hidden bg-[#0a0a10]">
                {output.output_url ? (
                  <video
                    src={output.output_url}
                    className="w-full h-full object-cover opacity-60 group-hover:opacity-100 group-hover:scale-105 transition-all duration-700"
                    muted
                    loop
                    playsInline
                    onMouseEnter={(e) => (e.target as HTMLVideoElement).play().catch(() => {})}
                    onMouseLeave={(e) => (e.target as HTMLVideoElement).pause()}
                  />
                ) : null}
                <div className="absolute inset-0 bg-gradient-to-t from-[#050508] via-transparent to-transparent opacity-80 group-hover:opacity-40 transition-opacity duration-500" />

                {/* Play overlay */}
                <a href={output.output_url} target="_blank" rel="noreferrer"
                  className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300">
                  <div className="w-14 h-14 rounded-full bg-[#7c5cff] flex items-center justify-center shadow-[0_0_30px_rgba(124,92,255,0.4)] scale-75 group-hover:scale-100 transition-transform duration-300">
                    <Play className="w-6 h-6 fill-white text-white" />
                  </div>
                </a>

                {/* Badges */}
                <div className="absolute top-3 right-3">
                  <Badge className="bg-[#38d9c4]/20 text-[#38d9c4] border-[#38d9c4]/20 text-[10px] font-mono rounded-lg px-2 py-0.5">
                    COMPLETE
                  </Badge>
                </div>
                <div className="absolute top-3 left-3 flex flex-col gap-1.5 items-start">
                  <Badge className="bg-[#7c5cff]/20 text-[#a78bfa] border-[#7c5cff]/20 text-[10px] font-mono rounded-lg px-2 py-0.5">
                    {output.template_name || 'auto'}
                  </Badge>
                  {/* B2 — recipe badge (V1.3) when manifest has _template_v2_recipe */}
                  {(() => {
                    const name = recipeDisplayName(output.recipe_name)
                    return name ? (
                      <Badge className="bg-[#38d9c4]/15 text-[#38d9c4] border-[#38d9c4]/30 text-[10px] font-mono rounded-lg px-2 py-0.5">
                        <span className="opacity-60 mr-1">// directed as:</span>
                        <span className="text-white">{name}</span>
                      </Badge>
                    ) : null
                  })()}
                </div>

                {/* Bottom info */}
                <div className="absolute bottom-4 left-4 right-4">
                  <h4 className="font-bold text-white text-lg leading-tight truncate mb-1">
                    {output.topic || output.project_name || `Job ${output.id}`}
                  </h4>
                  <span className="text-xs text-[#807d99] font-mono flex items-center gap-1.5">
                    <Calendar className="w-3 h-3" />
                    {formatDistanceToNow(new Date(output.updated_at))} ago
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="p-4 border-t border-white/[0.05] space-y-3 mt-auto">
                <div className="grid grid-cols-2 gap-2">
                  <Link
                    to={`/projects/${output.id}`}
                    className="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-medium text-[#807d99] hover:text-white hover:bg-white/[0.05] transition-all border border-white/[0.05]"
                  >
                    <Eye className="w-3.5 h-3.5" /> Details
                  </Link>
                  <a
                    href={output.output_url}
                    download
                    className="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-medium text-[#807d99] hover:text-white hover:bg-white/[0.05] transition-all border border-white/[0.05]"
                  >
                    <Download className="w-3.5 h-3.5" /> Download
                  </a>
                </div>
                <ExportPanel jobId={output.id} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ExportPanel({ jobId }: { jobId: number }) {
  const [busy, setBusy] = useState<ExportFormat | null>(null)
  const [results, setResults] = useState<Record<string, ExportResult>>({})

  const run = async (fmt: ExportFormat) => {
    setBusy(fmt)
    try {
      const res = await runExport(jobId, fmt)
      setResults((prev) => ({ ...prev, [fmt]: res.result }))
    } catch (e: any) {
      setResults((prev) => ({
        ...prev,
        [fmt]: { ok: false, format: fmt, error: e?.message || 'failed' },
      }))
    } finally {
      setBusy(null)
    }
  }

  const formats: { id: ExportFormat; label: string; icon: React.ComponentType<any> }[] = [
    { id: 'gif', label: 'GIF', icon: Film },
    { id: 'poster', label: 'Poster', icon: FileImage },
    { id: 'png_seq', label: 'PNGs', icon: FileArchive },
  ]

  return (
    <div className="pt-2 border-t border-white/[0.05]">
      <div className="text-[10px] font-mono text-[#4a4764] mb-2">// export</div>
      <div className="grid grid-cols-3 gap-1.5">
        {formats.map(({ id, label, icon: Icon }) => {
          const r = results[id]
          return (
            <button
              key={id}
              disabled={busy !== null}
              onClick={() => (r?.output_url ? window.open(r.output_url, '_blank') : run(id))}
              className={cn(
                'flex items-center justify-center gap-1 px-2 py-2 rounded-lg text-[10px] font-medium transition-all border',
                r?.ok
                  ? 'border-[#7c5cff]/30 text-[#a78bfa] bg-[#7c5cff]/5'
                  : 'border-white/[0.05] text-[#807d99] hover:text-white hover:bg-white/[0.05]',
                busy !== null && 'opacity-50'
              )}
            >
              {busy === id ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Icon className="w-3 h-3" />
              )}
              {r?.ok ? 'Open' : label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
