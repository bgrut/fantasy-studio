import React, { useEffect, useMemo, useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie
} from 'recharts'
import {
  Zap,
  Clock,
  CheckCircle2,
  XCircle,
  Layers,
  Activity,
  ArrowUpRight,
  Plus,
  ArrowRight,
  Cpu,
  Video
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Link } from '@tanstack/react-router'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { getHealth, listRenderJobs } from '@/lib/api'
import { formatDistanceToNow } from 'date-fns'

export default function Dashboard() {
  const [health, setHealth] = useState<any>(null)
  const [jobs, setJobs] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const fetchData = async () => {
    try {
      const [healthResp, jobsResp] = await Promise.all([
        getHealth(),
        listRenderJobs(),
      ])
      setHealth(healthResp)
      setJobs(jobsResp.jobs || [])
    } catch (error) {
      console.error('Failed to load dashboard:', error)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [])

  const counts = health?.counts || {
    queued: 0,
    planning: 0,
    rendering: 0,
    complete: 0,
    failed: 0,
  }

  const stats = [
    { label: 'Total Projects', value: String(jobs.length), icon: Layers, color: 'text-primary', trend: `${jobs.length}`, sub: 'Global production' },
    { label: 'Queued Jobs', value: String((counts.queued || 0) + (counts.planning || 0)), icon: Clock, color: 'text-amber-500', trend: `${counts.queued || 0}`, sub: 'Cluster backlog' },
    { label: 'Rendering', value: String(counts.rendering || 0), icon: Activity, color: 'text-blue-500', trend: 'Live', sub: 'Active compute' },
    { label: 'Completed', value: String(counts.complete || 0), icon: CheckCircle2, color: 'text-green-500', trend: 'OK', sub: 'Success count' },
    { label: 'Failed', value: String(counts.failed || 0), icon: XCircle, color: 'text-destructive', trend: `${counts.failed || 0}`, sub: 'Critical errors' },
  ]

  const chartData = useMemo(() => {
    const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
    const map = new Map<string, number>()
    for (let i = 6; i >= 0; i--) {
      const d = new Date()
      d.setDate(d.getDate() - i)
      map.set(days[d.getDay()], 0)
    }

    jobs.forEach((job) => {
      if (!job.updated_at) return
      const d = new Date(job.updated_at)
      const key = days[d.getDay()]
      if (map.has(key)) map.set(key, (map.get(key) || 0) + 1)
    })

    return Array.from(map.entries()).map(([name, value]) => ({ name, value }))
  }, [jobs])

  const templateUsage = useMemo(() => {
    const counts: Record<string, number> = {}
    jobs.forEach((job) => {
      const key = (job.template_name || 'unknown').replace(/_/g, ' ')
      counts[key] = (counts[key] || 0) + 1
    })
    const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1
    const palette = ['#0EA5E9', '#D946EF', '#F59E0B', '#22C55E', '#EF4444']
    return Object.entries(counts).slice(0, 5).map(([name, count], i) => ({
      name,
      value: Math.round((count / total) * 100),
      color: palette[i % palette.length],
    }))
  }, [jobs])

  const recentOutputs = jobs.filter((j) => j.status === 'complete').slice(0, 3)
  const recentActivity = jobs.slice(0, 5)

  if (isLoading) {
    return <div className="p-8 text-center text-muted-foreground animate-pulse font-display uppercase tracking-widest">Booting Dashboard...</div>
  }

  return (
    <div className="space-y-12 animate-reveal">
      <div className="relative p-12 rounded-[48px] overflow-hidden glass border-white/5 shadow-[0_40px_100px_-20px_rgba(0,0,0,0.8)]">
        <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-primary/[0.05] via-transparent to-accent/[0.05] pointer-events-none" />
        <div className="absolute -top-24 -right-24 w-96 h-96 bg-primary/10 rounded-full blur-[100px] pointer-events-none animate-pulse" />
        <div className="absolute -bottom-24 -left-24 w-96 h-96 bg-accent/10 rounded-full blur-[100px] pointer-events-none animate-pulse" />

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center justify-between gap-10">
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20 uppercase tracking-[0.3em] font-bold text-[10px] px-4 py-1 rounded-full backdrop-blur-md">
                Blender Lane OS v4.0.2
              </Badge>
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/10 border border-green-500/20">
                <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                <span className="text-[9px] font-bold text-green-500 uppercase tracking-widest">
                  {health?.settings?.local_render_mode ? 'Hybrid CLI Active' : 'Simulated Mode'}
                </span>
              </div>
            </div>
            <h1 className="text-6xl font-display font-bold tracking-tighter text-white leading-tight">
              Creative <span className="text-gradient-primary">Operating System</span>
            </h1>
            <p className="text-muted-foreground text-xl max-w-2xl leading-relaxed font-medium">
              Distributed render engine for vertical 3D content. High-throughput cluster monitoring and AI-assisted geometry synthesis.
            </p>
          </div>
          <div className="flex flex-wrap gap-4">
            <Link to="/create">
              <Button size="lg" className="neon-glow-primary bg-primary text-white h-20 px-10 rounded-[24px] font-bold text-lg transition-all hover:scale-105 active:scale-95 shadow-2xl group">
                <Plus className="w-6 h-6 mr-3 group-hover:rotate-90 transition-transform duration-500" />
                Initialize Cycle
              </Button>
            </Link>
            <Link to="/queue">
              <Button variant="outline" size="lg" className="glass rounded-[24px] h-20 px-10 font-bold uppercase tracking-widest text-xs transition-all hover:bg-white/5 active:scale-95 border-white/10 text-white/80">
                <Activity className="w-5 h-5 mr-3 text-primary" /> System Metrics
              </Button>
            </Link>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <Card key={stat.label} className="glass group hover:bg-white/[0.04] transition-all duration-500 border-white/5 rounded-3xl overflow-hidden relative">
              <div className={cn("absolute top-0 left-0 w-1 h-full opacity-50 bg-current", stat.color)} />
              <CardContent className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <div className={cn("p-2.5 rounded-xl bg-white/5", stat.color)}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <Badge variant="ghost" className={cn("text-[10px] font-bold", stat.color)}>
                    {stat.trend}
                  </Badge>
                </div>
                <div className="space-y-1">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">{stat.label}</p>
                  <p className="text-4xl font-display font-bold text-white">{stat.value}</p>
                  <p className="text-[10px] text-muted-foreground/60 font-medium">{stat.sub}</p>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <Card className="lg:col-span-2 glass rounded-3xl border-white/5 overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between px-8 pt-8">
            <div className="space-y-1">
              <CardTitle className="font-display text-2xl font-bold text-white">Cluster Output</CardTitle>
              <CardDescription className="text-muted-foreground">Historical render delivery performance.</CardDescription>
            </div>
            <div className="flex items-center gap-3 px-4 py-2 rounded-2xl bg-white/5 border border-white/5">
              <div className="flex flex-col items-end">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest leading-none mb-1">Live Counts</span>
                <span className="text-primary font-bold text-sm leading-none">{jobs.length} jobs</span>
              </div>
              <ArrowUpRight className="w-5 h-5 text-primary" />
            </div>
          </CardHeader>
          <CardContent className="h-[350px] px-4 pb-8">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={1}/>
                    <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0.3}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ffffff05" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 11, fontWeight: 600 }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 11, fontWeight: 600 }} />
                <Tooltip
                  cursor={{ fill: '#ffffff05' }}
                  contentStyle={{
                    backgroundColor: 'rgba(2, 6, 23, 0.8)',
                    backdropFilter: 'blur(12px)',
                    border: '1px solid rgba(255, 255, 255, 0.05)',
                    borderRadius: '16px',
                  }}
                />
                <Bar dataKey="value" fill="url(#barGradient)" radius={[6, 6, 0, 0]} animationDuration={1200} barSize={40} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="glass rounded-3xl border-white/5 overflow-hidden flex flex-col">
          <CardHeader className="p-8">
            <CardTitle className="font-display text-2xl font-bold text-white">Lane Allocation</CardTitle>
            <CardDescription className="text-muted-foreground">Template distribution across cluster.</CardDescription>
          </CardHeader>
          <CardContent className="h-[250px] flex items-center justify-center relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={templateUsage.length ? templateUsage : [{ name: 'No Jobs', value: 100, color: '#334155' }]} cx="50%" cy="50%" innerRadius={70} outerRadius={95} paddingAngle={8} dataKey="value" stroke="none">
                  {(templateUsage.length ? templateUsage : [{ name: 'No Jobs', value: 100, color: '#334155' }]).map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Active</span>
              <span className="text-3xl font-display font-bold text-white">{templateUsage.length || 0} Lanes</span>
            </div>
          </CardContent>
          <div className="p-8 pt-0 space-y-4 flex-1">
            {templateUsage.length ? templateUsage.map((entry) => (
              <div key={entry.name} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full shadow-[0_0_10px_currentcolor]" style={{ color: entry.color, backgroundColor: entry.color }} />
                  <span className="text-xs font-bold text-white/80 uppercase tracking-wider">{entry.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-20 h-1 rounded-full bg-white/5 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${entry.value}%`, backgroundColor: entry.color }} />
                  </div>
                  <span className="text-xs font-bold text-white">{entry.value}%</span>
                </div>
              </div>
            )) : (
              <div className="text-muted-foreground text-sm">No template usage yet.</div>
            )}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <Card className="glass rounded-3xl border-white/5 overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between p-8 border-b border-white/5">
            <CardTitle className="font-display text-2xl font-bold text-white">Recent Artifacts</CardTitle>
            <Link to="/outputs">
              <Button variant="ghost" size="sm" className="rounded-xl hover:bg-white/5 text-muted-foreground">
                View Grid <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </Link>
          </CardHeader>
          <div className="divide-y divide-white/5">
            {recentOutputs.length ? recentOutputs.map((job) => (
              <div key={job.id} className="flex items-center gap-6 p-6 hover:bg-white/[0.03] transition-all duration-300 group">
                <div className="relative w-32 h-20 rounded-2xl overflow-hidden bg-secondary border border-white/5 flex items-center justify-center">
                  {job.output_url ? (
                    <video className="w-full h-full object-cover opacity-60 group-hover:opacity-100 transition-all duration-700" src={job.output_url} muted />
                  ) : (
                    <Video className="w-8 h-8 text-primary/40" />
                  )}
                </div>
                <div className="flex-1 min-w-0 space-y-1">
                  <h4 className="text-sm font-bold text-white truncate group-hover:text-primary transition-colors">{job.project_name || `Job ${job.id}`}</h4>
                  <div className="flex items-center gap-3">
                    <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20 text-[9px] uppercase font-bold tracking-widest px-2 py-0">
                      {job.template_name || 'template'}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-widest flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {job.status}
                    </span>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_8px_#22c55e]" />
                    <span className="text-[10px] font-bold text-green-500 uppercase tracking-widest">Delivered</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-widest opacity-50">
                    {formatDistanceToNow(new Date(job.updated_at))} ago
                  </span>
                </div>
              </div>
            )) : (
              <div className="p-8 text-muted-foreground">No completed outputs yet.</div>
            )}
          </div>
        </Card>

        <Card className="glass rounded-3xl border-white/5 overflow-hidden">
          <CardHeader className="p-8 border-b border-white/5">
            <CardTitle className="font-display text-2xl font-bold text-white">Cluster Telemetry</CardTitle>
          </CardHeader>
          <div className="p-8 space-y-8 max-h-[400px] overflow-y-auto custom-scrollbar">
            {recentActivity.length ? recentActivity.map((job, i) => (
              <div key={job.id} className="flex gap-5 group relative">
                {i < recentActivity.length - 1 && <div className="absolute left-[7px] top-6 w-[2px] h-10 bg-white/5" />}
                <div className={cn(
                  "w-4 h-4 mt-1 rounded-full shrink-0 border-2 border-background z-10 transition-transform duration-300 group-hover:scale-125",
                  job.status === 'failed' ? 'bg-destructive shadow-[0_0_12px_hsl(var(--destructive))]' :
                  job.status === 'complete' ? 'bg-green-500 shadow-[0_0_12px_#22c55e]' :
                  job.status === 'rendering' ? 'bg-primary shadow-[0_0_12px_hsl(var(--primary))]' :
                  'bg-muted-foreground shadow-[0_0_12px_rgba(255,255,255,0.2)]'
                )} />
                <div className="space-y-1">
                  <p className="text-sm leading-tight text-white/90">
                    <span className="font-bold text-primary tracking-tight">@SYSTEM</span>{" "}
                    <span className="font-medium text-white/70">
                      Job #{job.id} for {job.project_name || job.topic} is currently {job.status}.
                    </span>
                  </p>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.1em]">
                    {formatDistanceToNow(new Date(job.updated_at))} ago
                  </p>
                </div>
              </div>
            )) : (
              <div className="text-muted-foreground">No activity yet.</div>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
