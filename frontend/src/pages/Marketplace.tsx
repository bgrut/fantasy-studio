// Phase 46 — the Community Marketplace: share full GAMES (playable links) and
// CHARACTERS (installable into anyone's library) with the community, and
// browse what everyone else has made. Local-first: nothing leaves this
// machine unless you press Publish.
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Cat,
  Check,
  Copy,
  Download,
  Gamepad2,
  Globe2,
  Loader2,
  Play,
  RefreshCw,
  Rocket,
  Settings2,
  ShieldCheck,
  Upload,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { gameHealth, listProjects, type GameProject } from '@/lib/gameApi'
import {
  installCharacter, publishCharacter, publishGame, saveShareConfig,
  shareFeed, shareStatus,
  type FeedItem, type ShareStatus,
} from '@/lib/shareApi'

type Tab = 'community' | 'share' | 'setup'

const WRANGLER_STEPS = [
  ['1', 'Create a free Cloudflare account', 'dash.cloudflare.com — the free tier is plenty'],
  ['2', 'Log in from a terminal', 'cd infra/share-worker · npx wrangler login (a browser window approves it)'],
  ['3', 'Create the storage bucket', 'npx wrangler r2 bucket create fantasy-studio-games'],
  ['4', 'Set your publish token', 'npx wrangler secret put PUBLISH_TOKEN — paste any long random string and keep it'],
  ['5', 'Deploy', 'npx wrangler deploy — copy the https://…workers.dev URL it prints'],
  ['6', 'Paste URL + token below', 'that’s it — Publish buttons light up everywhere'],
]

export default function Marketplace() {
  const [tab, setTab] = useState<Tab>('community')
  const [status, setStatus] = useState<ShareStatus | null>(null)
  const [feed, setFeed] = useState<FeedItem[]>([])
  const [feedLoading, setFeedLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // share tab data
  const [projects, setProjects] = useState<GameProject[]>([])
  const [kinds, setKinds] = useState<string[]>([])
  const [busy, setBusy] = useState<string | null>(null)   // id of the item publishing
  const [published, setPublished] = useState<Record<string, string>>({})  // key -> url
  const [agreed, setAgreed] = useState(false)

  // community tab interactions
  const [playUrl, setPlayUrl] = useState<string | null>(null)
  const [playTitle, setPlayTitle] = useState('')
  const [copied, setCopied] = useState<string | null>(null)
  const [installed, setInstalled] = useState<Record<string, string>>({})  // id -> note

  // setup form
  const [cfgUrl, setCfgUrl] = useState('')
  const [cfgToken, setCfgToken] = useState('')
  const [cfgAuthor, setCfgAuthor] = useState('')
  const [cfgSaving, setCfgSaving] = useState(false)
  const [cfgSaved, setCfgSaved] = useState(false)

  const refreshStatus = useCallback(async () => {
    try {
      const s = await shareStatus()
      setStatus(s)
      if (s.url) setCfgUrl(s.url)
      setCfgAuthor(a => a || s.author)
      return s
    } catch { return null }
  }, [])

  const loadFeed = useCallback(async () => {
    setFeedLoading(true)
    setError(null)
    try {
      const { items } = await shareFeed()
      setFeed(items)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setFeedLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshStatus().then(s => {
      if (s?.configured) loadFeed()
      else setTab('setup')
    })
    listProjects().then(({ projects }) => setProjects(projects)).catch(() => {})
    gameHealth().then(h => setKinds(h.library_kinds)).catch(() => {})
  }, [refreshStatus, loadFeed])

  const doPublishGame = useCallback(async (p: GameProject) => {
    setBusy(`game-${p.id}`)
    setError(null)
    try {
      const r = await publishGame(p.id, p.name)
      setPublished(prev => ({ ...prev, [`game-${p.id}`]: r.url }))
      loadFeed()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }, [loadFeed])

  const doPublishCharacter = useCallback(async (kind: string) => {
    setBusy(`char-${kind}`)
    setError(null)
    try {
      const r = await publishCharacter(kind)
      setPublished(prev => ({ ...prev, [`char-${kind}`]: r.url }))
      loadFeed()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }, [loadFeed])

  const doInstall = useCallback(async (item: FeedItem) => {
    setBusy(`install-${item.id}`)
    setError(null)
    try {
      const r = await installCharacter(item.id)
      setInstalled(prev => ({ ...prev, [item.id]: r.note ?? `'${r.kind}' installed` }))
      gameHealth().then(h => setKinds(h.library_kinds)).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }, [])

  const copyLink = useCallback(async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(url)
      setTimeout(() => setCopied(null), 1500)
    } catch { /* clipboard unavailable */ }
  }, [])

  const saveCfg = useCallback(async () => {
    setCfgSaving(true)
    setError(null)
    setCfgSaved(false)
    try {
      await saveShareConfig(cfgUrl.trim(), cfgToken.trim(), cfgAuthor.trim() || 'anonymous')
      setCfgSaved(true)
      const s = await refreshStatus()
      if (s?.configured) { setTab('community'); loadFeed() }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setCfgSaving(false)
    }
  }, [cfgUrl, cfgToken, cfgAuthor, refreshStatus, loadFeed])

  const stats = useMemo(() => ({
    games: feed.filter(i => i.kind === 'game').length,
    characters: feed.filter(i => i.kind === 'character').length,
    yours: feed.filter(i => i.author === (status?.author ?? '')).length,
  }), [feed, status])

  return (
    <div className="space-y-8 animate-reveal">
      {/* Header */}
      <div className="space-y-3">
        <span className="section-tag section-tag--pink font-mono text-xs">// marketplace</span>
        <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-gradient">
          Community Marketplace
        </h1>
        <p className="text-[#807d99] max-w-xl">
          Share full playable games and generated characters with the community —
          or install theirs into your own studio. Local-first: nothing leaves this
          machine until you press Publish.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard icon={<Gamepad2 className="w-5 h-5" />} value={stats.games} label="Community Games" color="#7c5cff" />
        <StatCard icon={<Cat className="w-5 h-5" />} value={stats.characters} label="Shared Characters" color="#ff5c8a" />
        <StatCard icon={<Rocket className="w-5 h-5" />} value={stats.yours} label="Published by You" color="#38d9c4" />
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 p-1 rounded-2xl bg-white/[0.03] border border-white/[0.05] w-fit">
        {([['community', 'Community', Globe2], ['share', 'Share Yours', Upload], ['setup', 'Setup', Settings2]] as [Tab, string, any][]).map(
          ([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => { setTab(id); if (id === 'community' && status?.configured) loadFeed() }}
              className={cn(
                'flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-300',
                tab === id
                  ? 'bg-[#7c5cff]/15 text-white border border-[#7c5cff]/25'
                  : 'text-[#807d99] hover:text-white hover:bg-white/[0.05] border border-transparent'
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          )
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-[#ff5c8a]/30 bg-[#ff5c8a]/5 px-4 py-3 text-sm text-[#ff9ab8]">
          {error}
        </div>
      )}

      {/* ── COMMUNITY: browse + play + install ─────────────────────────────── */}
      {tab === 'community' && (
        <div className="space-y-6">
          {!status?.configured ? (
            <NotConfigured onSetup={() => setTab('setup')} />
          ) : (
            <>
              <div className="flex items-center justify-between">
                <p className="text-xs font-mono text-[#4a4764]">
                  // everything here is shared under CC-BY-4.0 by its author
                </p>
                <button
                  onClick={loadFeed}
                  disabled={feedLoading}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-white/[0.08] text-[#807d99] hover:text-white transition-colors"
                >
                  {feedLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                  Refresh
                </button>
              </div>
              {feedLoading && feed.length === 0 ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="w-6 h-6 animate-spin text-[#7c5cff]" />
                </div>
              ) : feed.length === 0 ? (
                <div className="glass rounded-2xl py-16 text-center space-y-2">
                  <Globe2 className="w-8 h-8 text-[#4a4764] mx-auto" />
                  <p className="text-sm text-[#807d99]">The community feed is empty — be the first.</p>
                  <p className="text-xs font-mono text-[#4a4764]">publish a game or character from the Share tab</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5 stagger-reveal">
                  {feed.map(item => (
                    <div key={item.id} className="glass rounded-2xl p-5 card-hover flex flex-col gap-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-[10px] font-mono" style={{ color: item.kind === 'game' ? '#a78bfa' : '#ff9ab8' }}>
                            {item.kind === 'game' ? '🎮 GAME' : '🧬 CHARACTER'}
                          </div>
                          <h3 className="text-sm font-bold text-white truncate">{item.title}</h3>
                          <p className="text-xs font-mono text-[#4a4764]">
                            by {item.author} · {new Date(item.created).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      {item.description && (
                        <p className="text-xs text-[#807d99] line-clamp-2">{item.description}</p>
                      )}
                      <div className="mt-auto flex items-center gap-2">
                        {item.kind === 'game' ? (
                          <button
                            onClick={() => { setPlayUrl(item.url); setPlayTitle(item.title) }}
                            className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-semibold bg-[#5cffc9]/15 text-[#5cffc9] hover:bg-[#5cffc9]/25 transition-colors"
                          >
                            <Play className="w-3.5 h-3.5" /> Play
                          </button>
                        ) : installed[item.id] ? (
                          <span className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs bg-[#5cffc9]/10 text-[#5cffc9]" title={installed[item.id]}>
                            <Check className="w-3.5 h-3.5" /> In your library
                          </span>
                        ) : (
                          <button
                            onClick={() => doInstall(item)}
                            disabled={busy === `install-${item.id}`}
                            className="flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-semibold bg-[#7c5cff]/15 text-[#a78bfa] hover:bg-[#7c5cff]/25 transition-colors disabled:opacity-50"
                          >
                            {busy === `install-${item.id}` ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                            Install to library
                          </button>
                        )}
                        <button
                          onClick={() => copyLink(item.url)}
                          title="copy the public link"
                          className="p-2 rounded-xl border border-white/[0.08] text-[#807d99] hover:text-white transition-colors"
                        >
                          {copied === item.url ? <Check className="w-3.5 h-3.5 text-[#5cffc9]" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── SHARE YOURS: publish games + characters ─────────────────────────── */}
      {tab === 'share' && (
        <div className="space-y-6">
          {!status?.configured ? (
            <NotConfigured onSetup={() => setTab('setup')} />
          ) : (
            <>
              {/* the honest disclosure, once per session */}
              <div className="glass rounded-2xl p-4 flex items-start gap-3">
                <ShieldCheck className="w-5 h-5 text-[#38d9c4] shrink-0 mt-0.5" />
                <div className="text-xs text-[#807d99] space-y-1.5">
                  <p className="text-sm font-semibold text-white">Before you publish</p>
                  <p>
                    Publishing uploads the selected game files or character model to your
                    Cloudflare worker and lists them on the public community feed as
                    <span className="text-[#c9c6dd]"> {status.author}</span>. Shared content is
                    licensed <span className="text-[#c9c6dd]">CC-BY-4.0</span> — anyone may play,
                    install and remix it with credit. Only publish what you made and are happy
                    to share. Full policy: <span className="font-mono text-[#a78bfa]">PRIVACY.md</span> in the repo.
                  </p>
                  <label className="flex items-center gap-2 cursor-pointer text-[#c9c6dd]">
                    <input type="checkbox" checked={agreed} onChange={e => setAgreed(e.target.checked)} className="accent-[#7c5cff]" />
                    I understand — publish publicly under CC-BY-4.0
                  </label>
                </div>
              </div>

              {/* games */}
              <div className="space-y-3">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Gamepad2 className="w-4 h-4 text-[#a78bfa]" /> Your Games
                </h2>
                {projects.filter(p => p.level_count > 0).length === 0 ? (
                  <p className="text-xs font-mono text-[#4a4764]">// build levels in Game mode, add them to a project, Export game — then publish here</p>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {projects.filter(p => p.level_count > 0).map(p => {
                      const key = `game-${p.id}`
                      return (
                        <div key={p.id} className="glass rounded-2xl p-5 flex flex-col gap-2 card-hover">
                          <h3 className="text-sm font-bold text-white">{p.name}</h3>
                          <p className="text-xs font-mono text-[#4a4764]">
                            {p.level_count} level{p.level_count !== 1 ? 's' : ''} ·{' '}
                            {(p.level_titles ?? []).filter(Boolean).slice(0, 3).join(' · ') || 'untitled'}
                          </p>
                          {published[key] ? (
                            <div className="flex items-center gap-2 mt-auto">
                              <span className="text-xs text-[#5cffc9] truncate flex-1" title={published[key]}>✓ live: {published[key]}</span>
                              <button onClick={() => copyLink(published[key])} className="p-1.5 rounded-lg border border-white/[0.08] text-[#807d99] hover:text-white">
                                {copied === published[key] ? <Check className="w-3 h-3 text-[#5cffc9]" /> : <Copy className="w-3 h-3" />}
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => doPublishGame(p)}
                              disabled={!agreed || busy !== null}
                              title={!agreed ? 'tick the consent box above first' : 'requires an Export game first'}
                              className="mt-auto inline-flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-semibold bg-[#7c5cff]/15 text-[#a78bfa] hover:bg-[#7c5cff]/25 transition-colors disabled:opacity-40"
                            >
                              {busy === key ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Rocket className="w-3.5 h-3.5" />}
                              {busy === key ? 'Uploading…' : 'Publish game'}
                            </button>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* characters */}
              <div className="space-y-3">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Cat className="w-4 h-4 text-[#ff9ab8]" /> Your Characters
                </h2>
                <p className="text-xs font-mono text-[#4a4764]">// every kind in your library can be shared — installers can cast it in their own prompts</p>
                <div className="flex flex-wrap gap-2">
                  {kinds.map(k => {
                    const key = `char-${k}`
                    return published[key] ? (
                      <span key={k} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs bg-[#5cffc9]/10 border border-[#5cffc9]/25 text-[#5cffc9]">
                        <Check className="w-3 h-3" /> {k}
                        <button onClick={() => copyLink(published[key])} title="copy link" className="hover:text-white">
                          {copied === published[key] ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                        </button>
                      </span>
                    ) : (
                      <button
                        key={k}
                        onClick={() => doPublishCharacter(k)}
                        disabled={!agreed || busy !== null}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs border border-white/[0.08] bg-white/[0.02] text-[#807d99] hover:text-white hover:border-[#ff5c8a]/40 transition-all disabled:opacity-40"
                      >
                        {busy === key ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
                        {k}
                      </button>
                    )
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── SETUP: one-time Cloudflare wiring ───────────────────────────────── */}
      {tab === 'setup' && (
        <div className="space-y-6 max-w-3xl">
          <div className="glass rounded-2xl p-6 space-y-4">
            <h2 className="text-lg font-bold text-white">One-time setup — your own free share service</h2>
            <p className="text-xs text-[#807d99]">
              The marketplace runs on <span className="text-[#c9c6dd]">your</span> Cloudflare
              account (free tier), so your community stays yours. Six steps, about five minutes:
            </p>
            <ol className="space-y-2.5">
              {WRANGLER_STEPS.map(([n, title, detail]) => (
                <li key={n} className="flex gap-3">
                  <span className="w-6 h-6 rounded-lg bg-[#7c5cff]/15 text-[#a78bfa] text-xs font-mono flex items-center justify-center shrink-0">{n}</span>
                  <div>
                    <p className="text-sm text-white">{title}</p>
                    <p className="text-xs font-mono text-[#4a4764]">{detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>

          <div className="glass rounded-2xl p-6 space-y-4">
            <h3 className="text-sm font-semibold text-white">Connect</h3>
            <div className="grid gap-3">
              <label className="text-xs font-mono text-[#4a4764]">worker URL
                <input value={cfgUrl} onChange={e => setCfgUrl(e.target.value)}
                  placeholder="https://fantasy-studio-share.YOUR-NAME.workers.dev"
                  className="mt-1 w-full rounded-xl bg-white/[0.03] border border-white/[0.05] px-4 py-2.5 text-sm text-white placeholder:text-[#4a4764] focus:outline-none focus:border-[#7c5cff]/40" />
              </label>
              <label className="text-xs font-mono text-[#4a4764]">publish token
                <input value={cfgToken} onChange={e => setCfgToken(e.target.value)} type="password"
                  placeholder="the PUBLISH_TOKEN you set in step 4"
                  className="mt-1 w-full rounded-xl bg-white/[0.03] border border-white/[0.05] px-4 py-2.5 text-sm text-white placeholder:text-[#4a4764] focus:outline-none focus:border-[#7c5cff]/40" />
              </label>
              <label className="text-xs font-mono text-[#4a4764]">display name (shown as the author on everything you publish)
                <input value={cfgAuthor} onChange={e => setCfgAuthor(e.target.value)}
                  placeholder="anonymous"
                  className="mt-1 w-full rounded-xl bg-white/[0.03] border border-white/[0.05] px-4 py-2.5 text-sm text-white placeholder:text-[#4a4764] focus:outline-none focus:border-[#7c5cff]/40" />
              </label>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={saveCfg}
                disabled={cfgSaving || !cfgUrl.trim() || !cfgToken.trim()}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold btn-generate disabled:opacity-40"
              >
                {cfgSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                {cfgSaving ? 'Checking…' : 'Save & connect'}
              </button>
              {cfgSaved && <span className="text-xs text-[#5cffc9]">✓ connected</span>}
              {status?.configured && !cfgSaved && (
                <span className="text-xs font-mono text-[#4a4764]">currently: {status.url}</span>
              )}
            </div>
            <p className="text-[11px] font-mono text-[#4a4764]">
              // the token is stored locally (renders/share_config.json) and never leaves your machine except to YOUR worker
            </p>
          </div>
        </div>
      )}

      {/* in-app player for community games (WebView2 has no new-tab) */}
      {playUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setPlayUrl(null)}>
          <div className="w-[min(1100px,94vw)] rounded-2xl overflow-hidden border border-white/[0.1] bg-black shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-2.5">
              <span className="inline-flex items-center gap-2 text-xs text-[#eceaf6]">
                <Gamepad2 className="w-3.5 h-3.5 text-[#a78bfa]" /> {playTitle}
                <button onClick={() => copyLink(playUrl)} className="text-[#807d99] hover:text-white inline-flex items-center gap-1">
                  {copied === playUrl ? <Check className="w-3 h-3 text-[#5cffc9]" /> : <Copy className="w-3 h-3" />} copy link
                </button>
              </span>
              <button onClick={() => setPlayUrl(null)} className="text-[#807d99] hover:text-white text-xs inline-flex items-center gap-1">
                <X className="w-3.5 h-3.5" /> Close
              </button>
            </div>
            <iframe key={playUrl} src={playUrl} title={playTitle} className="w-full aspect-video bg-black"
              allow="fullscreen; gamepad; pointer-lock" allowFullScreen />
          </div>
        </div>
      )}
    </div>
  )
}

function NotConfigured({ onSetup }: { onSetup: () => void }) {
  return (
    <div className="glass rounded-2xl py-14 text-center space-y-3">
      <Settings2 className="w-8 h-8 text-[#4a4764] mx-auto" />
      <p className="text-sm text-[#807d99]">Connect your free Cloudflare share service to browse and publish.</p>
      <button onClick={onSetup} className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold btn-generate">
        <Rocket className="w-4 h-4" /> Set it up (5 min)
      </button>
    </div>
  )
}

function StatCard({ icon, value, label, color }: { icon: ReactNode; value: number | string; label: string; color: string }) {
  return (
    <div className="glass rounded-2xl p-5 flex items-center gap-4 card-hover">
      <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${color}15`, color }}>
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-xs font-mono text-[#4a4764]">{label}</p>
      </div>
    </div>
  )
}
