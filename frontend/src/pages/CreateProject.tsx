import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  PlusIcon, 
  ArrowRight, 
  ArrowLeft, 
  Settings, 
  Palette, 
  Music, 
  Image as ImageIcon,
  Cpu,
  Play,
  CheckCircle2,
  Trash2,
  Upload,
  AlertCircle,
  Plus,
  GripVertical,
  ChevronDown,
  ChevronUp,
  FileJson,
  Camera,
  Layers
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { 
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { createRenderJob, DirectorialControls } from '@/lib/api'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'react-hot-toast'
import { cn } from '@/lib/utils'

const STEPS = ['Configuration', 'Direction', 'Assets', 'Scene Spec']

export default function CreateProject() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [projectData, setProjectData] = useState({
    name: '',
    sourceMode: 'manual',
    engine: 'Blender Lane',
    manualTopic: '',
    styleNotes: '',
    captionGoal: '',
    audioVibe: '',
    brandColors: '#0EA5E9',
    targetDuration: 12,
    templatePreference: 'auto',
  })
  const [assets, setAssets] = useState<File[]>([])
  const [sceneSpec, setSceneSpec] = useState<any>(null)
  const [directorialControls, setDirectorialControls] = useState<DirectorialControls>({})

  const updateControl = (key: keyof DirectorialControls, value: string) => {
    setDirectorialControls(prev => {
      if (value === 'auto') {
        const next = { ...prev }
        delete next[key]
        return next
      }
      return { ...prev, [key]: value }
    })
  }

  const handleNext = () => setStep(s => Math.min(s + 1, STEPS.length - 1))
  const handleBack = () => setStep(s => Math.max(s - 1, 0))

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setAssets(prev => [...prev, ...Array.from(e.target.files!)])
    }
  }

  const removeAsset = (index: number) => {
    setAssets(prev => prev.filter((_, i) => i !== index))
  }

  const generateSceneSpec = async () => {
    setIsLoading(true)
    // Simulate AI generation delay
    await new Promise(r => setTimeout(r, 2000))

    // Simple routing rules
    let selectedTemplate = 'Neon News'
    const topic = projectData.manualTopic.toLowerCase()
    if (topic.includes('luxury') || topic.includes('product') || topic.includes('drop') || topic.includes('ad')) {
      selectedTemplate = 'Product Pedestal'
    } else if (topic.includes('city') || topic.includes('street') || topic.includes('drive')) {
      selectedTemplate = 'City Loop'
    }

    const mockSpec = {
      template_name: selectedTemplate,
      title_text: projectData.name,
      subtitle_text: 'AI GENERATED PRODUCTION',
      subject: projectData.manualTopic,
      hook: 'Experience the future of short-form creative ops.',
      palette: {
        primary: projectData.brandColors || '#0EA5E9',
        accent: '#D946EF'
      },
      camera_beats: [
        { id: '1', type: 'Pan', duration: 2, start: [0, 0, 10], end: [10, 0, 10] },
        { id: '2', type: 'Zoom', duration: 3, start: [10, 0, 10], end: [10, 0, 5] },
      ],
      audio_hint: projectData.audioVibe || 'Cinematic, fast-paced',
      caption_text: projectData.captionGoal || 'The new standard for 3D video production.',
      duration_seconds: projectData.targetDuration,
      aspect_ratio: '9:16',
      fps: 60,
      output_resolution: {
        width: 1080,
        height: 1920
      }
    }

    setSceneSpec(mockSpec)
    setIsLoading(false)
    handleNext()
  }

  const updateSceneSpecField = (field: string, value: any) => {
    setSceneSpec((prev: any) => ({ ...prev, [field]: value }))
  }

  const updatePalette = (key: 'primary' | 'accent', value: string) => {
    setSceneSpec((prev: any) => ({
      ...prev,
      palette: { ...prev.palette, [key]: value }
    }))
  }

  const addCameraBeat = () => {
    const newBeat = {
      id: Math.random().toString(36).substr(2, 9),
      type: 'Static',
      duration: 2,
      start: [0, 0, 10],
      end: [0, 0, 10]
    }
    setSceneSpec((prev: any) => ({
      ...prev,
      camera_beats: [...prev.camera_beats, newBeat]
    }))
  }

  const removeCameraBeat = (id: string) => {
    setSceneSpec((prev: any) => ({
      ...prev,
      camera_beats: prev.camera_beats.filter((b: any) => b.id !== id)
    }))
  }

  const updateCameraBeat = (id: string, field: string, value: any) => {
    setSceneSpec((prev: any) => ({
      ...prev,
      camera_beats: prev.camera_beats.map((b: any) => b.id === id ? { ...b, [field]: value } : b)
    }))
  }

  const moveCameraBeat = (index: number, direction: 'up' | 'down') => {
    const newBeats = [...sceneSpec.camera_beats]
    const targetIndex = direction === 'up' ? index - 1 : index + 1
    if (targetIndex < 0 || targetIndex >= newBeats.length) return
    
    const [movedItem] = newBeats.splice(index, 1)
    newBeats.splice(targetIndex, 0, movedItem)
    
    setSceneSpec((prev: any) => ({
      ...prev,
      camera_beats: newBeats
    }))
  }

  const createAndQueueJob = async () => {
    setIsLoading(true)
    try {
      if (!sceneSpec) throw new Error('No scene specification generated')

      // Only include directorial controls if user set at least one
      const hasControls = Object.keys(directorialControls).length > 0
      const result = await createRenderJob({
        project_name: projectData.name || `Manifest ${Date.now()}`,
        topic: sceneSpec.subject || projectData.manualTopic || projectData.styleNotes || 'Blender Lane render',
        template_name: String(sceneSpec.template_name || projectData.templatePreference || 'neon_news')
          .toLowerCase()
          .replace(/\s+/g, '_'),
        ...(hasControls ? { directorial_controls: directorialControls } : {}),
      })

      const jobId = String(result?.job?.id)
      if (!jobId) throw new Error('Backend did not return a job id')

      localStorage.setItem(
        `sceneSpec:${jobId}`,
        JSON.stringify(sceneSpec)
      )

      localStorage.setItem(
        `projectMeta:${jobId}`,
        JSON.stringify({
          name: projectData.name,
          sourceMode: projectData.sourceMode,
          engine: projectData.engine,
          manualTopic: projectData.manualTopic,
          styleNotes: projectData.styleNotes,
          captionGoal: projectData.captionGoal,
          audioVibe: projectData.audioVibe,
          brandColors: projectData.brandColors,
          targetDuration: projectData.targetDuration,
          templatePreference: projectData.templatePreference,
          selectedTemplate: sceneSpec.template_name,
          createdAt: new Date().toISOString(),
          assets: assets.map((f) => ({ name: f.name, size: f.size, type: f.type })),
        })
      )

      if (assets.length > 0) {
        toast.success('Assets indexed locally for this production cycle.')
      }

      toast.success('Production cycle deployed to Blender queue!')
      navigate({ to: '/projects/$id', params: { id: jobId } as any })
    } catch (error: any) {
      toast.error(error?.message || 'Failed to create project')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="max-w-5xl mx-auto py-10 px-6">
      {/* Stepper Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-8 mb-16">
        <div className="space-y-2">
          <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20 uppercase tracking-[0.2em] font-bold text-[10px] px-3 py-1">
            New Project Initialization
          </Badge>
          <h1 className="text-4xl font-display font-bold tracking-tight text-white">Production Wizard</h1>
          <p className="text-muted-foreground">Follow the sequence to deploy a new Blender Lane production job.</p>
        </div>
        
        <div className="flex items-center gap-2 p-2 rounded-2xl glass-dark border border-white/5">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center group">
              <div className={cn(
                "w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold transition-all duration-500",
                i === step ? "bg-primary text-white neon-glow-primary scale-110 shadow-xl" : 
                i < step ? "bg-green-500 text-white" : "bg-white/5 text-muted-foreground border border-white/5"
              )}>
                {i < step ? <CheckCircle2 className="w-5 h-5" /> : i + 1}
              </div>
              {i < STEPS.length - 1 && (
                <div className={cn(
                  "w-8 md:w-12 h-[2px] mx-2 rounded-full transition-colors duration-500",
                  i < step ? "bg-green-500/50" : "bg-white/5"
                )} />
              )}
            </div>
          ))}
        </div>
      </div>

      <AnimatePresence mode="wait">
        {step === 0 && (
          <motion.div
            key="step0"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="space-y-8"
          >
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2 space-y-6">
                <Card className="glass border-white/5 rounded-3xl overflow-hidden">
                  <CardHeader className="p-8 border-b border-white/5 bg-white/[0.01]">
                    <CardTitle className="font-display text-2xl text-white">Identification</CardTitle>
                    <CardDescription>Assign global parameters to the production manifest.</CardDescription>
                  </CardHeader>
                  <CardContent className="p-8 space-y-8">
                    <div className="grid gap-8 md:grid-cols-2">
                      <div className="space-y-3">
                        <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Manifest Name</Label>
                        <Input 
                          placeholder="e.g. Q4_LUXURY_CAMPAIGN_V1" 
                          className="bg-white/5 border-white/10 focus:border-primary/50 h-14 rounded-2xl px-5 font-medium text-white transition-all focus:ring-4 focus:ring-primary/10"
                          value={projectData.name}
                          onChange={e => setProjectData({ ...projectData, name: e.target.value })}
                        />
                      </div>
                      <div className="space-y-3">
                        <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Traffic Mode</Label>
                        <Select 
                          value={projectData.sourceMode}
                          onValueChange={v => setProjectData({ ...projectData, sourceMode: v })}
                        >
                          <SelectTrigger className="bg-white/5 border-white/10 h-14 rounded-2xl px-5 text-white transition-all focus:ring-4 focus:ring-primary/10">
                            <SelectValue placeholder="Select mode" />
                          </SelectTrigger>
                          <SelectContent className="bg-[#020617] border-white/10 rounded-2xl overflow-hidden">
                            <SelectItem value="manual" className="rounded-xl mx-1 my-1">Manual Operator</SelectItem>
                            <SelectItem value="trend" className="rounded-xl mx-1 my-1">Market Trend Signal</SelectItem>
                            <SelectItem value="campaign" className="rounded-xl mx-1 my-1">Branded Brief Injection</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Core Objective / Prompt</Label>
                      <Textarea 
                        placeholder="Define the visual narrative..." 
                        className="bg-white/5 border-white/10 focus:border-primary/50 min-h-[160px] rounded-2xl p-5 text-white transition-all focus:ring-4 focus:ring-primary/10 leading-relaxed"
                        value={projectData.manualTopic}
                        onChange={e => setProjectData({ ...projectData, manualTopic: e.target.value })}
                      />
                      <div className="flex items-center gap-2 mt-2 px-1">
                        <Badge variant="ghost" className="text-[9px] text-muted-foreground/60 border-none bg-white/5">HINT</Badge>
                        <p className="text-[10px] text-muted-foreground italic tracking-wide">"Cinematic overhead shot of a carbon-fiber watch resting on a levitating matte black monolith."</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-6">
                <Card className="glass border-accent/20 bg-accent/5 rounded-3xl p-8 space-y-6">
                  <div className="w-12 h-12 rounded-2xl bg-accent/20 flex items-center justify-center text-accent neon-glow-accent">
                    <AlertCircle className="w-6 h-6" />
                  </div>
                  <div className="space-y-2">
                    <h3 className="font-display font-bold text-xl text-white">Operator Note</h3>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      All prompts are processed through our proprietary AI-adapter before being converted to Blender scene geometry. Precision in your description leads to higher quality geometry.
                    </p>
                  </div>
                  <div className="pt-4 border-t border-white/10 space-y-4">
                    <div className="flex items-center gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-primary shadow-[0_0_8px_hsl(var(--primary))]" />
                      <span className="text-[10px] font-bold text-white uppercase tracking-widest">Cycles GPU Engine</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-1.5 h-1.5 rounded-full bg-accent shadow-[0_0_8px_hsl(var(--accent))]" />
                      <span className="text-[10px] font-bold text-white uppercase tracking-widest">Ray-traced Lighting</span>
                    </div>
                  </div>
                </Card>
              </div>
            </div>

            <div className="flex justify-end pt-4">
              <Button 
                onClick={handleNext} 
                disabled={!projectData.name || !projectData.manualTopic}
                className="h-16 px-10 rounded-2xl text-lg font-bold neon-glow-primary bg-primary text-white transition-all hover:scale-105 active:scale-95 group"
              >
                Proceed to Direction 
                <ArrowRight className="ml-3 w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Button>
            </div>
          </motion.div>
        )}

        {step === 1 && (
          <motion.div
            key="step1"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="space-y-8"
          >
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2 space-y-6">
                <Card className="glass border-white/5 rounded-3xl overflow-hidden">
                  <CardHeader className="p-8 border-b border-white/5 bg-white/[0.01]">
                    <CardTitle className="font-display text-2xl text-white">Creative DNA</CardTitle>
                    <CardDescription>Inject stylistic DNA into the Blender Lane template.</CardDescription>
                  </CardHeader>
                  <CardContent className="p-8 space-y-8">
                    <div className="grid gap-8 md:grid-cols-2">
                      <div className="space-y-3">
                        <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Template Bias</Label>
                        <Select 
                          value={projectData.templatePreference}
                          onValueChange={v => setProjectData({ ...projectData, templatePreference: v })}
                        >
                          <SelectTrigger className="bg-white/5 border-white/10 h-14 rounded-2xl px-5 text-white transition-all focus:ring-4 focus:ring-primary/10">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-[#020617] border-white/10 rounded-2xl overflow-hidden">
                            <SelectItem value="auto" className="rounded-xl mx-1 my-1">Auto Routing (AI Optimized)</SelectItem>
                            <SelectItem value="Neon News" className="rounded-xl mx-1 my-1">Neon News Cluster</SelectItem>
                            <SelectItem value="Product Pedestal" className="rounded-xl mx-1 my-1">Product Pedestal Node</SelectItem>
                            <SelectItem value="City Loop" className="rounded-xl mx-1 my-1">City Loop Segment</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-3">
                        <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Timeline Duration (s)</Label>
                        <Input 
                          type="number" 
                          value={projectData.targetDuration}
                          onChange={e => setProjectData({ ...projectData, targetDuration: parseInt(e.target.value) })}
                          className="bg-white/5 border-white/10 h-14 rounded-2xl px-5 text-white transition-all focus:ring-4 focus:ring-primary/10" 
                        />
                      </div>
                    </div>

                    <div className="grid gap-8 md:grid-cols-2">
                      <div className="space-y-3">
                        <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1 flex items-center gap-2">
                          <Palette className="w-3.5 h-3.5 text-primary" /> Brand Primary (HEX)
                        </Label>
                        <div className="relative group">
                          <div className="absolute left-4 top-1/2 -translate-y-1/2 w-6 h-6 rounded-lg border border-white/10" style={{ backgroundColor: projectData.brandColors }} />
                          <Input 
                            value={projectData.brandColors}
                            onChange={e => setProjectData({ ...projectData, brandColors: e.target.value })}
                            className="bg-white/5 border-white/10 h-14 rounded-2xl pl-14 text-white transition-all focus:ring-4 focus:ring-primary/10 uppercase font-mono" 
                          />
                        </div>
                      </div>
                      <div className="space-y-3">
                        <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1 flex items-center gap-2">
                          <Music className="w-3.5 h-3.5 text-accent" /> Sonic Frequency
                        </Label>
                        <Input 
                          placeholder="e.g. DARK_AMBIENT_CYBER" 
                          value={projectData.audioVibe}
                          onChange={e => setProjectData({ ...projectData, audioVibe: e.target.value })}
                          className="bg-white/5 border-white/10 h-14 rounded-2xl px-5 text-white transition-all focus:ring-4 focus:ring-primary/10" 
                        />
                      </div>
                    </div>

                    <div className="space-y-3">
                      <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Technical Style Constraints</Label>
                      <Textarea
                        placeholder="Define visual constraints or edge behaviors..."
                        value={projectData.styleNotes}
                        onChange={e => setProjectData({ ...projectData, styleNotes: e.target.value })}
                        className="bg-white/5 border-white/10 focus:border-primary/50 min-h-[100px] rounded-2xl p-5 text-white transition-all focus:ring-4 focus:ring-primary/10 leading-relaxed"
                      />
                    </div>
                  </CardContent>
                </Card>

                {/* Directorial Controls */}
                <Card className="glass border-white/5 rounded-3xl overflow-hidden">
                  <Collapsible>
                    <CollapsibleTrigger asChild>
                      <CardHeader className="p-8 border-b border-white/5 bg-white/[0.01] cursor-pointer hover:bg-white/[0.02] transition-colors group">
                        <div className="flex items-center justify-between">
                          <div className="space-y-1">
                            <CardTitle className="font-display text-2xl text-white flex items-center gap-4">
                              <Layers className="w-6 h-6 text-accent" /> Directorial Controls
                            </CardTitle>
                            <CardDescription className="text-sm">Optional. Guide the AI director with motion, camera, and energy preferences.</CardDescription>
                          </div>
                          <ChevronDown className="w-5 h-5 text-muted-foreground group-data-[state=open]:rotate-180 transition-transform" />
                        </div>
                      </CardHeader>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <CardContent className="p-8 space-y-8 animate-in slide-in-from-top-4 duration-500">
                        <p className="text-xs text-muted-foreground/60 italic">All controls default to <span className="text-primary font-bold">Auto</span> — the AI director decides. Override any to guide the scene.</p>

                        <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-3">
                          <div className="space-y-3">
                            <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Motion Style</Label>
                            <Select
                              value={directorialControls.motion_style || 'auto'}
                              onValueChange={v => updateControl('motion_style', v)}
                            >
                              <SelectTrigger className="bg-white/5 border-white/10 h-14 rounded-2xl px-5 text-white transition-all focus:ring-4 focus:ring-accent/10">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent className="bg-[#020617] border-white/10 rounded-2xl overflow-hidden">
                                <SelectItem value="auto" className="rounded-xl mx-1 my-1">Auto (AI Decides)</SelectItem>
                                <SelectItem value="static" className="rounded-xl mx-1 my-1">Static</SelectItem>
                                <SelectItem value="driving" className="rounded-xl mx-1 my-1">Driving</SelectItem>
                                <SelectItem value="walking" className="rounded-xl mx-1 my-1">Walking</SelectItem>
                                <SelectItem value="dancing" className="rounded-xl mx-1 my-1">Dancing</SelectItem>
                                <SelectItem value="drifting" className="rounded-xl mx-1 my-1">Drifting</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>

                          <div className="space-y-3">
                            <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Camera Style</Label>
                            <Select
                              value={directorialControls.camera_style || 'auto'}
                              onValueChange={v => updateControl('camera_style', v)}
                            >
                              <SelectTrigger className="bg-white/5 border-white/10 h-14 rounded-2xl px-5 text-white transition-all focus:ring-4 focus:ring-accent/10">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent className="bg-[#020617] border-white/10 rounded-2xl overflow-hidden">
                                <SelectItem value="auto" className="rounded-xl mx-1 my-1">Auto (AI Decides)</SelectItem>
                                <SelectItem value="orbit" className="rounded-xl mx-1 my-1">Orbit</SelectItem>
                                <SelectItem value="tracking" className="rounded-xl mx-1 my-1">Tracking</SelectItem>
                                <SelectItem value="follow" className="rounded-xl mx-1 my-1">Follow</SelectItem>
                                <SelectItem value="handheld" className="rounded-xl mx-1 my-1">Handheld</SelectItem>
                                <SelectItem value="reveal" className="rounded-xl mx-1 my-1">Reveal</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>

                          <div className="space-y-3">
                            <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Scene Dynamics</Label>
                            <Select
                              value={directorialControls.scene_dynamics || 'auto'}
                              onValueChange={v => updateControl('scene_dynamics', v)}
                            >
                              <SelectTrigger className="bg-white/5 border-white/10 h-14 rounded-2xl px-5 text-white transition-all focus:ring-4 focus:ring-accent/10">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent className="bg-[#020617] border-white/10 rounded-2xl overflow-hidden">
                                <SelectItem value="auto" className="rounded-xl mx-1 my-1">Auto (AI Decides)</SelectItem>
                                <SelectItem value="static" className="rounded-xl mx-1 my-1">Static</SelectItem>
                                <SelectItem value="subtle" className="rounded-xl mx-1 my-1">Subtle</SelectItem>
                                <SelectItem value="cinematic" className="rounded-xl mx-1 my-1">Cinematic</SelectItem>
                                <SelectItem value="high_energy" className="rounded-xl mx-1 my-1">High Energy</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>

                          <div className="space-y-3">
                            <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Character Behavior</Label>
                            <Select
                              value={directorialControls.character_behavior || 'auto'}
                              onValueChange={v => updateControl('character_behavior', v)}
                            >
                              <SelectTrigger className="bg-white/5 border-white/10 h-14 rounded-2xl px-5 text-white transition-all focus:ring-4 focus:ring-accent/10">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent className="bg-[#020617] border-white/10 rounded-2xl overflow-hidden">
                                <SelectItem value="auto" className="rounded-xl mx-1 my-1">Auto (AI Decides)</SelectItem>
                                <SelectItem value="idle" className="rounded-xl mx-1 my-1">Idle</SelectItem>
                                <SelectItem value="walk" className="rounded-xl mx-1 my-1">Walk</SelectItem>
                                <SelectItem value="dance" className="rounded-xl mx-1 my-1">Dance</SelectItem>
                                <SelectItem value="perform" className="rounded-xl mx-1 my-1">Perform</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>

                          <div className="space-y-3">
                            <Label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Energy Level</Label>
                            <Select
                              value={directorialControls.energy_level || 'auto'}
                              onValueChange={v => updateControl('energy_level', v)}
                            >
                              <SelectTrigger className="bg-white/5 border-white/10 h-14 rounded-2xl px-5 text-white transition-all focus:ring-4 focus:ring-accent/10">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent className="bg-[#020617] border-white/10 rounded-2xl overflow-hidden">
                                <SelectItem value="auto" className="rounded-xl mx-1 my-1">Auto (AI Decides)</SelectItem>
                                <SelectItem value="calm" className="rounded-xl mx-1 my-1">Calm</SelectItem>
                                <SelectItem value="cinematic" className="rounded-xl mx-1 my-1">Cinematic</SelectItem>
                                <SelectItem value="high" className="rounded-xl mx-1 my-1">High</SelectItem>
                                <SelectItem value="chaotic" className="rounded-xl mx-1 my-1">Chaotic</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                        </div>

                        {Object.keys(directorialControls).length > 0 && (
                          <div className="flex items-center gap-3 pt-4 border-t border-white/5">
                            <Badge className="bg-accent/10 text-accent border-accent/20 text-[9px] font-bold uppercase tracking-widest">
                              {Object.keys(directorialControls).length} Override{Object.keys(directorialControls).length > 1 ? 's' : ''} Active
                            </Badge>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setDirectorialControls({})}
                              className="text-[10px] text-muted-foreground hover:text-white uppercase tracking-widest"
                            >
                              Reset All to Auto
                            </Button>
                          </div>
                        )}
                      </CardContent>
                    </CollapsibleContent>
                  </Collapsible>
                </Card>
              </div>

              <div className="space-y-6">
                <Card className="glass border-accent/20 bg-accent/5 rounded-3xl p-8 space-y-6">
                  <div className="w-12 h-12 rounded-2xl bg-accent/20 flex items-center justify-center text-accent neon-glow-accent">
                    <Settings className="w-6 h-6" />
                  </div>
                  <div className="space-y-2">
                    <h3 className="font-display font-bold text-xl text-white">Geometry Engine</h3>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      Lanes are pre-cached on our GPU farm. Custom durations exceeding 30s may trigger multi-node partitioning for faster delivery.
                    </p>
                  </div>
                  <div className="pt-4 border-t border-white/10 space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Target Resolution</span>
                      <Badge className="bg-black/40 text-white border-white/10 text-[9px] font-bold">4K ULTRA</Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Frame Sampling</span>
                      <Badge className="bg-black/40 text-white border-white/10 text-[9px] font-bold">512 SAMPLES</Badge>
                    </div>
                  </div>
                </Card>
              </div>
            </div>

            <div className="flex justify-between pt-4">
              <Button variant="ghost" onClick={handleBack} className="h-16 px-8 rounded-2xl text-muted-foreground hover:text-white hover:bg-white/5 transition-all">
                <ArrowLeft className="mr-3 w-5 h-5" /> Back to Identity
              </Button>
              <Button onClick={handleNext} className="h-16 px-10 rounded-2xl text-lg font-bold neon-glow-primary bg-primary text-white transition-all hover:scale-105 active:scale-95 group">
                Index Production Assets 
                <ArrowRight className="ml-3 w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Button>
            </div>
          </motion.div>
        )}

        {step === 2 && (
          <motion.div
            key="step2"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-6"
          >
            <div className="space-y-1">
              <h2 className="text-3xl font-display font-bold">Production Assets</h2>
              <p className="text-muted-foreground">Upload concept boards, brand logos, or visual references.</p>
            </div>
            
            <Card className="glass border-dashed border-2 hover:border-primary/50 transition-colors">
              <CardContent className="p-12 flex flex-col items-center justify-center space-y-4">
                <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
                  <Upload className="w-8 h-8 text-primary" />
                </div>
                <div className="text-center">
                  <p className="font-semibold">Drag and drop assets here</p>
                  <p className="text-sm text-muted-foreground">Supports PNG, JPG, PDF (Max 10MB each)</p>
                </div>
                <Label 
                  htmlFor="file-upload" 
                  className="px-6 py-3 bg-white/5 border border-white/10 rounded-lg cursor-pointer hover:bg-white/10 transition-colors"
                >
                  Select Files
                  <input id="file-upload" type="file" multiple className="hidden" onChange={handleFileChange} />
                </Label>
              </CardContent>
            </Card>

            {assets.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {assets.map((file, i) => (
                  <Card key={i} className="glass group">
                    <CardContent className="p-3 relative">
                      <div className="aspect-square rounded bg-secondary flex items-center justify-center mb-2 overflow-hidden">
                        {file.type.startsWith('image/') ? (
                          <img src={URL.createObjectURL(file)} alt="asset" className="w-full h-full object-cover" />
                        ) : (
                          <ImageIcon className="w-8 h-8 text-muted-foreground" />
                        )}
                      </div>
                      <p className="text-[10px] font-medium truncate">{file.name}</p>
                      <button 
                        onClick={() => removeAsset(i)}
                        className="absolute top-1 right-1 p-1 rounded-full bg-destructive text-white opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            <div className="flex justify-between">
              <Button variant="ghost" onClick={handleBack} className="h-12 px-6">
                <ArrowLeft className="mr-2 w-4 h-4" /> Back
              </Button>
              <Button onClick={generateSceneSpec} disabled={isLoading} className="h-12 px-8 neon-glow-primary">
                {isLoading ? (
                  <><Cpu className="w-4 h-4 mr-2 animate-spin" /> Analyzing Requirements...</>
                ) : (
                  <><Cpu className="w-4 h-4 mr-2" /> Generate Production Spec</>
                )}
              </Button>
            </div>
          </motion.div>
        )}

        {step === 3 && (
          <motion.div
            key="step3"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.02 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="space-y-10"
          >
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <Badge variant="secondary" className="bg-primary/10 text-primary border-primary/20 h-7 flex items-center gap-2 px-3 py-0 uppercase tracking-widest text-[10px] font-bold">
                    <Cpu className="w-3.5 h-3.5" /> AI Routing: {sceneSpec?.template_name}
                  </Badge>
                </div>
                <h2 className="text-5xl font-display font-bold text-white tracking-tight text-gradient">Production Manifest</h2>
                <p className="text-muted-foreground text-lg max-w-2xl">Validate the synthesized Blender scene manifest. Adjust geometry nodes and camera kinematics before cluster deployment.</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
              <div className="lg:col-span-8 space-y-10">
                {/* Visual Configuration */}
                <Card className="glass rounded-[40px] border-white/5 overflow-hidden shadow-2xl">
                  <CardHeader className="p-10 border-b border-white/5 bg-white/[0.01]">
                    <div className="flex items-center justify-between">
                      <div className="space-y-1">
                        <CardTitle className="font-display text-2xl text-white flex items-center gap-4">
                          <Settings className="w-7 h-7 text-primary" /> Visual Logic
                        </CardTitle>
                        <CardDescription className="text-sm">Calibrate text overlays and shader matrices.</CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="p-10 space-y-12">
                    <div className="grid gap-10 md:grid-cols-2">
                      <div className="space-y-4">
                        <Label className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1">Primary Header Node</Label>
                        <Input 
                          value={sceneSpec?.title_text}
                          onChange={e => updateSceneSpecField('title_text', e.target.value)}
                          className="bg-white/5 border-white/10 h-16 rounded-[20px] px-6 text-white text-lg font-bold transition-all focus:ring-8 focus:ring-primary/5 focus:border-primary/30"
                        />
                      </div>
                      <div className="space-y-4">
                        <Label className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1">Sub-Tier Text Node</Label>
                        <Input 
                          value={sceneSpec?.subtitle_text}
                          onChange={e => updateSceneSpecField('subtitle_text', e.target.value)}
                          className="bg-white/5 border-white/10 h-16 rounded-[20px] px-6 text-white text-lg transition-all focus:ring-8 focus:ring-primary/5 focus:border-primary/30"
                        />
                      </div>
                    </div>

                    <div className="grid gap-10 md:grid-cols-2">
                      <div className="space-y-4">
                        <Label className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1">Geometry Subject</Label>
                        <Input 
                          value={sceneSpec?.subject}
                          onChange={e => updateSceneSpecField('subject', e.target.value)}
                          className="bg-white/5 border-white/10 h-16 rounded-[20px] px-6 text-white transition-all focus:ring-8 focus:ring-primary/5 focus:border-primary/30"
                        />
                      </div>
                      <div className="space-y-4">
                        <Label className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1 flex items-center gap-2">
                          <Palette className="w-4 h-4" /> Shader Matrix
                        </Label>
                        <div className="flex items-center gap-6">
                          <div className="flex-1 flex items-center gap-4 px-5 py-4 rounded-[20px] bg-white/5 border border-white/10 transition-all hover:border-primary/30">
                            <div className="w-10 h-10 rounded-xl border border-white/20 shrink-0 shadow-2xl" style={{ backgroundColor: sceneSpec?.palette.primary }} />
                            <Input 
                              value={sceneSpec?.palette.primary}
                              onChange={e => updatePalette('primary', e.target.value)}
                              className="h-8 bg-transparent border-none p-0 text-sm font-mono uppercase text-white focus-visible:ring-0"
                            />
                          </div>
                          <div className="flex-1 flex items-center gap-4 px-5 py-4 rounded-[20px] bg-white/5 border border-white/10 transition-all hover:border-accent/30">
                            <div className="w-10 h-10 rounded-xl border border-white/20 shrink-0 shadow-2xl" style={{ backgroundColor: sceneSpec?.palette.accent }} />
                            <Input 
                              value={sceneSpec?.palette.accent}
                              onChange={e => updatePalette('accent', e.target.value)}
                              className="h-8 bg-transparent border-none p-0 text-sm font-mono uppercase text-white focus-visible:ring-0"
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <Label className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1">Narrative Sequence Hook</Label>
                      <Textarea 
                        value={sceneSpec?.hook}
                        onChange={e => updateSceneSpecField('hook', e.target.value)}
                        className="bg-white/5 border-white/10 focus:border-primary/30 min-h-[120px] rounded-[24px] p-6 text-white transition-all focus:ring-8 focus:ring-primary/5 leading-relaxed text-base"
                      />
                    </div>

                    {/* Technical Metadata Matrix */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4 border-t border-white/5">
                      <div className="space-y-3">
                        <Label className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1">Aspect Ratio</Label>
                        <Select 
                          value={sceneSpec?.aspect_ratio}
                          onValueChange={v => updateSceneSpecField('aspect_ratio', v)}
                        >
                          <SelectTrigger className="h-12 bg-white/5 border-white/10 rounded-xl text-white transition-all focus:ring-4 focus:ring-primary/5">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-[#020617] border-white/10 rounded-xl">
                            <SelectItem value="9:16">Vertical (9:16)</SelectItem>
                            <SelectItem value="16:9">Widescreen (16:9)</SelectItem>
                            <SelectItem value="1:1">Square (1:1)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-3">
                        <Label className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1">Frame Rate (FPS)</Label>
                        <Input 
                          type="number" 
                          value={sceneSpec?.fps}
                          onChange={e => updateSceneSpecField('fps', parseInt(e.target.value))}
                          className="h-12 bg-white/5 border-white/10 rounded-xl px-4 text-white font-mono"
                        />
                      </div>
                      <div className="space-y-3">
                        <Label className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1">Resolution Protocol</Label>
                        <div className="flex items-center gap-2">
                          <Input 
                            type="number" 
                            value={sceneSpec?.output_resolution?.width}
                            onChange={e => updateSceneSpecField('output_resolution', { ...sceneSpec.output_resolution, width: parseInt(e.target.value) })}
                            className="h-12 bg-white/5 border-white/10 rounded-xl px-4 text-white font-mono text-xs"
                          />
                          <span className="text-muted-foreground">x</span>
                          <Input 
                            type="number" 
                            value={sceneSpec?.output_resolution?.height}
                            onChange={e => updateSceneSpecField('output_resolution', { ...sceneSpec.output_resolution, height: parseInt(e.target.value) })}
                            className="h-12 bg-white/5 border-white/10 rounded-xl px-4 text-white font-mono text-xs"
                          />
                        </div>
                      </div>
                    </div>

                    <Collapsible className="space-y-6">
                      <CollapsibleTrigger asChild>
                        <Button variant="ghost" size="lg" className="w-full justify-between text-muted-foreground hover:text-white rounded-2xl bg-white/[0.02] hover:bg-white/[0.04] h-16 px-8 transition-all border border-transparent hover:border-white/5 group">
                          <span className="text-xs font-bold uppercase tracking-[0.3em]">Advanced Manifest Properties</span>
                          <ChevronDown className="w-5 h-5 group-data-[state=open]:rotate-180 transition-transform" />
                        </Button>
                      </CollapsibleTrigger>
                      <CollapsibleContent className="space-y-8 pt-6 px-4 animate-in slide-in-from-top-4 duration-500">
                        <div className="space-y-4">
                          <Label className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1">Sonic Frequency Profile</Label>
                          <Input 
                            value={sceneSpec?.audio_hint}
                            onChange={e => updateSceneSpecField('audio_hint', e.target.value)}
                            className="bg-white/5 border-white/10 h-16 rounded-[20px] px-6 text-white transition-all focus:ring-8 focus:ring-primary/5"
                          />
                        </div>
                        <div className="space-y-4">
                          <Label className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground/60 ml-1">Caption Layer Data</Label>
                          <Textarea 
                            value={sceneSpec?.caption_text}
                            onChange={e => updateSceneSpecField('caption_text', e.target.value)}
                            className="bg-white/5 border-white/10 h-28 rounded-[24px] p-6 text-white transition-all focus:ring-8 focus:ring-primary/5"
                          />
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  </CardContent>
                </Card>

                {/* Camera Beat Sequencer */}
                <Card className="glass rounded-[40px] border-white/5 overflow-hidden shadow-2xl">
                  <CardHeader className="p-10 border-b border-white/5 bg-white/[0.01] flex flex-row items-center justify-between">
                    <div className="space-y-1">
                      <CardTitle className="font-display text-2xl text-white flex items-center gap-4">
                        <Camera className="w-7 h-7 text-primary" /> Beat Sequencer
                      </CardTitle>
                      <CardDescription className="text-sm">Chain camera pathing nodes for this production cycle.</CardDescription>
                    </div>
                    <Button variant="outline" size="sm" onClick={addCameraBeat} className="glass rounded-xl h-12 px-6 text-[10px] font-bold uppercase tracking-widest text-primary border-primary/30 hover:bg-primary/10 transition-all active:scale-95">
                      <Plus className="w-4 h-4 mr-2" /> Add Sequence Node
                    </Button>
                  </CardHeader>
                  <CardContent className="p-10 space-y-8">
                    <div className="space-y-6">
                      {sceneSpec?.camera_beats.map((beat: any, index: number) => (
                        <motion.div 
                          layout
                          key={beat.id} 
                          className="flex items-start gap-8 p-8 rounded-[32px] bg-white/[0.02] border border-white/5 group relative hover:bg-white/[0.04] hover:border-primary/30 transition-all duration-500"
                        >
                          <div className="flex flex-col items-center gap-3 pt-2">
                            <Button variant="ghost" size="icon" className="h-10 w-10 rounded-xl hover:bg-white/5 text-muted-foreground/40 hover:text-white" onClick={() => moveCameraBeat(index, 'up')} disabled={index === 0}>
                              <ChevronUp className="w-5 h-5" />
                            </Button>
                            <div className="w-14 h-14 rounded-[20px] bg-primary/10 border border-primary/20 flex items-center justify-center text-primary text-lg font-bold font-display shadow-inner neon-glow-primary">
                              0{index + 1}
                            </div>
                            <Button variant="ghost" size="icon" className="h-10 w-10 rounded-xl hover:bg-white/5 text-muted-foreground/40 hover:text-white" onClick={() => moveCameraBeat(index, 'down')} disabled={index === sceneSpec.camera_beats.length - 1}>
                              <ChevronDown className="w-5 h-5" />
                            </Button>
                          </div>
                          
                          <div className="flex-1 grid gap-10 md:grid-cols-3">
                            <div className="space-y-3">
                              <Label className="text-[10px] uppercase font-bold text-muted-foreground/60 tracking-[0.2em] ml-1">Motion Protocol</Label>
                              <Select 
                                value={beat.type}
                                onValueChange={v => updateCameraBeat(beat.id, 'type', v)}
                              >
                                <SelectTrigger className="h-14 bg-white/5 border-white/10 rounded-2xl text-white font-bold transition-all focus:ring-8 focus:ring-primary/5">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-[#020617] border-white/10 rounded-2xl p-1">
                                  <SelectItem value="Pan" className="rounded-xl my-0.5">Kinetic Pan</SelectItem>
                                  <SelectItem value="Tilt" className="rounded-xl my-0.5">Dynamic Tilt</SelectItem>
                                  <SelectItem value="Dolly" className="rounded-xl my-0.5">Dolly Tracking</SelectItem>
                                  <SelectItem value="Zoom" className="rounded-xl my-0.5">Focal Zoom</SelectItem>
                                  <SelectItem value="Static" className="rounded-xl my-0.5">Static Lock</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-3">
                              <Label className="text-[10px] uppercase font-bold text-muted-foreground/60 tracking-[0.2em] ml-1">Duration Node (s)</Label>
                              <Input 
                                type="number" 
                                value={beat.duration}
                                onChange={e => updateCameraBeat(beat.id, 'duration', parseFloat(e.target.value))}
                                className="h-14 bg-white/5 border-white/10 rounded-2xl px-6 text-white font-mono text-lg font-bold"
                              />
                            </div>
                            <div className="flex items-end pb-1.5">
                              <Button variant="ghost" size="lg" className="h-14 w-full text-destructive hover:bg-destructive/10 rounded-2xl border border-transparent hover:border-destructive/20 opacity-0 group-hover:opacity-100 transition-all font-bold uppercase tracking-widest text-[10px]" onClick={() => removeCameraBeat(beat.id)}>
                                <Trash2 className="w-4 h-4 mr-3" /> Terminate Node
                              </Button>
                            </div>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="lg:col-span-4 space-y-10">
                <Card className="glass rounded-[40px] border-white/5 overflow-hidden sticky top-10 shadow-[0_40px_100px_-20px_rgba(0,0,0,0.8)]">
                  <CardHeader className="p-10 border-b border-white/5 bg-white/[0.01]">
                    <CardTitle className="text-xs font-display font-bold text-white flex items-center gap-4 uppercase tracking-[0.3em]">
                      <FileJson className="w-6 h-6 text-accent" /> Manifest Stream
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <div className="relative group">
                      <pre className="p-8 text-[11px] font-mono text-primary/80 bg-black/60 overflow-x-auto max-h-[500px] custom-scrollbar leading-relaxed">
                        {JSON.stringify(sceneSpec, null, 2)}
                      </pre>
                      <div className="absolute top-6 right-6 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Badge variant="outline" className="bg-black/60 backdrop-blur-md border-white/10 text-[9px] font-bold uppercase tracking-widest px-3 py-1">READ_ONLY_ACCESS</Badge>
                      </div>
                    </div>
                  </CardContent>
                  <CardFooter className="p-10 flex flex-col gap-8 border-t border-white/5 bg-white/[0.01]">
                    <div className="w-full space-y-5">
                      <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.2em] font-bold">
                        <span className="text-muted-foreground/60">Cluster Identity</span>
                        <span className="text-white">ALPHA_NODE_01</span>
                      </div>
                      <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.2em] font-bold">
                        <span className="text-muted-foreground/60">Geometry Pipeline</span>
                        <span className="text-white">{sceneSpec?.camera_beats.length} ACTIVE_NODES</span>
                      </div>
                      <div className="flex items-center justify-between text-base font-display font-bold pt-6 border-t border-white/5">
                        <span className="text-white uppercase tracking-widest">EST_RUNTIME</span>
                        <span className="text-primary text-3xl shadow-[0_0_20px_hsla(var(--primary)/0.3)]">{sceneSpec?.camera_beats.reduce((acc: number, b: any) => acc + b.duration, 0)}s</span>
                      </div>
                    </div>
                    
                    <div className="w-full space-y-4 pt-2">
                      <Button 
                        onClick={createAndQueueJob} 
                        disabled={isLoading}
                        size="lg"
                        className="w-full h-20 rounded-[24px] text-xl font-bold neon-glow-primary bg-primary text-white transition-all hover:scale-[1.02] active:scale-[0.98] shadow-2xl group"
                      >
                        {isLoading ? (
                          <><Cpu className="w-7 h-7 mr-4 animate-spin" /> Cluster Syncing...</>
                        ) : (
                          <><Play className="w-7 h-7 mr-4 fill-white group-hover:scale-110 transition-transform" /> Deploy Production Cycle</>
                        )}
                      </Button>
                      <Button variant="ghost" size="lg" onClick={handleBack} className="w-full h-14 rounded-2xl text-[11px] font-bold uppercase tracking-[0.3em] text-muted-foreground hover:text-white transition-all">
                        Abort to Index
                      </Button>
                    </div>
                  </CardFooter>
                </Card>

                <Card className="glass bg-accent/5 border-accent/20 rounded-[32px] p-8 shadow-xl">
                  <CardContent className="p-0 flex items-start gap-6">
                    <div className="w-14 h-14 rounded-2xl bg-accent/20 flex items-center justify-center text-accent shrink-0 mt-1 shadow-inner">
                      <AlertCircle className="w-7 h-7" />
                    </div>
                    <div className="space-y-2">
                      <p className="text-sm font-bold uppercase tracking-[0.2em] text-accent">Deployment Directive</p>
                      <p className="text-[11px] text-muted-foreground/80 leading-relaxed font-medium">
                        Deployment to the cluster creates an immutable manifest. Retries consume secondary GPU cycles. Verify kinematics before initiation.
                      </p>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

