// Phase 35 — Video Projects: collect rendered scenes into one exported film.

export interface VideoProject {
  id: number
  name: string
  scene_count: number
  scenes: { title: string | null; prompt: string | null }[]
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

export async function exportVideoProject(projectId: number) {
  return j<{ ok: boolean; scenes: number; mp4_mb: number; play_url: string; download: string }>(
    await fetch(`/api/video/projects/${projectId}/export`, { method: 'POST' }))
}
