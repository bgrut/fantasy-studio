import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  BarChart3,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  TrendingUp,
  Film,
  Layers,
  Loader2,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { getAnalytics, type AnalyticsResponse } from '@/lib/api'
import { formatDistanceToNow } from 'date-fns'

function AnimatedNumber({ value, duration = 1200 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0)
  const ref = useRef<number | null>(null)

  useEffect(() => {
    const start = performance.now()
    const from = display
    const animate = (now: number) => {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
      setDisplay(Math.round(from + (value - from) * eased))
      if (progress < 1) ref.current = requestAnimationFrame(animate)
    }
    ref.current = requestAnimationFrame(animate)
    return () => { if (ref.current) cancelAnimationFrame(ref.current) }
  }, [value, duration])

  return <>{display}</>
}

function HorizontalBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-[#807d99] w-24 truncate">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-white/[0.03] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}, ${color}cc)`,
            boxShadow: `0 0 8px ${color}40`,
          }}
        />
      </div>
      <span className="text-xs font-mono text-white w-8 text-right">{value}</span>
    </div>
  )
}

function VerticalBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="flex flex-col items-center gap-1.5 flex-1">
      <span className="text-xs font-mono text-white">{value}</span>
      <div className="w-full h-24 rounded-lg bg-white/[0.03] overflow-hidden flex items-end">
        <div
          className="w-full rounded-lg transition-all duration-1000 ease-out"
          style={{
            height: `${Math.max(pct, 4)}%`,
            background: `linear-gradient(to top, ${color}, ${color}88)`,
            boxShadow: `0 0 10px ${color}30`,
          }}
        />
      </div>
      <span className="text-[10px] font-mono text-[#4a4764]">{label}</span>
    </div>
  )
}

const TIER_COLORS: Record<string, string> = {
  preview: '#7c5cff',
  fast: '#38d9c4',
  standard: '#ffc857',
  cinematic: '#ff5c8a',
}

export default function Insights() {
  const [data, setData] = useState<AnalyticsResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const res = await getAnalytics()
        if (alive) setData(res)
      } catch (e) {
        console.error('Failed to load analytics:', e)
      } finally {
        if (alive) setIsLoading(false)
      }
    }
    load()
    const iv = setInterval(load, 30000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-3">
          <Loader2 className="w-6 h-6 animate-spin text-[#7c5cff] mx-auto" />
          <p className="text-sm font-mono text-[#4a4764]">Loading insights...</p>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <p className="text-sm text-[#4a4764]">Failed to load analytics</p>
      </div>
    )
  }

  const { summary, tier_breakdown, top_subjects, template_usage, timeline, recent } = data
  const maxSubject = Math.max(...top_subjects.map((s) => s.count), 1)
  const maxTimeline = Math.max(...timeline.map((t) => t.count), 1)
  const maxTier = Math.max(...Object.values(tier_breakdown), 1)
  const maxTemplate = Math.max(...Object.values(template_usage), 1)

  return (
    <div className="space-y-8 animate-reveal">
      {/* Header */}
      <div className="space-y-3">
        <span className="section-tag section-tag--primary font-mono text-xs">// production insights</span>
        <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-gradient">
          Engine Analytics
        </h1>
        <p className="text-[#807d99] max-w-xl">
          Your cinematic production engine at a glance.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-reveal">
        <StatCard
          icon={<Film className="w-5 h-5 text-[#7c5cff]" />}
          label="Total Renders"
          value={<AnimatedNumber value={summary.total_renders} />}
          bg="bg-[#7c5cff]/10"
        />
        <StatCard
          icon={<CheckCircle2 className="w-5 h-5 text-[#38d9c4]" />}
          label="Completed"
          value={<AnimatedNumber value={summary.completed} />}
          bg="bg-[#38d9c4]/10"
        />
        <StatCard
          icon={<Clock className="w-5 h-5 text-[#ffc857]" />}
          label="Avg Time"
          value={formatDurationFriendly(summary.avg_render_time_s)}
          bg="bg-[#ffc857]/10"
        />
        <StatCard
          icon={<TrendingUp className="w-5 h-5 text-[#ff5c8a]" />}
          label="Success Rate"
          value={`${Math.round(summary.success_rate * 100)}%`}
          bg="bg-[#ff5c8a]/10"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Render Timeline */}
        <div className="glass rounded-2xl p-6 card-hover">
          <div className="flex items-center gap-2 mb-5">
            <BarChart3 className="w-4 h-4 text-[#7c5cff]" />
            <span className="text-sm font-semibold">Render Timeline</span>
            <span className="section-tag text-xs ml-auto">renders/hour</span>
          </div>
          <div className="flex gap-1.5 items-end">
            {timeline.map((t) => (
              <VerticalBar
                key={t.hour}
                label={t.hour.replace(':00', 'h')}
                value={t.count}
                max={maxTimeline}
                color="#7c5cff"
              />
            ))}
          </div>
        </div>

        {/* Top Subjects */}
        <div className="glass rounded-2xl p-6 card-hover">
          <div className="flex items-center gap-2 mb-5">
            <Zap className="w-4 h-4 text-[#ff5c8a]" />
            <span className="text-sm font-semibold">Top Subjects</span>
          </div>
          <div className="space-y-3">
            {top_subjects.slice(0, 8).map((s) => (
              <HorizontalBar
                key={s.subject}
                label={s.subject}
                value={s.count}
                max={maxSubject}
                color="#ff5c8a"
              />
            ))}
          </div>
        </div>

        {/* Tier Breakdown */}
        <div className="glass rounded-2xl p-6 card-hover">
          <div className="flex items-center gap-2 mb-5">
            <Layers className="w-4 h-4 text-[#38d9c4]" />
            <span className="text-sm font-semibold">Render Tier Breakdown</span>
          </div>
          <div className="space-y-3">
            {Object.entries(tier_breakdown).map(([tier, count]) => (
              <HorizontalBar
                key={tier}
                label={tier.charAt(0).toUpperCase() + tier.slice(1)}
                value={count}
                max={maxTier}
                color={TIER_COLORS[tier] || '#7c5cff'}
              />
            ))}
          </div>
        </div>

        {/* Template Usage */}
        <div className="glass rounded-2xl p-6 card-hover">
          <div className="flex items-center gap-2 mb-5">
            <Layers className="w-4 h-4 text-[#ffc857]" />
            <span className="text-sm font-semibold">Template Usage</span>
          </div>
          <div className="space-y-3">
            {Object.entries(template_usage)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 8)
              .map(([name, count]) => (
                <HorizontalBar
                  key={name}
                  label={name}
                  value={count}
                  max={maxTemplate}
                  color="#ffc857"
                />
              ))}
          </div>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="glass rounded-2xl p-6 card-hover">
        <div className="flex items-center gap-2 mb-5">
          <Clock className="w-4 h-4 text-[#7c5cff]" />
          <span className="text-sm font-semibold">Recent Activity</span>
        </div>
        <div className="space-y-1">
          {recent.map((job) => (
            <div
              key={job.id}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/[0.02] transition-colors"
            >
              <span className="text-xs font-mono text-[#4a4764] w-16 flex-shrink-0">
                {job.timestamp ? new Date(job.timestamp + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
              </span>
              {job.status === 'complete' ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-[#38d9c4] flex-shrink-0" />
              ) : (
                <XCircle className="w-3.5 h-3.5 text-[#ff5c8a] flex-shrink-0" />
              )}
              <span className="text-sm text-white truncate flex-1">{job.topic}</span>
              <Badge className={cn(
                'text-[10px] font-mono rounded-lg px-2 py-0.5 flex-shrink-0',
                job.tier === 'preview' ? 'bg-[#7c5cff]/10 text-[#a78bfa] border-[#7c5cff]/20' :
                job.tier === 'fast' ? 'bg-[#38d9c4]/10 text-[#38d9c4] border-[#38d9c4]/20' :
                job.tier === 'cinematic' ? 'bg-[#ff5c8a]/10 text-[#ff5c8a] border-[#ff5c8a]/20' :
                'bg-white/[0.03] text-[#807d99] border-white/[0.05]'
              )}>
                {job.template_name || job.tier || 'preview'}
              </Badge>
              <span className="text-xs font-mono text-[#4a4764] w-12 text-right flex-shrink-0">
                {job.duration_s != null ? formatDurationFriendly(job.duration_s) : 'FAIL'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function StatCard({ icon, label, value, bg }: { icon: React.ReactNode; label: string; value: React.ReactNode; bg: string }) {
  return (
    <div className="glass rounded-2xl p-5 card-hover">
      <div className={cn('w-11 h-11 rounded-xl flex items-center justify-center mb-3', bg)}>
        {icon}
      </div>
      <div className="text-2xl font-bold font-mono text-white">{value}</div>
      <div className="text-xs font-mono text-[#4a4764] mt-1">{label}</div>
    </div>
  )
}

function formatDurationFriendly(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}
