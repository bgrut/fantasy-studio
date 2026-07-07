// Phase 30 — game-mode API client. Mirrors the render-jobs submit→poll UX;
// game builds need NO GPU (library assets), so this lane works even when the
// video lane's asset generation is GPU-blocked.

export interface GameJob {
  id: number
  prompt: string
  status: 'running' | 'complete' | 'failed'
  stage: string
  title?: string
  play_url?: string
  godot_path?: string
  checks?: number
  notes?: string[]
  error?: string
  created_at: number
  updated_at: number
}

export interface GameHealth {
  ok: boolean
  gpu_free: boolean
  ollama: boolean
  library_kinds: string[]
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export async function gameHealth(): Promise<GameHealth> {
  return j(await fetch('/api/game/health'))
}

// Inspector (Phase 42): what the user clicked in the running game — edits
// carry real world coordinates ("place a book HERE")
export interface PickPoint { x: number; z: number; target?: string }

export async function exportGame(prompt: string, opts?: { godot?: boolean; player?: string; baseJobId?: number; at?: PickPoint }) {
  const res = await fetch('/api/game/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // player omitted by default — the backend CASTS it from the prompt subject
    body: JSON.stringify({ prompt, godot: opts?.godot ?? false,
                           ...(opts?.player ? { player: opts.player } : {}),
                           // R-ITER: edit an existing game instead of generating anew
                           ...(opts?.baseJobId != null ? { base_job_id: opts.baseJobId } : {}),
                           ...(opts?.at ? { at_x: opts.at.x, at_z: opts.at.z,
                                            ...(opts.at.target ? { at_target: opts.at.target } : {}) } : {}) }),
  })
  return j<{ ok: boolean; job_id: number }>(res)
}

export async function getGameJob(id: number) {
  return j<{ ok: boolean; job: GameJob }>(await fetch(`/api/game/jobs/${id}`))
}

export async function listGameJobs() {
  return j<{ ok: boolean; jobs: GameJob[] }>(await fetch('/api/game/jobs'))
}

// ── Phase 34: Game Projects (collect levels -> one exported game) ──────────
export interface GameProject {
  id: number
  name: string
  level_count: number
  level_titles: (string | null)[]
}

export async function listProjects() {
  return j<{ ok: boolean; projects: GameProject[] }>(await fetch('/api/game/projects'))
}

export async function createProject(name: string) {
  return j<{ ok: boolean; project: { id: number } }>(await fetch('/api/game/projects', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  }))
}

export async function addLevelToProject(projectId: number, jobId: number) {
  return j<{ ok: boolean; level_count: number }>(await fetch(`/api/game/projects/${projectId}/levels`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId }),
  }))
}

export async function removeLevelFromProject(projectId: number, index: number) {
  return j<{ ok: boolean; removed: string | null; level_count: number }>(
    await fetch(`/api/game/projects/${projectId}/levels/${index}`, { method: 'DELETE' }))
}

export async function revealProjectZip(projectId: number) {
  // desktop shell: no browser download UI — backend opens Explorer at the zip
  return j<{ ok: boolean; path: string }>(
    await fetch(`/api/game/projects/${projectId}/reveal`, { method: 'POST' }))
}

export async function exportProject(projectId: number) {
  return j<{ ok: boolean; levels: number; play_url: string; zip: string; zip_mb: number }>(
    await fetch(`/api/game/projects/${projectId}/export`, { method: 'POST' }))
}
