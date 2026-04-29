import React from 'react'
import { Link, useLocation } from '@tanstack/react-router'
import {
  Wand2,
  Film,
  BarChart3,
  Layers,
  Store,
  Settings as SettingsIcon,
  Menu,
  X,
  Github,
  MessagesSquare,
  Heart,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { motion, AnimatePresence } from 'framer-motion'

interface LayoutProps {
  children: React.ReactNode
}

const navItems = [
  { label: 'Studio', href: '/studio', icon: Wand2 },
  { label: 'Gallery', href: '/outputs', icon: Film },
  { label: 'Insights', href: '/insights', icon: BarChart3 },
  { label: 'Assets', href: '/templates', icon: Layers },
  { label: 'Marketplace', href: '/marketplace', icon: Store },
]

export function AppLayout({ children }: LayoutProps) {
  const { pathname } = useLocation()
  const [mobileOpen, setMobileOpen] = React.useState(false)

  return (
    <div className="min-h-screen bg-[#050508] text-[#e4e2f0] overflow-x-hidden selection:bg-primary/30 selection:text-white">
      {/* Floating CSS shapes (GameCube parallax feel) */}
      <div className="floating-shapes">
        <div className="shape shape-1" />
        <div className="shape shape-2" />
        <div className="shape shape-3" />
        <div className="shape shape-4" />
        <div className="shape shape-5" />
        <div className="shape shape-6" />
      </div>

      {/* Grid overlay */}
      <div className="grid-overlay" />

      {/* Scanlines */}
      <div className="scanlines" />

      {/* ── Top Navigation Bar ────────────────────────────── */}
      <nav className="fixed top-0 left-0 right-0 z-50 glass-dark border-b border-white/[0.05]">
        <div className="max-w-[1600px] mx-auto px-6 h-16 flex items-center justify-between">
          {/* Left: Logo */}
          <Link to="/studio" className="flex items-center gap-3 group">
            <div className="spinning-cube" />
            <span className="text-lg font-bold tracking-tight text-gradient">
              Fantasy Studio
            </span>
          </Link>

          {/* Center: Nav links (desktop) */}
          <div className="hidden md:flex items-center gap-1 p-1 rounded-2xl bg-white/[0.03] border border-white/[0.05]">
            {navItems.map((item) => {
              const isActive = pathname === item.href ||
                (item.href === '/studio' && pathname === '/') ||
                (item.href === '/studio' && pathname === '/create')
              return (
                <Link
                  key={item.href}
                  to={item.href}
                  className={cn(
                    'relative flex items-center gap-2 px-5 py-2 rounded-xl text-sm font-medium transition-all duration-300',
                    isActive
                      ? 'text-white'
                      : 'text-[#807d99] hover:text-white'
                  )}
                >
                  {isActive && (
                    <motion.div
                      layoutId="nav-pill"
                      className="absolute inset-0 bg-primary/15 border border-primary/25 rounded-xl"
                      transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
                    />
                  )}
                  <item.icon className="w-4 h-4 relative z-10 icon-bounce" />
                  <span className="relative z-10">{item.label}</span>
                </Link>
              )
            })}
          </div>

          {/* Right: Status + Socials + Settings */}
          <div className="flex items-center gap-3">
            <ClusterStatusPill />

            {/* F1 — Discord / GitHub / Patreon links. Stubs until URLs land
                in settings; show a "coming soon" tooltip + disabled look. */}
            <div className="hidden md:flex items-center gap-0.5">
              <SocialIconLink
                href={null}
                label="Discord (coming soon)"
                Icon={MessagesSquare}
              />
              <SocialIconLink
                href={null}
                label="GitHub (coming soon)"
                Icon={Github}
              />
              <SocialIconLink
                href={null}
                label="Patreon (coming soon)"
                Icon={Heart}
              />
            </div>

            <Link
              to="/settings"
              className={cn(
                'p-2 rounded-xl transition-all hover:bg-white/[0.05]',
                pathname === '/settings' ? 'text-primary' : 'text-[#807d99] hover:text-white'
              )}
            >
              <SettingsIcon className="w-5 h-5" />
            </Link>

            {/* Mobile menu toggle */}
            <button
              className="md:hidden p-2 rounded-xl hover:bg-white/[0.05] text-[#807d99]"
              onClick={() => setMobileOpen(!mobileOpen)}
            >
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile nav dropdown */}
        <AnimatePresence>
          {mobileOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="md:hidden overflow-hidden border-t border-white/[0.05]"
            >
              <div className="p-4 space-y-1">
                {navItems.map((item) => {
                  const isActive = pathname === item.href ||
                    (item.href === '/studio' && pathname === '/')
                  return (
                    <Link
                      key={item.href}
                      to={item.href}
                      onClick={() => setMobileOpen(false)}
                      className={cn(
                        'flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all',
                        isActive
                          ? 'bg-primary/15 text-white border border-primary/25'
                          : 'text-[#807d99] hover:bg-white/[0.05] hover:text-white'
                      )}
                    >
                      <item.icon className="w-4 h-4" />
                      {item.label}
                    </Link>
                  )
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>

      {/* Mobile backdrop overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* ── Main Content ─────────────────────────────────── */}
      {/* v1.4 follow-up — smoother route transitions:
          • dropped mode="wait" so exit + enter run in PARALLEL (crossfade)
            instead of sequentially. No more brief blank frame between routes.
          • shaved transition to 200ms; large enough to feel intentional,
            short enough to stop feeling sticky.
          • lighter Y shift (4→2) so the page slide doesn't overpower the
            actual content arrival. */}
      <main className="relative z-10 pt-16 min-h-screen">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8 pb-28">
          <ClusterOfflineBanner />
          <AnimatePresence initial={false}>
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              style={{ willChange: 'opacity, transform' }}
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  )
}

// F1 — icon-only social button. When href is null, show a dimmed "coming
// soon" state with tooltip; otherwise open in a new tab.
function SocialIconLink({
  href,
  label,
  Icon,
}: {
  href: string | null
  label: string
  Icon: React.ComponentType<any>
}) {
  const common =
    'p-2 rounded-xl transition-all flex items-center justify-center'
  if (!href) {
    return (
      <button
        type="button"
        title={label}
        aria-label={label}
        className={cn(
          common,
          'text-[#4a4764] hover:text-[#807d99] hover:bg-white/[0.03] cursor-default',
        )}
      >
        <Icon className="w-4 h-4" />
      </button>
    )
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      title={label}
      aria-label={label}
      className={cn(
        common,
        'text-[#807d99] hover:text-white hover:bg-white/[0.05]',
      )}
    >
      <Icon className="w-4 h-4" />
    </a>
  )
}

// F4 — Cluster status pill. Polls /api/health; swaps pill + broadcasts state
// via window event so the offline banner can subscribe.
function ClusterStatusPill() {
  const [online, setOnline] = React.useState<boolean>(true)
  React.useEffect(() => {
    let cancelled = false
    const ping = async () => {
      try {
        const r = await fetch('/api/health', { cache: 'no-store' })
        if (!cancelled) setOnline(r.ok)
      } catch {
        if (!cancelled) setOnline(false)
      }
    }
    ping()
    const iv = setInterval(ping, 10_000)
    return () => {
      cancelled = true
      clearInterval(iv)
    }
  }, [])
  React.useEffect(() => {
    ;(window as any).__fsClusterOnline = online
    window.dispatchEvent(
      new CustomEvent('fs:cluster', { detail: { online } }),
    )
  }, [online])
  return (
    <div
      className={cn(
        'hidden lg:flex items-center gap-2.5 px-3 py-1.5 rounded-full border transition-colors',
        online
          ? 'bg-[#38d9c4]/[0.06] border-[#38d9c4]/20'
          : 'bg-[#ff5c8a]/10 border-[#ff5c8a]/30',
      )}
    >
      {/* v1.4 polish — radial pulse on the dot rather than a glow throb. */}
      <div
        className={cn(
          'cluster-dot-pulse w-2 h-2 rounded-full',
          online
            ? 'bg-[#38d9c4] text-[#38d9c4]'
            : 'bg-[#ff5c8a] text-[#ff5c8a]',
        )}
        style={{ boxShadow: online ? '0 0 8px rgba(56,217,196,0.7)' : '0 0 8px rgba(255,92,138,0.7)' }}
      />
      <span
        className={cn(
          'text-xs font-mono',
          online ? 'text-[#9ad7cb]' : 'text-[#ff5c8a]',
        )}
      >
        {online ? 'Cluster Active' : 'Cluster Offline'}
      </span>
    </div>
  )
}

function ClusterOfflineBanner() {
  const [online, setOnline] = React.useState<boolean>(
    () => (window as any).__fsClusterOnline !== false,
  )
  React.useEffect(() => {
    const handler = (e: Event) => {
      const ev = e as CustomEvent<{ online: boolean }>
      setOnline(Boolean(ev.detail?.online))
    }
    window.addEventListener('fs:cluster', handler as EventListener)
    return () =>
      window.removeEventListener('fs:cluster', handler as EventListener)
  }, [])
  if (online) return null
  return (
    <div className="mb-4 rounded-2xl border border-[#ff5c8a]/30 bg-[#ff5c8a]/5 px-4 py-3 text-sm text-[#ff5c8a] flex items-center gap-3">
      <div className="w-2 h-2 rounded-full bg-[#ff5c8a] flex-shrink-0 shadow-[0_0_8px_rgba(255,92,138,0.6)]" />
      <span className="font-mono text-xs">
        Backend unreachable. Render disabled — retrying every 10 s.
      </span>
    </div>
  )
}
