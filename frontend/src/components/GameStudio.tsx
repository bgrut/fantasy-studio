// Phase 30 — Game mode for the Studio. Prompt → playable web game, built by
// the backend in ~30-60s with NO GPU (library assets + Ollama extraction),
// then embedded right here so the user plays what they typed.
import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Crosshair, Download, FolderPlus, Gamepad2, Loader2, Maximize2, RotateCcw } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  addLevelToProject, createProject, exportGame, exportProject, gameHealth,
  getGameJob, listProjects, openLevel, removeLevelFromProject, revealProjectZip,
  updateLevel,
  type GameHealth, type GameJob, type GameProject,
} from '@/lib/gameApi'

// Breadth showcase: classics that always work + wild ideas that exercise the
// whole pipeline (new creatures generate on first use, worlds span earth to
// mars, any species can race, rewards headline the win screen).
const GAME_PROMPTS = [
  'A fox on a snowy night quest: collect 6 fireflies, then race to the glowing beacon before dawn',
  'A samurai with a katana fights hostile dogs in a stormy forest — defeat 3, then reach the ancient shrine',
  'A dragon soaring over the mountains — collect 5 fire flames between the peaks',
  'A whale in the deep ocean: dive for 5 pearls, then surface at the beacon',
  'A red sports car races 5 rivals through New York City streets at night',
  'A cat fighting a monkey on mars — the winner gets a banana',
  'A wizard defends a windswept meadow — defeat 4 wild wolves with magic bolts, collect 3 lost runes',
  'A knight racing three other knights across the castle grounds at dusk',
  'One man with a bow against 12 hostile wolves in the arctic — survive and reach the cabin',
  'A penguin waddling across the moon, collect 6 moon rocks',
  'A detective collects 5 clues inside a mansion at night',
  'A knight fights 6 hostile goblins inside a torchlit castle',
]

// Phase 44 STYLE PRESETS — the user picks, the AI never guesses. One global
// render treatment (cel shading, outlines, grain, palette) per game.
const STYLES: { id: string; label: string; hint: string }[] = [
  { id: 'default', label: '🎬 Photoreal', hint: 'the classic look — natural light and texture' },
  { id: 'cartoon', label: '🖍️ Cartoon', hint: 'cel shading + ink outlines, bold and friendly' },
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
  const [view, setView] = useState('3d')                   // Phase 45 view preset
  const [placeMode, setPlaceMode] = useState<'point' | 'line'>('point')
  const [lineA, setLineA] = useState<Pick | null>(null)    // line tool first click
  const [selLine, setSelLine] = useState<{ a: Pick; b: Pick } | null>(null)
  const [showRules, setShowRules] = useState(false)        // Truth Table panel
  const pollRef = useRef<number | null>(null)
  const gameFrameRef = useRef<HTMLIFrameElement | null>(null)
  const hubFrameRef = useRef<HTMLIFrameElement | null>(null)
  const [showLevels, setShowLevels] = useState(true)   // level tiles open by default

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
                                      at2?: { x: number; z: number }) => {
    setError(null)
    setSavedLevel(null)                   // any rebuild invalidates "Saved ✓"
    if (baseJobId == null) { setJob(null); setOpenedLevel(null) }  // fresh build = not a level edit
    setBuilding(true)
    try {
      const { job_id } = await exportGame(p, baseJobId != null
        ? { baseJobId, at, at2 }
        // fresh build: USER-SELECTED style + view ride along — never guessed
        : { style: style !== 'default' ? style : undefined,
            view: view !== '3d' ? view : undefined })
      pollJob(job_id)
    } catch (e) {
      setBuilding(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [pollJob, style, view])

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

  const playing = job?.status === 'complete' && job.play_url

  // Inspector bridge: the game raycasts under the cursor and reports what/where
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      const d = e.data
      if (!d || d.type !== 'fs-pick') return
      const p: Pick = { x: d.x, z: d.z, target: d.target ?? { type: 'ground', name: 'ground' } }
      if (d.kind === 'hover') { setHoverPick(p); return }
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
      {/* Prompt input — mirrors the video-mode hero input */}
      <div className="max-w-2xl mx-auto space-y-3">
        <div className="relative group">
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

        {/* prompt chips — SCRUNCHED: truncated multi-column pills instead of
            ten full-width rows (full prompt on hover + on click) */}
        <div className="flex flex-wrap justify-center gap-1.5">
          {GAME_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => setPrompt(p)}
              title={p}
              className="px-3 py-1 rounded-full text-[11px] border border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white hover:border-[#5cffc9]/30 transition-all max-w-[240px] truncate"
            >
              {p}
            </button>
          ))}
        </div>

        {/* STYLE + VIEW PRESETS: the user picks — the AI never guesses */}
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
          <span className="text-[10px] font-mono text-[#4a4764] ml-2">view:</span>
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
              <span className="text-[10px] font-mono text-[#4a4764] self-center">cast today:</span>
              {health.library_kinds.map((k) => (
                <button
                  key={k}
                  onClick={() => setPrompt((p) => (p.trim() ? p : `A ${k} `))}
                  title={`"${k}" is in your generated library — star it in a prompt`}
                  className="px-2 py-0.5 rounded-full text-[10px] font-mono border border-[#5cffc9]/20 bg-[#5cffc9]/5 text-[#5cffc9]/80 hover:bg-[#5cffc9]/15 transition-colors"
                >
                  {k}
                </button>
              ))}
              <span className="text-[10px] font-mono text-[#4a4764] self-center">
                · new characters are CREATED on first use (image → 3D; slower without a GPU)
              </span>
            </div>
          </>
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
            {BUILD_STAGES[job.stage] ?? job.stage}
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
                title="the Truth Table: every rule this game actually enforces"
                className={cn(
                  'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors',
                  showRules
                    ? 'bg-[#a78bfa]/20 text-[#a78bfa]'
                    : 'border border-white/[0.08] text-[#807d99] hover:text-white'
                )}
              >
                📜 Rules
              </button>
              <button
                onClick={build}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-white/[0.08] text-[#807d99] hover:text-white transition-colors"
              >
                <RotateCcw className="w-3 h-3" /> New level
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
              key={job!.play_url}   /* new game = fresh iframe: releases the old
                                       WebGL context (WebView2 caps them; leaks
                                       caused the silent white-canvas bug) */
              ref={gameFrameRef}
              src={job!.play_url}
              title={job!.title ?? 'game'}
              className="w-full h-full"
              allow="fullscreen; gamepad; pointer-lock"
              allowFullScreen
              onLoad={() => { gameFrameRef.current?.focus({ preventScroll: true }); if (inspect) sendInspect(true) }}
            />
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
            return (
              <div className="rounded-xl border border-[#a78bfa]/25 bg-[#a78bfa]/5 px-4 py-3">
                <div className="text-[10px] font-mono text-[#a78bfa] mb-1.5">
                  // THE TRUTH TABLE — every rule this game enforces
                </div>
                <div className="grid gap-1 [grid-template-columns:repeat(auto-fit,minmax(280px,1fr))]">
                  {rows.map((r, i) => (
                    <div key={i} className="text-[11px] font-mono text-[#c9c6dd]">{r}</div>
                  ))}
                </div>
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
