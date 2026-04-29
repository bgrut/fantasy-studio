import React, { createContext, useCallback, useContext, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle2, XCircle, Download, RefreshCw, X } from 'lucide-react'
import { cn } from '@/lib/utils'

type ToastType = 'success' | 'error' | 'info' | 'warning'

interface Toast {
  id: string
  type: ToastType
  message: string
}

interface ToastContextValue {
  addToast: (type: ToastType, message: string) => void
}

const ToastContext = createContext<ToastContextValue>({ addToast: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

const ICONS: Record<ToastType, React.ComponentType<any>> = {
  success: CheckCircle2,
  error: XCircle,
  info: Download,
  warning: RefreshCw,
}

const COLORS: Record<ToastType, { border: string; icon: string; bg: string }> = {
  success: { border: 'border-l-[#38d9c4]', icon: 'text-[#38d9c4]', bg: 'bg-[#38d9c4]/5' },
  error: { border: 'border-l-[#ff5c8a]', icon: 'text-[#ff5c8a]', bg: 'bg-[#ff5c8a]/5' },
  info: { border: 'border-l-[#7c5cff]', icon: 'text-[#7c5cff]', bg: 'bg-[#7c5cff]/5' },
  warning: { border: 'border-l-[#ffc857]', icon: 'text-[#ffc857]', bg: 'bg-[#ffc857]/5' },
}

let _nextId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((type: ToastType, message: string) => {
    const id = `toast-${++_nextId}`
    setToasts((prev) => [...prev.slice(-4), { id, type, message }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 5000)
  }, [])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="fixed top-20 right-4 z-[100] flex flex-col gap-2 pointer-events-none max-w-sm w-full">
        <AnimatePresence>
          {toasts.map((toast) => {
            const Icon = ICONS[toast.type]
            const colors = COLORS[toast.type]
            return (
              <motion.div
                key={toast.id}
                initial={{ opacity: 0, x: 80, scale: 0.95 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 80, scale: 0.95 }}
                transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
                className={cn(
                  'pointer-events-auto glass rounded-xl border-l-[3px] px-4 py-3 flex items-start gap-3',
                  colors.border, colors.bg
                )}
              >
                <Icon className={cn('w-4 h-4 mt-0.5 flex-shrink-0', colors.icon)} />
                <p className="text-sm text-white flex-1 leading-snug">{toast.message}</p>
                <button
                  onClick={() => dismiss(toast.id)}
                  className="text-[#4a4764] hover:text-white transition-colors flex-shrink-0"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}
