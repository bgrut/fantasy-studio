// Phase 35 — "Add scene to my video" + project export, the video sibling of
// GameStudio's "Add to my game". Compact: lives in the Output panel header.
// Phase 43 — scene TILES: watch any scene in-app, "change this scene…"
// re-renders it through the same pipeline (Inspector methodology for video).
import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, Film, FolderPlus, Loader2, Pencil } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  addScene, createVideoProject, editScene, exportVideoProject,
  listVideoProjects, removeScene, revealVideoProject,
  type VideoProject,
} from '@/lib/videoApi'

export default function VideoProjectBar({ outputUrl, prompt }: { outputUrl: string | null; prompt: string }) {
  const [project, setProject] = useState<VideoProject | null>(null)
  const [addedUrl, setAddedUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState<'add' | 'export' | null>(null)
  const [exported, setExported] = useState<{ play_url: string; download: string; mp4_mb: number } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [showScenes, setShowScenes] = useState(false)
  const [watchUrl, setWatchUrl] = useState<string | null>(null)   // in-app player
  const [watchTitle, setWatchTitle] = useState<string>('')
  const [editIdx, setEditIdx] = useState<number | null>(null)     // scene being edited
  const [editText, setEditText] = useState('')
  const pollRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      const { projects } = await listVideoProjects()
      setProject(prev => (prev ? projects.find(p => p.id === prev.id) : projects[projects.length - 1]) ?? null)
    } catch { /* keep current */ }
  }, [])

  useEffect(() => {
    refresh()
    return () => { if (pollRef.current) window.clearInterval(pollRef.current) }
  }, [refresh])

  // while any scene re-renders, poll so tiles show live status
  const rendering = (project?.scenes ?? []).some(s => s.edit?.status === 'running')
  useEffect(() => {
    if (pollRef.current) window.clearInterval(pollRef.current)
    if (rendering) pollRef.current = window.setInterval(refresh, 4000)
    return () => { if (pollRef.current) window.clearInterval(pollRef.current) }
  }, [rendering, refresh])

  const add = useCallback(async () => {
    if (!outputUrl || busy) return
    setBusy('add')
    setErr(null)
    try {
      let p = project
      if (!p) {
        const { project: np } = await createVideoProject('My Video')
        p = { id: np.id, name: 'My Video', scene_count: 0, scenes: [] }
        setProject(p)
      }
      await addScene(p.id, outputUrl, {
        title: prompt.slice(0, 60) || undefined, prompt: prompt || undefined,
      })
      setAddedUrl(outputUrl)
      setExported(null)
      await refresh()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }, [outputUrl, prompt, project, busy, refresh])

  const doExport = useCallback(async () => {
    if (!project || busy) return
    setBusy('export')
    setErr(null)
    try {
      const r = await exportVideoProject(project.id)
      setExported({ play_url: r.play_url, download: r.download, mp4_mb: r.mp4_mb })
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }, [project, busy])

  const submitEdit = useCallback(async (index: number) => {
    if (!project || !editText.trim()) return
    setErr(null)
    try {
      await editScene(project.id, index, editText.trim())
      setEditIdx(null)
      setEditText('')
      setExported(null)               // the film no longer matches its scenes
      await refresh()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [project, editText, refresh])

  const added = addedUrl === outputUrl

  return (
    <div className="relative flex items-center gap-2 text-xs">
      {err && <span className="text-[#ff5c8a] max-w-[260px] truncate" title={err}>{err}</span>}
      {exported && (
        <>
          {/* buttons, not <a>: the desktop shell ignores target=_blank and
              has no download UI (same fix as the game-side export buttons) */}
          <button
            onClick={() => { setWatchUrl(exported.play_url); setWatchTitle(project?.name ?? 'My Video') }}
            className="text-[#5cffc9] hover:underline"
          >▶ Watch film</button>
          <button
            onClick={async () => {
              try { await revealVideoProject(project!.id) }
              catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
            }}
            title="opens the folder containing the mp4"
            className="text-[#5cffc9] hover:underline"
          >⬇ Show mp4 in folder ({exported.mp4_mb} MB)</button>
        </>
      )}
      {project && project.scene_count > 0 && (
        <>
          <button
            onClick={() => setShowScenes(v => !v)}
            className="font-mono text-[#a78bfa] hover:text-white transition-colors"
            title="show / hide scene tiles"
          >
            🎬 {project.scene_count} scene{project.scene_count !== 1 ? 's' : ''} {showScenes ? '▾' : '▸'}
          </button>
          <button
            onClick={doExport}
            disabled={busy !== null || rendering}
            title={rendering ? 'a scene is re-rendering — export when it finishes' : undefined}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#ff5c8a]/10 text-[#ff9ab8] hover:bg-[#ff5c8a]/20 transition-colors disabled:opacity-50"
          >
            {busy === 'export' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
            Export film ({project.scene_count})
          </button>
        </>
      )}
      {outputUrl && (
        <button
          onClick={add}
          disabled={busy !== null || added}
          className={cn(
            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors',
            added
              ? 'bg-[#7c5cff]/10 text-[#a78bfa] cursor-default'
              : 'bg-[#7c5cff]/15 text-[#a78bfa] hover:bg-[#7c5cff]/25 disabled:opacity-50'
          )}
        >
          {busy === 'add' ? <Loader2 className="w-3 h-3 animate-spin" /> : <FolderPlus className="w-3 h-3" />}
          {added ? 'Scene added ✓' : 'Add scene to my video'}
        </button>
      )}

      {/* Phase 43 — SCENE TILES panel: watch / change / remove each scene */}
      {showScenes && project && (
        <div className="absolute right-0 top-full mt-2 z-40 w-[420px] max-h-[60vh] overflow-y-auto rounded-2xl border border-white/[0.08] bg-[rgba(14,14,22,0.97)] backdrop-blur-xl p-3 space-y-2 shadow-2xl">
          {project.scenes.map((s, i) => (
            <div key={i} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-[10px] font-mono text-[#ff9ab8]">SCENE {i + 1}</div>
                  <div className="text-xs font-semibold text-[#eceaf6] truncate">
                    {s.title || 'untitled scene'}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {s.video && (
                    <button
                      onClick={() => { setWatchUrl(s.video); setWatchTitle(s.title || `Scene ${i + 1}`) }}
                      className="text-[#5cffc9] hover:underline"
                    >▶ Watch</button>
                  )}
                  <button
                    onClick={() => { setEditIdx(editIdx === i ? null : i); setEditText('') }}
                    disabled={s.edit?.status === 'running' || !s.prompt}
                    title={!s.prompt ? 'this scene has no saved prompt to edit' : 'change this scene'}
                    className="inline-flex items-center gap-1 text-[#a78bfa] hover:text-white disabled:opacity-40 transition-colors"
                  >
                    <Pencil className="w-3 h-3" /> Change
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        await removeScene(project.id, i)
                        setExported(null)
                        await refresh()
                      } catch { /* keep list */ }
                    }}
                    className="text-[#807d99] hover:text-[#ff5c8a] transition-colors"
                    title="remove this scene"
                  >✕</button>
                </div>
              </div>
              {s.edit?.status === 'running' && (
                <div className="mt-1.5 inline-flex items-center gap-1.5 text-[10px] text-[#ffd88a]">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  re-rendering: {s.edit.prompt?.slice(0, 52)}…
                </div>
              )}
              {s.edit?.status === 'failed' && (
                <div className="mt-1.5 text-[10px] text-[#ff5c8a]" title={s.edit.error}>
                  re-render failed — the original scene is untouched
                </div>
              )}
              {editIdx === i && (
                <div className="mt-2 flex gap-1.5">
                  <input
                    autoFocus
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') submitEdit(i) }}
                    placeholder="Change this scene… (e.g. make it night · heavy snow · slower camera)"
                    className="flex-1 rounded-lg bg-black/40 border border-white/[0.08] px-2.5 py-1.5 text-xs text-white placeholder:text-[#4a4764] focus:outline-none focus:border-[#a78bfa]/50"
                  />
                  <button
                    onClick={() => submitEdit(i)}
                    disabled={!editText.trim()}
                    className="px-2.5 py-1.5 rounded-lg bg-[#7c5cff]/20 text-[#a78bfa] hover:bg-[#7c5cff]/30 disabled:opacity-40 transition-colors"
                  >
                    Re-render
                  </button>
                </div>
              )}
            </div>
          ))}
          <p className="text-[10px] text-[#4a4764] px-1">
            edits re-render the scene through the full pipeline (minutes on CPU) — the film updates on the next export
          </p>
        </div>
      )}

      {/* in-app video player (film or single scene) */}
      {watchUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={() => setWatchUrl(null)}
        >
          <div
            className="w-[min(960px,92vw)] rounded-2xl overflow-hidden border border-white/[0.1] bg-black shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-2.5">
              <span className="inline-flex items-center gap-2 text-xs text-[#eceaf6]">
                <Film className="w-3.5 h-3.5 text-[#ff9ab8]" /> {watchTitle}
              </span>
              <button onClick={() => setWatchUrl(null)} className="text-[#807d99] hover:text-white text-xs">✕ Close</button>
            </div>
            <video key={watchUrl} src={watchUrl} controls autoPlay className="w-full aspect-video bg-black" />
          </div>
        </div>
      )}
    </div>
  )
}
