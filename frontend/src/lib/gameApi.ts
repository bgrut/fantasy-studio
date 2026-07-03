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

export async function exportGame(prompt: string, opts?: { godot?: boolean; player?: string }) {
  const res = await fetch('/api/game/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, godot: opts?.godot ?? false, player: opts?.player ?? 'man' }),
  })
  return j<{ ok: boolean; job_id: number }>(res)
}

export async function getGameJob(id: number) {
  return j<{ ok: boolean; job: GameJob }>(await fetch(`/api/game/jobs/${id}`))
}

export async function listGameJobs() {
  return j<{ ok: boolean; jobs: GameJob[] }>(await fetch('/api/game/jobs'))
}
