import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Sparkles,
  Send,
  Loader2,
  Film,
  Layers,
  Wand2,
  PlayCircle,
  RefreshCw,
  Image as ImageIcon,
  FileVideo,
  Download,
  AlertCircle,
  History,
  Zap,
  ChevronRight,
  ChevronDown,
  Sun,
  Camera,
  Wind,
  User,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import {
  renderPreview,
  submitOrchestrate,
  renderIterate,
  renderVariations,
  type IterationStep,
  type Variation,
  type RenderTier,
  type RenderExtrasResult,
  type DirectorialControls,
} from '@/lib/api'
import { motion, AnimatePresence } from 'framer-motion'
import VideoPlayer from '@/components/VideoPlayer'
import GameStudio from '@/components/GameStudio'
import CastPanel, { type CastChoice } from '@/components/CastPanel'
import InlineCastStrip, { type InlineCastSlot } from '@/components/InlineCastStrip'
import LibraryBrowser, { type LibraryBrowserChoice } from '@/components/LibraryBrowser'
import { recipeDisplayName } from '@/lib/recipes'
import { useToast } from '@/components/Toast'
import { pickPrompts, PROMPT_CHIP_COUNT, CURATED_PROMPTS } from '@/lib/curated_prompts'
import { analyzePrompt } from '@/lib/prompt_heuristics'
import { Lightbulb, FileBox } from 'lucide-react'
import ShowcaseCarousel from '@/components/ShowcaseCarousel'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select'
import ColorSwatchPicker from '@/components/ColorSwatchPicker'
import {
  EASE_OUT_SOFT,
  MOTION_STD,
  SPRING_BOUNCY,
  TRANSITION_STD,
} from '@/lib/motion'

// Phase 8: extend the locally-visible tier set with 'ai_compose' which routes
// to the orchestrator (POST /api/orchestrate) instead of the legacy preview pipeline.
type Tier = RenderTier | 'ai_compose'

// v1.4 polish — Phase 7 tier cards. Each tier carries a friendly label, a
// short descriptor, an estimated time, and a 1-4 dot quality indicator.
// spp counts hide behind a hover info icon (i icon tooltip).
const TIERS: {
  id: Tier
  label: string
  spp: string
  time: string
  descriptor: string
  dots: number
  color: string
  badge?: string
  hint: string
}[] = [
  { id: 'preview', label: 'Quick Preview', spp: 'Eevee · 16 samples', time: '~1 min', descriptor: 'Best for iterating', dots: 1, color: '#38d9c4', hint: 'Eevee engine, 16 samples. ~60 s render. Best for iterating on prompts.' },
  { id: 'fast', label: 'Polished', spp: 'Cycles · 32 spp', time: '~2 min', descriptor: 'Evaluate variations', dots: 2, color: '#7c5cff', hint: 'Cycles 32 samples. ~2 min render. Clean enough to evaluate variations.' },
  { id: 'standard', label: 'High Quality', spp: 'Cycles · 128 spp', time: '~5 min', descriptor: 'Production-ready', dots: 3, color: '#a78bfa', hint: 'Cycles 128 samples. ~5 min render. Sharp, low noise — production-ready.' },
  { id: 'cinematic', label: 'Final Cinematic', spp: 'Cycles · 512 spp', time: '~15 min', descriptor: 'Flagship hero shots', dots: 4, color: '#ff5c8a', badge: 'max quality', hint: 'Cycles 512 samples. ~15 min render. Flagship quality for hero shots.' },
  // Phase 8: local-LLM orchestrator. Composes the scene from English using
  // Ollama + the tool registry instead of running a template recipe. Status
  // visible in the bottom Pipeline panel — same render_jobs table.
  { id: 'ai_compose', label: 'AI Compose', spp: 'Ollama · Llama 3.1', time: '~2-3 min', descriptor: 'Compose from prompt', dots: 3, color: '#4de1ff', badge: 'experimental', hint: 'Local LLM (Ollama) composes the scene step-by-step using 30+ tools. No templates — pure prompt-driven generation.' },
]

// V1.4.2 launch-frame — prompt suggestions now read from the curated,
// verified set in src/lib/curated_prompts.ts. Single source of truth so
// the marketing demo prompts and the studio chips stay aligned.

// A7 — rotating placeholder hints for the iterate input + quick-chip presets
const ITERATE_PLACEHOLDER_HINTS = [
  'Try: "make it more dramatic"',
  'Try: "add fog"',
  'Try: "golden hour lighting"',
  'Try: "lower the camera"',
  'Try: "zoom out"',
]

const ITERATE_QUICK_CHIPS = [
  { label: '+ More dramatic', text: 'Make it more dramatic.' },
  { label: '+ Golden hour', text: 'Switch to golden hour lighting.' },
  { label: '+ Camera lower', text: 'Lower the camera angle.' },
]

// v1.4 polish — director-phrased stage labels cycle every ~5s while a render
// is in flight. COSMETIC cycling, not real progress (preview is synchronous).
// Real SSE-based progress on the V1.5 backlog.
const RENDER_STAGES = [
  { key: 'casting', label: 'Casting your scene…' },
  { key: 'building', label: 'Building the world…' },
  { key: 'camera', label: 'Setting up the camera…' },
  { key: 'lighting', label: 'Lighting…' },
  { key: 'rolling', label: 'Rolling…' },
  { key: 'cutting', label: 'Cutting the final video…' },
]
const RENDER_STAGE_INTERVAL_MS = 5000

type ChatTurn =
  | { kind: 'user'; text: string }
  | { kind: 'system'; step: IterationStep; render?: RenderExtrasResult | null }

export default function SceneStudio() {
  const [topic, setTopic] = useState('')
  const [template, setTemplate] = useState('auto')
  const [tier, setTier] = useState<Tier>('preview')

  // Phase 30 — studio MODE: video (Blender render) or game (playable export).
  // Persisted so the app reopens where the user works.
  const [mode, setMode] = useState<'video' | 'game'>(() => {
    try {
      return localStorage.getItem('fs.mode') === 'game' ? 'game' : 'video'
    } catch {
      return 'video'
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem('fs.mode', mode)
    } catch {}
  }, [mode])

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [previewResult, setPreviewResult] = useState<RenderExtrasResult | null>(null)
  const [chat, setChat] = useState<ChatTurn[]>([])
  const [busy, setBusy] = useState<'idle' | 'preview' | 'iterate' | 'controls' | 'variations'>('idle')
  const [error, setError] = useState<string | null>(null)

  const [instruction, setInstruction] = useState('')

  // Scene controls
  const [lighting, setLighting] = useState('')
  // v1.3.7 — separate camera_style (orbit/tracking/follow/handheld/reveal)
  // and a flag for explicit "Static". The frontend dropdown maps to one of:
  //   { camera_style?: string, camera_motion_disabled?: true }
  const [cameraStyle, setCameraStyle] = useState<'' | 'static' | 'tracking' | 'orbit' | 'push_in' | 'reveal'>('')
  const [brand, setBrand] = useState('#7c5cff')
  const [brandAccent, setBrandAccent] = useState('#ff5c8a')
  const [duration, setDuration] = useState(12)
  // v1.3.7 — secondary panels start collapsed to reduce visual noise.
  const [controlsOpen, setControlsOpen] = useState(false)
  const [iterateOpen, setIterateOpen] = useState(false)
  const [variationsOpen, setVariationsOpen] = useState(false)
  // A1 — Cinematic AI Direction (V1.3 template_v2). Default ON for new users,
  // persisted to localStorage.
  const [cinematicAI, setCinematicAI] = useState<boolean>(() => {
    try {
      const v = localStorage.getItem('fs.cinematicAI')
      return v === null ? true : v === '1'
    } catch {
      return true
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem('fs.cinematicAI', cinematicAI ? '1' : '0')
    } catch {}
  }, [cinematicAI])

  // V1.4.2 launch-frame — curated prompt set; randomized once per page
  // load so Studio feels fresh but stable within a session. PROMPT_CHIP_COUNT
  // (8) sits perfectly in two desktop rows / three mobile rows.
  const promptExamples = useMemo(() => pickPrompts(PROMPT_CHIP_COUNT), [])

  // V1.4.2 — heuristic advice. Runs every keystroke (it's cheap regex).
  // Soft signal only — never blocks Generate.
  const promptAdvice = useMemo(() => analyzePrompt(topic), [topic])

  // Dismissable. Cleared whenever the topic itself changes so the pill
  // re-evaluates against the new text.
  const [adviceDismissed, setAdviceDismissed] = useState<string | null>(null)
  useEffect(() => {
    setAdviceDismissed(null)
  }, [topic])

  // Three suggestion chips for the pill: pulled from curated set, picked
  // once per page load so they stay stable across edits.
  const adviceSuggestions = useMemo(() => pickPrompts(3), [])

  // A7 — rotate iterate placeholder hints every ~3.5s for discoverability.
  const [iteratePlaceholderIdx, setIteratePlaceholderIdx] = useState(0)
  useEffect(() => {
    const iv = setInterval(
      () =>
        setIteratePlaceholderIdx(
          (i) => (i + 1) % ITERATE_PLACEHOLDER_HINTS.length,
        ),
      3500,
    )
    return () => clearInterval(iv)
  }, [])
  const iteratePlaceholder = ITERATE_PLACEHOLDER_HINTS[iteratePlaceholderIdx]

  // v1.3.7 Phase 6 — cycling stage label while a render is in flight.
  const [renderStageIdx, setRenderStageIdx] = useState(0)
  useEffect(() => {
    if (busy !== 'preview') {
      setRenderStageIdx(0)
      return
    }
    const iv = setInterval(() => {
      setRenderStageIdx((i) => (i + 1) % RENDER_STAGES.length)
    }, RENDER_STAGE_INTERVAL_MS)
    return () => clearInterval(iv)
  }, [busy])

  // Phase 6 — pick a single nudge prompt for the empty-state CTA, stable
  // for the page lifetime so it doesn't churn on every state change.
  const emptyStateNudge = useMemo(
    () => promptExamples[Math.floor(Math.random() * promptExamples.length)],
    [promptExamples],
  )

  // Phase 6 — detect HERO_VERIFY-style failures so we can surface a
  // specific, actionable copy instead of the generic backend error.
  const friendlyError = useMemo(() => {
    if (!error) return null
    const e = error.toLowerCase()
    if (
      e.includes('hero_verify') ||
      e.includes('hero asset') ||
      e.includes('hero not found') ||
      e.includes('forced_hero') ||
      e.includes('not found in library')
    ) {
      return "The character or environment couldn't be loaded. Try changing the cast."
    }
    if (e.includes('timeout')) {
      return 'The render took too long. Try a simpler prompt or a lighter tier.'
    }
    return null
  }, [error])

  // Variations
  const [variationCount, setVariationCount] = useState(4)
  const [variations, setVariations] = useState<Variation[]>([])

  // Cast panel (hero + environment picker)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerPrompt, setPickerPrompt] = useState('')
  const [forcedHeroId, setForcedHeroId] = useState<string | null>(null)
  const [forcedEnvId, setForcedEnvId] = useState<string | null>(null)
  // When true, Generate bypasses the cast panel. Set by Assets-tab nav
  // (use this specific asset). Single-use: reset after consumption.
  const [skipPicker, setSkipPicker] = useState(false)

  // A3 — Inline cast preview. Mirror the CastPanel's confirmed selections so
  // the strip can show real thumbnails + titles. Persisted to sessionStorage
  // so they survive intra-session nav; cleared when the prompt is cleared.
  const [castHero, setCastHero] = useState<InlineCastSlot>(() => {
    try {
      const raw = sessionStorage.getItem('fs.cast.hero')
      return raw ? (JSON.parse(raw) as InlineCastSlot) : null
    } catch {
      return null
    }
  })
  const [castEnv, setCastEnv] = useState<InlineCastSlot>(() => {
    try {
      const raw = sessionStorage.getItem('fs.cast.env')
      return raw ? (JSON.parse(raw) as InlineCastSlot) : null
    } catch {
      return null
    }
  })
  useEffect(() => {
    try {
      if (castHero) sessionStorage.setItem('fs.cast.hero', JSON.stringify(castHero))
      else sessionStorage.removeItem('fs.cast.hero')
    } catch {}
  }, [castHero])
  useEffect(() => {
    try {
      if (castEnv) sessionStorage.setItem('fs.cast.env', JSON.stringify(castEnv))
      else sessionStorage.removeItem('fs.cast.env')
    } catch {}
  }, [castEnv])

  // v1.3.7 — per-slot library browser + "cast modified since last render" pill
  const [browserCategory, setBrowserCategory] = useState<'character' | 'environment' | null>(null)
  const [castModified, setCastModified] = useState(false)

  const chatScrollRef = useRef<HTMLDivElement | null>(null)

  // F4 — remember the last render parameters so the error toast's Retry button
  // can re-submit with the same hero/env.
  const lastRenderRef = useRef<{ heroId: string | null; envId: string | null } | null>(null)
  const { addToast } = useToast()
  // v1.4 polish — devtools mode toggle: surfaces session IDs + raw debug info
  // when the URL has ?dev=1. Hidden by default for non-technical users.
  const [devMode] = useState<boolean>(() => {
    try {
      return new URLSearchParams(window.location.search).has('dev')
    } catch {
      return false
    }
  })

  const scrollChatToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (chatScrollRef.current) {
        chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight
      }
    })
  }, [])

  // ── Asset preselect from Assets tab ────────────────────────────
  // Supported params: ?forced_hero_id=<id>&prompt=<text>
  // Legacy fallback: ?asset=<id>&topic=<text>
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const heroId = params.get('forced_hero_id') || params.get('asset')
    const preTopic = params.get('prompt') || params.get('topic')
    if (preTopic) setTopic(preTopic)
    if (heroId) {
      setForcedHeroId(heroId)
      setSkipPicker(true) // explicit pick from Assets → skip picker on Generate
    }
    if (heroId || preTopic) {
      // Clear query params so a reload doesn't re-trigger
      window.history.replaceState({}, '', window.location.pathname)
    }
    // run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ───────── Preview ─────────
  // v1.3.7 — Build the scene_params_override + directorial_controls payload
  // from the Scene Controls panel state. This is what 4.8 consolidates: the
  // SAME render path Generate uses also honors all controls.
  const buildSceneOverrides = useCallback(() => {
    const sceneOverride: Record<string, any> = {}
    if (lighting) sceneOverride.lighting_preset = lighting
    if (brand) sceneOverride.brand_primary = brand
    if (brandAccent) sceneOverride.brand_accent = brandAccent
    // Camera: explicit "Static" flips a real boolean the backend honors;
    // other choices feed directorial_controls.camera_style.
    let directorialControls: DirectorialControls | undefined
    if (cameraStyle === 'static') {
      sceneOverride.camera_motion_disabled = true
    } else if (cameraStyle) {
      // tracking / orbit / push_in / reveal map onto camera_style.
      directorialControls = { camera_style: cameraStyle as any }
    }
    return { sceneOverride, directorialControls }
  }, [lighting, brand, brandAccent, cameraStyle])

  // Fire the actual preview render (called after the cast panel confirms).
  const runPreviewRender = useCallback(
    async (heroId: string | null, envId: string | null) => {
      setError(null)
      setBusy('preview')
      setVariations([])
      setChat([])
      setForcedHeroId(heroId)
      setForcedEnvId(envId)
      lastRenderRef.current = { heroId, envId }

      // Phase 8 — AI Compose tier routes to the local-LLM orchestrator.
      // Returns immediately with a job_id; progress shows in PipelineStatus.
      if (tier === 'ai_compose') {
        try {
          const res = await submitOrchestrate({
            prompt: topic.trim(),
            duration_seconds: duration,
            fps: 24,
            render_tier: 'standard',
          })
          addToast('success', `Orchestrator submitted (job #${res.job_id}). Watch progress in the Pipeline panel below.`)
        } catch (e: any) {
          const msg = e?.message || 'Orchestrate submit failed'
          setError(msg)
          addToast('error', `Orchestrator submission failed: ${msg.slice(0, 120)}`)
        } finally {
          setBusy('idle')
        }
        return
      }

      const { sceneOverride, directorialControls } = buildSceneOverrides()
      try {
        const res = await renderPreview({
          topic: topic.trim(),
          template_name: template || 'auto',
          start_session: true,
          // v1.3.7 — Scene Controls now flow through main Generate.
          render_tier: tier as RenderTier,
          ...(directorialControls ? { directorial_controls: directorialControls } : {}),
          ...(Object.keys(sceneOverride).length > 0 ? { scene_params_override: sceneOverride } : {}),
          ...(duration ? { duration_seconds: duration } : {}),
          ...(heroId ? { forced_hero_id: heroId } : {}),
          ...(envId ? { forced_environment_id: envId } : {}),
          ...(cinematicAI ? { template_v2_enabled: true } : {}),
        })
        setPreviewResult(res)
        setSessionId(res.session_id || null)
        setCastModified(false)
        if (!res.ok) {
          const msg = res.error || 'Preview failed'
          setError(msg)
          addToast('error', `Render failed: ${msg.slice(0, 120)}`)
        }
      } catch (e: any) {
        const msg = e?.message || 'Preview failed'
        setError(msg)
        // F4 — 5xx / network error surfaces as a toast
        addToast('error', `Something went wrong: ${msg.slice(0, 120)}`)
      } finally {
        setBusy('idle')
      }
    },
    [topic, template, tier, duration, cinematicAI, buildSceneOverrides, addToast],
  )

  // User clicks Generate. The only time we skip the cast panel is when the
  // user arrived via the Assets-tab pre-lock flow (forcedHeroId AND skipPicker
  // both set). Every other Generate opens the panel so the choice is explicit.
  //
  // skipPicker is SINGLE-USE: consumed here so subsequent Generates go through
  // the panel as normal.
  const handleStartPreview = useCallback(() => {
    if (!topic.trim()) {
      setError('Enter a topic to start a session')
      return
    }
    setError(null)
    if (forcedHeroId && skipPicker) {
      setSkipPicker(false)
      // Pre-lock flow carries a hero only; env stays null so backend picks one.
      runPreviewRender(forcedHeroId, null)
      return
    }
    setPickerPrompt(topic.trim())
    setPickerOpen(true)
  }, [topic, forcedHeroId, skipPicker, runPreviewRender])

  const handlePickerConfirm = useCallback(
    (hero: CastChoice | null, env: CastChoice | null) => {
      setPickerOpen(false)
      setCastHero(hero ? { id: hero.id, title: hero.title, thumbnail_url: hero.thumbnail_url } : null)
      setCastEnv(env ? { id: env.id, title: env.title, thumbnail_url: env.thumbnail_url } : null)
      runPreviewRender(hero?.id ?? null, env?.id ?? null)
    },
    [runPreviewRender],
  )

  const handlePickerClose = useCallback(() => {
    setPickerOpen(false)
  }, [])

  // Open the cast panel without starting a render — used by the inline strip's
  // empty-state "Cast scene" action (prompt-aware re-pick of both slots).
  const openCastPanel = useCallback(() => {
    if (!topic.trim()) {
      setError('Type a prompt first')
      return
    }
    setError(null)
    setPickerPrompt(topic.trim())
    setPickerOpen(true)
  }, [topic])

  // v1.3.7 — per-slot library browser. Opens the paginated browser scoped
  // to one category and updates only that cast slot on choose.
  const openHeroBrowser = useCallback(() => setBrowserCategory('character'), [])
  const openEnvBrowser = useCallback(() => setBrowserCategory('environment'), [])
  const handleBrowserChoose = useCallback(
    (choice: LibraryBrowserChoice) => {
      const slot: InlineCastSlot = {
        id: choice.id,
        title: choice.title,
        thumbnail_url: choice.thumbnail_url ?? null,
      }
      if (browserCategory === 'character') {
        setCastHero(slot)
        setForcedHeroId(choice.id)
      } else if (browserCategory === 'environment') {
        setCastEnv(slot)
        setForcedEnvId(choice.id)
      }
      setBrowserCategory(null)
      // If a successful render already exists, mark cast as modified so the
      // user knows the next Generate will reflect their new choice.
      if (previewResult?.output_url) setCastModified(true)
    },
    [browserCategory, previewResult],
  )

  // Clear cast slots when the user clears the prompt entirely.
  useEffect(() => {
    if (!topic.trim()) {
      setCastHero(null)
      setCastEnv(null)
    }
  }, [topic])

  // ───────── Iterate ─────────
  const handleIterate = useCallback(async () => {
    if (!sessionId) {
      setError('Start a preview session first')
      return
    }
    if (!instruction.trim()) return
    setError(null)
    setBusy('iterate')
    const userText = instruction.trim()
    setChat((prev) => [...prev, { kind: 'user', text: userText }])
    setInstruction('')
    scrollChatToBottom()
    try {
      const res = await renderIterate({
        session_id: sessionId,
        instruction: userText,
        render: true,
        render_tier: tier,
      })
      setChat((prev) => [...prev, { kind: 'system', step: res.step, render: res.render_result }])
      if (res.render_result?.output_url) {
        setPreviewResult(res.render_result)
      }
      if (!res.ok || (res.render_result && !res.render_result.ok)) {
        setError(res.render_result?.error || 'Iteration render failed')
      }
      scrollChatToBottom()
    } catch (e: any) {
      setError(e?.message || 'Iteration failed')
    } finally {
      setBusy('idle')
    }
  }, [sessionId, instruction, tier, scrollChatToBottom])

  // ───────── Variations ─────────
  const handleVariations = useCallback(async () => {
    if (!topic.trim()) {
      setError('Enter a topic first')
      return
    }
    setError(null)
    setBusy('variations')
    setVariations([])
    try {
      const res = await renderVariations({
        topic: topic.trim(),
        template_name: template,
        count: variationCount,
        render: true,
        render_tier: 'preview',
      })
      setVariations(res.variations || [])
    } catch (e: any) {
      setError(e?.message || 'Variations failed')
    } finally {
      setBusy('idle')
    }
  }, [topic, template, variationCount])

  const isRendering = busy === 'preview'

  return (
    // v1.4 polish — Phase 2 page-load entrance choreography. Direct children
    // fade-in-and-rise sequentially with 80ms stagger, total under 1.2s.
    <div className="space-y-8 entrance-stagger">
      {/* ── Hero Prompt ────────────────────────────────────── */}
      {/* v1.4 follow-up — title in Cabinet Grotesk display face, full title
          inherits the animated text-gradient (purple→pink→teal). overflow-hidden
          on the wrapper as a defensive guard against any horizontal layout
          shift during page entrance / render state changes. */}
      <div className="text-center space-y-3 pt-4 overflow-x-clip">
        <h1 className="font-display text-5xl sm:text-6xl md:text-7xl font-bold leading-[1.0] text-gradient inline-block">
          What do you Imagine?
        </h1>
        <p className="text-sm sm:text-base text-[#807d99] max-w-lg mx-auto">
          {mode === 'game'
            ? 'Type a prompt. AI directs. You play.'
            : 'Type a prompt. AI directs. Blender renders.'}
        </p>
      </div>

      {/* Phase 30 — Video / Game mode chooser */}
      <div className="flex justify-center">
        <div className="inline-flex items-center p-1 rounded-2xl border border-white/[0.06] bg-[rgba(14,14,22,0.7)] backdrop-blur-xl">
          {(
            [
              { id: 'video' as const, label: '🎬 Video', hint: 'Cinematic render' },
              { id: 'game' as const, label: '🕹️ Game', hint: 'Playable world' },
            ]
          ).map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMode(m.id)}
              className={cn(
                'px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 flex flex-col items-center leading-tight',
                mode === m.id
                  ? m.id === 'game'
                    ? 'bg-[#5cffc9]/15 text-[#5cffc9] shadow-[0_0_18px_-6px_rgba(92,255,201,0.5)]'
                    : 'bg-[#7c5cff]/20 text-[#a78bfa] shadow-[0_0_18px_-6px_rgba(124,92,255,0.5)]'
                  : 'text-[#4a4764] hover:text-[#807d99]'
              )}
            >
              <span>{m.label}</span>
              <span className="text-[9px] font-normal opacity-70">{m.hint}</span>
            </button>
          ))}
        </div>
      </div>

      {mode === 'game' && <GameStudio />}

      <div className={mode === 'game' ? 'hidden' : 'space-y-8'}>
      {/* Prompt input */}
      <div className="max-w-2xl mx-auto space-y-3">
        <div className="relative group">
          <input
            data-prompt-input
            data-tour-id="prompt-input"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleStartPreview()
              }
            }}
            placeholder="A cheetah in the desert..."
            className={cn(
              'w-full rounded-2xl bg-[rgba(14,14,22,0.7)] backdrop-blur-xl border px-4 sm:px-6 py-3 sm:py-4 text-base sm:text-lg text-white',
              'placeholder:text-[#4a4764] focus:outline-none transition-all duration-300 focus-glow',
              isRendering
                ? 'border-[#ff5c8a]/40 glow-border'
                : 'border-white/[0.05]'
            )}
          />
          <Tooltip>
            <TooltipTrigger
              data-tour-id="generate-btn"
              render={(props) => (
                <button
                  {...props}
                  onClick={handleStartPreview}
                  disabled={busy !== 'idle' || !topic.trim()}
                  // v1.4.1 audit — drop min-width (was producing visual
                  // off-center). Both states use identical icon + text DOM
                  // shape so flexbox centering is consistent. Icon swaps
                  // Sparkles ↔ Loader2; label swaps Generate ↔ Rendering.
                  className={cn(
                    'absolute right-2 top-1/2 -translate-y-1/2 px-5 py-2.5 rounded-xl font-semibold text-sm',
                    'inline-flex items-center justify-center gap-2 leading-none',
                    'transition-transform duration-200 active:scale-[0.97] hover:scale-[1.02]',
                    busy === 'preview'
                      ? 'btn-generate btn-generate-rendering text-white shadow-[0_0_18px_-4px_rgba(255,92,138,0.4)]'
                      : busy !== 'idle' || !topic.trim()
                        ? 'bg-white/[0.05] text-[#4a4764] cursor-not-allowed'
                        : 'btn-generate cursor-pointer hover:shadow-[0_8px_30px_-5px_rgba(124,92,255,0.5)]',
                  )}
                >
                  {busy === 'preview' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4" />
                  )}
                  <span>{busy === 'preview' ? 'Rendering' : 'Generate'}</span>
                </button>
              )}
            />
            <TooltipContent side="bottom" sideOffset={8}>
              {busy === 'preview'
                ? 'Rendering your scene…'
                : !topic.trim()
                  ? 'Type a prompt first'
                  : 'Render this scene · 60–90 s'}
            </TooltipContent>
          </Tooltip>
        </div>

        {/* Prompt examples — 7 random from a 12-pool; rotating highlight */}
        <PromptSuggestions examples={promptExamples} onSelect={setTopic} />

        {/* V1.4.2 launch-frame — soft heuristic guardrail. Brand-tinted
            info pill (NOT red/error). Doesn't block Generate. Three curated
            suggestions for friction-free recovery. Dismissable. */}
        <AnimatePresence>
          {!promptAdvice.ok &&
            promptAdvice.reason &&
            adviceDismissed !== promptAdvice.reason && (
              <motion.div
                key="prompt-advice"
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.22, ease: EASE_OUT_SOFT }}
                className="mx-auto max-w-2xl"
              >
                <div className="rounded-xl border border-[#7c5cff]/25 bg-[#7c5cff]/[0.06] px-3 py-2.5 flex items-start gap-2.5">
                  <Lightbulb className="w-4 h-4 text-[#a78bfa] flex-shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0 space-y-2">
                    <p className="text-xs sm:text-sm text-white/90">
                      {promptAdvice.reason}{' '}
                      <span className="text-[#807d99]">
                        Try one of these proven prompts:
                      </span>
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {adviceSuggestions.map((suggestion) => (
                        <button
                          key={suggestion}
                          type="button"
                          onClick={() => setTopic(suggestion)}
                          className="rounded-full border border-[#7c5cff]/30 bg-[#7c5cff]/[0.08] px-3 py-1 text-[11px] font-mono text-[#a78bfa] hover:border-[#7c5cff]/50 hover:bg-[#7c5cff]/15 hover:text-white transition-all hover:scale-[1.02] active:scale-[0.98]"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setAdviceDismissed(promptAdvice.reason || null)}
                    aria-label="Dismiss suggestion"
                    className="flex-shrink-0 p-1 rounded-md text-[#4a4764] hover:text-white hover:bg-white/[0.05] transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </motion.div>
            )}
        </AnimatePresence>

        {/* Forced hero asset pin — only shown while the next Generate will
            actually use it (i.e., pre-lock flow from Assets tab). Once
            consumed, the pin hides so it can't mislead the user about the
            upcoming Generate. */}
        {forcedHeroId && skipPicker && (
          <div className="flex items-center justify-center">
            <div className="inline-flex items-center gap-2 pl-3 pr-1.5 py-1.5 rounded-full border border-[#7c5cff]/30 bg-[#7c5cff]/10 text-xs shadow-[0_0_18px_rgba(124,92,255,0.15)]">
              <Sparkles className="w-3 h-3 text-[#a78bfa]" />
              <span className="text-[#a78bfa] font-mono">
                Using asset:{' '}
                <span className="text-white">{prettyAssetId(forcedHeroId)}</span>
              </span>
              <button
                type="button"
                onClick={() => {
                  // "change" — drop the pre-lock so next Generate opens picker
                  setForcedHeroId(null)
                  setSkipPicker(false)
                }}
                className="ml-1 px-2 py-0.5 rounded-full border border-white/[0.08] bg-white/[0.03] text-[#a78bfa] hover:bg-[#7c5cff]/15 hover:text-white transition-all text-[10px] font-semibold"
              >
                change
              </button>
              <button
                type="button"
                onClick={() => {
                  // "×" — dismiss the pin. Next Generate opens the picker,
                  // where "Surprise Me" gives AI auto-match if they want it.
                  setForcedHeroId(null)
                  setSkipPicker(false)
                }}
                aria-label="Dismiss pinned asset"
                className="p-1 rounded-full text-[#4a4764] hover:bg-white/[0.06] hover:text-white transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Error + Retry (F4) */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex items-start gap-3 rounded-2xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-400 max-w-2xl mx-auto"
          >
            <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0" />
            <span className="flex-1">{error}</span>
            {lastRenderRef.current && busy === 'idle' && (
              <button
                onClick={() =>
                  runPreviewRender(
                    lastRenderRef.current!.heroId,
                    lastRenderRef.current!.envId,
                  )
                }
                className="flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-[11px] font-semibold border border-red-500/30 bg-red-500/10 text-red-300 hover:bg-red-500/20 hover:text-white transition-all"
              >
                Retry
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* A3 — Inline Cast preview strip. Per-slot Change opens the paginated
          library browser (Phase 3); empty-state Cast scene opens the full
          prompt-aware Cast panel. */}
      {topic.trim() && (
        <InlineCastStrip
          hero={castHero}
          env={castEnv}
          onCast={openCastPanel}
          onChangeHero={openHeroBrowser}
          onChangeEnv={openEnvBrowser}
          modified={castModified}
          disabled={busy !== 'idle'}
        />
      )}

      {/* ── Main Content: Video + Sidebar ──────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Video player / render status */}
        <div className="lg:col-span-2 space-y-4">
          {/* A6 — indeterminate progress strip while a render is in flight */}
          {isRendering && (
            <div className="relative h-1 w-full overflow-hidden rounded-full bg-white/[0.04]">
              <div
                className="absolute inset-y-0 left-0 h-full rounded-full"
                style={{
                  width: '35%',
                  background:
                    'linear-gradient(90deg, transparent 0%, rgba(255,92,138,0.7) 30%, rgba(124,92,255,0.9) 55%, rgba(56,217,196,0.7) 80%, transparent 100%)',
                  animation: 'fs-progress-shimmer 1.4s linear infinite',
                }}
              />
              <style>{`@keyframes fs-progress-shimmer{0%{transform:translateX(-30%)}100%{transform:translateX(300%)}}`}</style>
            </div>
          )}

          <div className="glass rounded-2xl overflow-hidden card-hover">
            {/* Compact header — Output title only. Technical badges (recipe,
                tier, session id) move under the video as secondary text. */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.05]">
              <div className="flex items-center gap-2">
                <Film className="w-4 h-4 text-[#7c5cff]" />
                <span className="text-sm font-semibold">Output</span>
              </div>
            </div>

            {previewResult?.output_url ? (
              <div>
                {/* v1.4 polish — promote the video as the page's primary
                    surface. Brand-tinted asymmetric drop shadow (purple
                    upper-left, pink lower-right). Scale-in entrance + one-shot
                    pulse ring on render completion. */}
                <div className="bg-[#070710] py-4 px-3 flex items-center justify-center">
                  <motion.div
                    key={previewResult.output_url}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: MOTION_STD, ease: EASE_OUT_SOFT }}
                    className="rounded-2xl overflow-hidden video-brand-frame completion-pulse"
                  >
                    <VideoPlayer
                      src={previewResult.output_url}
                      className="aspect-[9/16] w-full max-h-[78vh] sm:max-h-[68vh]"
                    />
                  </motion.div>
                </div>
                {/* Secondary metadata under the video */}
                <div className="px-5 py-3 flex flex-wrap items-center gap-3 border-t border-white/[0.05]">
                  {(() => {
                    const name = recipeDisplayName(previewResult?.recipe_name)
                    return name ? (
                      <span className="text-xs font-mono text-[#807d99]">
                        AI directed as:{' '}
                        <span className="text-white">{name}</span>
                      </span>
                    ) : null
                  })()}
                  {previewResult.render_tier && (
                    <Badge className="bg-[#7c5cff]/10 text-[#a78bfa] border-[#7c5cff]/20 text-xs rounded-lg">
                      {previewResult.render_tier}
                    </Badge>
                  )}
                  <a
                    href={previewResult.output_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-[#7c5cff] hover:text-[#a78bfa] transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" /> Download MP4
                  </a>

                  {/* v1.4.3 polish — companion .blend download. Hidden when
                      the backend didn't save one (e.g. older renders or save
                      failure). Blender-orange accent (#ea7600) creates
                      instant visual distinction from the MP4 link. Tooltip
                      converts the feature from "developer thing" to
                      "creator ownership signal". */}
                  {previewResult.blend_url && (
                    <Tooltip>
                      <TooltipTrigger
                        render={(props) => (
                          <a
                            {...props}
                            href={previewResult.blend_url || undefined}
                            target="_blank"
                            rel="noreferrer"
                            download
                            className="inline-flex items-center gap-1.5 text-xs text-[#ea7600] hover:text-[#ff8c1a] transition-colors"
                          >
                            <FileBox className="w-3.5 h-3.5" />
                            Download .blend
                          </a>
                        )}
                      />
                      <TooltipContent side="top" className="max-w-[280px]">
                        Open this scene in Blender to edit, re-render, or remix.
                        Free at{' '}
                        <span className="text-[#ea7600] underline">
                          blender.org
                        </span>
                        .
                      </TooltipContent>
                    </Tooltip>
                  )}
                  {/* Session ID hidden unless ?dev=1 query param is set */}
                  {sessionId && devMode && (
                    <Tooltip>
                      <TooltipTrigger
                        render={(props) => (
                          <span
                            {...props}
                            className="ml-auto text-[10px] font-mono text-[#3a3850] cursor-help"
                          >
                            {sessionId.slice(0, 8)}
                          </span>
                        )}
                      />
                      <TooltipContent>session: {sessionId}</TooltipContent>
                    </Tooltip>
                  )}
                </div>
              </div>
            ) : (
              <div className="min-h-[60vh] sm:min-h-[55vh] aspect-[9/16] sm:aspect-auto flex items-center justify-center bg-[#0a0a10] mx-auto" style={{ maxWidth: 480 }}>
                {isRendering ? (
                  // v1.4 polish — director-phrased cycling stage label, big
                  // centered cube, brand-gradient bar, expectation line.
                  // Stage label cross-fades for a softer feel.
                  <div className="text-center space-y-6 px-6">
                    <div className="spinning-cube mx-auto" />
                    <div className="space-y-2">
                      <AnimatePresence mode="wait">
                        <motion.p
                          key={RENDER_STAGES[renderStageIdx].key}
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -4 }}
                          transition={{ duration: 0.32, ease: EASE_OUT_SOFT }}
                          className="font-display text-base font-semibold text-white"
                        >
                          {RENDER_STAGES[renderStageIdx].label}
                        </motion.p>
                      </AnimatePresence>
                      <p className="text-xs text-[#807d99]">
                        This usually takes 60–90 seconds.
                      </p>
                    </div>
                    <div className="w-56 mx-auto h-1.5 rounded-full bg-white/[0.05] overflow-hidden">
                      <div className="h-full progress-gradient rounded-full" style={{ width: '45%' }} />
                    </div>
                  </div>
                ) : friendlyError || (error && !isRendering) ? (
                  // v1.4 Wave C — richer error state. Friendly icon + display
                  // headline + recovery actions (Try again + Change cast).
                  // Errors should feel recoverable, not terminal.
                  <div className="text-center space-y-5 px-6 max-w-sm">
                    {/* Icon with brand-pink soft glow ring */}
                    <div className="relative w-14 h-14 mx-auto">
                      <div className="absolute inset-0 rounded-full bg-[#ff5c8a]/10 animate-pulse" />
                      <div className="absolute inset-1.5 rounded-full bg-[#ff5c8a]/15 border border-[#ff5c8a]/30 flex items-center justify-center">
                        <AlertCircle className="w-6 h-6 text-[#ff5c8a]" />
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <p className="font-display text-base font-semibold text-white">
                        {friendlyError || 'Hmm, something went wrong directing this scene.'}
                      </p>
                      <p className="text-xs text-[#807d99]">
                        Try the same shot again, or recast the scene with new players.
                      </p>
                    </div>
                    {/* Recovery actions: primary Retry + secondary Change cast */}
                    <div className="flex items-center justify-center gap-2 flex-wrap">
                      {lastRenderRef.current && (
                        <button
                          onClick={() =>
                            runPreviewRender(
                              lastRenderRef.current!.heroId,
                              lastRenderRef.current!.envId,
                            )
                          }
                          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold border border-[#ff5c8a]/30 bg-[#ff5c8a]/10 text-[#ff5c8a] hover:bg-[#ff5c8a]/20 hover:text-white transition-all hover:scale-[1.03] active:scale-[0.97]"
                        >
                          <RefreshCw className="w-3.5 h-3.5" />
                          Try again
                        </button>
                      )}
                      <button
                        onClick={() => {
                          // Clear error, open Cast panel for re-pick
                          setError(null)
                          openCastPanel()
                        }}
                        disabled={!topic.trim()}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold border border-white/[0.08] bg-white/[0.03] text-[#a78bfa] hover:bg-[#7c5cff]/15 hover:border-[#7c5cff]/30 hover:text-white transition-all hover:scale-[1.03] active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        Change cast
                      </button>
                    </div>
                  </div>
                ) : (
                  // V1.4.2 launch-frame — empty Output panel shows the
                  // ShowcaseCarousel auto-cycling 4 hero clips. Click any
                  // clip to copy its prompt into the input. If the MP4s
                  // aren't on disk yet (or any fail to load), the carousel
                  // gracefully falls back to the v1.4 cube empty state.
                  <ShowcaseCarousel
                    onSelectPrompt={(p) => setTopic(p)}
                    fallback={
                      <div className="text-center space-y-5 px-6 max-w-sm">
                        <div className="relative w-14 h-14 mx-auto flex items-center justify-center">
                          <div
                            className="absolute inset-0 rounded-full opacity-30 animate-pulse"
                            style={{
                              background: 'radial-gradient(circle, rgba(124,92,255,0.35), rgba(255,92,138,0.18) 50%, transparent 70%)',
                            }}
                          />
                          <div className="spinning-cube relative z-10" />
                        </div>
                        <div className="space-y-2">
                          <p className="font-display text-base font-semibold text-white">
                            Your scene will appear here
                          </p>
                          <p className="text-xs text-[#807d99] leading-relaxed">
                            Type any prompt above. I'll cast, light, and shoot it for you.
                          </p>
                          <div className="flex items-center justify-center gap-1.5 pt-1">
                            {[0, 1, 2].map((i) => (
                              <span
                                key={i}
                                className="w-1 h-1 rounded-full bg-gradient-to-br from-[#7c5cff] to-[#ff5c8a] opacity-40 animate-pulse"
                                style={{ animationDelay: `${i * 240}ms`, animationDuration: '1800ms' }}
                              />
                            ))}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => setTopic(emptyStateNudge)}
                          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-[#7c5cff]/20 bg-[#7c5cff]/[0.06] text-[11px] font-mono text-[#a78bfa] hover:border-[#7c5cff]/40 hover:bg-[#7c5cff]/12 transition-all hover:scale-[1.02] active:scale-[0.98]"
                        >
                          <Sparkles className="w-3 h-3" />
                          try: {emptyStateNudge}
                        </button>
                      </div>
                    }
                  />
                )}
              </div>
            )}
          </div>

          {/* Iteration chat input — collapsible */}
          <div className="glass rounded-2xl card-hover overflow-hidden">
            <button
              type="button"
              onClick={() => setIterateOpen((v) => !v)}
              aria-expanded={iterateOpen}
              className="w-full flex items-center justify-between gap-2 px-4 py-3 hover:bg-white/[0.02] transition-colors"
            >
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-[#ff5c8a]" />
                <span className="text-sm font-semibold">Refine this scene</span>
                {chat.length > 0 && (
                  <span className="text-[10px] font-mono text-[#4a4764]">
                    {chat.filter((t) => t.kind === 'user').length} change{chat.length === 1 ? '' : 's'}
                  </span>
                )}
              </div>
              <ChevronDown
                className={cn(
                  'w-4 h-4 text-[#4a4764] transition-transform duration-300',
                  iterateOpen && 'rotate-180',
                )}
              />
            </button>
            <AnimatePresence>
            {iterateOpen && (
            <motion.div
              initial={{ height: 0 }}
              animate={{ height: 'auto' }}
              exit={{ height: 0 }}
              className="overflow-hidden"
            >
            <div className="px-4 pb-4 border-t border-white/[0.05] pt-4">

            {/* Chat history */}
            {chat.length > 0 && (
              <div
                ref={chatScrollRef}
                className="max-h-[240px] overflow-y-auto space-y-2 mb-3 custom-scrollbar"
              >
                {chat.map((turn, i) =>
                  turn.kind === 'user' ? (
                    <div key={i} className="rounded-xl bg-[#7c5cff]/10 border border-[#7c5cff]/20 px-3 py-2 text-sm text-white">
                      {turn.text}
                    </div>
                  ) : (
                    <div key={i} className="rounded-xl bg-white/[0.03] border border-white/[0.05] px-3 py-2 text-sm text-[#807d99]">
                      <div className="flex items-center gap-1 text-xs text-[#ff5c8a] mb-1 font-mono">
                        <Sparkles className="w-3 h-3" /> {turn.step.source}
                      </div>
                      <div className="text-white/90">{turn.step.notes || 'manifest mutated'}</div>
                      {turn.render?.output_url && (
                        <a href={turn.render.output_url} target="_blank" rel="noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-[#7c5cff] hover:text-[#a78bfa] mt-1">
                          <FileVideo className="w-3 h-3" /> Open render
                        </a>
                      )}
                      {turn.render && !turn.render.ok && (
                        <div className="text-xs text-red-400 mt-1">{turn.render.error}</div>
                      )}
                    </div>
                  )
                )}
              </div>
            )}

            <div className="flex gap-2">
              <input
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleIterate()
                  }
                }}
                placeholder={sessionId ? 'Tell me what to change…' : 'Generate a render first'}
                disabled={!sessionId || busy !== 'idle'}
                className="flex-1 rounded-xl bg-white/[0.03] border border-white/[0.05] px-4 py-3 text-sm text-white placeholder:text-[#4a4764] focus:outline-none focus-glow-pink transition-colors disabled:opacity-40"
              />
              <button
                onClick={handleIterate}
                disabled={!sessionId || busy !== 'idle' || !instruction.trim()}
                className={cn(
                  'px-4 py-3 rounded-xl transition-all duration-200 flex items-center gap-2',
                  !sessionId || busy !== 'idle' || !instruction.trim()
                    ? 'bg-white/[0.03] text-[#4a4764] cursor-not-allowed'
                    : 'bg-[#ff5c8a]/15 text-[#ff5c8a] hover:bg-[#ff5c8a]/25 border border-[#ff5c8a]/20'
                )}
              >
                {busy === 'iterate' ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>

            {/* A7 — quick-chip modifiers */}
            <div className="flex flex-wrap gap-2 mt-3">
              {ITERATE_QUICK_CHIPS.map((chip) => (
                <button
                  key={chip.label}
                  type="button"
                  disabled={!sessionId || busy !== 'idle'}
                  onClick={() =>
                    setInstruction((cur) =>
                      cur.trim() ? `${chip.text} ${cur.trim()}` : chip.text,
                    )
                  }
                  className={cn(
                    'rounded-full border px-3 py-1 text-[11px] font-mono transition-all',
                    !sessionId || busy !== 'idle'
                      ? 'border-white/[0.04] bg-white/[0.02] text-[#4a4764] cursor-not-allowed'
                      : 'border-[#ff5c8a]/20 bg-[#ff5c8a]/5 text-[#ff5c8a] hover:bg-[#ff5c8a]/12 hover:border-[#ff5c8a]/35',
                  )}
                >
                  {chip.label}
                </button>
              ))}
            </div>
            </div>
            </motion.div>
            )}
            </AnimatePresence>
          </div>
        </div>

        {/* Right: Scene controls sidebar */}
        <div className="space-y-4">
          {/* Render Tier */}
          <div className="glass rounded-2xl p-5 card-hover">
            <div className="flex items-center gap-2 mb-4">
              <Zap className="w-4 h-4 text-[#ffc857]" />
              <span className="text-sm font-semibold">Render Tier</span>
            </div>
            <div className="space-y-2">
              {TIERS.map((t) => {
                const isSelected = tier === t.id
                return (
                <button
                  key={t.id}
                  onClick={() => setTier(t.id)}
                  className={cn(
                    'group w-full flex items-center gap-3 px-4 py-3 rounded-xl border text-left',
                    'transition-all duration-300',
                    isSelected
                      ? 'gradient-border-rotate border-transparent bg-[#7c5cff]/[0.08] shadow-[0_8px_22px_-8px_rgba(0,0,0,0.5),_0_0_18px_-4px_rgba(124,92,255,0.35)]'
                      : 'border-white/[0.05] bg-white/[0.02] hover:border-white/[0.1] hover:bg-white/[0.04]'
                  )}
                >
                  <div
                    className={cn(
                      'w-3 h-3 rounded-full border-2 transition-all flex-shrink-0',
                      isSelected
                        ? 'border-[#7c5cff] bg-[#7c5cff] shadow-[0_0_8px_rgba(124,92,255,0.5)]'
                        : 'border-[#4a4764]'
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-white">{t.label}</span>
                      {t.badge && (
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-full border border-[#ff5c8a]/30 bg-[#ff5c8a]/10 text-[#ff5c8a]">
                          {t.badge}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[10px] text-[#807d99]">{t.descriptor}</span>
                      <span className="text-[10px] font-mono text-[#4a4764]">·</span>
                      <span className="text-[10px] font-mono text-[#4a4764]">{t.time}</span>
                    </div>
                  </div>
                  {/* 1–4 quality dots */}
                  <div className="flex items-center gap-0.5 flex-shrink-0">
                    {[1, 2, 3, 4].map((dotIdx) => (
                      <span
                        key={dotIdx}
                        className={cn(
                          'w-1 h-1 rounded-full transition-colors',
                          dotIdx <= t.dots
                            ? isSelected
                              ? 'bg-[#a78bfa]'
                              : 'bg-[#4a4764]'
                            : 'bg-white/[0.04]',
                        )}
                      />
                    ))}
                  </div>
                  {/* v1.4 polish — info tooltip with engine + samples + time
                      estimate. Hidden until hover so spp jargon doesn't
                      overwhelm non-engineers. */}
                  <Tooltip>
                    <TooltipTrigger
                      render={(props) => (
                        <div
                          {...props}
                          className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 cursor-help"
                          aria-label={`${t.label} info`}
                        >
                          <div className="w-4 h-4 rounded-full border border-[#4a4764] text-[10px] font-mono text-[#4a4764] flex items-center justify-center hover:text-white hover:border-white/30 transition-colors">
                            i
                          </div>
                        </div>
                      )}
                    />
                    <TooltipContent side="left" className="max-w-[260px]">
                      <div className="space-y-1">
                        <div className="font-mono text-[10px] uppercase tracking-wider text-[#a78bfa]">{t.spp}</div>
                        <div className="text-white/90">{t.hint}</div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </button>
              )
              })}
            </div>
          </div>

          {/* Scene Controls */}
          <div className="glass rounded-2xl overflow-hidden card-hover">
            <button
              onClick={() => setControlsOpen(!controlsOpen)}
              className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition-colors"
            >
              <div className="flex items-center gap-2">
                <Wand2 className="w-4 h-4 text-[#7c5cff]" />
                <span className="text-sm font-semibold">Scene Controls</span>
              </div>
              <ChevronDown className={cn(
                'w-4 h-4 text-[#4a4764] transition-transform duration-300',
                controlsOpen && 'rotate-180'
              )} />
            </button>

            <AnimatePresence>
              {controlsOpen && (
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: 'auto' }}
                  exit={{ height: 0 }}
                  className="overflow-hidden"
                >
                  <div className="px-5 pb-5 space-y-4 border-t border-white/[0.05] pt-4">
                    {/* A1 — Cinematic AI Direction (V1.3 template_v2) */}
                    <div data-tour-id="cinematic-ai-toggle" className="rounded-xl border border-[#7c5cff]/20 bg-[#7c5cff]/[0.06] px-3 py-2.5 space-y-1.5">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <Sparkles className="w-3.5 h-3.5 text-[#a78bfa] flex-shrink-0" />
                          <label
                            htmlFor="cinematic-ai-toggle"
                            className="text-xs font-medium text-white truncate"
                          >
                            Cinematic AI Direction
                          </label>
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] font-mono font-semibold bg-[#ff5c8a]/15 border border-[#ff5c8a]/30 text-[#ff5c8a]">
                            beta
                          </span>
                        </div>
                        <Tooltip>
                          <TooltipTrigger
                            render={(props) => (
                              <button
                                {...props}
                                id="cinematic-ai-toggle"
                                type="button"
                                role="switch"
                                aria-checked={cinematicAI}
                                onClick={() => setCinematicAI((v) => !v)}
                                className={cn(
                                  'relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full border transition-colors',
                                  cinematicAI
                                    ? 'bg-[#7c5cff]/80 border-[#7c5cff] shadow-[0_0_10px_rgba(124,92,255,0.4)]'
                                    : 'bg-white/[0.05] border-white/[0.1]',
                                )}
                              >
                                <span
                                  className={cn(
                                    'inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform',
                                    cinematicAI ? 'translate-x-5' : 'translate-x-0.5',
                                  )}
                                />
                              </button>
                            )}
                          />
                          <TooltipContent side="left" className="max-w-[260px]">
                            When on, the AI plans camera, lighting, and pacing for you. When off, uses deterministic templates.
                          </TooltipContent>
                        </Tooltip>
                      </div>
                      <p className="text-[11px] font-mono text-[#4a4764] leading-snug">
                        Let the director decide.
                      </p>
                    </div>

                    {/* v1.4 polish — Phase 7 ui/select.tsx replacing native
                        <select>. Each item carries a tooltip-style descriptor.
                        Values map to REAL backend preset keys. */}
                    <ControlField icon={<Sun className="w-3.5 h-3.5 text-[#ffc857]" />} label="Lighting">
                      <Select
                        value={lighting || 'default'}
                        onValueChange={(v: string) => setLighting(v === 'default' ? '' : v)}
                      >
                        <SelectTrigger className="w-full rounded-lg bg-white/[0.03] border border-white/[0.05] px-3 py-2 text-sm text-white hover:border-[#7c5cff]/30 hover:bg-white/[0.05] h-auto">
                          <SelectValue placeholder="Default" />
                        </SelectTrigger>
                        <SelectContent className="elevation-3 border-white/[0.1] rounded-xl">
                          <LightingItem value="default" label="Default (let AI decide)" hint="The director chooses lighting based on the prompt." />
                          <LightingItem value="sunset_landscape" label="Golden Hour" hint="Warm low sun, long shadows, glowing rim. Best for outdoor and natural scenes." />
                          <LightingItem value="studio_five_point" label="Overcast" hint="Soft, neutral, even illumination. Flatters most subjects, low drama." />
                          <LightingItem value="studio_five_point" label="Studio" hint="Five-point stage lighting. Clean key + back + fill, ideal for products and characters." />
                          <LightingItem value="neon_city" label="Night" hint="Cool key with magenta and cyan accent practicals. Cinematic neon mood." />
                        </SelectContent>
                      </Select>
                    </ControlField>

                    {/* Camera: maps to directorial_controls.camera_style + an
                        explicit camera_motion_disabled flag for "Static". */}
                    <ControlField icon={<Camera className="w-3.5 h-3.5 text-[#38d9c4]" />} label="Camera">
                      <Select
                        value={cameraStyle || 'default'}
                        onValueChange={(v: string) => setCameraStyle(v === 'default' ? '' : (v as any))}
                      >
                        <SelectTrigger className="w-full rounded-lg bg-white/[0.03] border border-white/[0.05] px-3 py-2 text-sm text-white hover:border-[#7c5cff]/30 hover:bg-white/[0.05] h-auto">
                          <SelectValue placeholder="Default" />
                        </SelectTrigger>
                        <SelectContent className="elevation-3 border-white/[0.1] rounded-xl">
                          <CameraItem value="default" label="Default (let AI decide)" hint="The director picks camera motion based on the prompt." />
                          <CameraItem value="static" label="Static (no motion)" hint="Locked tripod. No drift, no motion. Best for product shots and architectural reveals." />
                          <CameraItem value="tracking" label="Tracking" hint="Camera follows the subject as they move through the scene." />
                          <CameraItem value="orbit" label="Orbit" hint="Smooth circular arc around the subject. Reveals shape and context." />
                          <CameraItem value="push_in" label="Push-in" hint="Slow dolly forward, building intimacy and tension." />
                          <CameraItem value="reveal" label="Pull-back / Reveal" hint="Camera pulls back to reveal scale and surroundings." />
                        </SelectContent>
                      </Select>
                    </ControlField>

                    <ControlField icon={<Wind className="w-3.5 h-3.5 text-[#a78bfa]" />} label={`Duration: ${duration}s`}>
                      <input
                        type="range"
                        min={4}
                        max={24}
                        step={4}
                        value={duration}
                        onChange={(e) => setDuration(parseInt(e.target.value, 10))}
                        className="w-full accent-[#7c5cff] h-1"
                      />
                    </ControlField>

                    {/* v1.4 polish — Phase 7 swatch + hex pickers. Replaces
                        native <input type=color> with brand-aligned palette
                        + custom hex. */}
                    <ControlField icon={<User className="w-3.5 h-3.5 text-[#ff5c8a]" />} label="Brand Colors">
                      <div className="flex gap-3 items-center flex-wrap">
                        <div className="flex items-center gap-1.5">
                          <ColorSwatchPicker
                            value={brand}
                            onChange={setBrand}
                            label="Primary"
                            tooltip="Primary color used for hero accents and UI elements in the render."
                          />
                          <span className="text-[10px] font-mono text-[#4a4764]">primary</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <ColorSwatchPicker
                            value={brandAccent}
                            onChange={setBrandAccent}
                            label="Accent"
                            tooltip="Secondary color used for highlights, edges, and rim lighting accents."
                          />
                          <span className="text-[10px] font-mono text-[#4a4764]">accent</span>
                        </div>
                      </div>
                    </ControlField>

                    {/* v1.4 polish — Template via ui/select. Each option's
                        tooltip describes the family of scene it produces. */}
                    <div className="pt-2 border-t border-white/[0.05]">
                      <label className="text-xs font-mono text-[#4a4764] block mb-1.5">Template</label>
                      <Select value={template} onValueChange={(v: string) => setTemplate(v)}>
                        <SelectTrigger className="w-full rounded-lg bg-white/[0.03] border border-white/[0.05] px-3 py-2 text-sm text-white hover:border-[#7c5cff]/30 hover:bg-white/[0.05] h-auto">
                          <SelectValue placeholder="Auto" />
                        </SelectTrigger>
                        <SelectContent className="elevation-3 border-white/[0.1] rounded-xl">
                          <TemplateItem value="auto" label="Auto (let AI pick)" hint="The dispatcher selects the best template based on your prompt." />
                          <TemplateItem value="car_hero" label="Car Hero" hint="Reflective floor, automotive lighting rig, low orbital camera. Built for vehicle showcases." />
                          <TemplateItem value="scenic_landscape" label="Scenic Landscape" hint="Wide establishing shot, terrain ground, sunset sky. Built for nature and outdoor scenes." />
                          <TemplateItem value="character_stage" label="Character Stage" hint="Studio backdrop, five-point lighting, stage arc camera. Built for characters and creatures." />
                          <TemplateItem value="product_scene" label="Product Hero" hint="Studio cyc, product lighting, cinematic reveal camera. Built for product close-ups." />
                        </SelectContent>
                      </Select>
                    </div>

                    {/* v1.4 polish — Reset link with refresh icon and hover */}
                    <div className="pt-2">
                      <button
                        type="button"
                        onClick={() => {
                          setLighting('')
                          setCameraStyle('')
                          setBrand('#7c5cff')
                          setBrandAccent('#ff5c8a')
                          setDuration(12)
                          setTemplate('auto')
                        }}
                        className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[#4a4764] hover:text-[#ff5c8a] transition-colors group"
                      >
                        <RefreshCw className="w-3 h-3 transition-transform group-hover:-rotate-180 duration-500" />
                        Reset scene controls
                      </button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Variations — collapsible */}
          <div className="glass rounded-2xl card-hover overflow-hidden">
            <button
              type="button"
              onClick={() => setVariationsOpen((v) => !v)}
              aria-expanded={variationsOpen}
              className="w-full flex items-center justify-between gap-2 px-5 py-4 hover:bg-white/[0.02] transition-colors"
            >
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-[#ff5c8a]" />
                <span className="text-sm font-semibold">Variations</span>
                {variations.length > 0 && (
                  <span className="text-[10px] font-mono text-[#4a4764]">
                    {variations.length}
                  </span>
                )}
              </div>
              <ChevronDown
                className={cn(
                  'w-4 h-4 text-[#4a4764] transition-transform duration-300',
                  variationsOpen && 'rotate-180',
                )}
              />
            </button>
            <AnimatePresence>
              {variationsOpen && (
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: 'auto' }}
                  exit={{ height: 0 }}
                  className="overflow-hidden"
                >
                  <div className="px-5 pb-5 border-t border-white/[0.05] pt-4">
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min={1}
                        max={8}
                        value={variationCount}
                        onChange={(e) => setVariationCount(parseInt(e.target.value, 10) || 4)}
                        className="w-16 rounded-lg bg-white/[0.03] border border-white/[0.05] px-2 py-2 text-sm text-white text-center focus:outline-none focus:border-[#ff5c8a]/40"
                      />
                      <Tooltip>
                        <TooltipTrigger
                          render={(props) => (
                            <Button
                              {...props}
                              onClick={handleVariations}
                              disabled={busy !== 'idle' || !topic.trim()}
                              className="flex-1 rounded-xl bg-[#ff5c8a]/15 text-[#ff5c8a] border border-[#ff5c8a]/20 hover:bg-[#ff5c8a]/25 text-xs font-semibold"
                            >
                              {busy === 'variations' ? (
                                <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                              ) : (
                                <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                              )}
                              Sweep
                            </Button>
                          )}
                        />
                        <TooltipContent side="top" className="max-w-[220px]">
                          Generate {variationCount} variations of this scene with slight directorial differences.
                        </TooltipContent>
                      </Tooltip>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* ── Cast Panel (character + environment picker) ─────── */}
      <CastPanel
        open={pickerOpen}
        prompt={pickerPrompt}
        onClose={handlePickerClose}
        onConfirm={handlePickerConfirm}
        initialHeroId={castHero?.id ?? null}
        initialEnvId={castEnv?.id ?? null}
      />

      {/* v1.4 follow-up — per-slot library browser. Hero slot now spans
          character + vehicle + prop (anything except environment / hdri). */}
      <LibraryBrowser
        open={browserCategory !== null}
        category={browserCategory === 'environment' ? 'environment' : 'character,vehicle,prop'}
        title={browserCategory === 'environment' ? 'Browse environments' : 'Browse characters & vehicles'}
        onClose={() => setBrowserCategory(null)}
        onChoose={handleBrowserChoose}
      />

      {/* ── Variations Grid ────────────────────────────────── */}
      {variations.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="section-tag section-tag--pink font-mono text-xs">// variations</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 stagger-reveal">
            {variations.map((v) => (
              <VariationCard
                key={v.variation_id}
                variation={v}
                onPromote={(picked) => {
                  // v1.4 polish — promote a variation into the main Output
                  // panel. Slide-in on previewResult swap is handled by the
                  // motion.div in the Output card (keyed on output_url).
                  const r = picked.render_result
                  if (!r?.output_url) return
                  setPreviewResult(r)
                  // Smooth scroll back to the top so user sees their pick.
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
              />
            ))}
          </div>
        </div>
      )}
      </div>{/* end video-mode wrapper (Phase 30) */}
    </div>
  )
}

// Format an asset id like "lib_cat_cat_box_meme" → "Cat Box Meme" best-effort.
function prettyAssetId(id: string): string {
  const trimmed = id.replace(/^lib_/, '').replace(/^(animal|registry|cat|character)_/, '')
  const words = trimmed.split('_').filter(Boolean)
  if (words.length === 0) return id
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

// v1.4 polish — Phase 7 ui/select item with hint. Each option carries a
// short descriptor surfaced under the label in muted text — Phase 5's
// "each option's tooltip explains what it does visually" goal.
function LightingItem({ value, label, hint }: { value: string; label: string; hint: string }) {
  return (
    <SelectItem
      value={value}
      className="rounded-md px-2 py-2 hover:bg-[#7c5cff]/10 focus:bg-[#7c5cff]/15 data-[selected]:bg-[#7c5cff]/15"
    >
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-sm font-medium text-white">{label}</span>
        <span className="text-[10px] text-[#807d99] line-clamp-2">{hint}</span>
      </div>
    </SelectItem>
  )
}
const CameraItem = LightingItem
const TemplateItem = LightingItem

function ControlField({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        {icon}
        <label className="text-xs font-medium text-[#807d99]">{label}</label>
      </div>
      {children}
    </div>
  )
}

function PromptSuggestions({ examples, onSelect }: { examples: string[]; onSelect: (v: string) => void }) {
  const [highlighted, setHighlighted] = useState(0)

  useEffect(() => {
    const iv = setInterval(() => {
      setHighlighted((prev) => (prev + 1) % examples.length)
    }, 3000)
    return () => clearInterval(iv)
  }, [examples.length])

  return (
    <div className="flex flex-wrap gap-2 justify-center">
      {examples.map((ex, i) => (
        <button
          key={ex}
          type="button"
          onClick={() => onSelect(ex)}
          className={cn(
            'rounded-full border px-3 py-1.5 text-xs transition-all duration-500',
            i === highlighted
              ? 'border-[#7c5cff]/40 text-[#a78bfa] bg-[#7c5cff]/8 shadow-[0_0_12px_rgba(124,92,255,0.15)]'
              : 'border-white/[0.05] bg-white/[0.02] text-[#807d99] hover:border-[#7c5cff]/30 hover:text-[#a78bfa] hover:bg-[#7c5cff]/5'
          )}
        >
          {ex}
        </button>
      ))}
    </div>
  )
}

function VariationCard({
  variation,
  onPromote,
}: {
  variation: Variation
  onPromote?: (v: Variation) => void
}) {
  const r = variation.render_result
  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.18 }}
      className="glass rounded-2xl overflow-hidden card-hover"
    >
      <div className="aspect-video bg-[#0a0a10] flex items-center justify-center relative group">
        {r?.output_url ? (
          <>
            <video src={r.output_url} controls playsInline className="w-full h-full object-cover" />
            {/* v1.4 polish — Phase 7 promote-to-main on hover */}
            {onPromote && (
              <button
                type="button"
                onClick={() => onPromote(variation)}
                className="absolute top-2 right-2 inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold opacity-0 group-hover:opacity-100 transition-all bg-gradient-to-r from-[#7c5cff] to-[#ff5c8a] text-white shadow-[0_0_18px_-2px_rgba(255,92,138,0.6)] hover:scale-[1.05] active:scale-95"
              >
                <ChevronRight className="w-3 h-3" />
                Promote
              </button>
            )}
          </>
        ) : r && !r.ok ? (
          <div className="flex items-center gap-2 text-sm text-red-400">
            <AlertCircle className="w-4 h-4" /> {r.error || 'failed'}
          </div>
        ) : (
          <Loader2 className="w-5 h-5 animate-spin text-[#4a4764]" />
        )}
      </div>
      <div className="p-4 space-y-2">
        <div className="text-sm font-semibold text-white">{variation.label}</div>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(variation.mutation.directorial_controls || {}).map(([k, v]) =>
            v ? (
              <Badge key={k} className="bg-white/[0.03] border-white/[0.05] text-[#807d99] text-xs rounded-lg">
                {k}: {String(v)}
              </Badge>
            ) : null
          )}
          {Object.entries(variation.mutation.scene_params || {}).map(([k, v]) =>
            v ? (
              <Badge key={k} className="bg-white/[0.03] border-white/[0.05] text-[#807d99] text-xs rounded-lg">
                {k}: {String(v)}
              </Badge>
            ) : null
          )}
        </div>
        {r?.output_url && (
          <a href={r.output_url} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-[#7c5cff] hover:text-[#a78bfa] transition-colors">
            <Download className="w-3.5 h-3.5" /> Open MP4
          </a>
        )}
      </div>
    </motion.div>
  )
}
