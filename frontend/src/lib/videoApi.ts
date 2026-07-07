// Phase 35 — Video Projects: collect rendered scenes into one exported film.

export interface VideoScene {
  title: string | null
  prompt: string | null
  video: string | null                     // /outputs/... — playable in-app
  edit?: { status: 'running' | 'done' | 'failed'; prompt?: string; error?: string } | null
}

export interface VideoProject {
  id: number
  name: string
  scene_count: number
  scenes: VideoScene[]
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export async function listVideoProjects() {
  return j<{ ok: boolean; projects: VideoProject[] }>(await fetch('/api/video/projects'))
}

export async function createVideoProject(name: string) {
  return j<{ ok: boolean; project: { id: number } }>(await fetch('/api/video/projects', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  }))
}

export async function addScene(projectId: number, video: string, opts?: { title?: string; prompt?: string }) {
  return j<{ ok: boolean; scene_count: number }>(await fetch(`/api/video/projects/${projectId}/scenes`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video, title: opts?.title, prompt: opts?.prompt }),
  }))
}

export async function editScene(projectId: number, index: number, change: string) {
  // Phase 43 — Inspector for video: "change this scene…" re-renders the scene
  return j<{ ok: boolean; new_prompt: string }>(
    await fetch(`/api/video/projects/${projectId}/scenes/${index}/edit`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ change }),
    }))
}

export async function removeScene(projectId: number, index: number) {
  return j<{ ok: boolean; scene_count: number }>(
    await fetch(`/api/video/projects/${projectId}/scenes/${index}`, { method: 'DELETE' }))
}

export async function revealVideoProject(projectId: number) {
  // desktop shell: no download UI — backend opens Explorer at the film
  return j<{ ok: boolean; path: string }>(
    await fetch(`/api/video/projects/${projectId}/reveal`, { method: 'POST' }))
}

export async function exportVideoProject(projectId: number) {
  return j<{ ok: boolean; scenes: number; mp4_mb: number; play_url: string; download: string }>(
    await fetch(`/api/video/projects/${projectId}/export`, { method: 'POST' }))
}
