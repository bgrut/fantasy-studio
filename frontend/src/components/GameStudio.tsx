// Phase 30 — Game mode for the Studio. Prompt → playable web game, built by
// the backend in ~30-60s with NO GPU (library assets + Ollama extraction),
// then embedded right here so the user plays what they typed.
import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Crosshair, Download, FolderPlus, Gamepad2, Loader2, Maximize2, RotateCcw } from 'lucide-react'
import { cn } from '@/lib/utils'
import AssetPalette, { type PaletteAsset } from '@/components/AssetPalette'
import EnginePanel from '@/components/EnginePanel'
import {
  addLevelToProject, createProject, exportGame, exportProject, gameHealth,
  cancelJob, getGameJob, listProjects, openLevel, removeLevelFromProject, revealProjectZip, uploadSplat, listSplats, trainSplat, getSplatJob, imagineSplat, uploadScene,
  rerollAsset, updateLevel,
  type GameHealth, type GameJob, type GameProject,
} from '@/lib/gameApi'
import OnboardingTour, { type TourStep } from '@/components/OnboardingTour'

// First-run walkthroughs (each shows once per browser). The basics tour fires
// on first visit to Game mode; the Inspect tour fires the first time a
// playable game appears (its target only mounts then).
const GAME_TOUR: TourStep[] = [
  {
    id: 'game-prompt',
    targetAttr: 'game-prompt',
    title: 'Describe your game',
    body: 'One sentence is enough — cast, world, missions and rules are all generated. Pick a sample card below or type your own, then hit Build Game.',
    placement: 'bottom',
  },
  {
    id: 'game-look',
    targetAttr: 'game-look',
    title: 'Pick a look (optional)',
    body: 'Style, camera view, and quality are one-click presets applied to the whole world. The defaults — Photoreal · 3D · ultra — are great; change nothing and just build.',
    placement: 'top',
  },
  {
    id: 'game-splat',
    targetAttr: 'game-splat',
    title: 'Splat worlds are extra credit',
    body: 'Totally optional and experimental — swaps your scenery for a photographic 3D scene. Skip it for your first builds; hover the ? anytime to learn more.',
    placement: 'top',
  },
]
const INSPECT_TOUR: TourStep[] = [
  {
    id: 'game-inspect',
    targetAttr: 'game-inspect',
    title: 'Point at the world and change it',
    body: 'Toggle Inspect, then hover anything in the running game to identify it. Click a spot and type an edit — "place a campfire here", "fence off this pass" — and it drops in live. Rules shows everything your game enforces.',
    placement: 'bottom',
  },
]

// Breadth showcase: classics that always work + wild ideas that exercise the
// whole pipeline (new creatures generate on first use, worlds span earth to
// mars, any species can race, rewards headline the win screen).
// one chip per GENRE the engine is good at — icon + short readable line,
// no truncation (variety: quest, city race, mystery, combat, sport,
// survival, ocean, flight, delivery, whimsy, magic, hunt)
const GAME_PROMPTS: { icon: string; text: string }[] = [
  { icon: '🦊', text: 'A fox on a snowy night quest: collect 6 fireflies, then reach the glowing beacon' },
  { icon: '🏎️', text: 'A red sports car races 5 rivals through New York City at night' },
  { icon: '🕵️', text: 'A detective collects 5 clues inside a mansion at night' },
  { icon: '⚔️', text: 'A knight fights 6 hostile goblins inside a torchlit castle great hall' },
  { icon: '🏹', text: 'A hunter stalking elk through a misty pine forest at dawn' },
  { icon: '⚽', text: 'A soccer player scoring 3 goals in a packed stadium' },
  { icon: '🐉', text: 'A dragon soaring over the mountains — collect 5 fire flames between the peaks' },
  { icon: '🌊', text: 'A whale in the deep ocean: dive for 5 pearls, then surface at the beacon' },
  { icon: '🧙', text: 'A wizard defends a windswept meadow — defeat 4 wolves with magic bolts' },
  { icon: '🚕', text: 'A taxi weaving through Tokyo streets — race 4 rivals before midnight' },
  { icon: '🛡️', text: 'Outlast 8 rivals as the storm closes in on a ruined village' },
  { icon: '🐧', text: 'A penguin waddling across the moon, collect 6 moon rocks' },
]

// Phase 44 STYLE PRESETS — the user picks, the AI never guesses. One global
// render treatment (cel shading, outlines, grain, palette) per game.
const STYLES: { id: string; label: string; hint: string }[] = [
  { id: 'default', label: '🎬 Photoreal', hint: 'the classic look — natural light and texture' },
  { id: 'cartoon', label: '🖍️ Cartoon', hint: 'TRUE cel shading — flat color bands + thick clean ink outlines' },
  { id: 'sketch', label: '✏️ Sketch', hint: 'pencil-drawn look — fine cross-hatched lines (the old Cartoon)' },
  { id: 'anime', label: '🌸 Anime', hint: 'soft cel bands, dreamy bloom, vivid color' },
  { id: 'horror', label: '🕯️ Horror', hint: 'crushing dark, thick fog, film grain' },
  { id: 'pixel', label: '👾 Pixel', hint: 'chunky retro pixels, posterized palette' },
  { id: 'lowpoly', label: '📐 Low-poly', hint: 'flat-shaded facets, minimalist color' },
]

// Phase 45 VIEW PRESETS — same world, different game: classic 3D, top-down
// 2D (orthographic Zelda feel), or a side-scroller locked to one lane.
const VIEWS: { id: string; label: string; hint: string }[] = [
  { id: '3d', label: '🧊 3D', hint: 'classic third-person camera' },
  { id: 'topdown', label: '🗺️ Top-down 2D', hint: 'orthographic overhead — the 2D-Zelda feel (pairs great with Pixel style)' },
  { id: 'side', label: '🎞️ Side-scroller', hint: 'run and jump along one lane — terrain becomes the platforming' },
]

const BUILD_STAGES: Record<string, string> = {
  queued: 'Queued…',
  extracting: 'Reading your idea…',
  'resolving assets': 'Casting characters…',
  building: 'Building the world…',
  verifying: 'Playtesting the build…',
  'emitting godot project': 'Emitting Godot project…',
}

export default function GameStudio() {
  const [prompt, setPrompt] = useState('')
  const [job, setJob] = useState<GameJob | null>(null)
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<GameHealth | null>(null)
  const [project, setProject] = useState<GameProject | null>(null)
  const [addedJob, setAddedJob] = useState<number | null>(null)
  const [exporting, setExporting] = useState(false)
  const [exported, setExported] = useState<{ play_url: string; zip: string; zip_mb: number } | null>(null)
  const [hubUrl, setHubUrl] = useState<string | null>(null)   // exported game playing in-app
  // Inspector (Phase 42): hover-audit + click-to-select inside the running game
  type Pick = { x: number; z: number; target: { type: string; name: string; detail?: string
                                                idx?: number; kind?: string; rules?: string[] } }
  const [inspect, setInspect] = useState(false)
  const [hoverPick, setHoverPick] = useState<Pick | null>(null)
  const [selPick, setSelPick] = useState<Pick | null>(null)
  const [style, setStyle] = useState('default')            // Phase 44 style preset
  const [splatPath, setSplatPath] = useState<string | null>(null)
  const [splatList, setSplatList] = useState<{ name: string; path: string; mb: number }[] | null>(null)
  const [splatTrain, setSplatTrain] = useState<string | null>(null)  // splat job stage text
  const [panoPath, setPanoPath] = useState<string | null>(null)      // Phase 140: scene-image world

  // shared poll for train_splat / imagine_splat jobs — attaches the result
  // and AUTO-BUILDS the game with it so the play panel updates like any run
  const pollSplat = (jobId: number, buildPrompt?: string) => {
    setSplatTrain('starting')
    const poll = window.setInterval(async () => {
      try {
        const { job } = await getSplatJob(jobId)
        setSplatTrain(job.stage)
        if (job.status === 'complete') {
          window.clearInterval(poll); setSplatTrain(null)
          const p = (buildPrompt ?? prompt).trim()
          if (job.splat) {
            setSplatPath(job.splat)
            if (p) startJob(p, undefined, undefined, undefined, job.splat)
          } else if (job.pano) {
            setPanoPath(job.pano)
            if (p) startJob(p, undefined, undefined, undefined, undefined, job.pano)
          }
        } else if (job.status === 'failed') {
          window.clearInterval(poll); setSplatTrain(null)
          setError(job.error ?? 'splat job failed')
        }
      } catch { /* backend restart mid-poll — keep trying */ }
    }, 5000)
  }
  const [quality, setQuality] = useState<string>(() => {
    try { return localStorage.getItem('fs_quality') || 'ultra' } catch { return 'ultra' }
  })
  const [view, setView] = useState('3d')                   // Phase 45 view preset
  const [placeMode, setPlaceMode] = useState<'point' | 'line'>('point')
  const [lineA, setLineA] = useState<Pick | null>(null)    // line tool first click
  const [selLine, setSelLine] = useState<{ a: Pick; b: Pick } | null>(null)
  const [showRules, setShowRules] = useState(false)        // Studio panel open
  // STUDIO PANEL (2026-08-05): the Truth Table grew into the studio — Cast
  // (who is in the game), Rules (what it enforces), Scene (live dials).
  const [studioTab, setStudioTab] =
    useState<'cast' | 'library' | 'engines' | 'rules' | 'scene'>('cast')
  // DRAG-AND-DROP PLACEMENT (2026-08-06). `dragAsset` is live only while a
  // palette card is in flight; it raises the drop overlay over the iframe,
  // because an iframe swallows the parent's drag events and there is
  // otherwise no way to drop onto the running game. `pendingDrop` survives
  // the round trip to the runtime, which answers with fs-pick asynchronously.
  const [dragAsset, setDragAsset] = useState<PaletteAsset | null>(null)
  const [dropToast, setDropToast] = useState<string | null>(null)
  const pendingDrop = useRef<PaletteAsset | null>(null)
  // A card can unmount mid-drag (switching palette tabs), and then its own
  // dragend never fires and the overlay stays up over the running game —
  // which is how it ended up printed across a defeat dialog. Window-level
  // listeners end the drag no matter where it died.
  useEffect(() => {
    const clear = () => setDragAsset(null)
    window.addEventListener('dragend', clear)
    window.addEventListener('drop', clear)
    return () => {
      window.removeEventListener('dragend', clear)
      window.removeEventListener('drop', clear)
    }
  }, [])
  // live dials: these postMessage STRAIGHT to the running game. No backend
  // roundtrip, no rebuild — dragging a slider changes the world you are
  // looking at, which is the whole point of the studio.
  const [dials, setDials] = useState({ fog: 6, sun: 2.2, exposure: 1.0 })
  // Move 5: quality pack — applies LIVE via fs-grade and rides along on the
  // next build so it persists. Move 1: locked layers — the user's approvals;
  // every edit carries them and the backend enforces them verbatim.
  const [grade, setGrade] = useState<string>('none')
  const [lockedLayers, setLockedLayers] = useState<string[]>([])
  const toggleLock = useCallback((layer: string) => {
    setLockedLayers(ls => ls.includes(layer)
      ? ls.filter(l => l !== layer) : [...ls, layer])
  }, [])
  const sendPatch = useCallback((patch: Record<string, number>) => {
    gameFrameRef.current?.contentWindow?.postMessage(
      { type: 'fs-patch', patch }, '*')
  }, [])
  const pollRef = useRef<number | null>(null)
  const gameFrameRef = useRef<HTMLIFrameElement | null>(null)
  const hubFrameRef = useRef<HTMLIFrameElement | null>(null)
  const [showLevels, setShowLevels] = useState(true)   // level tiles open by default
  const [showCast, setShowCast] = useState(false)      // cast library collapsed by default

  useEffect(() => {
    gameHealth().then(setHealth).catch(() => setHealth(null))
    listProjects().then(({ projects }) => setProject(projects[projects.length - 1] ?? null)).catch(() => {})
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [])

  const addToGame = useCallback(async () => {
    if (!job || job.status !== 'complete') return
    try {
      let p = project
      if (!p) {
        const { project: np } = await createProject('My Game')
        p = { id: np.id, name: 'My Game', level_count: 0, level_titles: [] }
      }
      const { level_count } = await addLevelToProject(p.id, job.id)
      setProject({ ...p, level_count })
      // pull fresh titles so the levels manager shows the new entry
      listProjects().then(({ projects }) =>
        setProject(projects.find(pr => pr.id === p!.id) ?? null)).catch(() => {})
      setAddedJob(job.id)
      setExported(null)                    // stale export after adding a level
      setHubUrl(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [job, project])

  const doExport = useCallback(async () => {
    if (!project || exporting) return
    setExporting(true)
    setError(null)
    try {
      const r = await exportProject(project.id)
      setExported({ play_url: r.play_url, zip: r.zip, zip_mb: r.zip_mb })
      setHubUrl(null)                      // fresh export: don't keep playing the old one
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setExporting(false)
    }
  }, [project, exporting])

  const pollJob = useCallback((job_id: number) => {
    if (pollRef.current) window.clearInterval(pollRef.current)
    let misses = 0
    pollRef.current = window.setInterval(async () => {
      try {
        const { job: jb } = await getGameJob(job_id)
        misses = 0
        setJob(jb)
        if (jb.status !== 'running') {
          if (pollRef.current) window.clearInterval(pollRef.current)
          setBuilding(false)
          if (jb.status === 'failed') setError(jb.error ?? 'build failed')
        }
      } catch {
        // a couple of misses are transient; a dead backend / vanished job is
        // not — never leave the Building spinner wedged forever
        misses += 1
        if (misses >= 8) {
          if (pollRef.current) window.clearInterval(pollRef.current)
          setBuilding(false)
          setError('lost contact with the build (backend restarted?) — try again')
        }
      }
    }, 1500)
  }, [])

  const startJob = useCallback(async (p: string, baseJobId?: number,
                                      at?: { x: number; z: number; target?: string },
                                      at2?: { x: number; z: number },
                                      splatNow?: string, panoNow?: string) => {
    setError(null)
    setSavedLevel(null)                   // any rebuild invalidates "Saved ✓"
    if (baseJobId == null) { setJob(null); setOpenedLevel(null) }  // fresh build = not a level edit
    setBuilding(true)
    try {
      const res = await exportGame(p, baseJobId != null
        ? { baseJobId, at, at2,
            locked: lockedLayers.length ? lockedLayers : undefined,
            grade: grade !== 'none' ? grade : undefined }
        // fresh build: USER-SELECTED style + view ride along — never guessed
        : { style: style !== 'default' ? style : undefined,
            view: view !== '3d' ? view : undefined,
            grade: grade !== 'none' ? grade : undefined,
            splat: (splatNow ?? splatPath) ?? undefined,
            pano: (panoNow ?? panoPath) ?? undefined })
      // LIVE EDIT (2026-08-05): dial-only changes never rebuild — the
      // running game applies them in a frame. Two-minute rebuilds to
      // change one number are what stopped iteration from happening.
      if (res.hot && res.patch) {
        gameFrameRef.current?.contentWindow?.postMessage(
          { type: 'fs-patch', patch: res.patch }, '*')
        setBuilding(false)
        setPrompt('')
        return
      }
      pollJob(res.job_id)
    } catch (e) {
      setBuilding(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [pollJob, style, view, splatPath, panoPath, lockedLayers, grade])

  // Phase 43 level tiles: click a level -> exact re-export opens as a live
  // job in the player above — play it, Inspect it, edit it, save it back.
  const [openedLevel, setOpenedLevel] = useState<number | null>(null)
  const [savedLevel, setSavedLevel] = useState<number | null>(null)
  const playLevel = useCallback(async (index: number) => {
    if (!project || building) return
    setError(null)
    setBuilding(true)
    setSavedLevel(null)
    try {
      const { job_id } = await openLevel(project.id, index)
      setOpenedLevel(index)
      pollJob(job_id)
    } catch (e) {
      setBuilding(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [project, building, pollJob])
  const saveLevel = useCallback(async () => {
    if (!project || openedLevel == null || !job || job.status !== 'complete') return
    try {
      await updateLevel(project.id, openedLevel, job.id)
      setSavedLevel(openedLevel)
      setExported(null)                 // the export no longer matches the project
      setHubUrl(null)
      const { projects } = await listProjects()
      setProject(projects.find(p => p.id === project.id) ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [project, openedLevel, job])

  const build = useCallback(() => {
    const p = prompt.trim()
    if (!p || building) return
    void startJob(p)
  }, [prompt, building, startJob])

  // R-ITER: edit THIS game — same world, cached assets, seconds not minutes
  const [editPrompt, setEditPrompt] = useState('')
  const iterate = useCallback(() => {
    const p = editPrompt.trim()
    if (!p || building || !job) return
    // "place a X here" without a clicked spot would leave the LLM guessing
    // coordinates (it echoes existing ones — the sign-inside-the-campfire).
    // Require a selection so "here" always means somewhere real.
    if (!selPick && !selLine && /^\s*(place|put|drop|spawn)\b/i.test(p) && /\b(here|there|this spot)\b/i.test(p)) {
      setError('Where is “here”? Turn on Inspect, click a spot (or two, in Line mode), then apply this edit.')
      return
    }
    setError(null)
    setEditPrompt('')
    // the selection rides along: a point places once, a line tiles A→B
    const at = selLine
      ? { x: selLine.a.x, z: selLine.a.z, target: selLine.a.target.name }
      : selPick ? { x: selPick.x, z: selPick.z, target: selPick.target.name } : undefined
    const at2 = selLine ? { x: selLine.b.x, z: selLine.b.z } : undefined
    setSelPick(null)
    setSelLine(null)
    void startJob(p, job.id, at, at2)
  }, [editPrompt, building, job, startJob, selPick, selLine])

  // The runtime is the only thing that can turn a screen point into a world
  // point, so the drop asks it and finishes in the fs-pick handler below.
  const onGameDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const raw = e.dataTransfer.getData('application/x-fs-asset')
    setDragAsset(null)
    if (!raw || !job || building) return
    let asset: PaletteAsset
    try { asset = JSON.parse(raw) } catch { return }
    const frame = gameFrameRef.current
    if (!frame) return
    const r = frame.getBoundingClientRect()
    pendingDrop.current = asset
    frame.contentWindow?.postMessage(
      { type: 'fs-dropat', cx: e.clientX - r.left, cy: e.clientY - r.top }, '*')
  }, [job, building])

  const playing = job?.status === 'complete' && job.play_url

  // Inspector bridge: the game raycasts under the cursor and reports what/where
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      const d = e.data
      if (d && d.type === 'fs-spawned') {
        if (!d.ok) setError(`Could not place that live (${d.err ?? 'unknown'}) — `
          + 'press Apply edit to place it with a rebuild instead.')
        return
      }
      if (!d || d.type !== 'fs-pick') return
      // the game could not resolve a ground point (dropped on the sky, or
      // past the map edge) — say so instead of leaving the drag armed and
      // the user staring at an unchanged world
      if (d.kind === 'dropfail') {
        pendingDrop.current = null
        setDragAsset(null)
        setError('Dropped past the edge of the world — aim at the ground and try again.')
        return
      }
      const p: Pick = { x: d.x, z: d.z, target: d.target ?? { type: 'ground', name: 'ground' } }
      if (d.kind === 'hover') { setHoverPick(p); return }
      // a drop already knows WHAT it is placing, so it goes straight to the
      // edit instead of arming a selection the user then has to describe
      if (d.kind === 'drop') {
        const a = pendingDrop.current
        pendingDrop.current = null
        if (!a) return
        // A DROP IS A COMPLETE INSTRUCTION (2026-08-06 r2). Staging it in
        // the edit bar meant a drag did nothing visible until you found and
        // pressed a button somewhere else, which read as "drag is broken".
        // You already said what and where by dropping, so it applies itself.
        // The sentence still lands in the edit bar so the edit is legible and
        // re-runnable, and Inspect is no longer the only route to a placed
        // edit.
        // HOT DROP (2026-08-07). Rebuilding to place one object threw away
        // the thing this studio is actually better at: a two-minute wait to
        // see a bench. The runtime can build every placeable kind itself, so
        // the drop lands LIVE and the sentence is staged in the edit bar —
        // press Apply edit when you want it baked into the spec for good.
        setSelLine(null); setLineA(null)
        setError(null)
        setSelPick(p)
        setEditPrompt(`place a ${a.subject} here`)
        gameFrameRef.current?.contentWindow?.postMessage(
          { type: 'fs-spawn', kind: a.subject, x: p.x, z: p.z }, '*')
        setDropToast(`${a.subject} placed live — Apply edit to keep it`)
        return
      }
      // LINE TOOL: first click anchors A, second closes the run A→B
      setPlaceMode(mode => {
        if (mode === 'line') {
          setLineA(a => {
            if (!a) return p
            setSelLine({ a, b: p })
            setSelPick(null)
            return null
          })
        } else {
          setSelPick(p)
          setSelLine(null)
        }
        return mode
      })
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  // the fs-pick listener is mounted once and must not capture a stale job or
  // a stale startJob; refs keep it correct without re-subscribing every render
  const startJobRef = useRef<typeof startJob | null>(null)
  const jobRef = useRef<typeof job>(null)
  useEffect(() => { startJobRef.current = startJob }, [startJob])
  useEffect(() => { jobRef.current = job }, [job])

  useEffect(() => {
    if (!dropToast) return
    const t = setTimeout(() => setDropToast(null), 6000)
    return () => clearTimeout(t)
  }, [dropToast])

  const sendInspect = useCallback((on: boolean) => {
    gameFrameRef.current?.contentWindow?.postMessage({ type: 'fs-inspect', on }, '*')
  }, [])
  const toggleInspect = useCallback(() => {
    setInspect(v => {
      sendInspect(!v)
      if (v) { setHoverPick(null); setSelPick(null); setLineA(null); setSelLine(null) }
      return !v
    })
  }, [sendInspect])
  // a rebuild replaces the iframe: picks are stale, but Inspect MODE stays on
  // (it re-arms via the iframe's onLoad) — mid-editing flow never breaks
  useEffect(() => { setHoverPick(null); setSelPick(null); setLineA(null); setSelLine(null) }, [job?.play_url])

  // RULE CHIPS: flip one honored rule on the selected placed item — fully
  // deterministic on the backend, re-exports in seconds
  const toggleRule = useCallback(async (name: string) => {
    if (!job || building || selPick?.target.type !== 'placed' || selPick.target.idx == null) return
    const has = (selPick.target.rules ?? []).includes(name)
    setError(null)
    setSelPick(null)
    setBuilding(true)
    try {
      const { job_id } = await exportGame(`toggle rule ${name}`, {
        baseJobId: job.id,
        rule: { index: selPick.target.idx, name, on: !has },
      })
      pollJob(job_id)
    } catch (e) {
      setBuilding(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [job, building, selPick, pollJob])

  // While a game is playable, arrows/space must DRIVE THE GAME, not scroll
  // the studio page out from under the recording. Keys that reach the parent
  // (iframe unfocused) get their default scroll behavior suppressed.
  useEffect(() => {
    if (!playing && !hubUrl) return
    const KEYS = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '])
    const swallow = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.isContentEditable)) {
        return                          // typing a prompt keeps its arrow keys
      }
      if (KEYS.has(e.key)) {
        e.preventDefault()
        // hand the keys back to whichever game is open (hub wins: it opened
        // last). preventScroll: plain focus() SCROLLS the page to the iframe —
        // that was the "screen jumps upward in Inspect mode" bug.
        ;(hubFrameRef.current ?? gameFrameRef.current)?.focus({ preventScroll: true })
      }
    }
    window.addEventListener('keydown', swallow, { capture: true })
    return () => window.removeEventListener('keydown', swallow, { capture: true })
  }, [playing, hubUrl])

  return (
    <div className="space-y-8">
      {/* first-run walkthroughs — basics now, Inspect when a game is playable */}
      <OnboardingTour steps={GAME_TOUR} storageKey="fs.tour.game.v1" />
      <OnboardingTour steps={INSPECT_TOUR} storageKey="fs.tour.inspect.v1" />
      {/* Prompt input — mirrors the video-mode hero input */}
      <div className="max-w-4xl mx-auto space-y-4">
        <div data-tour-id="game-prompt" className="relative group max-w-2xl mx-auto w-full">
          <textarea
            value={prompt}
            rows={1}
            onChange={(e) => {
              setPrompt(e.target.value)
              // auto-grow DOWNWARD so long prompts never hide behind the button
              e.target.style.height = 'auto'
              e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                build()
              }
            }}
            placeholder="A knight exploring a foggy forest…"
            className={cn(
              'w-full resize-none overflow-hidden rounded-2xl bg-[rgba(14,14,22,0.7)] backdrop-blur-xl border pl-4 sm:pl-6 pr-36 py-3 sm:py-4 text-base sm:text-lg text-white',
              'placeholder:text-[#4a4764] focus:outline-none transition-all duration-300 focus-glow',
              building ? 'border-[#5cffc9]/40' : 'border-white/[0.05]'
            )}
          />
          <button
            onClick={build}
            disabled={building || !prompt.trim()}
            className={cn(
              'absolute right-2 top-3 px-5 py-2.5 rounded-xl font-semibold text-sm',
              'inline-flex items-center justify-center gap-2 leading-none',
              'transition-transform duration-200 active:scale-[0.97] hover:scale-[1.02]',
              building
                ? 'bg-[#5cffc9]/20 text-[#5cffc9]'
                : 'bg-gradient-to-r from-[#5cffc9] to-[#7c5cff] text-[#0a0a12] disabled:opacity-40'
            )}
          >
            {building ? <Loader2 className="w-4 h-4 animate-spin" /> : <Gamepad2 className="w-4 h-4" />}
            {building ? 'Building' : 'Build Game'}
          </button>
        </div>

        {/* sample prompts — readable 3-column cards (icon + full text, no
            truncation) instead of scrunched truncated pills */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {GAME_PROMPTS.map((p) => (
            <button
              key={p.text}
              onClick={() => setPrompt(p.text)}
              className="group flex items-start gap-2.5 text-left px-3.5 py-2.5 rounded-xl border border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04] hover:border-[#5cffc9]/30 transition-all"
            >
              <span className="text-base leading-5 shrink-0">{p.icon}</span>
              <span className="text-[12px] leading-5 text-[#9a96b8] group-hover:text-white">{p.text}</span>
            </button>
          ))}
        </div>

        {/* LOOK & FEEL card: style / view / quality grouped in one place */}
        <div data-tour-id="game-look" className="mx-auto max-w-4xl w-full rounded-xl border border-white/[0.06] bg-white/[0.015] px-5 py-4 space-y-2.5">
        <div className="flex flex-wrap justify-center items-center gap-1.5">
          <span className="text-[10px] font-mono text-[#4a4764]">style:</span>
          {STYLES.map((s) => (
            <button
              key={s.id}
              onClick={() => setStyle(s.id)}
              title={s.hint}
              className={cn(
                'px-2.5 py-1 rounded-full text-[11px] border transition-all',
                style === s.id
                  ? 'border-[#5cffc9]/50 bg-[#5cffc9]/10 text-[#5cffc9]'
                  : 'border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white'
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap justify-center items-center gap-1.5">
          <span className="text-[10px] font-mono text-[#4a4764]">view:</span>
          {VIEWS.map((v) => (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
              title={v.hint}
              className={cn(
                'px-2.5 py-1 rounded-full text-[11px] border transition-all',
                view === v.id
                  ? 'border-[#a78bfa]/50 bg-[#a78bfa]/10 text-[#a78bfa]'
                  : 'border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white'
              )}
            >
              {v.label}
            </button>
          ))}
          <span className="text-[10px] font-mono text-[#4a4764] self-center ml-4">quality:</span>
          {(['ultra', 'balanced', 'performance'] as const).map(q => (
            <button
              key={q}
              title={q === 'ultra' ? 'native res + 4x MSAA + 4K shadows (default)'
                : q === 'balanced' ? '1.5x res, 4x MSAA, 2K shadows'
                : 'lowest cost — 1x res, no MSAA'}
              onClick={() => { setQuality(q); try { localStorage.setItem('fs_quality', q) } catch {} }}
              className={cn(
                'px-2.5 py-1 rounded-full text-[11px] border transition-all',
                quality === q
                  ? 'border-[#5cffc9]/50 bg-[#5cffc9]/10 text-[#5cffc9]'
                  : 'border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white'
              )}
            >
              {q}
            </button>
          ))}
        </div>
        <p className="text-center text-[10px] font-mono text-[#4a4764]">
          exports: 🌐 Web (three.js, plays anywhere) · 🎮 Godot 4 project (open-source engine — full editor access) · 🕹 Godot multiplayer guide included
        </p>
        </div>

        {/* SPLAT WORLD — optional + experimental, deliberately its own card so
            it never reads as a required step */}
        <div data-tour-id="game-splat" className="mx-auto max-w-4xl w-full rounded-xl border border-dashed border-[#c86bff]/20 bg-[#c86bff]/[0.02] px-5 py-3 space-y-2">
        <div className="flex flex-wrap justify-center items-center gap-2">
          <span className="text-[10px] font-mono text-[#c86bff]/80">🌌 splat world</span>
          <span className="px-1.5 py-0.5 rounded text-[9px] font-mono border border-white/[0.08] text-[#807d99]">optional · experimental</span>
          <span
            className="w-4 h-4 inline-flex items-center justify-center rounded-full border border-white/[0.12] text-[10px] text-[#807d99] cursor-help"
            title="Games never need this — every build works without it. A splat world swaps your level's scenery for a photographic 3D 'Gaussian splat' scene: pick a sample (▾), upload a .ply/.splat file, ✨ imagine one from your prompt, or 🎥 train one from a walkthrough video.">?</span>
          {splatPath ? (
            <span className="px-2.5 py-1 rounded-full text-[11px] border border-[#c86bff]/60 bg-[#c86bff]/15 text-[#c86bff]"
                  title="This splat world is attached — it becomes the scenery of your next build. Hit ✕ to go back to normal worlds.">
              🌌 {splatPath.split('/').pop()}
            </span>
          ) : (
            <label className="px-2.5 py-1 rounded-full text-[11px] border border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white cursor-pointer transition-all"
                   title="Optional: upload a Gaussian-splat world file (.ply/.splat). Off by default — builds work normally without one.">
              🌌 Splat world: off
              <input type="file" accept=".ply,.splat,.ksplat" className="hidden"
                onChange={async (e) => {
                  const f = e.target.files?.[0]
                  if (!f) return
                  try {
                    const r = await uploadSplat(f)
                    setSplatPath(r.path)
                  } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
                }} />
            </label>
          )}
          {splatPath && (
            <button onClick={() => setSplatPath(null)}
              className="text-[11px] text-[#807d99] hover:text-white" title="detach splat world">✕</button>
          )}
          {!splatPath && (
            <button
              className="px-2 py-1 rounded-full text-[11px] border border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white transition-all"
              title="pick a splat world already on this machine (samples included)"
              onClick={async () => {
                if (splatList) { setSplatList(null); return }
                try { setSplatList((await listSplats()).splats) } catch { setSplatList([]) }
              }}>▾</button>
          )}
          {splatTrain ? (
            <span className="text-[11px] font-mono text-[#c86bff] animate-pulse"
                  title="Your splat world is being generated — the game will build automatically the moment it's ready.">
              🌌 building splat world: {splatTrain}… (game auto-builds when done)
            </span>
          ) : (
            <label className="px-2.5 py-1 rounded-full text-[11px] border border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white cursor-pointer transition-all"
                   title="Train a splat world from your own walkthrough video (steady sideways motion, 20-60s). Takes 20-60 min on GPU.">
              🎥 train from video
              <input type="file" accept=".mp4,.mov,.mkv,.webm" className="hidden"
                onChange={async (e) => {
                  const f = e.target.files?.[0]
                  if (!f) return
                  try {
                    const r = await trainSplat(f)
                    pollSplat(r.job_id)
                  } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
                }} />
            </label>
          )}
          {!splatTrain && (panoPath ? (
            <span className="px-2.5 py-1 rounded-full text-[11px] border border-[#5cffc9]/50 bg-[#5cffc9]/10 text-[#5cffc9]"
                  title="Your scene image is the world — backdrop and lighting come from it. ✕ to detach.">
              🖼 {panoPath.split('/').pop()}
              <button onClick={() => setPanoPath(null)}
                className="ml-1.5 text-[#5cffc9]/70 hover:text-white">✕</button>
            </span>
          ) : (
            <label className="px-2.5 py-1 rounded-full text-[11px] border border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white cursor-pointer transition-all"
                   title="Drop a photo or concept image and it BECOMES the world: a 360 panorama is painted from it and used as the backdrop + lighting (~1 min on GPU). The game auto-builds when ready.">
              🖼 scene image
              <input type="file" accept=".png,.jpg,.jpeg,.webp" className="hidden"
                onChange={async (e) => {
                  const f = e.target.files?.[0]
                  if (!f) return
                  try {
                    const r = await uploadScene(f)
                    pollSplat(r.job_id, prompt)
                  } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
                }} />
            </label>
          ))}
          {!splatTrain && (
            <button
              className="px-2.5 py-1 rounded-full text-[11px] border border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white transition-all"
              title="Imagine a splat world from your game prompt (SDXL + TRELLIS gaussians, ~5-10 min on GPU)"
              onClick={async () => {
                const p = prompt.trim()
                if (!p) { setError('type a prompt first — the splat is imagined from it'); return }
                try {
                  const r = await imagineSplat(p)
                  pollSplat(r.job_id, p)
                } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
              }}>✨ imagine</button>
          )}
        </div>
        {splatList && (
          <div className="flex justify-center items-center gap-1.5 flex-wrap">
            {splatList.length === 0 && (
              <span className="text-[10px] font-mono text-[#4a4764]">no splats on disk yet — upload or train one</span>
            )}
            {splatList.map((s) => (
              <button key={s.path}
                onClick={() => { setSplatPath(s.path); setSplatList(null) }}
                className="px-2 py-0.5 rounded-full text-[10px] border border-[#c86bff]/25 text-[#a58cc9] hover:text-[#c86bff] hover:bg-[#c86bff]/10 transition-all">
                {s.name} · {s.mb}MB
              </button>
            ))}
          </div>
        )}
        </div>

        {/* health strip + the CASTABLE CHARACTER LIBRARY (your generations) */}
        {health && (
          <>
            <p className="text-center text-[11px] text-[#4a4764] font-mono">
              {health.gpu ? `GPU: ${health.gpu} (~6 min characters)` : 'no GPU needed'} · ollama{' '}
              {health.ollama ? 'online' : 'offline (keyword fallback)'} ·{' '}
              {health.library_kinds.length} characters in library
            </p>
            <div className="flex flex-wrap justify-center gap-1.5">
              <button
                onClick={() => setShowCast(v => !v)}
                className="text-[10px] font-mono text-[#5cffc9]/70 hover:text-[#5cffc9] self-center"
                title="characters you have generated — click one to start a prompt with it"
              >
                🎭 cast library ({health.library_kinds.length}) {showCast ? '▾' : '▸'}
              </button>
              {showCast && health.library_kinds.map((k) => (
                <button
                  key={k}
                  onClick={() => setPrompt((p) => (p.trim() ? p : `A ${k} `))}
                  title={`"${k}" is in your generated library — star it in a prompt`}
                  className="px-2 py-0.5 rounded-full text-[10px] font-mono border border-[#5cffc9]/20 bg-[#5cffc9]/5 text-[#5cffc9]/80 hover:bg-[#5cffc9]/15 transition-colors"
                >
                  {k}
                </button>
              ))}
              {showCast && (
                <span className="text-[10px] font-mono text-[#4a4764] self-center">
                  · new characters are CREATED on first use (image → 3D)
                </span>
              )}
            </div>
          </>
        )}

        {job?.godot_path && (
          <p className="text-center text-[11px] font-mono text-[#5cffc9]/80">
            🎮 Godot 4 project emitted: <span className="text-[#efeaff]">{job.godot_path}</span> — open with Godot 4.x (free, godotengine.org)
          </p>
        )}

        {/* MY GAME: collected levels + manager + one-click export (Phase 34/41) */}
        {project && project.level_count > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-center gap-3 text-xs">
              <button
                onClick={() => setShowLevels(v => !v)}
                className="font-mono text-[#a78bfa] hover:text-white transition-colors"
                title="show / hide level list"
              >
                🎮 {project.name}: {project.level_count} level{project.level_count !== 1 ? 's' : ''} {showLevels ? '▾' : '▸'}
              </button>
              <button
                onClick={doExport}
                disabled={exporting}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#7c5cff]/15 text-[#a78bfa] hover:bg-[#7c5cff]/25 transition-colors disabled:opacity-50"
              >
                {exporting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                {exporting ? 'Exporting…' : 'Export game'}
              </button>
              {exported && (
                <>
                  {/* buttons, not <a>: the desktop shell (WebView2) ignores
                      target="_blank" and has no download UI — both anchors
                      silently did nothing. Play in-app; reveal zip in Explorer. */}
                  <button
                    onClick={() => setHubUrl(exported.play_url)}
                    className="text-[#5cffc9] hover:underline"
                  >▶ Play it</button>
                  <button
                    onClick={async () => {
                      try { await revealProjectZip(project.id) }
                      catch (e) { setError(e instanceof Error ? e.message : String(e)) }
                    }}
                    title="opens the folder containing the zip"
                    className="text-[#5cffc9] hover:underline"
                  >⬇ Show zip in folder ({exported.zip_mb} MB)</button>
                </>
              )}
            </div>
            {showLevels && (
              /* Phase 43: LEVEL TILES — the hub's level-select cards, live in
                 the studio. Click one to play + Inspect + edit that level. */
              <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(180px,1fr))]">
                {(project.levels ?? (project.level_titles ?? []).map(t => ({ title: t, player: null, seed: null }))).map((lv, i) => (
                  <div
                    key={i}
                    onClick={() => playLevel(i)}
                    role="button"
                    className={cn(
                      'relative group text-left rounded-xl border p-3 cursor-pointer transition-all',
                      'hover:-translate-y-0.5',
                      openedLevel === i
                        ? 'border-[#5cffc9]/40 bg-[#5cffc9]/5'
                        : 'border-white/[0.07] bg-white/[0.02] hover:border-[#7c5cff]/40'
                    )}
                    title="play, inspect and edit this level"
                  >
                    <div className="text-[10px] font-mono text-[#7c5cff]">LEVEL {i + 1}</div>
                    <div className="text-xs font-semibold text-[#eceaf6] truncate mt-0.5">
                      {lv.title || 'untitled level'}
                    </div>
                    <div className="text-[10px] text-[#807d99] font-mono mt-0.5">
                      {lv.seed != null ? `world #${lv.seed} · ` : ''}{lv.player || 'hero'}
                    </div>
                    <div className="text-[10px] text-[#5cffc9] mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      ▶ {openedLevel === i ? 'playing above' : 'play + inspect'}
                    </div>
                    <button
                      onClick={async (e) => {
                        e.stopPropagation()
                        try {
                          await removeLevelFromProject(project.id, i)
                          const { projects } = await listProjects()
                          setProject(projects.find(p => p.id === project.id) ?? null)
                          setExported(null)
                          setHubUrl(null)
                          if (openedLevel === i) setOpenedLevel(null)
                        } catch { /* leave list as-is */ }
                      }}
                      className="absolute top-1.5 right-2 text-[#807d99] hover:text-[#ff5c8a] transition-colors"
                      title="remove this level"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* the EXPORTED game (hub + all levels) playing in-app */}
      {hubUrl && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="max-w-5xl mx-auto space-y-3"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="section-tag font-mono text-xs">// your exported game</span>
              <span className="text-sm font-semibold text-white">{project?.name ?? 'My Game'}</span>
              <span className="text-[10px] font-mono text-[#807d99]">
                {project?.level_count ?? 0} level{(project?.level_count ?? 0) !== 1 ? 's' : ''} · pick one to play
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  const f = hubFrameRef.current
                  if (!f) return
                  f.requestFullscreen?.().catch(() => {})
                  f.focus()
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-[#5cffc9]/15 text-[#5cffc9] hover:bg-[#5cffc9]/25 transition-colors"
              >
                <Maximize2 className="w-3 h-3" /> Fullscreen
              </button>
              <button
                onClick={() => setHubUrl(null)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-white/[0.08] text-[#807d99] hover:text-white transition-colors"
              >
                ✕ Close
              </button>
            </div>
          </div>
          <div
            className="rounded-2xl overflow-hidden border border-white/[0.06] bg-black aspect-video"
            onClick={() => hubFrameRef.current?.focus({ preventScroll: true })}
          >
            <iframe
              key={hubUrl}          /* fresh iframe per export: releases the old
                                       WebGL context (WebView2 caps them) */
              ref={hubFrameRef}
              src={hubUrl}
              title={project?.name ?? 'exported game'}
              className="w-full h-full"
              allow="fullscreen; gamepad; pointer-lock"
              allowFullScreen
              onLoad={() => hubFrameRef.current?.focus({ preventScroll: true })}
            />
          </div>
        </motion.div>
      )}

      {/* build progress */}
      <AnimatePresence>
        {building && job && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="max-w-2xl mx-auto flex items-center justify-center gap-3 text-sm text-[#5cffc9]"
          >
            <Loader2 className="w-4 h-4 animate-spin" />
            {BUILD_STAGES[job.stage] ?? job.stage} <button onClick={async () => { try { await cancelJob(job.id) } catch {} }}
                title="Cancel this build (kills any character generation in progress)"
                className="ml-2 px-2 py-0.5 rounded text-[10px] border border-red-400/30 text-red-300 hover:bg-red-500/10">✕ cancel</button>
          </motion.div>
        )}
      </AnimatePresence>

      {error && (
        <p className="max-w-2xl mx-auto text-center text-sm text-[#ff5c8a]">{error}</p>
      )}

      {/* the playable game */}
      {playing && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="max-w-5xl mx-auto space-y-3"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="section-tag font-mono text-xs">// playable</span>
              <span className="text-sm font-semibold text-white">{job!.title}</span>
              {job!.checks != null && (
                <span className="text-[10px] font-mono text-[#5cffc9]">{job!.checks} checks passed</span>
              )}
              {(job as GameJob & { seed?: number }).seed != null && (
                <span className="text-[10px] font-mono text-[#807d99]">
                  level #{(job as GameJob & { seed?: number }).seed}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {openedLevel != null && (
                <button
                  onClick={saveLevel}
                  disabled={savedLevel === openedLevel}
                  className={cn(
                    'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors',
                    savedLevel === openedLevel
                      ? 'bg-[#5cffc9]/10 text-[#5cffc9] cursor-default'
                      : 'bg-[#5cffc9]/15 text-[#5cffc9] hover:bg-[#5cffc9]/25'
                  )}
                  title="save this (possibly edited) game back into the level tile it came from"
                >
                  {savedLevel === openedLevel
                    ? `Saved to level ${openedLevel + 1} ✓`
                    : `Save to level ${openedLevel + 1}`}
                </button>
              )}
              <button
                onClick={addToGame}
                disabled={addedJob === job!.id}
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors',
                  addedJob === job!.id
                    ? 'bg-[#7c5cff]/10 text-[#a78bfa] cursor-default'
                    : 'bg-[#7c5cff]/15 text-[#a78bfa] hover:bg-[#7c5cff]/25'
                )}
              >
                <FolderPlus className="w-3 h-3" />
                {addedJob === job!.id ? 'In your game ✓' : 'Add to my game'}
              </button>
              <button
                data-tour-id="game-inspect"
                onClick={toggleInspect}
                title="hover to identify things · click to select a spot or thing, then describe your edit"
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors',
                  inspect
                    ? 'bg-[#ffd88a]/20 text-[#ffd88a]'
                    : 'border border-white/[0.08] text-[#807d99] hover:text-white'
                )}
              >
                <Crosshair className="w-3 h-3" />
                {inspect ? 'Inspecting' : 'Inspect'}
              </button>
              {inspect && (
                <div className="inline-flex rounded-lg border border-[#ffd88a]/25 overflow-hidden text-xs">
                  <button
                    onClick={() => { setPlaceMode('point'); setLineA(null); setSelLine(null) }}
                    title="one click selects one spot"
                    className={cn('px-2.5 py-1.5 transition-colors',
                      placeMode === 'point' ? 'bg-[#ffd88a]/20 text-[#ffd88a]' : 'text-[#807d99] hover:text-white')}
                  >📍 Point</button>
                  <button
                    onClick={() => { setPlaceMode('line'); setSelPick(null) }}
                    title="two clicks select a run — fences, walls, torch rows tile from A to B"
                    className={cn('px-2.5 py-1.5 transition-colors',
                      placeMode === 'line' ? 'bg-[#ffd88a]/20 text-[#ffd88a]' : 'text-[#807d99] hover:text-white')}
                  >📏 Line</button>
                </div>
              )}
              <button
                onClick={() => setShowRules(v => !v)}
                title="Studio: who is in the game, what rules it enforces, and live scene dials"
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors',
                  showRules
                    ? 'bg-[#a78bfa]/20 text-[#a78bfa]'
                    : 'border border-white/[0.08] text-[#807d99] hover:text-white'
                )}
              >
                🎛 Studio
              </button>
              <button
                onClick={build}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-white/[0.08] text-[#807d99] hover:text-white transition-colors"
              >
                <RotateCcw className="w-3 h-3" /> New level
              </button>
              <button
                title="Rebuild this game as a Godot 4 project (open-source engine - full editor access)"
                onClick={async () => {
                  if (!job || building) return
                  setBuilding(true)
                  try {
                    const { job_id } = await exportGame(job.prompt, {
                      godot: true,
                      style: style !== 'default' ? style : undefined,
                      view: view !== '3d' ? view : undefined,
                    })
                    pollJob(job_id)
                  } catch (e) {
                    setBuilding(false)
                    setError(e instanceof Error ? e.message : String(e))
                  }
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-white/[0.08] text-[#807d99] hover:text-white transition-colors"
              >
                🎮 Godot
              </button>
              <button
                title="Regenerate this hero with a different look (~6 min), then rebuild the level"
                onClick={async () => {
                  const kind = job?.spec_resolved?.player?.name
                  if (!kind) return
                  if (!confirm(`Regenerate '${kind}' with a new look? Takes ~6 minutes, then the level rebuilds.`)) return
                  try {
                    await rerollAsset(kind)
                    build()
                  } catch (e) {
                    alert(`Hero reroll failed — generate any game with '${kind}' to retry the cast.`)
                  }
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-white/[0.08] text-[#807d99] hover:text-white transition-colors"
              >
                🎭 New hero
              </button>
              <button
                onClick={() => {
                  // REAL fullscreen (the old target="_blank" link did nothing
                  // in the desktop shell). Focus first so WASD/arrows keep
                  // driving the game while recording.
                  const f = gameFrameRef.current
                  if (!f) return
                  f.requestFullscreen?.().catch(() => {})
                  f.focus()
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-[#5cffc9]/15 text-[#5cffc9] hover:bg-[#5cffc9]/25 transition-colors"
              >
                <Maximize2 className="w-3 h-3" /> Fullscreen
              </button>
            </div>
          </div>
          <div
            className={cn(
              'relative rounded-2xl overflow-hidden border bg-black aspect-video',
              inspect ? 'border-[#ffd88a]/40' : 'border-white/[0.06]'
            )}
            onClick={() => gameFrameRef.current?.focus({ preventScroll: true })}
          >
            <iframe
              key={job!.play_url + quality} /* fresh iframe per game AND per tier — the
                                       runtime reads ?q= once at boot, so a tier
                                       change must reload; also releases the old
                                       WebGL context (WebView2 caps them; leaks
                                       caused the silent white-canvas bug) */
              ref={gameFrameRef}
              src={job!.play_url + '?q=' + quality}
              title={job!.title ?? 'game'}
              className="w-full h-full"
              allow="fullscreen; gamepad; pointer-lock"
              allowFullScreen
              onLoad={() => { gameFrameRef.current?.focus({ preventScroll: true }); if (inspect) sendInspect(true) }}
            />
            {/* DROP TARGET. Only mounted mid-drag: a permanent overlay would
                eat every click meant for the game. */}
            {dragAsset && (
              <div
                className="absolute inset-0 z-20 flex items-center justify-center
                           bg-[#a78bfa]/10 border-2 border-dashed border-[#a78bfa]/70
                           rounded-2xl"
                onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy' }}
                onDrop={onGameDrop}
              >
                <span className="px-3 py-1.5 rounded-lg bg-[rgba(10,9,18,0.9)]
                                 border border-[#a78bfa]/40 text-xs text-[#d6c9ff]">
                  drop to place <b>{dragAsset.subject}</b>
                </span>
              </div>
            )}
            {dropToast && (
              <div className="absolute top-2 right-2 z-30 px-3 py-1.5 rounded-lg
                              bg-[rgba(10,9,18,0.9)] border border-[#a78bfa]/40
                              text-xs text-[#d6c9ff] pointer-events-none">
                🧩 {dropToast}
              </div>
            )}
            {/* hover-audit chip: what's under the cursor, live */}
            {inspect && (
              <div className="absolute top-2 left-2 pointer-events-none px-3 py-1.5 rounded-lg bg-[rgba(10,9,18,0.85)] border border-[#ffd88a]/30 text-xs font-mono">
                {lineA ? (
                  <span className="text-[#ffd88a]">
                    📏 A set at ({lineA.x.toFixed(1)}, {lineA.z.toFixed(1)}) — click point B
                  </span>
                ) : hoverPick ? (
                  <>
                    <span className="text-[#ffd88a]">{hoverPick.target.name}</span>
                    {hoverPick.target.detail && (
                      <span className="text-[#807d99]"> · {hoverPick.target.detail}</span>
                    )}
                    <span className="text-[#4a4764]"> — click to select{placeMode === 'line' ? ' point A' : ''}</span>
                  </>
                ) : (
                  <span className="text-[#807d99]">
                    WASD flies the camera · {placeMode === 'line' ? 'click two points for a run' : 'move the cursor over the world…'}
                  </span>
                )}
              </div>
            )}
          </div>
          {/* THE TRUTH TABLE (Phase 44): every rule this game ENFORCES, derived
              from the resolved spec — nothing listed here is decorative */}
          {showRules && job!.spec_resolved && (() => {
            const sp = job!.spec_resolved!
            const rows: string[] = []
            if (sp.style && sp.style !== 'default') rows.push(`🎨 style: ${sp.style} — global render treatment`)
            rows.push(`🎮 ${sp.player?.name ?? 'hero'}: ${sp.player?.hp ?? 5} HP` +
              (sp.player?.attack && sp.player.attack !== 'none' ? ` · attacks with F (${sp.player.attack}, 3.2m reach, aim-assisted)` : ''))
            for (const [i, o] of (sp.objectives ?? []).entries()) {
              rows.push(`🎯 step ${i + 1}: ${o.kind} ${o.count} ${o.label}` +
                (o.kind === 'survive' ? ` (${o.count}s of escalating waves)` : ''))
            }
            for (const e of sp.entities ?? []) {
              rows.push(e.behavior === 'hostile'
                ? `🐺 ${e.count} × ${e.name}: hostile — chases within 14m, 1 dmg per hit, ${e.hp} HP each`
                : `🐾 ${e.count} × ${e.name}: ${e.behavior}`)
            }
            if ((sp.world?.health_packs ?? 0) > 0) rows.push(`❤️ ${sp.world!.health_packs} health packs: +1 HP on touch`)
            if (sp.world?.weather && sp.world.weather !== 'none') rows.push(`🌨️ weather: ${sp.world.weather}`)
            for (const it of sp.world?.placed_items ?? []) {
              const r: string[] = []
              if ((it.rules ?? []).includes('safe_zone')) r.push('safe zone (hostiles kept out, 6m)')
              if ((it.rules ?? []).includes('blocks_enemies')) r.push('blocks enemies')
              if ((it.rules ?? []).includes('hurts_touch')) r.push('hurts on touch (1 dmg/s)')
              if (it.interact) r.push('readable (E)')
              rows.push(`📦 ${it.name || it.kind} at (${it.x.toFixed(0)}, ${it.z.toFixed(0)})${r.length ? ': ' + r.join(' · ') : ''}`)
            }
            if (sp.reward) rows.push(`🏆 winner gets: ${sp.reward}`)
            const cast = [
              { who: sp.player?.name ?? 'hero', role: 'you', n: 1, lock: 'player',
                detail: `${sp.player?.hp ?? 5} HP` +
                  (sp.player?.attack && sp.player.attack !== 'none'
                    ? ` · ${sp.player.attack} (F)` : ' · no weapon'),
                vfx: (sp.player as { vfx?: string })?.vfx },
              ...(sp.entities ?? []).map(e => ({
                who: e.name, role: e.behavior, n: e.count,
                lock: `entities:${e.name.toLowerCase()}`,
                detail: `${e.hp} HP · speed ${e.speed}`, vfx: undefined })),
            ]
            const Dial = ({ label, hint, val, min, max, step, onSet }: {
              label: string; hint: string; val: number; min: number
              max: number; step: number; onSet: (v: number) => void }) => (
              <label className="flex items-center gap-2.5">
                <span className="w-[86px] shrink-0 text-[11px] font-mono text-[#9a96b8]">{label}</span>
                <input type="range" min={min} max={max} step={step} value={val}
                  onChange={e => onSet(parseFloat(e.target.value))}
                  className="flex-1 accent-[#5cffc9] h-1" />
                <span className="w-[46px] shrink-0 text-right text-[11px] font-mono text-[#5cffc9]">
                  {val.toFixed(2)}
                </span>
                <span className="hidden lg:block text-[10px] text-[#4a4764]">{hint}</span>
              </label>
            )
            return (
              <div className="rounded-xl border border-[#a78bfa]/25 bg-[#a78bfa]/5 px-4 py-3 space-y-2.5">
                <div className="flex items-center gap-1.5">
                  {([['cast', '🎭 Cast'], ['library', '🧩 Library'],
                     ['engines', '⚙ Engines'], ['rules', '📜 Rules'],
                     ['scene', '🎚 Scene']] as const).map(([id, lbl]) => (
                    <button key={id} onClick={() => setStudioTab(id)}
                      className={cn('px-2.5 py-1 rounded-full text-[11px] transition-all',
                        studioTab === id
                          ? 'bg-[#a78bfa]/25 text-[#d6c9ff]'
                          : 'text-[#807d99] hover:text-white')}>{lbl}</button>
                  ))}
                  <span className="ml-auto text-[10px] font-mono text-[#4a4764]">
                    {studioTab === 'scene'
                      ? 'live — changes the running game instantly'
                      : studioTab === 'library'
                        ? 'drag onto the game to place — rebuilds with the edit'
                        : studioTab === 'engines'
                          ? 'procedural systems every generated city inherits'
                          : 'derived from the spec this game actually runs'}
                  </span>
                </div>

                {studioTab === 'cast' && (
                  <div className="grid gap-1.5 [grid-template-columns:repeat(auto-fit,minmax(210px,1fr))]">
                    {cast.map((c, i) => (
                      <div key={i} className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[12px] text-white capitalize">{c.who}</span>
                          {c.n > 1 && <span className="text-[10px] font-mono text-[#807d99]">×{c.n}</span>}
                          <span className={cn('ml-auto px-1.5 py-0.5 rounded text-[9px] font-mono',
                            c.role === 'hostile' ? 'bg-[#ff5c8a]/15 text-[#ff8fae]'
                              : c.role === 'guard' ? 'bg-[#ffd88a]/15 text-[#ffd88a]'
                              : c.role === 'you' ? 'bg-[#5cffc9]/15 text-[#5cffc9]'
                              : 'bg-white/[0.05] text-[#807d99]')}>{c.role}</span>
                          <button onClick={() => toggleLock(c.lock)}
                            title={lockedLayers.includes(c.lock)
                              ? 'locked — edits can never change this; click to unlock'
                              : 'lock this so future edits keep it exactly as-is'}
                            className={cn('text-[11px] transition-all',
                              lockedLayers.includes(c.lock)
                                ? 'opacity-100' : 'opacity-30 hover:opacity-70')}>
                            {lockedLayers.includes(c.lock) ? '🔒' : '🔓'}
                          </button>
                        </div>
                        <div className="text-[10px] font-mono text-[#807d99] mt-0.5">{c.detail}</div>
                        {c.vfx && <div className="text-[10px] font-mono text-[#c86bff] mt-0.5">✦ {c.vfx} aura</div>}
                      </div>
                    ))}
                    <button onClick={() => setEditPrompt('add ')}
                      className="rounded-lg border border-dashed border-white/[0.10] px-3 py-2 text-[11px] text-[#807d99] hover:text-white hover:border-[#5cffc9]/40 transition-all">
                      + add a character
                    </button>
                  </div>
                )}

                {studioTab === 'library' && (
                  <AssetPalette
                    disabled={!playing || building}
                    onDragStart={setDragAsset}
                    onDragEnd={() => setDragAsset(null)}
                  />
                )}

                {studioTab === 'engines' && <EnginePanel />}

                {studioTab === 'rules' && (
                  <div className="grid gap-1 [grid-template-columns:repeat(auto-fit,minmax(280px,1fr))]">
                    {rows.map((r, i) => (
                      <div key={i} className="text-[11px] font-mono text-[#c9c6dd]">{r}</div>
                    ))}
                  </div>
                )}

                {studioTab === 'scene' && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[11px] font-mono text-[#9a96b8] w-[86px] shrink-0">polish</span>
                      {([['none', '— none'], ['cinematic', '🎬 Cinematic'],
                         ['noir', '🌫 Noir'], ['golden', '🌇 Golden'],
                         ['retro', '🕹 Retro']] as const).map(([id, lbl]) => (
                        <button key={id}
                          onClick={() => {
                            setGrade(id)
                            gameFrameRef.current?.contentWindow?.postMessage(
                              { type: 'fs-grade', grade: id }, '*')
                          }}
                          title="a coherent exposure/fog/light recipe — applies instantly and sticks for future builds"
                          className={cn('px-2.5 py-1 rounded-full text-[11px] transition-all',
                            grade === id
                              ? 'bg-[#5cffc9]/15 text-[#5cffc9] border border-[#5cffc9]/40'
                              : 'border border-white/[0.08] text-[#807d99] hover:text-white')}>
                          {lbl}
                        </button>
                      ))}
                      <button onClick={() => toggleLock('world')}
                        title="lock the world: scenery, sky and layout survive every future edit untouched"
                        className={cn('ml-auto px-2.5 py-1 rounded-full text-[11px] border transition-all',
                          lockedLayers.includes('world')
                            ? 'border-[#ffd88a]/50 text-[#ffd88a] bg-[#ffd88a]/10'
                            : 'border-white/[0.08] text-[#807d99] hover:text-white')}>
                        {lockedLayers.includes('world') ? '🔒 world locked' : '🔓 lock world'}
                      </button>
                    </div>
                    <Dial label="fog" hint="haze / depth" val={dials.fog}
                      min={0} max={20} step={0.5}
                      onSet={v => { setDials(d => ({ ...d, fog: v })); sendPatch({ fog_density: v }) }} />
                    <Dial label="sunlight" hint="key light" val={dials.sun}
                      min={0} max={6} step={0.1}
                      onSet={v => { setDials(d => ({ ...d, sun: v })); sendPatch({ sun_intensity: v }) }} />
                    <Dial label="exposure" hint="overall brightness" val={dials.exposure}
                      min={0.3} max={2.2} step={0.05}
                      onSet={v => { setDials(d => ({ ...d, exposure: v })); sendPatch({ exposure: v }) }} />
                    <div className="flex flex-wrap gap-1.5 pt-0.5">
                      {([['🐺 enemies slower', { enemy_speed: 1.6 }],
                         ['🐺 enemies faster', { enemy_speed: 4.2 }],
                         ['❤️ more HP', { player_hp: 8 }],
                         ['🏃 run faster', { run_speed: 9, walk_speed: 3.4 }]] as const).map(([lbl, patch]) => (
                        <button key={lbl} onClick={() => sendPatch(patch as Record<string, number>)}
                          className="px-2.5 py-1 rounded-full text-[11px] border border-white/[0.08] text-[#807d99] hover:text-white hover:border-[#5cffc9]/40 transition-all">
                          {lbl}
                        </button>
                      ))}
                    </div>
                    <div className="text-[10px] text-[#4a4764] pt-0.5">
                      Scene dials apply to the running game — no rebuild. Weather,
                      time of day and new content still rebuild (type them below).
                    </div>
                  </div>
                )}
              </div>
            )
          })()}

          {/* R-ITER: conversational editing — the generator becomes an engine.
              A selected point/thing from Inspect mode rides along with the edit. */}
          {selLine && (
            <div className="flex items-center gap-2 text-xs">
              <span className="px-3 py-1.5 rounded-lg bg-[#ffd88a]/10 border border-[#ffd88a]/30 text-[#ffd88a] font-mono">
                📏 line ({selLine.a.x.toFixed(1)}, {selLine.a.z.toFixed(1)}) → ({selLine.b.x.toFixed(1)}, {selLine.b.z.toFixed(1)})
                · {Math.hypot(selLine.b.x - selLine.a.x, selLine.b.z - selLine.a.z).toFixed(0)}m
              </span>
              <button onClick={() => setSelLine(null)} className="text-[#807d99] hover:text-white transition-colors" title="clear selection">✕</button>
              <span className="text-[#4a4764]">“place a fence here” tiles segments along this run</span>
            </div>
          )}
          {selPick && (
            <div className="flex items-center gap-2 text-xs flex-wrap">
              <span className="px-3 py-1.5 rounded-lg bg-[#ffd88a]/10 border border-[#ffd88a]/30 text-[#ffd88a] font-mono">
                📍 {selPick.target.name} at ({selPick.x.toFixed(1)}, {selPick.z.toFixed(1)})
              </span>
              <button
                onClick={() => setSelPick(null)}
                className="text-[#807d99] hover:text-white transition-colors"
                title="clear selection"
              >
                ✕
              </button>
              {selPick.target.type === 'placed' && selPick.target.idx != null ? (
                /* RULE CHIPS: every toggle is an honored runtime behavior */
                <span className="inline-flex items-center gap-1.5">
                  {[['safe_zone', '🔥 safe zone'], ['blocks_enemies', '🚧 blocks enemies'],
                    ['hurts_touch', '⚡ hurts on touch']].map(([rule, label]) => {
                    const on = (selPick.target.rules ?? []).includes(rule)
                    return (
                      <button
                        key={rule}
                        onClick={() => toggleRule(rule)}
                        disabled={building}
                        title={on ? 'rule is ON — click to remove' : 'rule is OFF — click to enable'}
                        className={cn(
                          'px-2 py-1 rounded-full text-[10px] border transition-colors disabled:opacity-40',
                          on ? 'border-[#5cffc9]/50 bg-[#5cffc9]/10 text-[#5cffc9]'
                             : 'border-white/[0.08] text-[#807d99] hover:text-white'
                        )}
                      >
                        {label}{on ? ' ✓' : ''}
                      </button>
                    )
                  })}
                </span>
              ) : (
                <span className="text-[#4a4764]">
                  “here” and “this” in your edit now mean this spot
                </span>
              )}
            </div>
          )}
          <div className="flex gap-2">
            <input
              value={editPrompt}
              onChange={(e) => setEditPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') iterate() }}
              placeholder={selPick
                ? `Edit here… (e.g. place a book here that says 'follow the river' · place a building here${selPick.target.type === 'npc' ? ` · make this ${selPick.target.name} faster` : ''})`
                : 'Edit this game… (e.g. make it night · add 3 wolves · winner gets a crown)'}
              className={cn(
                'flex-1 rounded-xl bg-[rgba(14,14,22,0.7)] border px-4 py-2.5 text-sm text-white placeholder:text-[#4a4764] focus:outline-none',
                selPick ? 'border-[#ffd88a]/30 focus:border-[#ffd88a]/50' : 'border-white/[0.06] focus:border-[#7c5cff]/40'
              )}
            />
            <button
              onClick={iterate}
              disabled={building || !editPrompt.trim()}
              className="px-4 py-2 rounded-xl text-sm font-semibold bg-[#7c5cff]/20 text-[#a78bfa] hover:bg-[#7c5cff]/30 disabled:opacity-40 transition-colors"
            >
              {building ? 'Applying…' : 'Apply edit'}
            </button>
          </div>
          {job!.notes?.length ? (
            <p className="text-[11px] font-mono text-[#4a4764]">
              {job!.notes.join(' · ')}
            </p>
          ) : null}
        </motion.div>
      )}
    </div>
  )
}
