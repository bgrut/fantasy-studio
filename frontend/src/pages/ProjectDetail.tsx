import React, { useEffect, useMemo, useState } from 'react'
import { useParams, Link, useNavigate } from '@tanstack/react-router'
import {
  ArrowLeft,
  Play,
  RefreshCcw,
  Copy,
  Download,
  Clock,
  CheckCircle2,
  XCircle,
  Activity,
  FileJson,
  Video,
  Layers,
  Zap,
  Terminal,
  Server,
  HardDrive,
  AlertTriangle,
  Sparkles,
  Camera,
  ScrollText,
  Sun,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import { cn } from '@/lib/utils'
import {
  getRenderJob,
  retryRenderJob,
  createRenderJob,
  getSettings,
  getRenderJobCredits,
  getRenderJobRecipe,
  type CreditsPayload,
  type SceneRecipe,
} from '@/lib/api'

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    queued: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    planning: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    rendering: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    complete: 'bg-green-500/10 text-green-400 border-green-500/20',
    failed: 'bg-red-500/10 text-red-400 border-red-500/20',
    draft: 'bg-white/5 text-muted-foreground border-white/10',
  }
  return (
    <Badge variant="outline" className={cn("uppercase tracking-[0.2em] font-bold text-[9px] px-3 py-1", map[status] || map.draft)}>
      {status}
    </Badge>
  )
}

export default function ProjectDetail() {
  const { id } = useParams({ from: '/projects/$id' })
  const navigate = useNavigate()
  const jobId = Number(id)

  const [job, setJob] = useState<any>(null)
  const [events, setEvents] = useState<any[]>([])
  const [sceneSpec, setSceneSpec] = useState<any>(null)
  const [projectMeta, setProjectMeta] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [providerMode, setProviderMode] = useState('Unknown')
  const [isReadyToPost, setIsReadyToPost] = useState(false)
  const [recipe, setRecipe] = useState<SceneRecipe | null>(null)
  const [credits, setCredits] = useState<CreditsPayload | null>(null)

  const fetchData = async () => {
    if (!Number.isFinite(jobId)) {
      setIsLoading(false)
      return
    }

    try {
      const [jobResp, settings] = await Promise.all([
        getRenderJob(jobId),
        getSettings(),
      ])

      setJob(jobResp.job)
      setEvents(jobResp.events || [])
      setProviderMode(settings.local_render_mode ? 'Hybrid CLI (Local)' : 'Simulated (Cloud Mock)')

      const rawSpec = localStorage.getItem(`sceneSpec:${jobId}`)
      const rawMeta = localStorage.getItem(`projectMeta:${jobId}`)

      if (rawSpec) {
        try { setSceneSpec(JSON.parse(rawSpec)) } catch {}
      }

      if (rawMeta) {
        try { setProjectMeta(JSON.parse(rawMeta)) } catch {}
      }

      // Fetch scene recipe + credits in parallel — both tolerate missing manifest.
      try {
        const [recipeResp, creditsResp] = await Promise.all([
          getRenderJobRecipe(jobId).catch(() => null),
          getRenderJobCredits(jobId).catch(() => null),
        ])
        if (recipeResp?.ok) setRecipe(recipeResp.recipe || null)
        if (creditsResp?.ok) setCredits(creditsResp.credits || null)
      } catch {
        // Silently ignore — manifest may not exist for this job yet.
      }
    } catch (error) {
      console.error('Failed to fetch project detail:', error)
      toast.error('Failed to load project details')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [jobId])

  const effectiveSpec = useMemo(() => {
    if (sceneSpec) return sceneSpec

    if (!job) return null

    return {
      template_name: job.template_name || 'neon_news',
      title_text: projectMeta?.name || job.project_name || `Job ${job.id}`,
      subtitle_text: 'AI GENERATED PRODUCTION',
      palette: {
        primary: projectMeta?.brandColors || '#0EA5E9',
        accent: '#D946EF',
      },
      subject: job.topic,
      hook: projectMeta?.captionGoal || 'Experience the future of short-form creative ops.',
      camera_beats: [],
      audio_hint: projectMeta?.audioVibe || '',
      caption_text: projectMeta?.captionGoal || '',
      duration_seconds: projectMeta?.targetDuration || 12,
      aspect_ratio: '9:16',
      fps: 24,
      output_resolution: { width: 1080, height: 1920 },
    }
  }, [sceneSpec, job, projectMeta])

  const copyJson = () => {
    if (!effectiveSpec) return
    navigator.clipboard.writeText(JSON.stringify(effectiveSpec, null, 2))
    toast.success('Scene manifest copied to clipboard')
  }

  const downloadSceneSpec = () => {
    if (!effectiveSpec) return

    const blob = new Blob([JSON.stringify(effectiveSpec, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(projectMeta?.name || job?.project_name || `job_${jobId}`).replace(/\s+/g, '_')}_manifest.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success('Manifest exported successfully')
  }

  const copyLog = (log: string | undefined) => {
    if (!log) return
    navigator.clipboard.writeText(log)
    toast.success('Production log copied to clipboard')
  }

  const copyCredits = () => {
    if (!credits?.text) return
    navigator.clipboard.writeText(credits.text)
    toast.success('Attribution credits copied to clipboard')
  }

  const deployNewJob = async () => {
    if (!effectiveSpec) {
      toast.error('No scene specification found')
      return
    }

    try {
      const result = await createRenderJob({
        project_name: projectMeta?.name || job?.project_name || `Job ${jobId}`,
        topic: effectiveSpec.subject || job?.topic || 'Blender Lane render',
        template_name: String(effectiveSpec.template_name || 'neon_news').toLowerCase().replace(/\s+/g, '_'),
      })

      const newJobId = String(result?.job?.id)
      if (newJobId) {
        localStorage.setItem(`sceneSpec:${newJobId}`, JSON.stringify(effectiveSpec))
        localStorage.setItem(`projectMeta:${newJobId}`, JSON.stringify(projectMeta || {}))
        toast.success('Project deployed to Blender Render Queue')
        navigate({ to: '/projects/$id', params: { id: newJobId } as any })
      } else {
        toast.success('Project deployed to Blender Render Queue')
      }
    } catch (error) {
      console.error('Failed to create render job:', error)
      toast.error('Failed to initialize production cycle')
    }
  }

  const retryJobNow = async () => {
    if (!job?.id) return
    try {
      await retryRenderJob(job.id)
      toast.success('Job re-queued successfully')
      fetchData()
    } catch (error) {
      toast.error('Failed to retry job')
    }
  }

  const toggleReadyToPost = () => {
    setIsReadyToPost(!isReadyToPost)
    toast.success(isReadyToPost ? 'Marked as draft' : 'Marked as Ready to Post')
  }

  if (isLoading) return <div className="p-8 text-center text-muted-foreground animate-pulse font-display uppercase tracking-widest">Accessing Node...</div>

  if (!job) {
    return (
      <div className="p-8 text-center text-white">
        Job not found.
        <div className="mt-4">
          <Link to="/queue">
            <Button variant="outline">Return to queue</Button>
          </Link>
        </div>
      </div>
    )
  }

  const projectName = projectMeta?.name || job.project_name || `Job ${job.id}`
  const outputUrl = job.output_url || null

  return (
    <div className="space-y-10 animate-reveal">
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-8">
        <div className="flex items-center gap-6">
          <Link to="/queue">
            <Button variant="ghost" size="icon" className="h-14 w-14 rounded-2xl glass transition-all hover:scale-105 active:scale-95 group">
              <ArrowLeft className="w-6 h-6 group-hover:-translate-x-1 transition-transform" />
            </Button>
          </Link>

          <div className="space-y-2">
            <div className="flex items-center gap-4">
              <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20 uppercase tracking-[0.2em] font-bold text-[9px] px-3 py-1">
                Production Manifest Detail
              </Badge>
              <StatusBadge status={job.status || 'draft'} />
            </div>
            <h1 className="text-5xl font-display font-bold tracking-tight text-white">{projectName}</h1>
            <div className="flex flex-wrap items-center gap-6 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
              <span className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-primary" /> {effectiveSpec?.template_name || job.template_name}</span>
              <div className="w-1 h-1 rounded-full bg-white/10" />
              <span className="flex items-center gap-2"><Clock className="w-3.5 h-3.5" /> Updated {formatDistanceToNow(new Date(job.updated_at))} ago</span>
              <div className="w-1 h-1 rounded-full bg-white/10" />
              <span className="flex items-center gap-2 px-2 py-0.5 rounded bg-white/5 border border-white/5 font-mono text-primary/80">JOB: {job.id}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {!['queued', 'planning', 'rendering'].includes(job.status) && (
            <Button size="lg" className="neon-glow-primary bg-primary text-white rounded-2xl h-14 px-8 font-bold text-sm transition-all hover:scale-105 active:scale-95 shadow-2xl" onClick={deployNewJob}>
              <Play className="w-5 h-5 mr-3 fill-white" /> Deploy Production Cycle
            </Button>
          )}

          {job.status === 'failed' && (
            <Button onClick={retryJobNow} size="lg" variant="outline" className="glass rounded-2xl h-14 px-8 font-bold uppercase tracking-widest text-[10px] transition-all hover:scale-105 active:scale-95 shadow-xl">
              <RefreshCcw className="w-4 h-4 mr-3" /> Re-Deploy Spec
            </Button>
          )}

          <Button variant="outline" className="rounded-2xl h-14 px-6" onClick={copyJson}>
            <Copy className="w-4 h-4 mr-2" /> Copy JSON
          </Button>

          <Button variant="outline" className="rounded-2xl h-14 px-6" onClick={downloadSceneSpec}>
            <Download className="w-4 h-4 mr-2" /> Download Manifest
          </Button>
        </div>
      </div>

      <div className="grid gap-10 xl:grid-cols-12">
        <div className="xl:col-span-8 space-y-8">
          <Card className="glass rounded-[36px] border-white/5 overflow-hidden">
            <CardHeader className="p-8 border-b border-white/5">
              <CardTitle className="font-display text-2xl text-white flex items-center gap-3">
                <FileJson className="w-6 h-6 text-primary" /> Manifest Stream
              </CardTitle>
              <CardDescription>Strict scene manifest used for this deployment cycle.</CardDescription>
            </CardHeader>
            <CardContent className="p-8">
              <pre className="bg-black/30 rounded-2xl p-6 overflow-auto text-cyan-300 text-xs leading-6 border border-white/5">
{JSON.stringify(effectiveSpec, null, 2)}
              </pre>
            </CardContent>
          </Card>

          <Tabs defaultValue="output" className="w-full">
            <TabsList className="grid grid-cols-3 w-full glass rounded-2xl h-14">
              <TabsTrigger value="output">Output</TabsTrigger>
              <TabsTrigger value="logs">Logs</TabsTrigger>
              <TabsTrigger value="events">Events</TabsTrigger>
            </TabsList>

            <TabsContent value="output" className="mt-6">
              <Card className="glass rounded-[36px] border-white/5 overflow-hidden">
                <CardHeader className="p-8 border-b border-white/5">
                  <CardTitle className="font-display text-2xl text-white flex items-center gap-3">
                    <Video className="w-6 h-6 text-primary" /> Render Output
                  </CardTitle>
                  <CardDescription>Completed MP4 output from the Blender lane.</CardDescription>
                </CardHeader>
                <CardContent className="p-8">
                  {outputUrl && job.status === 'complete' ? (
                    <div className="space-y-6">
                      <video controls className="w-full rounded-3xl border border-white/10 bg-black" src={outputUrl} />
                      <div className="flex flex-wrap gap-3">
                        <a href={outputUrl} target="_blank" rel="noreferrer">
                          <Button className="rounded-2xl">Open Output</Button>
                        </a>
                        <a href={outputUrl} download>
                          <Button variant="outline" className="rounded-2xl">Download MP4</Button>
                        </a>
                        <Button variant="outline" className="rounded-2xl" onClick={toggleReadyToPost}>
                          {isReadyToPost ? <XCircle className="w-4 h-4 mr-2" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
                          {isReadyToPost ? 'Mark Draft' : 'Mark Ready To Post'}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-muted-foreground">No completed MP4 available yet.</div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="logs" className="mt-6">
              <div className="grid gap-6 md:grid-cols-2">
                <Card className="glass rounded-[32px] border-white/5 overflow-hidden">
                  <CardHeader className="p-6 border-b border-white/5">
                    <CardTitle className="text-white flex items-center gap-2"><Terminal className="w-4 h-4 text-primary" /> Stdout</CardTitle>
                  </CardHeader>
                  <CardContent className="p-6">
                    <pre className="bg-black/30 rounded-2xl p-4 overflow-auto text-xs text-cyan-300 max-h-[500px] whitespace-pre-wrap">{job.stdout_log || 'No stdout log'}</pre>
                    <div className="mt-4">
                      <Button variant="outline" className="rounded-2xl" onClick={() => copyLog(job.stdout_log)}>Copy Stdout</Button>
                    </div>
                  </CardContent>
                </Card>

                <Card className="glass rounded-[32px] border-white/5 overflow-hidden">
                  <CardHeader className="p-6 border-b border-white/5">
                    <CardTitle className="text-white flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-amber-400" /> Stderr</CardTitle>
                  </CardHeader>
                  <CardContent className="p-6">
                    <pre className="bg-black/30 rounded-2xl p-4 overflow-auto text-xs text-amber-300 max-h-[500px] whitespace-pre-wrap">{job.stderr_log || 'No stderr log'}</pre>
                    <div className="mt-4">
                      <Button variant="outline" className="rounded-2xl" onClick={() => copyLog(job.stderr_log)}>Copy Stderr</Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="events" className="mt-6">
              <Card className="glass rounded-[36px] border-white/5 overflow-hidden">
                <CardHeader className="p-8 border-b border-white/5">
                  <CardTitle className="font-display text-2xl text-white flex items-center gap-3">
                    <Activity className="w-6 h-6 text-primary" /> Event Timeline
                  </CardTitle>
                  <CardDescription>Real backend job events for this render cycle.</CardDescription>
                </CardHeader>
                <CardContent className="p-8 space-y-4">
                  {events.length === 0 ? (
                    <div className="text-muted-foreground">No events found.</div>
                  ) : (
                    events.map((event) => (
                      <div key={event.id} className="rounded-2xl border border-white/5 bg-white/[0.02] p-4">
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <div className="text-white font-semibold uppercase tracking-widest text-[10px]">{event.stage}</div>
                            <div className="text-sm text-muted-foreground mt-1">{event.message}</div>
                          </div>
                          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                            {formatDistanceToNow(new Date(event.created_at))} ago
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        <div className="xl:col-span-4 space-y-8">
          <Card className="glass rounded-[36px] border-white/5 overflow-hidden">
            <CardHeader className="p-8 border-b border-white/5">
              <CardTitle className="font-display text-2xl text-white">Cluster Session</CardTitle>
              <CardDescription>Live job metadata from the backend worker.</CardDescription>
            </CardHeader>
            <CardContent className="p-8 space-y-5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-[0.2em] font-bold text-muted-foreground/60">Provider</span>
                <span className="text-white font-bold">{job.provider_name || providerMode}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-[0.2em] font-bold text-muted-foreground/60">Template</span>
                <span className="text-white font-bold">{effectiveSpec?.template_name || job.template_name}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-[0.2em] font-bold text-muted-foreground/60">Retries</span>
                <span className="text-white font-bold">{job.retry_count ?? 0}</span>
              </div>
              <div className="flex items-start justify-between gap-4">
                <span className="text-[11px] uppercase tracking-[0.2em] font-bold text-muted-foreground/60">Output Path</span>
                <span className="text-white font-mono text-xs text-right break-all">{job.local_output_path || 'N/A'}</span>
              </div>
              {job.error_text ? (
                <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-300">
                  {job.error_text}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="glass rounded-[36px] border-white/5 overflow-hidden">
            <CardHeader className="p-8 border-b border-white/5">
              <CardTitle className="font-display text-2xl text-white flex items-center gap-3">
                <Layers className="w-6 h-6 text-primary" /> Source Brief
              </CardTitle>
            </CardHeader>
            <CardContent className="p-8 space-y-4 text-sm">
              <div><span className="text-muted-foreground">Prompt:</span> <span className="text-white">{job.topic}</span></div>
              <div><span className="text-muted-foreground">Project Name:</span> <span className="text-white">{projectName}</span></div>
              <div><span className="text-muted-foreground">Brand Color:</span> <span className="text-white">{projectMeta?.brandColors || '#0EA5E9'}</span></div>
              <div><span className="text-muted-foreground">Duration:</span> <span className="text-white">{effectiveSpec?.duration_seconds || 12}s</span></div>
            </CardContent>
          </Card>

          {recipe ? <SceneBreakdownCard recipe={recipe} /> : null}

          {credits && credits.required ? (
            <CreditsCard credits={credits} onCopy={copyCredits} />
          ) : credits && !credits.required ? (
            <Card className="glass rounded-[36px] border-white/5 overflow-hidden">
              <CardHeader className="p-8 border-b border-white/5">
                <CardTitle className="font-display text-2xl text-white flex items-center gap-3">
                  <ScrollText className="w-6 h-6 text-primary" /> Attribution
                </CardTitle>
              </CardHeader>
              <CardContent className="p-8 text-sm text-muted-foreground">
                {credits.text || 'No attribution required — all assets are CC0.'}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function RecipeRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-[11px] uppercase tracking-[0.2em] font-bold text-muted-foreground/60">{label}</span>
      <span className="text-white text-xs text-right break-words">{value ?? '—'}</span>
    </div>
  )
}

function SceneBreakdownCard({ recipe }: { recipe: SceneRecipe }) {
  const summary = recipe.summary
  const hero = recipe.hero as any
  const camera = recipe.camera as any
  const lighting = recipe.lighting as any
  const atmosphere = recipe.atmosphere as any
  const ground = recipe.ground as any
  const sky = recipe.sky as any
  const hdriKeywords = Array.isArray(sky?.hdri_keywords) ? sky.hdri_keywords.slice(0, 6) : []

  return (
    <Card className="glass rounded-[36px] border-white/5 overflow-hidden">
      <CardHeader className="p-8 border-b border-white/5">
        <CardTitle className="font-display text-2xl text-white flex items-center gap-3">
          <Sparkles className="w-6 h-6 text-primary" /> Scene Breakdown
        </CardTitle>
        <CardDescription>How the prompt decomposed into a cinematic recipe.</CardDescription>
      </CardHeader>
      <CardContent className="p-8 space-y-4">
        {summary && (
          <>
            <RecipeRow label="Hero" value={summary.subject || hero?.query || '—'} />
            <RecipeRow label="Environment" value={summary.environment || '—'} />
            <RecipeRow label="Action" value={summary.action || '—'} />
            <RecipeRow label="Time of Day" value={summary.time_of_day || '—'} />
            <RecipeRow label="Mood" value={summary.mood || '—'} />
          </>
        )}
        <div className="h-px bg-white/5" />
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] font-bold text-muted-foreground/60">
          <Camera className="w-3.5 h-3.5" /> Camera
        </div>
        <RecipeRow
          label="Style"
          value={
            <span>
              {camera?.style || '—'}{' '}
              <span className="text-muted-foreground">· {camera?.lens ?? '—'}mm · f/{camera?.dof_fstop ?? '—'}</span>
            </span>
          }
        />
        <RecipeRow label="Angle" value={camera?.angle || '—'} />
        <div className="h-px bg-white/5" />
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] font-bold text-muted-foreground/60">
          <Sun className="w-3.5 h-3.5" /> Lighting &amp; Atmosphere
        </div>
        <RecipeRow
          label="Lighting"
          value={
            <span>
              {lighting?.style || '—'}{' '}
              <span className="text-muted-foreground">· {lighting?.color_temp || '—'} · {lighting?.key_energy ?? '—'}W</span>
            </span>
          }
        />
        <RecipeRow
          label="Atmosphere"
          value={
            <span>
              {atmosphere?.type || '—'}{' '}
              <span className="text-muted-foreground">· density {atmosphere?.density ?? '—'}</span>
            </span>
          }
        />
        <RecipeRow
          label="Ground"
          value={
            <span>
              {ground?.material || '—'}
              {ground?.detail ? <span className="text-muted-foreground"> · {ground.detail}</span> : null}
            </span>
          }
        />
        {hdriKeywords.length > 0 && (
          <div className="space-y-2">
            <span className="text-[11px] uppercase tracking-[0.2em] font-bold text-muted-foreground/60">HDRI Keywords</span>
            <div className="flex flex-wrap gap-1.5">
              {hdriKeywords.map((k: string) => (
                <Badge key={k} variant="outline" className="rounded-full border-white/10 text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
                  {k}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function CreditsCard({ credits, onCopy }: { credits: CreditsPayload; onCopy: () => void }) {
  return (
    <Card className="glass rounded-[36px] border-white/5 overflow-hidden">
      <CardHeader className="p-8 border-b border-white/5">
        <CardTitle className="font-display text-2xl text-white flex items-center gap-3">
          <ScrollText className="w-6 h-6 text-primary" /> Attribution Credits
        </CardTitle>
        <CardDescription>Required for CC-licensed assets used in this render.</CardDescription>
      </CardHeader>
      <CardContent className="p-8 space-y-4">
        <pre className="bg-black/30 rounded-2xl p-4 overflow-auto text-xs text-cyan-200 leading-6 border border-white/5 whitespace-pre-wrap max-h-[280px]">
{credits.text}
        </pre>
        <div className="space-y-2">
          {credits.items.map((c, i) => (
            <div key={`${c.name}-${i}`} className="rounded-2xl border border-white/5 bg-white/[0.02] p-3 text-xs">
              <div className="text-white font-semibold">{c.name}</div>
              <div className="text-muted-foreground">
                by {c.author} <span className="text-primary/70">· {c.license}</span>
              </div>
              {c.source ? (
                <a
                  href={c.source}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[10px] text-primary hover:underline break-all"
                >
                  {c.source}
                </a>
              ) : null}
            </div>
          ))}
        </div>
        <Button variant="outline" className="rounded-2xl w-full" onClick={onCopy}>
          <Copy className="w-4 h-4 mr-2" /> Copy Attribution Text
        </Button>
      </CardContent>
    </Card>
  )
}
