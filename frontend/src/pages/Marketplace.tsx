import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Store,
  Package,
  Upload,
  CheckCircle2,
  AlertCircle,
  Trash2,
  Loader2,
  ShieldCheck,
  Sparkles,
  FileArchive,
  RefreshCw,
  X,
  Star,
  Download,
  Search,
  Crown,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import {
  listTemplatePacks,
  validateTemplatePack,
  installTemplatePack,
  uninstallTemplatePack,
  getCatalog,
  searchCatalog,
  submitTemplate,
  type TemplatePackRecord,
  type PackValidationResponse,
  type PackInstallResponse,
  type CatalogTemplate,
} from '@/lib/api'

type Tab = 'browse' | 'installed' | 'submit'
type WorkingState = 'idle' | 'validating' | 'installing' | 'submitting'

const FAMILY_OPTIONS = [
  { value: '', label: 'All Families' },
  { value: 'street_scene', label: 'Street Scene' },
  { value: 'car_hero', label: 'Car Hero' },
  { value: 'scenic_landscape', label: 'Scenic Landscape' },
  { value: 'ocean_scene', label: 'Ocean Scene' },
  { value: 'character_stage', label: 'Character Stage' },
  { value: 'product_scene', label: 'Product Scene' },
]

export default function Marketplace() {
  const [tab, setTab] = useState<Tab>('browse')

  const [catalog, setCatalog] = useState<CatalogTemplate[]>([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [searchQ, setSearchQ] = useState('')
  const [filterFamily, setFilterFamily] = useState('')
  const [filterPrice, setFilterPrice] = useState<'' | 'free' | 'paid'>('')
  const [sortBy, setSortBy] = useState<'rating' | 'downloads' | 'newest'>('rating')

  const [packs, setPacks] = useState<TemplatePackRecord[]>([])
  const [packsLoading, setPacksLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [validation, setValidation] = useState<PackValidationResponse | null>(null)
  const [installResult, setInstallResult] = useState<PackInstallResponse | null>(null)
  const [working, setWorking] = useState<WorkingState>('idle')
  const [forceInstall, setForceInstall] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true)
    try {
      const params: any = { sort: sortBy }
      if (searchQ) params.q = searchQ
      if (filterFamily) params.family = filterFamily
      if (filterPrice) params.price = filterPrice
      const data = await searchCatalog(params)
      setCatalog(data.templates || [])
    } catch {
      setCatalog([])
    } finally {
      setCatalogLoading(false)
    }
  }, [searchQ, filterFamily, filterPrice, sortBy])

  useEffect(() => { loadCatalog() }, [loadCatalog])

  const refreshPacks = useCallback(async () => {
    setRefreshing(true)
    setError(null)
    try {
      const data = await listTemplatePacks()
      setPacks(data.packs || [])
    } catch (e: any) {
      setError(e?.message || 'Failed to load packs')
    } finally {
      setPacksLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { refreshPacks() }, [refreshPacks])

  const handlePickFile = useCallback((file: File | null) => {
    setSelectedFile(file)
    setValidation(null)
    setInstallResult(null)
  }, [])

  const onDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(true) }, [])
  const onDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(false) }, [])
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handlePickFile(file)
  }, [handlePickFile])

  const runValidate = useCallback(async () => {
    if (!selectedFile) return
    setWorking('validating')
    setInstallResult(null)
    try {
      const result = await validateTemplatePack(selectedFile)
      setValidation(result)
    } catch (e: any) {
      setValidation({ ok: false, errors: [e?.message || 'Validation failed'], warnings: [] })
    } finally {
      setWorking('idle')
    }
  }, [selectedFile])

  const runInstall = useCallback(async () => {
    if (!selectedFile) return
    setWorking('installing')
    try {
      const result = await installTemplatePack(selectedFile, forceInstall)
      setInstallResult(result)
      if (result.ok) {
        await refreshPacks()
        setSelectedFile(null); setValidation(null)
        if (fileInputRef.current) fileInputRef.current.value = ''
      }
    } catch (e: any) {
      setInstallResult({ ok: false, error: e?.message || 'Install failed', warnings: [] })
    } finally {
      setWorking('idle')
    }
  }, [selectedFile, forceInstall, refreshPacks])

  const runUninstall = useCallback(async (packId: string) => {
    if (!window.confirm(`Uninstall "${packId}"?`)) return
    try {
      await uninstallTemplatePack(packId)
      await refreshPacks()
    } catch (e: any) {
      setError(e?.message || 'Uninstall failed')
    }
  }, [refreshPacks])

  const runSubmit = useCallback(async () => {
    if (!selectedFile) return
    setWorking('submitting')
    try {
      await submitTemplate(selectedFile)
      setInstallResult({ ok: true, warnings: [], pack_id: selectedFile.name, error: null })
      setSelectedFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (e: any) {
      setInstallResult({ ok: false, error: e?.message || 'Submit failed', warnings: [] })
    } finally {
      setWorking('idle')
    }
  }, [selectedFile])

  const installedIds = useMemo(() => new Set(packs.map(p => p.pack_id)), [packs])

  const stats = useMemo(() => ({
    catalogCount: catalog.length,
    installedCount: packs.length,
    freeCount: catalog.filter(t => t.price.toLowerCase() === 'free').length,
  }), [catalog, packs])

  return (
    <div className="space-y-8 animate-reveal">
      {/* Header */}
      <div className="space-y-3">
        <span className="section-tag section-tag--pink font-mono text-xs">// marketplace</span>
        <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-gradient">
          Template Marketplace
        </h1>
        <p className="text-[#807d99] max-w-xl">
          Browse community templates, install packs, and submit your own creations.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard icon={<Store className="w-5 h-5" />} value={stats.catalogCount} label="In Catalog" color="#7c5cff" />
        <StatCard icon={<Package className="w-5 h-5" />} value={stats.installedCount} label="Installed" color="#ff5c8a" />
        <StatCard icon={<Sparkles className="w-5 h-5" />} value={stats.freeCount} label="Free Packs" color="#38d9c4" />
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 p-1 rounded-2xl bg-white/[0.03] border border-white/[0.05] w-fit">
        {([['browse', 'Browse', Store], ['installed', 'Installed', Package], ['submit', 'Submit', Upload]] as [Tab, string, any][]).map(
          ([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
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

      {/* Browse tab */}
      {tab === 'browse' && (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#4a4764]" />
              <input
                value={searchQ}
                onChange={e => setSearchQ(e.target.value)}
                placeholder="Search templates..."
                className="w-full rounded-xl bg-white/[0.03] border border-white/[0.05] pl-10 pr-4 py-2.5 text-sm text-white placeholder:text-[#4a4764] focus:outline-none focus:border-[#7c5cff]/40 transition-colors"
              />
            </div>
            <select value={filterFamily} onChange={e => setFilterFamily(e.target.value)}
              className="rounded-xl bg-white/[0.03] border border-white/[0.05] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#7c5cff]/40">
              {FAMILY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <select value={filterPrice} onChange={e => setFilterPrice(e.target.value as any)}
              className="rounded-xl bg-white/[0.03] border border-white/[0.05] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#7c5cff]/40">
              <option value="">All Prices</option>
              <option value="free">Free</option>
              <option value="paid">Paid</option>
            </select>
            <select value={sortBy} onChange={e => setSortBy(e.target.value as any)}
              className="rounded-xl bg-white/[0.03] border border-white/[0.05] px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[#7c5cff]/40">
              <option value="rating">Top Rated</option>
              <option value="downloads">Most Downloads</option>
              <option value="newest">Newest</option>
            </select>
          </div>

          {catalogLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-[#7c5cff]" />
            </div>
          ) : catalog.length === 0 ? (
            <div className="glass rounded-2xl py-16 text-center">
              <p className="text-sm text-[#4a4764] font-mono">No templates match your filters.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5 stagger-reveal">
              {catalog.map(t => (
                <CatalogCard key={t.pack_id} template={t} isInstalled={installedIds.has(t.pack_id)} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Installed tab */}
      {tab === 'installed' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white">Installed Packs</h2>
            <Button onClick={refreshPacks} disabled={refreshing}
              className="rounded-xl bg-white/[0.03] border border-white/[0.05] text-[#807d99] hover:text-white hover:bg-white/[0.05] text-sm">
              {refreshing ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1.5" />}
              Refresh
            </Button>
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-400">
              <AlertCircle className="w-4 h-4" /> {error}
            </div>
          )}

          {packsLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-[#7c5cff]" />
            </div>
          ) : packs.length === 0 ? (
            <div className="glass rounded-2xl py-16 text-center">
              <Package className="w-8 h-8 text-[#4a4764] mx-auto mb-3" />
              <p className="text-sm text-[#4a4764]">No packs installed yet.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {packs.map(pack => (
                <InstalledPackCard key={pack.pack_id} pack={pack} onUninstall={() => runUninstall(pack.pack_id)} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Submit tab */}
      {tab === 'submit' && (
        <div className="space-y-6">
          <div className="glass rounded-2xl p-6 space-y-5">
            <div className="flex items-center gap-2 mb-1">
              <Upload className="w-4 h-4 text-[#7c5cff]" />
              <span className="text-sm font-semibold">Upload Template Pack</span>
            </div>
            <p className="text-xs font-mono text-[#4a4764]">// drop a .zip pack to validate + install</p>

            <div
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                'flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 cursor-pointer transition-all',
                isDragging ? 'border-[#7c5cff]/60 bg-[#7c5cff]/5' : 'border-white/[0.08] bg-white/[0.02] hover:border-[#7c5cff]/30',
              )}
            >
              <input ref={fileInputRef} type="file" accept=".zip" className="hidden" onChange={e => handlePickFile(e.target.files?.[0] ?? null)} />
              <FileArchive className={cn('w-8 h-8', isDragging ? 'text-[#7c5cff]' : 'text-[#4a4764]')} />
              {selectedFile ? (
                <div className="text-center">
                  <p className="text-sm font-semibold text-white">{selectedFile.name}</p>
                  <p className="text-xs font-mono text-[#4a4764]">{(selectedFile.size / 1024).toFixed(1)} KB</p>
                </div>
              ) : (
                <p className="text-sm text-[#807d99]">Drop .zip here or click to browse</p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={runValidate} disabled={!selectedFile || working !== 'idle'}
                className="rounded-xl bg-white/[0.03] border border-white/[0.05] text-[#807d99] hover:text-white text-sm">
                {working === 'validating' ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <ShieldCheck className="w-4 h-4 mr-1.5" />}
                Validate
              </Button>
              <Button onClick={runInstall} disabled={!selectedFile || working !== 'idle'}
                className="rounded-xl btn-generate text-sm">
                {working === 'installing' ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Download className="w-4 h-4 mr-1.5" />}
                Install
              </Button>
              <Button onClick={runSubmit} disabled={!selectedFile || working !== 'idle'}
                className="rounded-xl bg-[#ff5c8a]/10 border border-[#ff5c8a]/20 text-[#ff5c8a] hover:bg-[#ff5c8a]/20 text-sm">
                {working === 'submitting' ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Upload className="w-4 h-4 mr-1.5" />}
                Submit
              </Button>
              <label className="flex items-center gap-2 text-xs font-mono text-[#4a4764] cursor-pointer">
                <input type="checkbox" checked={forceInstall} onChange={e => setForceInstall(e.target.checked)} className="accent-[#7c5cff]" />
                Force overwrite
              </label>
              {selectedFile && (
                <button onClick={() => { handlePickFile(null); if (fileInputRef.current) fileInputRef.current.value = '' }}
                  className="ml-auto text-[#807d99] hover:text-white text-xs font-mono flex items-center gap-1">
                  <X className="w-3 h-3" /> Clear
                </button>
              )}
            </div>

            {validation && <ValidationPanel validation={validation} />}
            {installResult && <InstallPanel result={installResult} />}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon, value, label, color }: { icon: React.ReactNode; value: number | string; label: string; color: string }) {
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

function CatalogCard({ template: t, isInstalled }: { template: CatalogTemplate; isInstalled: boolean }) {
  const isFree = t.price.toLowerCase() === 'free'
  return (
    <div className="glass rounded-2xl overflow-hidden card-hover flex flex-col group">
      <div className="aspect-video bg-gradient-to-br from-white/[0.03] to-white/[0.01] flex items-center justify-center relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-t from-[#050508]/60 to-transparent" />
        <Package className="w-10 h-10 text-[#4a4764]/30" />
        <div className="absolute top-3 right-3">
          <Badge className={cn(
            'text-[10px] font-mono rounded-lg px-2.5 py-0.5',
            isFree ? 'bg-[#38d9c4]/20 text-[#38d9c4] border-[#38d9c4]/20' : 'bg-[#ffc857]/20 text-[#ffc857] border-[#ffc857]/20'
          )}>
            {t.price}
          </Badge>
        </div>
        {isInstalled && (
          <div className="absolute top-3 left-3">
            <Badge className="bg-[#7c5cff]/20 text-[#a78bfa] border-[#7c5cff]/20 text-[10px] font-mono rounded-lg px-2.5 py-0.5">
              Installed
            </Badge>
          </div>
        )}
        <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between">
          <div className="flex items-center gap-1 text-[#ffc857]">
            <Star className="w-3 h-3 fill-[#ffc857]" />
            <span className="text-xs font-mono">{t.rating}</span>
          </div>
          <div className="flex items-center gap-1 text-[#807d99]">
            <Download className="w-3 h-3" />
            <span className="text-xs font-mono">{t.downloads.toLocaleString()}</span>
          </div>
        </div>
      </div>

      <div className="p-4 flex-1 flex flex-col gap-2">
        <div>
          <h3 className="text-sm font-bold text-white">{t.name}</h3>
          <p className="text-xs font-mono text-[#4a4764]">by {t.author} v{t.version}</p>
        </div>
        <p className="text-xs text-[#807d99] line-clamp-2 flex-1">{t.description}</p>
        <div className="flex flex-wrap gap-1.5">
          <Badge className="bg-white/[0.03] border-white/[0.05] text-[#807d99] text-[10px] font-mono rounded-lg px-2 py-0.5">
            {t.scene_family}
          </Badge>
          {t.tags.slice(0, 2).map(tag => (
            <Badge key={tag} className="bg-white/[0.03] border-white/[0.05] text-[#807d99] text-[10px] font-mono rounded-lg px-2 py-0.5">
              {tag}
            </Badge>
          ))}
        </div>
      </div>

      <div className="px-4 pb-4">
        {isFree && t.bundled ? (
          <button disabled={isInstalled}
            className={cn('w-full py-2.5 rounded-xl text-sm font-semibold transition-all', isInstalled ? 'bg-white/[0.03] text-[#4a4764]' : 'btn-generate')}>
            {isInstalled ? 'Installed' : 'Install'}
          </button>
        ) : !isFree ? (
          <button disabled className="w-full py-2.5 rounded-xl text-sm font-semibold bg-[#ffc857]/10 text-[#ffc857] border border-[#ffc857]/20 opacity-60">
            <Crown className="w-3.5 h-3.5 inline mr-1.5" />
            Coming Soon
          </button>
        ) : (
          <button className="w-full py-2.5 rounded-xl text-sm font-semibold bg-white/[0.03] border border-white/[0.05] text-[#807d99] hover:text-white hover:bg-white/[0.05] transition-all">
            Install
          </button>
        )}
      </div>
    </div>
  )
}

function InstalledPackCard({ pack, onUninstall }: { pack: TemplatePackRecord; onUninstall: () => void }) {
  const isBuiltIn = !pack.install_path || pack.install_path.includes('built')
  return (
    <div className="glass rounded-2xl overflow-hidden card-hover flex flex-col">
      <div className="p-5 flex-1 space-y-3">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#7c5cff]/10 flex items-center justify-center text-[#7c5cff]">
            <Package className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold text-white truncate">{pack.name || pack.pack_id}</h3>
            <p className="text-xs font-mono text-[#4a4764]">v{pack.version || '0.0.0'} {pack.author || ''}</p>
          </div>
          <Badge className={cn(
            'text-[10px] font-mono rounded-lg px-2 py-0.5',
            isBuiltIn ? 'bg-[#ff5c8a]/10 text-[#ff5c8a] border-[#ff5c8a]/20' : 'bg-[#7c5cff]/10 text-[#a78bfa] border-[#7c5cff]/20'
          )}>
            {isBuiltIn ? 'Built-in' : 'Community'}
          </Badge>
        </div>
        {pack.manifest?.description && (
          <p className="text-xs text-[#807d99] line-clamp-2">{pack.manifest.description}</p>
        )}
        <div className="flex flex-wrap gap-1.5">
          {pack.scene_family && (
            <Badge className="bg-white/[0.03] border-white/[0.05] text-[#807d99] text-[10px] font-mono rounded-lg px-2 py-0.5">
              {pack.scene_family}
            </Badge>
          )}
        </div>
      </div>
      <div className="px-5 py-3 border-t border-white/[0.05]">
        <button onClick={onUninstall}
          className="w-full py-2 rounded-xl text-xs font-medium text-[#807d99] hover:text-red-400 hover:bg-red-400/5 transition-all flex items-center justify-center gap-1.5">
          <Trash2 className="w-3.5 h-3.5" /> Uninstall
        </button>
      </div>
    </div>
  )
}

function ValidationPanel({ validation }: { validation: PackValidationResponse }) {
  return (
    <div className={cn('rounded-xl border p-4 space-y-2', validation.ok ? 'border-[#38d9c4]/30 bg-[#38d9c4]/5' : 'border-red-500/30 bg-red-500/5')}>
      <div className="flex items-center gap-2">
        {validation.ok ? <CheckCircle2 className="w-4 h-4 text-[#38d9c4]" /> : <AlertCircle className="w-4 h-4 text-red-400" />}
        <span className={cn('text-sm font-semibold', validation.ok ? 'text-[#38d9c4]' : 'text-red-400')}>
          {validation.ok ? 'Passed' : 'Failed'}
        </span>
        {validation.pack_id && <Badge className="ml-auto bg-white/[0.03] border-white/[0.05] text-[#807d99] text-xs rounded-lg">{validation.pack_id}</Badge>}
      </div>
      {validation.errors?.length > 0 && (
        <ul className="text-xs text-red-400 space-y-1">{validation.errors.map((e, i) => <li key={i}>- {e}</li>)}</ul>
      )}
      {validation.warnings?.length > 0 && (
        <ul className="text-xs text-[#ffc857] space-y-1">{validation.warnings.map((w, i) => <li key={i}>- {w}</li>)}</ul>
      )}
    </div>
  )
}

function InstallPanel({ result }: { result: PackInstallResponse }) {
  return (
    <div className={cn('rounded-xl border p-4', result.ok ? 'border-[#7c5cff]/30 bg-[#7c5cff]/5' : 'border-red-500/30 bg-red-500/5')}>
      <div className="flex items-center gap-2">
        {result.ok ? <CheckCircle2 className="w-4 h-4 text-[#7c5cff]" /> : <AlertCircle className="w-4 h-4 text-red-400" />}
        <span className={cn('text-sm font-semibold', result.ok ? 'text-[#a78bfa]' : 'text-red-400')}>
          {result.ok ? `Installed ${result.pack_id || ''}` : 'Failed'}
        </span>
      </div>
      {result.error && <p className="text-xs text-red-400 mt-1">{result.error}</p>}
    </div>
  )
}
