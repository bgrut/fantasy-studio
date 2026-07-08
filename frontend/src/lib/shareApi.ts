// Phase 46 — Community Marketplace client. The publish token lives on the
// backend only; the app talks to /api/share/* and the backend talks to the
// user's Cloudflare worker.

export interface ShareStatus {
  ok: boolean
  configured: boolean
  url?: string | null
  author: string
  publish?: { status: string; file?: string; url?: string; error?: string }
}

export interface FeedItem {
  id: string
  kind: 'game' | 'character'
  title: string
  author: string
  description?: string
  character_kind?: string | null
  created: string
  license: string
  url: string
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try { detail = (await res.json()).detail ?? detail } catch { /* keep default */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export async function shareStatus() {
  return j<ShareStatus>(await fetch('/api/share/status'))
}

export async function saveShareConfig(url: string, token: string, author: string) {
  return j<{ ok: boolean; url: string }>(await fetch('/api/share/config', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, token, author }),
  }))
}

export async function shareFeed() {
  return j<{ items: FeedItem[] }>(await fetch('/api/share/feed'))
}

export async function publishGame(projectId: number, title?: string, description?: string) {
  return j<{ ok: boolean; url: string; files: number }>(await fetch('/api/share/publish/game', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, title, description }),
  }))
}

export async function publishCharacter(kind: string, description?: string) {
  return j<{ ok: boolean; url: string; files: number }>(await fetch('/api/share/publish/character', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind, description }),
  }))
}

export async function installCharacter(id: string) {
  return j<{ ok: boolean; kind: string; note?: string }>(await fetch('/api/share/install/character', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id }),
  }))
}
