import React, { useEffect, useState } from 'react'
import {
  Save,
  Terminal,
  FolderOpen,
  Cpu,
  AlertCircle,
  RefreshCcw,
  Monitor,
  Film,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { toast } from 'react-hot-toast'
import { getSettings, saveSettings } from '@/lib/api'

type BackendSettings = {
  blender_executable_path: string
  ffmpeg_executable_path: string
  local_render_mode: boolean
}

export default function Settings() {
  const [settings, setSettings] = useState<BackendSettings>({
    blender_executable_path: '',
    ffmpeg_executable_path: '',
    local_render_mode: true,
  })
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)

  const fetchSettings = async () => {
    setIsLoading(true)
    try {
      const data = await getSettings()
      setSettings({
        blender_executable_path: data.blender_executable_path || '',
        ffmpeg_executable_path: data.ffmpeg_executable_path || '',
        local_render_mode: !!data.local_render_mode,
      })
    } catch (error) {
      toast.error('Failed to load settings')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => { fetchSettings() }, [])

  const saveAll = async () => {
    setIsSaving(true)
    try {
      await saveSettings(settings)
      toast.success('Settings saved')
      await fetchSettings()
    } catch (error) {
      toast.error('Failed to save settings')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-3">
          <Loader2 className="w-6 h-6 animate-spin text-[#7c5cff] mx-auto" />
          <p className="text-sm font-mono text-[#4a4764]">Loading settings...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8 animate-reveal">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="space-y-3">
          <span className="section-tag section-tag--teal font-mono text-xs">// settings</span>
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-gradient">System Preferences</h1>
          <p className="text-[#807d99] max-w-xl">
            Configure Blender paths, FFmpeg, and render mode.
          </p>
        </div>
        <button onClick={saveAll} disabled={isSaving}
          className="btn-generate px-6 py-3 rounded-xl font-semibold text-sm flex items-center gap-2 disabled:opacity-50">
          {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Save Settings
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main settings */}
        <div className="lg:col-span-2 space-y-6">
          {/* Render mode */}
          <div className="glass rounded-2xl p-6 card-hover">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl bg-[#7c5cff]/10 flex items-center justify-center">
                <Cpu className="w-5 h-5 text-[#7c5cff]" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">Render Engine</h2>
                <p className="text-xs font-mono text-[#4a4764]">// runtime configuration</p>
              </div>
            </div>

            <div className="flex items-center justify-between p-4 rounded-xl bg-white/[0.02] border border-white/[0.05]">
              <div>
                <p className="text-sm font-semibold text-white">Local Render Mode</p>
                <p className="text-xs text-[#807d99] mt-1">Use local Blender CLI instead of mock provider</p>
              </div>
              <Switch
                checked={settings.local_render_mode}
                onCheckedChange={(checked) => setSettings((prev) => ({ ...prev, local_render_mode: checked }))}
              />
            </div>
          </div>

          {/* Paths */}
          <div className="glass rounded-2xl p-6 card-hover">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl bg-[#ff5c8a]/10 flex items-center justify-center">
                <FolderOpen className="w-5 h-5 text-[#ff5c8a]" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">Binary Paths</h2>
                <p className="text-xs font-mono text-[#4a4764]">// executable locations</p>
              </div>
            </div>

            <div className="space-y-5">
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-xs font-mono text-[#4a4764]">
                  <Terminal className="w-3.5 h-3.5" /> Blender Executable
                </label>
                <input
                  value={settings.blender_executable_path}
                  onChange={(e) => setSettings((prev) => ({ ...prev, blender_executable_path: e.target.value }))}
                  placeholder="C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
                  className="w-full rounded-xl bg-white/[0.03] border border-white/[0.05] px-4 py-3 text-sm text-white font-mono placeholder:text-[#4a4764] focus:outline-none focus:border-[#7c5cff]/40 transition-colors"
                />
              </div>

              <div className="space-y-2">
                <label className="flex items-center gap-2 text-xs font-mono text-[#4a4764]">
                  <Film className="w-3.5 h-3.5" /> FFmpeg Executable
                </label>
                <input
                  value={settings.ffmpeg_executable_path}
                  onChange={(e) => setSettings((prev) => ({ ...prev, ffmpeg_executable_path: e.target.value }))}
                  placeholder="C:\Path\To\ffmpeg.exe"
                  className="w-full rounded-xl bg-white/[0.03] border border-white/[0.05] px-4 py-3 text-sm text-white font-mono placeholder:text-[#4a4764] focus:outline-none focus:border-[#7c5cff]/40 transition-colors"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Status sidebar */}
        <div className="space-y-6">
          <div className="glass rounded-2xl p-6 card-hover">
            <div className="flex items-center gap-2 mb-5">
              <Monitor className="w-4 h-4 text-[#38d9c4]" />
              <span className="text-sm font-semibold">System Status</span>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-[#4a4764]">Health</span>
                <Badge className="bg-[#38d9c4]/10 text-[#38d9c4] border-[#38d9c4]/20 text-xs rounded-lg">OK</Badge>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-[#4a4764]">Mode</span>
                <span className="text-sm font-semibold text-white">{settings.local_render_mode ? 'Local CLI' : 'Simulated'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-[#4a4764]">Latency</span>
                <span className="text-sm font-semibold text-white">128ms</span>
              </div>

              <div className="pt-4 border-t border-white/[0.05]">
                <div className="flex items-center gap-2">
                  <div className="pulse-dot" />
                  <span className="text-xs font-mono text-white">
                    {settings.local_render_mode ? 'Ready' : 'Offline'}
                  </span>
                </div>
              </div>
            </div>

            <button onClick={fetchSettings}
              className="mt-4 w-full py-2.5 rounded-xl text-xs font-medium text-[#807d99] hover:text-white hover:bg-white/[0.05] transition-all border border-white/[0.05] flex items-center justify-center gap-1.5">
              <RefreshCcw className="w-3.5 h-3.5" /> Refresh
            </button>
          </div>

          <div className="glass rounded-2xl p-5 border-[#ffc857]/10 bg-[#ffc857]/[0.02]">
            <div className="flex gap-3">
              <AlertCircle className="w-5 h-5 text-[#ffc857] flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-[#ffc857] mb-1">Note</p>
                <p className="text-xs text-[#807d99] leading-relaxed">
                  Ensure Blender and FFmpeg are accessible to the backend service account.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
