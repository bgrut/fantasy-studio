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
  spec_resolved?: GameSpecResolved       // full resolved spec — the Truth Table reads it
}

// the slice of the resolved spec the studio UI actually reads
export interface GameSpecResolved {
  style?: string
  world?: {
    name?: string; sky?: string; weather?: string; health_packs?: number
    fog_density?: number | null
    placed_items?: { kind: string; name?: string; x: number; z: number
                     interact?: string | null; rules?: string[] }[]
  }
  entities?: { name: string; behavior: string; count: number; speed: number; hp: number }[]
  objectives?: { kind: string; label: string; count: number }[]
  player?: { name?: string; hp?: number; attack?: string }
  reward?: string | null
}

export interface GameHealth {
  ok: boolean
  gpu_free: boolean
  gpu?: string | null            // CUDA device name when generation runs on GPU
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

export async function exportGame(prompt: string, opts?: {
  godot?: boolean; player?: string; baseJobId?: number; at?: PickPoint
  at2?: { x: number; z: number }                     // line tool second point
  style?: string                                     // USER-selected style preset
  view?: string                                      // 3d / topdown / side (Phase 45)
  rule?: { index: number; name: string; on: boolean } // rule chip toggle
}) {
  const res = await fetch('/api/game/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // player omitted by default — the backend CASTS it from the prompt subject
    body: JSON.stringify({ prompt, godot: opts?.godot ?? false,
                           ...(opts?.player ? { player: opts.player } : {}),
                           // R-ITER: edit an existing game instead of generating anew
                           ...(opts?.baseJobId != null ? { base_job_id: opts.baseJobId } : {}),
                           ...(opts?.at ? { at_x: opts.at.x, at_z: opts.at.z,
                                            ...(opts.at.target ? { at_target: opts.at.target } : {}) } : {}),
                           ...(opts?.at2 ? { at_x2: opts.at2.x, at_z2: opts.at2.z } : {}),
                           ...(opts?.style ? { style: opts.style } : {}),
                           ...(opts?.view ? { view: opts.view } : {}),
                           ...(opts?.rule ? { rule_index: opts.rule.index,
                                              rule_name: opts.rule.name,
                                              rule_on: opts.rule.on } : {}) }),
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
  levels?: { title: string | null; player: string | null; seed: number | null }[]
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

export async function openLevel(projectId: number, index: number) {
  // Phase 43 level tiles: click a level -> live job (play + Inspect + edit)
  return j<{ ok: boolean; job_id: number; title: string | null }>(
    await fetch(`/api/game/projects/${projectId}/levels/${index}/open`, { method: 'POST' }))
}

export async function updateLevel(projectId: number, index: number, jobId: number) {
  // save the edited game back into the level it was opened from
  return j<{ ok: boolean; updated: number; title: string | null }>(
    await fetch(`/api/game/projects/${projectId}/levels/${index}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
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
