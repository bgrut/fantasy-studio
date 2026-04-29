import React, { useEffect, useState } from 'react'
import {
  ChevronUp,
  ChevronDown,
  Play,
  Download,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Activity,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { getPipelineStatus, retryRenderJob, type PipelineStatusResponse } from '@/lib/api'
import { formatDistanceToNow } from 'date-fns'
import { motion, AnimatePresence } from 'framer-motion'

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

export default function PipelineStatus() {
  const [data, setData] = useState<PipelineStatusResponse | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [retrying, setRetrying] = useState<number | null>(null)

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const res = await getPipelineStatus()
        if (alive) setData(res)
      } catch {}
    }
    poll()
    const iv = setInterval(poll, 3000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  const handleRetry = async (id: number) => {
    setRetrying(id)
    try {
      await retryRenderJob(id)
    } catch {}
    setRetrying(null)
  }

  if (!data) return null

  const { active, queued, recent, stats } = data
  const hasActivity = active || queued.length > 0

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50">
      {/* Collapsed bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'w-full glass-dark border-t border-white/[0.05] px-4 sm:px-6 py-2.5 flex items-center justify-between',
          'hover:bg-white/[0.02] transition-colors cursor-pointer'
        )}
      >
        <div className="flex items-center gap-4 min-w-0">
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5 text-[#7c5cff]" />
            <span className="text-xs font-mono text-[#807d99]">// pipeline</span>
          </div>

          {active ? (
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-2 h-2 rounded-full bg-[#7c5cff] shadow-[0_0_8px_#7c5cff] animate-pulse" />
              <span className="text-xs text-white truncate max-w-[200px]">
                {active.topic}
              </span>
              <div className="w-24 h-1 rounded-full bg-white/[0.05] overflow-hidden hidden sm:block">
                <motion.div
                  className="h-full progress-gradient rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${(active.progress || 0.5) * 100}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </div>
          ) : (
            <span className="text-xs text-[#4a4764]">Idle</span>
          )}

          {queued.length > 0 && (
            <span className="text-xs text-[#ffc857] font-mono hidden sm:block">
              {queued.length} queued
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden md:flex items-center gap-4 text-xs font-mono">
            <span className="text-[#38d9c4]">{stats.completed} done</span>
            {stats.failed > 0 && <span className="text-[#ff5c8a]">{stats.failed} failed</span>}
          </div>
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-[#4a4764]" />
          ) : (
            <ChevronUp className="w-4 h-4 text-[#4a4764]" />
          )}
        </div>
      </button>

      {/* Expanded panel */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            transition={{ type: 'spring', bounce: 0, duration: 0.35 }}
            className="overflow-hidden glass-dark border-t border-white/[0.05]"
          >
            <div className="px-4 sm:px-6 py-5 max-w-[1400px] mx-auto space-y-4">
              {/* Job list */}
              <div className="space-y-1.5 max-h-[200px] overflow-y-auto custom-scrollbar">
                {/* Active */}
                {active && (
                  <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-[#7c5cff]/5 border border-[#7c5cff]/10">
                    <Loader2 className="w-3.5 h-3.5 text-[#7c5cff] animate-spin flex-shrink-0" />
                    <span className="text-xs font-semibold text-[#7c5cff] uppercase w-20 flex-shrink-0">Rendering</span>
                    <span className="text-sm text-white truncate flex-1">{active.topic}</span>
                    <div className="w-32 h-1.5 rounded-full bg-white/[0.05] overflow-hidden flex-shrink-0 hidden sm:block">
                      <motion.div
                        className="h-full progress-gradient rounded-full"
                        animate={{ width: `${(active.progress || 0.5) * 100}%` }}
                        transition={{ duration: 0.5 }}
                      />
                    </div>
                  </div>
                )}

                {/* Queued */}
                {queued.map((j) => (
                  <div key={j.id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/[0.01]">
                    <Clock className="w-3.5 h-3.5 text-[#ffc857] flex-shrink-0" />
                    <span className="text-xs font-semibold text-[#ffc857] uppercase w-20 flex-shrink-0">Queued</span>
                    <span className="text-sm text-[#807d99] truncate flex-1">{j.topic}</span>
                    <span className="text-xs text-[#4a4764] font-mono flex-shrink-0">waiting...</span>
                  </div>
                ))}

                {/* Recent */}
                {recent.slice(0, 5).map((j) => (
                  <div key={j.id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/[0.01] group">
                    {j.status === 'complete' ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#38d9c4] flex-shrink-0" />
                    ) : (
                      <XCircle className="w-3.5 h-3.5 text-[#ff5c8a] flex-shrink-0" />
                    )}
                    <span className={cn(
                      'text-xs font-semibold uppercase w-20 flex-shrink-0',
                      j.status === 'complete' ? 'text-[#38d9c4]' : 'text-[#ff5c8a]'
                    )}>
                      {j.status}
                    </span>
                    <span className="text-sm text-[#807d99] truncate flex-1">{j.topic}</span>
                    <span className="text-xs text-[#4a4764] font-mono flex-shrink-0">
                      {j.completed_at ? formatDistanceToNow(new Date(j.completed_at + 'Z')) + ' ago' : ''}
                    </span>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                      {j.status === 'complete' && j.output_url && (
                        <>
                          <a href={j.output_url} target="_blank" rel="noreferrer"
                            className="p-1 rounded hover:bg-white/[0.05] text-[#38d9c4]">
                            <Play className="w-3 h-3" />
                          </a>
                          <a href={j.output_url} download
                            className="p-1 rounded hover:bg-white/[0.05] text-[#807d99]">
                            <Download className="w-3 h-3" />
                          </a>
                        </>
                      )}
                      {j.status === 'failed' && (
                        <button
                          onClick={() => handleRetry(j.id)}
                          disabled={retrying === j.id}
                          className="p-1 rounded hover:bg-white/[0.05] text-[#ff5c8a]"
                        >
                          {retrying === j.id ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <RefreshCw className="w-3 h-3" />
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <StatMini label="total" value={stats.total_renders} />
                <StatMini label="done" value={stats.completed} color="text-[#38d9c4]" />
                <StatMini label="queue" value={stats.queued} color="text-[#ffc857]" />
                <StatMini label="fail" value={stats.failed} color="text-[#ff5c8a]" />
                <StatMini label="avg" value={formatDuration(stats.avg_render_time_s)} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function StatMini({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="glass rounded-xl px-3 py-2.5 text-center card-hover">
      <div className={cn('text-lg font-bold font-mono', color || 'text-white')}>{value}</div>
      <div className="text-[10px] font-mono text-[#4a4764] uppercase">{label}</div>
    </div>
  )
}
