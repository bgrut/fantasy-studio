import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Wand2,
  Film,
  BarChart3,
  Layers,
  Store,
  Settings,
  Search,
  Command,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface Action {
  id: string
  label: string
  icon: React.ComponentType<any>
  shortcut?: string
  action: () => void
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const actions: Action[] = [
    { id: 'studio', label: 'Go to Studio', icon: Wand2, shortcut: 'Ctrl+1', action: () => navigate({ to: '/studio' }) },
    { id: 'gallery', label: 'Go to Gallery', icon: Film, shortcut: 'Ctrl+2', action: () => navigate({ to: '/outputs' }) },
    { id: 'insights', label: 'Go to Insights', icon: BarChart3, shortcut: 'Ctrl+3', action: () => navigate({ to: '/insights' }) },
    { id: 'assets', label: 'Go to Assets', icon: Layers, shortcut: 'Ctrl+4', action: () => navigate({ to: '/templates' }) },
    { id: 'marketplace', label: 'Go to Marketplace', icon: Store, action: () => navigate({ to: '/marketplace' }) },
    { id: 'settings', label: 'Go to Settings', icon: Settings, action: () => navigate({ to: '/settings' }) },
    { id: 'focus-prompt', label: 'Focus prompt input', icon: Search, shortcut: 'Ctrl+P', action: () => {
      const el = document.querySelector<HTMLInputElement>('[data-prompt-input]')
      if (el) { el.focus(); el.select() }
    }},
  ]

  const filtered = query
    ? actions.filter((a) => a.label.toLowerCase().includes(query.toLowerCase()))
    : actions

  useEffect(() => {
    setSelected(0)
  }, [query])

  const run = useCallback((action: Action) => {
    setOpen(false)
    setQuery('')
    action.action()
  }, [])

  // Global keyboard handler
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+K — open palette
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((prev) => !prev)
        return
      }

      // Ctrl+P — focus prompt
      if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
        e.preventDefault()
        const el = document.querySelector<HTMLInputElement>('[data-prompt-input]')
        if (el) { el.focus(); el.select() }
        return
      }

      // Ctrl+1-4 — tab switching
      if ((e.ctrlKey || e.metaKey) && e.key >= '1' && e.key <= '4') {
        e.preventDefault()
        const routes = ['/studio', '/outputs', '/insights', '/templates']
        const idx = parseInt(e.key) - 1
        if (routes[idx]) navigate({ to: routes[idx] as any })
        return
      }

      // Escape — close
      if (e.key === 'Escape' && open) {
        setOpen(false)
        setQuery('')
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, navigate])

  // Focus input when opening
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelected((prev) => Math.min(prev + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelected((prev) => Math.max(prev - 1, 0))
    } else if (e.key === 'Enter' && filtered[selected]) {
      e.preventDefault()
      run(filtered[selected])
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[200]"
            onClick={() => { setOpen(false); setQuery('') }}
          />

          {/* Palette */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ type: 'spring', bounce: 0.15, duration: 0.3 }}
            className="fixed top-[20%] left-1/2 -translate-x-1/2 z-[201] w-full max-w-lg"
          >
            <div className="glass rounded-2xl border border-white/[0.08] overflow-hidden shadow-[0_25px_60px_-15px_rgba(124,92,255,0.2)]">
              {/* Search */}
              <div className="flex items-center gap-3 px-4 py-3 border-b border-white/[0.05]">
                <Command className="w-4 h-4 text-[#7c5cff]" />
                <input
                  ref={inputRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type a command..."
                  className="flex-1 bg-transparent text-sm text-white placeholder:text-[#4a4764] focus:outline-none"
                />
                <kbd className="text-[10px] font-mono text-[#4a4764] bg-white/[0.03] border border-white/[0.05] px-1.5 py-0.5 rounded">
                  ESC
                </kbd>
              </div>

              {/* Results */}
              <div className="py-2 max-h-[300px] overflow-y-auto">
                {filtered.length === 0 ? (
                  <div className="px-4 py-6 text-center text-sm text-[#4a4764]">
                    No results
                  </div>
                ) : (
                  filtered.map((action, i) => (
                    <button
                      key={action.id}
                      onClick={() => run(action)}
                      onMouseEnter={() => setSelected(i)}
                      className={cn(
                        'w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors',
                        i === selected
                          ? 'bg-[#7c5cff]/10 text-white'
                          : 'text-[#807d99] hover:bg-white/[0.02]'
                      )}
                    >
                      <action.icon className={cn(
                        'w-4 h-4 flex-shrink-0',
                        i === selected ? 'text-[#7c5cff]' : 'text-[#4a4764]'
                      )} />
                      <span className="flex-1 text-left">{action.label}</span>
                      {action.shortcut && (
                        <kbd className="text-[10px] font-mono text-[#4a4764] bg-white/[0.03] border border-white/[0.05] px-1.5 py-0.5 rounded">
                          {action.shortcut}
                        </kbd>
                      )}
                    </button>
                  ))
                )}
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
