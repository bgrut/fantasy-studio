import React, { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const STORAGE_KEY = 'fantasy-studio-onboarded'

export default function Onboarding() {
  const [show, setShow] = useState(false)
  const [phase, setPhase] = useState(0)

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return
    setShow(true)

    const timers = [
      setTimeout(() => setPhase(1), 400),
      setTimeout(() => setPhase(2), 1200),
      setTimeout(() => setPhase(3), 2000),
      setTimeout(() => {
        setShow(false)
        localStorage.setItem(STORAGE_KEY, '1')
      }, 3200),
    ]
    return () => timers.forEach(clearTimeout)
  }, [])

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.6 }}
          className="fixed inset-0 z-[300] bg-[#050508] flex items-center justify-center"
        >
          <div className="text-center space-y-6">
            {/* Spinning cube — grows in */}
            <motion.div
              initial={{ scale: 0, rotate: -180 }}
              animate={{ scale: phase >= 0 ? 1 : 0, rotate: 0 }}
              transition={{ type: 'spring', bounce: 0.3, duration: 0.8 }}
              className="mx-auto"
            >
              <div className="spinning-cube mx-auto" style={{ width: 48, height: 48, borderWidth: 3 }} />
            </motion.div>

            {/* Title */}
            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: phase >= 1 ? 1 : 0, y: phase >= 1 ? 0 : 20 }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
              className="text-4xl md:text-5xl font-bold tracking-tight text-gradient"
            >
              Fantasy Studio
            </motion.h1>

            {/* Subtitle */}
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: phase >= 2 ? 1 : 0 }}
              transition={{ duration: 0.4 }}
              className="text-sm font-mono text-[#807d99]"
            >
              // prompt to cinematic video
            </motion.p>

            {/* Prompt hint */}
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: phase >= 3 ? 1 : 0, y: phase >= 3 ? 0 : 30 }}
              transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
              className="inline-block"
            >
              <div className="glass rounded-2xl px-8 py-3 border border-[#7c5cff]/20">
                <span className="text-sm text-[#4a4764]">Type a prompt to get started...</span>
              </div>
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
