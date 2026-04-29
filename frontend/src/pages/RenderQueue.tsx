import React, { useEffect, useState } from 'react'
import {
  Layers,
  Clock,
  Activity,
  CheckCircle2,
  XCircle,
  RefreshCcw,
  MoreVertical,
  Cpu,
  Eye,
  Terminal,
  History,
  ChevronRight,
  AlertCircle,
  Zap,
  Trash2
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from 'react-hot-toast'
import { Link } from '@tanstack/react-router'
import { formatDistanceToNow } from 'date-fns'
import { cn } from '@/lib/utils'
import { listRenderJobs, getRenderJob, retryRenderJob } from '@/lib/api'

const STATUSES = ['queued', 'planning', 'rendering', 'complete', 'failed'] as const
type JobStatus = typeof STATUSES[number]

const STATUS_CONFIG: Record<JobStatus, { label: string, icon: any, color: string, glow: string }> = {
  queued: { label: 'Queued', icon: Clock, color: 'text-amber-500', glow: 'shadow-[0_0_15px_-3px_#f59e0b]' },
  planning: { label: 'Planning', icon: Cpu, color: 'text-blue-500', glow: 'shadow-[0_0_15px_-3px_#3b82f6]' },
  rendering: { label: 'Rendering', icon: Activity, color: 'text-primary', glow: 'shadow-[0_0_15px_-3px_hsl(var(--primary))]' },
  complete: { label: 'Complete', icon: CheckCircle2, color: 'text-green-500', glow: 'shadow-[0_0_15px_-3px_#22c55e]' },
  failed: { label: 'Failed', icon: XCircle, color: 'text-destructive', glow: 'shadow-[0_0_15px_-3px_hsl(var(--destructive))]' },
}

// Time-based progress estimate — the backend doesn't emit a live percentage,
// but `updated_at` is stamped at every status transition (including the
// transition into 'rendering'), so we can ramp from there for a reasonable
// in-flight indicator.
function estimateProgress(job: any): number {
  const status = job.status as JobStatus
  if (status === 'complete' || status === 'failed') return 100
  if (status === 'queued') return 5
  if (status === 'planning') return 20
  if (status === 'rendering') {
    const start = new Date(job.updated_at).getTime()
    const elapsedSec = Math.max(0, (Date.now() - start) / 1000)
    const frac = Math.min(1, elapsedSec / 180) // ramp over ~3 min
    return Math.round(30 + frac * 60)
  }
  return 0
}

function stageLabel(status: JobStatus): string {
  switch (status) {
    case 'queued': return 'Queued — awaiting worker'
    case 'planning': return 'Planning scene…'
    case 'rendering': return 'Rendering frames…'
    case 'complete': return 'Render complete'
    case 'failed': return 'Render failed'
    default: return ''
  }
}

export default function RenderQueue() {
  const [jobs, setJobs] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [selectedJob, setSelectedJob] = useState<any>(null)
  const [jobEvents, setJobEvents] = useState<any[]>([])
  const [isEventsLoading, setIsEventsLoading] = useState(false)

  const fetchJobs = async () => {
    try {
      const data = await listRenderJobs()
      setJobs(data.jobs || [])
    } catch (error) {
      console.error('Failed to fetch jobs:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const fetchEvents = async (jobId: number) => {
    setIsEventsLoading(true)
    try {
      const data = await getRenderJob(jobId)
      setSelectedJob(data.job)
      setJobEvents(data.events || [])
    } catch (error) {
      toast.error('Failed to load job events')
    } finally {
      setIsEventsLoading(false)
    }
  }

  useEffect(() => {
    fetchJobs()
    const interval = setInterval(fetchJobs, 3000)
    return () => clearInterval(interval)
  }, [])

  const retryJobNow = async (jobId: number) => {
    try {
      await retryRenderJob(jobId)
      toast.success('Job re-queued successfully')
      fetchJobs()
      if (selectedJob?.id === jobId) fetchEvents(jobId)
    } catch (error) {
      toast.error('Failed to retry job')
    }
  }

  const openLogs = (job: any) => {
    setSelectedJob(job)
    fetchEvents(job.id)
  }

  if (isLoading) return <div className="p-8 text-center text-muted-foreground font-display uppercase tracking-widest animate-pulse">Scanning Grid...</div>

  const groupedJobs = STATUSES.reduce((acc, status) => {
    acc[status] = jobs.filter(j => j.status === status)
    return acc
  }, {} as Record<JobStatus, any[]>)

  return (
    <div className="space-y-12 animate-reveal">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
        <div className="space-y-3">
          <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20 uppercase tracking-[0.3em] font-bold text-[9px] px-3 py-1">
            Cluster Traffic Control
          </Badge>
          <h1 className="text-5xl font-display font-bold tracking-tight text-gradient">Production Pipeline</h1>
          <p className="text-muted-foreground text-lg max-w-2xl leading-relaxed">
            Real-time status monitoring and resource allocation for distributed Blender render clusters.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="px-6 py-3 rounded-2xl glass-dark border border-white/5 flex items-center gap-4">
            <div className="flex flex-col items-end">
              <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest leading-none mb-1">Compute Status</span>
              <div className="flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5 text-primary" />
                <span className="text-sm font-bold text-white uppercase">Backend Live</span>
              </div>
            </div>
            <div className="w-px h-10 bg-white/10" />
            <Button variant="outline" size="sm" onClick={fetchJobs} className="glass h-10 px-4 rounded-xl font-bold uppercase tracking-widest text-[9px] text-muted-foreground hover:text-white transition-all">
              <RefreshCcw className="w-3.5 h-3.5 mr-2" /> Force Sync
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-8">
        {STATUSES.map((status) => {
          const config = STATUS_CONFIG[status]
          const StatusIcon = config.icon
          const currentJobs = groupedJobs[status]

          return (
            <div key={status} className="space-y-6">
              <div className="flex items-center justify-between px-4">
                <div className="flex items-center gap-3">
                  <div className={cn("p-2 rounded-xl bg-white/5 shadow-inner", config.color)}>
                    <StatusIcon className="w-4 h-4" />
                  </div>
                  <h3 className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/80">{config.label}</h3>
                </div>
                <Badge variant="outline" className="bg-white/5 border-white/10 text-[10px] h-6 min-w-[24px] flex items-center justify-center font-bold rounded-lg shadow-inner">
                  {currentJobs.length}
                </Badge>
              </div>

              <div className="space-y-6 min-h-[600px] p-3 rounded-[32px] bg-white/[0.01] border border-white/5 shadow-inner relative overflow-hidden group/lane">
                <div className="absolute inset-0 bg-gradient-to-b from-white/[0.01] to-transparent opacity-0 group-hover/lane:opacity-100 transition-opacity duration-1000" />

                {currentJobs.length === 0 ? (
                  <div className="h-32 flex flex-col items-center justify-center border border-dashed border-white/5 rounded-[24px] mt-2 opacity-40">
                    <p className="text-[9px] text-muted-foreground font-bold uppercase tracking-[0.2em]">IDLE_NODE</p>
                  </div>
                ) : (
                  currentJobs.map((job) => (
                    <Card key={job.id} className={cn(
                      "glass group/card border-white/5 hover:border-white/20 transition-all duration-500 rounded-[24px] cursor-pointer overflow-hidden shadow-xl hover:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.5)]",
                      status === 'rendering' ? "border-primary/30 shadow-[0_0_25px_-5px_hsla(var(--primary)/0.3)]" : ""
                    )} onClick={() => openLogs(job)}>
                      <div className="aspect-[16/10] relative bg-black/40 overflow-hidden border-b border-white/5 flex items-center justify-center">
                        {job.output_url && job.status === 'complete' ? (
                          <video src={job.output_url} className="w-full h-full object-cover opacity-40 group-hover/card:opacity-100 group-hover/card:scale-110 transition-all duration-1000" muted />
                        ) : (
                          <Layers className="w-8 h-8 text-primary/20 animate-pulse" />
                        )}
                        {status === 'rendering' && <div className="absolute inset-0 bg-primary/5 animate-pulse" />}
                        <div className="absolute top-3 right-3 flex gap-2 z-10">
                          {job.retry_count > 0 && (
                            <Badge className="bg-amber-500/90 text-[8px] h-4.5 px-1.5 border-none font-bold shadow-lg">RETRY_{job.retry_count}</Badge>
                          )}
                        </div>
                      </div>
                      <CardContent className="p-5 space-y-4">
                        <div className="space-y-1.5">
                          <h4 className="text-sm font-bold truncate tracking-tight text-white uppercase group-hover/card:text-primary transition-colors duration-300">
                            {job.project_name || `Job ${job.id}`}
                          </h4>
                          <div className="flex items-center gap-2">
                            <Badge variant="ghost" className="p-0 text-[9px] text-primary uppercase font-bold tracking-[0.1em] border-none bg-transparent opacity-80">
                              {job.template_name || 'DYNAMIC_NODE'}
                            </Badge>
                          </div>
                        </div>

                        {(status === 'rendering' || status === 'planning') && (
                          <div className="space-y-2 pt-1">
                            <div className="flex justify-between text-[9px] text-muted-foreground/60 font-bold tracking-widest uppercase">
                              <span className="truncate">{stageLabel(status)}</span>
                              <span className="text-primary">{estimateProgress(job)}%</span>
                            </div>
                            <Progress value={estimateProgress(job)} className="h-1 bg-white/5 rounded-full" />
                          </div>
                        )}

                        <div className="flex items-center justify-between pt-2">
                          <div className="flex items-center gap-2 px-2 py-1 rounded-lg bg-white/5 border border-white/5">
                            <div className={cn("w-1.5 h-1.5 rounded-full animate-pulse", config.color, config.glow)} />
                            <span className="text-[9px] font-bold text-white/60 uppercase tracking-widest">{status}</span>
                          </div>
                          <div className="flex items-center gap-1.5 opacity-0 group-hover/card:opacity-100 transition-all duration-300 translate-x-2 group-hover/card:translate-x-0">
                            {job.status === 'failed' && (
                              <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-muted-foreground hover:text-white hover:bg-white/5" onClick={(e) => { e.stopPropagation(); retryJobNow(job.id) }}>
                                <RefreshCcw className="w-4 h-4" />
                              </Button>
                            )}
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-muted-foreground hover:text-white hover:bg-white/5" onClick={e => e.stopPropagation()}>
                                  <MoreVertical className="w-4 h-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end" className="glass-dark border-white/10 bg-[#020617] rounded-2xl p-1.5 min-w-[180px] shadow-2xl">
                                <DropdownMenuItem asChild className="rounded-xl my-0.5 cursor-pointer">
                                  <Link to={`/projects/${job.id}`} className="flex items-center px-3 py-2.5">
                                    <Eye className="w-4 h-4 mr-3 text-primary" />
                                    <span className="font-bold text-[10px] uppercase tracking-widest">Detail View</span>
                                  </Link>
                                </DropdownMenuItem>
                                {job.status === 'failed' && (
                                  <DropdownMenuItem className="rounded-xl my-0.5 cursor-pointer" onClick={() => retryJobNow(job.id)}>
                                    <RefreshCcw className="w-4 h-4 mr-3 text-amber-500" />
                                    <span className="font-bold text-[10px] uppercase tracking-widest">Force Reboot</span>
                                  </DropdownMenuItem>
                                )}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>

      <Sheet open={!!selectedJob} onOpenChange={() => setSelectedJob(null)}>
        <SheetContent className="glass-dark border-white/5 sm:max-w-2xl overflow-hidden flex flex-col p-0">
          <SheetHeader className="p-8 border-b border-white/5">
            <div className="flex items-center gap-4 mb-2">
              <div className={cn("p-3 rounded-2xl bg-white/5 shadow-inner", selectedJob && STATUS_CONFIG[selectedJob.status as JobStatus]?.color)}>
                <Terminal className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <SheetTitle className="font-display text-2xl text-white">{selectedJob?.project_name || `Job ${selectedJob?.id}`}</SheetTitle>
                <SheetDescription className="text-[10px] uppercase font-bold tracking-[0.2em] text-primary">
                  INSTANCE_MANIFEST: {selectedJob?.id}
                </SheetDescription>
              </div>
            </div>
            {selectedJob && (
              <div className="flex items-center gap-8 pt-6">
                <div className="flex flex-col">
                  <span className="text-[9px] font-bold text-muted-foreground/60 uppercase tracking-widest">Status</span>
                  <Badge variant="outline" className={cn("mt-1.5 text-[10px] uppercase font-bold border-white/10 rounded-lg py-0.5 px-3", STATUS_CONFIG[selectedJob.status as JobStatus]?.color)}>
                    {selectedJob.status}
                  </Badge>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] font-bold text-muted-foreground/60 uppercase tracking-widest">Compute Node</span>
                  <span className="text-xs font-mono font-bold mt-1.5 text-white/90 truncate max-w-[160px]">{selectedJob.provider_name || 'AUTO_PROVISIONING'}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[9px] font-bold text-muted-foreground/60 uppercase tracking-widest">Runtime</span>
                  <span className="text-xs font-bold mt-1.5 text-white/90">{formatDistanceToNow(new Date(selectedJob.created_at))}</span>
                </div>
              </div>
            )}
          </SheetHeader>

          <Tabs defaultValue="events" className="flex-1 flex flex-col overflow-hidden">
            <div className="px-8 pt-4 bg-white/[0.01] border-b border-white/5">
              <TabsList className="bg-transparent h-auto p-0 gap-8">
                <TabsTrigger value="events" className="data-[state=active]:text-primary data-[state=active]:border-primary border-b-2 border-transparent rounded-none px-0 py-3 text-[10px] font-bold uppercase tracking-[0.2em] transition-all">Telemetry Events</TabsTrigger>
                <TabsTrigger value="stdout" className="data-[state=active]:text-accent data-[state=active]:border-accent border-b-2 border-transparent rounded-none px-0 py-3 text-[10px] font-bold uppercase tracking-[0.2em] transition-all">Cluster Stdout</TabsTrigger>
                <TabsTrigger value="stderr" className="data-[state=active]:text-destructive data-[state=active]:border-destructive border-b-2 border-transparent rounded-none px-0 py-3 text-[10px] font-bold uppercase tracking-[0.2em] transition-all">System Errors</TabsTrigger>
              </TabsList>
            </div>

            <div className="flex-1 overflow-hidden bg-black/40">
              <TabsContent value="events" className="h-full m-0 p-0 overflow-y-auto custom-scrollbar font-mono">
                <div className="divide-y divide-white/5">
                  {isEventsLoading ? (
                    <div className="p-12 text-center text-[10px] text-muted-foreground animate-pulse uppercase tracking-[0.3em]">Intercepting cluster telemetry...</div>
                  ) : jobEvents.length === 0 ? (
                    <div className="p-16 text-center text-[11px] text-muted-foreground/40 italic font-medium">No telemetry data recorded for this node instance.</div>
                  ) : (
                    jobEvents.map((event, i) => (
                      <div key={i} className="p-6 space-y-2 hover:bg-white/[0.02] transition-colors group">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <span className="text-[10px] text-primary font-bold uppercase tracking-widest bg-primary/10 px-2 py-0.5 rounded">[{event.stage}]</span>
                            <div className="w-1 h-1 rounded-full bg-white/20" />
                            <span className="text-[10px] text-muted-foreground/60 font-medium">{formatDistanceToNow(new Date(event.created_at))} ago</span>
                          </div>
                          <ChevronRight className="w-4 h-4 text-muted-foreground/20 group-hover:text-primary transition-colors" />
                        </div>
                        <p className="text-xs text-white/80 leading-relaxed pl-4 border-l-2 border-primary/20">{event.message}</p>
                      </div>
                    ))
                  )}
                </div>
              </TabsContent>

              <TabsContent value="stdout" className="h-full m-0 p-0 overflow-y-auto custom-scrollbar font-mono">
                {selectedJob?.stdout_log ? (
                  <pre className="p-8 text-[11px] text-green-500/80 leading-relaxed whitespace-pre-wrap selection:bg-green-500/20">
                    {selectedJob.stdout_log}
                  </pre>
                ) : (
                  <div className="p-16 text-center text-[11px] text-muted-foreground/40 italic font-medium uppercase tracking-widest">Stdout stream empty.</div>
                )}
              </TabsContent>

              <TabsContent value="stderr" className="h-full m-0 p-0 overflow-y-auto custom-scrollbar font-mono">
                {selectedJob?.stderr_log ? (
                  <pre className="p-8 text-[11px] text-destructive/80 leading-relaxed whitespace-pre-wrap selection:bg-destructive/20">
                    {selectedJob.stderr_log}
                  </pre>
                ) : (
                  <div className="p-16 text-center text-[11px] text-muted-foreground/40 italic font-medium uppercase tracking-widest">No critical system errors detected.</div>
                )}
              </TabsContent>
            </div>
          </Tabs>

          <div className="p-8 border-t border-white/5 bg-white/[0.02] space-y-6">
            <div className="grid grid-cols-2 gap-3">
              <Button variant="outline" className="glass h-12 font-bold uppercase tracking-widest text-[11px]" onClick={() => retryJobNow(selectedJob.id)}>
                <RefreshCcw className="w-4 h-4 mr-2" /> Retry Instance
              </Button>
              <Button asChild variant="outline" className="glass h-12 font-bold uppercase tracking-widest text-[11px]">
                <a href={selectedJob?.output_url || '#'} target="_blank" rel="noreferrer">
                  <Eye className="w-4 h-4 mr-2" /> Open Output
                </a>
              </Button>
            </div>
            <Button asChild className="w-full h-12 neon-glow-primary bg-primary text-white font-bold uppercase tracking-widest text-[11px]">
              <Link to={`/projects/${selectedJob?.id}`}>
                <Eye className="w-4 h-4 mr-2" /> Inspect Project Logic
              </Link>
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Card className="glass p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Network Load</p>
              <p className="text-xl font-bold font-display">{jobs.length} Active Jobs</p>
            </div>
          </div>
          <Progress value={Math.min(100, jobs.length * 10)} className="h-1 bg-white/5" />
        </Card>
        <Card className="glass p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-green-500/10 text-green-500">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Successful Today</p>
              <p className="text-xl font-bold font-display">{groupedJobs.complete.length} Renders</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-bold text-green-500">
            <AlertCircle className="w-3 h-3" />
            <span>Operational Excellence: live backend</span>
          </div>
        </Card>
        <Card className="glass p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-amber-500/10 text-amber-500">
              <History className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Pending Queue</p>
              <p className="text-xl font-bold font-display">{groupedJobs.queued.length + groupedJobs.planning.length} Jobs</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-bold text-amber-500">
            <Clock className="w-3 h-3" />
            <span>Est. Wait Time: dynamic</span>
          </div>
        </Card>
        <Card className="glass p-6 flex flex-col gap-4 border-destructive/20">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-destructive/10 text-destructive">
              <XCircle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Failure Rate</p>
              <p className="text-xl font-bold font-display">{groupedJobs.failed.length} Failed</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-[10px] font-bold text-destructive">
            <Zap className="w-3 h-3" />
            <span>Active Alerts: {groupedJobs.failed.length}</span>
          </div>
        </Card>
      </div>
    </div>
  )
}
