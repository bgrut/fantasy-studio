// Phase 30 — Game mode for the Studio. Prompt → playable web game, built by
// the backend in ~30-60s with NO GPU (library assets + Ollama extraction),
// then embedded right here so the user plays what they typed.
import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Download, FolderPlus, Gamepad2, Loader2, Maximize2, RotateCcw } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  addLevelToProject, createProject, exportGame, exportProject, gameHealth,
  getGameJob, listProjects, type GameHealth, type GameJob, type GameProject,
} from '@/lib/gameApi'

const GAME_PROMPTS = [
  'A samurai with a katana fights hostile dogs in a stormy forest — defeat 3, then reach the ancient shrine',
  'A fox on a snowy night quest: collect 6 fireflies, then race to the glowing beacon before dawn',
  'A wizard defends a windswept meadow — defeat 4 wild wolves with magic bolts, collect 3 lost runes',
  'A knight escorts his loyal dog across rainy highlands to a distant watchtower, collect 5 relics on the way',
  'A horse galloping free across golden-hour countryside, reach the far hilltop',
  'A man with a bow hunts through a foggy forest — defeat 2 hostile cats, collect 4 arrows, reach camp',
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
  const pollRef = useRef<number | null>(null)

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
      setAddedJob(job.id)
      setExported(null)                    // stale export after adding a level
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setExporting(false)
    }
  }, [project, exporting])

  const build = useCallback(async () => {
    const p = prompt.trim()
    if (!p || building) return
    setError(null)
    setJob(null)
    setBuilding(true)
    try {
      const { job_id } = await exportGame(p)
      pollRef.current = window.setInterval(async () => {
        try {
          const { job: jb } = await getGameJob(job_id)
          setJob(jb)
          if (jb.status !== 'running') {
            if (pollRef.current) window.clearInterval(pollRef.current)
            setBuilding(false)
            if (jb.status === 'failed') setError(jb.error ?? 'build failed')
          }
        } catch {
          /* transient poll miss — keep polling */
        }
      }, 1500)
    } catch (e) {
      setBuilding(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [prompt, building])

  const playing = job?.status === 'complete' && job.play_url

  return (
    <div className="space-y-8">
      {/* Prompt input — mirrors the video-mode hero input */}
      <div className="max-w-2xl mx-auto space-y-3">
        <div className="relative group">
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                build()
              }
            }}
            placeholder="A knight exploring a foggy forest…"
            className={cn(
              'w-full rounded-2xl bg-[rgba(14,14,22,0.7)] backdrop-blur-xl border px-4 sm:px-6 py-3 sm:py-4 text-base sm:text-lg text-white',
              'placeholder:text-[#4a4764] focus:outline-none transition-all duration-300 focus-glow',
              building ? 'border-[#5cffc9]/40' : 'border-white/[0.05]'
            )}
          />
          <button
            onClick={build}
            disabled={building || !prompt.trim()}
            className={cn(
              'absolute right-2 top-1/2 -translate-y-1/2 px-5 py-2.5 rounded-xl font-semibold text-sm',
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

        {/* prompt chips */}
        <div className="flex flex-wrap justify-center gap-2">
          {GAME_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => setPrompt(p)}
              className="px-3 py-1.5 rounded-full text-xs border border-white/[0.06] bg-white/[0.02] text-[#807d99] hover:text-white hover:border-[#5cffc9]/30 transition-all"
            >
              {p}
            </button>
          ))}
        </div>

        {/* health strip: game mode works with no GPU */}
        {health && (
          <p className="text-center text-[11px] text-[#4a4764] font-mono">
            no GPU needed · ollama {health.ollama ? 'online' : 'offline (keyword fallback)'} ·{' '}
            {health.library_kinds.length} characters in library
          </p>
        )}

        {/* MY GAME: collected levels + one-click export (Phase 34) */}
        {project && project.level_count > 0 && (
          <div className="flex items-center justify-center gap-3 text-xs">
            <span className="font-mono text-[#a78bfa]">
              🎮 {project.name}: {project.level_count} level{project.level_count !== 1 ? 's' : ''}
            </span>
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
                <a href={exported.play_url} target="_blank" rel="noreferrer"
                   className="text-[#5cffc9] hover:underline">▶ Play it</a>
                <a href={exported.zip}
                   className="text-[#5cffc9] hover:underline">⬇ Download zip ({exported.zip_mb} MB)</a>
              </>
            )}
          </div>
        )}
      </div>

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
                onClick={build}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-white/[0.08] text-[#807d99] hover:text-white transition-colors"
              >
                <RotateCcw className="w-3 h-3" /> New level
              </button>
              <a
                href={job!.play_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs bg-[#5cffc9]/15 text-[#5cffc9] hover:bg-[#5cffc9]/25 transition-colors"
              >
                <Maximize2 className="w-3 h-3" /> Fullscreen
              </a>
            </div>
          </div>
          <div className="rounded-2xl overflow-hidden border border-white/[0.06] bg-black aspect-video">
            <iframe
              src={job!.play_url}
              title={job!.title ?? 'game'}
              className="w-full h-full"
              allow="fullscreen; gamepad; pointer-lock"
            />
          </div>
          {job!.notes?.length ? (
            <p className="text-[11px] font-mono text-[#4a4764]">
              {job!.notes.join(' · ')} — new characters unlock with GPU generation
            </p>
          ) : null}
        </motion.div>
      )}
    </div>
  )
}
