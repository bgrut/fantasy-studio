// Phase 35 — "Add scene to my video" + project export, the video sibling of
// GameStudio's "Add to my game". Compact: lives in the Output panel header.
import { useCallback, useEffect, useState } from 'react'
import { Download, FolderPlus, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  addScene, createVideoProject, exportVideoProject, listVideoProjects,
  type VideoProject,
} from '@/lib/videoApi'

export default function VideoProjectBar({ outputUrl, prompt }: { outputUrl: string | null; prompt: string }) {
  const [project, setProject] = useState<VideoProject | null>(null)
  const [addedUrl, setAddedUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState<'add' | 'export' | null>(null)
  const [exported, setExported] = useState<{ play_url: string; download: string; mp4_mb: number } | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    listVideoProjects()
      .then(({ projects }) => setProject(projects[projects.length - 1] ?? null))
      .catch(() => {})
  }, [])

  const add = useCallback(async () => {
    if (!outputUrl || busy) return
    setBusy('add')
    setErr(null)
    try {
      let p = project
      if (!p) {
        const { project: np } = await createVideoProject('My Video')
        p = { id: np.id, name: 'My Video', scene_count: 0, scenes: [] }
      }
      const { scene_count } = await addScene(p.id, outputUrl, {
        title: prompt.slice(0, 60) || undefined, prompt: prompt || undefined,
      })
      setProject({ ...p, scene_count })
      setAddedUrl(outputUrl)
      setExported(null)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }, [outputUrl, prompt, project, busy])

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

  const added = addedUrl === outputUrl

  return (
    <div className="flex items-center gap-2 text-xs">
      {err && <span className="text-[#ff5c8a]">{err}</span>}
      {exported && (
        <>
          <a href={exported.play_url} target="_blank" rel="noreferrer"
             className="text-[#5cffc9] hover:underline">▶ Watch film</a>
          <a href={exported.download} className="text-[#5cffc9] hover:underline">
            ⬇ mp4 ({exported.mp4_mb} MB)
          </a>
        </>
      )}
      {project && project.scene_count > 0 && (
        <button
          onClick={doExport}
          disabled={busy !== null}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#ff5c8a]/10 text-[#ff9ab8] hover:bg-[#ff5c8a]/20 transition-colors disabled:opacity-50"
        >
          {busy === 'export' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
          Export film ({project.scene_count})
        </button>
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
    </div>
  )
}
