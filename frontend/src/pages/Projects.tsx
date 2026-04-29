import React, { useEffect, useState } from 'react'
import { 
  Search, 
  Filter, 
  Plus, 
  MoreVertical, 
  Play, 
  Clock, 
  CheckCircle2, 
  XCircle,
  Eye,
  Trash2,
  Calendar,
  Grid,
  List as ListIcon,
  Library,
  ChevronRight
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu'
import { blink } from '@/blink/client'
import { Link } from '@tanstack/react-router'
import { formatDistanceToNow } from 'date-fns'
import { cn } from '@/lib/utils'

export default function Projects() {
  const [projects, setProjects] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [view, setView] = useState<'grid' | 'list'>('grid')

  const fetchProjects = async () => {
    try {
      const data = await blink.db.projects.list({
        orderBy: { createdAt: 'desc' }
      })
      setProjects(data)
    } catch (error) {
      console.error('Failed to fetch projects:', error)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchProjects()
  }, [])

  const filteredProjects = projects.filter(p => 
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.selectedTemplate?.toLowerCase().includes(search.toLowerCase())
  )

  const deleteProject = async (id: string) => {
    if (!confirm('Are you sure you want to delete this project?')) return
    try {
      await blink.db.projects.delete(id)
      setProjects(prev => prev.filter(p => p.id !== id))
    } catch (error) {
      console.error('Failed to delete project:', error)
    }
  }

  if (isLoading) return <div className="p-8 text-center text-muted-foreground animate-pulse font-display uppercase tracking-widest">Scanning Storage...</div>

  return (
    <div className="space-y-10 animate-reveal">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
        <div className="space-y-3">
          <Badge variant="outline" className="bg-primary/10 text-primary border-primary/20 uppercase tracking-[0.3em] font-bold text-[9px] px-3 py-1">
            Production Archives
          </Badge>
          <h1 className="text-5xl font-display font-bold tracking-tight text-gradient">Manifest Grid</h1>
          <p className="text-muted-foreground text-lg max-w-2xl leading-relaxed">
            Access and manage the complete history of Blender Lane production manifests, scene geometry, and delivered artifacts.
          </p>
        </div>
        <Button asChild size="lg" className="neon-glow-primary bg-primary text-white h-16 px-10 rounded-[20px] font-bold transition-all hover:scale-105 active:scale-95 shadow-2xl group">
          <Link to="/create">
            <Plus className="w-6 h-6 mr-3 group-hover:rotate-90 transition-transform duration-500" /> Initialize Manifest
          </Link>
        </Button>
      </div>

      <div className="flex flex-col md:flex-row gap-6 items-center justify-between p-3 rounded-[28px] glass-dark border border-white/5 bg-white/[0.01] shadow-inner">
        <div className="relative w-full md:w-[450px] group ml-3">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-muted-foreground group-focus-within:text-primary transition-all duration-300" />
          <Input 
            placeholder="Search manifests, templates, or operator IDs..." 
            className="pl-14 bg-transparent border-none focus:ring-0 h-14 text-white placeholder:text-muted-foreground/40 font-bold text-base"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-4 px-3">
          <div className="flex items-center gap-1.5 bg-white/5 p-1.5 rounded-[18px] border border-white/5 shadow-inner">
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => setView('grid')}
              className={cn("h-11 w-11 p-0 rounded-xl transition-all duration-500", view === 'grid' ? "bg-primary text-white shadow-[0_0_20px_hsla(var(--primary)/0.4)]" : "text-muted-foreground hover:text-white hover:bg-white/5")}
            >
              <Grid className="w-5 h-5" />
            </Button>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => setView('list')}
              className={cn("h-11 w-11 p-0 rounded-xl transition-all duration-500", view === 'list' ? "bg-primary text-white shadow-[0_0_20px_hsla(var(--primary)/0.4)]" : "text-muted-foreground hover:text-white hover:bg-white/5")}
            >
              <ListIcon className="w-5 h-5" />
            </Button>
          </div>
          <div className="w-px h-10 bg-white/10 mx-1" />
          <Button variant="outline" size="sm" className="glass h-14 px-8 rounded-[18px] font-bold uppercase tracking-[0.2em] text-[10px] text-muted-foreground hover:text-white transition-all hover:border-primary/30">
            <Filter className="w-4 h-4 mr-3" /> Refine Pipeline
          </Button>
        </div>
      </div>

      {filteredProjects.length === 0 ? (
        <Card className="glass border-dashed border-2 border-white/5 py-40 rounded-[48px] overflow-hidden relative group shadow-2xl">
          <div className="absolute inset-0 bg-primary/[0.02] group-hover:bg-primary/[0.04] transition-colors duration-1000" />
          <CardContent className="flex flex-col items-center justify-center text-center space-y-10 relative z-10">
            <div className="w-32 h-32 rounded-[40px] bg-white/5 flex items-center justify-center border border-white/5 group-hover:scale-110 group-hover:rotate-12 transition-all duration-1000 shadow-[0_20px_50px_rgba(0,0,0,0.5)]">
              <Library className="w-12 h-12 text-primary opacity-20 group-hover:opacity-60 transition-opacity" />
            </div>
            <div className="space-y-4">
              <h3 className="text-4xl font-display font-bold text-white tracking-tight">Archives Offline</h3>
              <p className="text-muted-foreground max-w-md mx-auto text-lg leading-relaxed font-medium">
                No production manifests detected in the current cluster nodes. Initialize an engine cycle to start indexing metadata.
              </p>
            </div>
            <Button asChild size="lg" className="neon-glow-primary bg-primary text-white h-20 px-12 rounded-[24px] font-bold transition-all hover:scale-105 active:scale-95 shadow-2xl text-lg">
              <Link to="/create">Initiate Primary Sequence</Link>
            </Button>
          </CardContent>
        </Card>
      ) : view === 'grid' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
          {filteredProjects.map((project) => (
            <Card key={project.id} className="glass group overflow-hidden border-white/5 hover:border-primary/40 transition-all duration-700 rounded-[40px] hover:shadow-[0_40px_80px_-20px_hsla(var(--primary)/0.3)] flex flex-col">
              <Link to={`/projects/${project.id}`} className="relative block aspect-[16/9] overflow-hidden bg-secondary/50 border-b border-white/5">
                <img 
                  src={`https://images.unsplash.com/photo-1620641788421-7a1c342ea42e?w=800&q=80`} 
                  alt={project.name}
                  className="w-full h-full object-cover opacity-40 group-hover:opacity-100 group-hover:scale-110 transition-all duration-1000 ease-in-out"
                />
                <div className="absolute top-6 right-6 z-10">
                  <StatusBadge status={project.status} />
                </div>
                <div className="absolute inset-0 bg-gradient-to-t from-black via-black/20 to-transparent opacity-90 group-hover:opacity-40 transition-opacity duration-700" />
                <div className="absolute bottom-6 left-6 z-10">
                  <Badge variant="outline" className="bg-primary/20 text-primary border-primary/30 text-[9px] uppercase font-bold tracking-[0.2em] px-4 py-1.5 rounded-xl backdrop-blur-xl shadow-lg">
                    {project.selectedTemplate || 'DYNAMIC_LANE'}
                  </Badge>
                </div>
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-700 bg-primary/10 backdrop-blur-[2px]">
                  <div className="w-20 h-20 rounded-full bg-primary flex items-center justify-center text-white shadow-[0_0_40px_hsla(var(--primary)/0.6)] scale-75 group-hover:scale-100 transition-all duration-500 ease-[0.16, 1, 0.3, 1]">
                    <Play className="w-8 h-8 fill-white ml-1" />
                  </div>
                </div>
              </Link>
              <CardContent className="p-10 space-y-6 flex-1">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 space-y-2">
                    <h3 className="font-display font-bold text-3xl text-white truncate tracking-tight group-hover:text-primary transition-colors duration-500 uppercase">{project.name}</h3>
                    <div className="flex items-center gap-4 text-[10px] font-bold text-muted-foreground/60 uppercase tracking-[0.2em]">
                      <Calendar className="w-4 h-4 text-primary" />
                      <span>{formatDistanceToNow(new Date(project.createdAt))} ago</span>
                    </div>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-12 w-12 rounded-2xl text-muted-foreground hover:text-white hover:bg-white/5 transition-all">
                        <MoreVertical className="w-6 h-6" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="glass-dark border-white/10 bg-[#020617] rounded-2xl overflow-hidden p-1.5 min-w-[220px] shadow-2xl">
                      <DropdownMenuItem asChild className="rounded-xl my-1 cursor-pointer hover:bg-primary/10 hover:text-primary focus:bg-primary/10 focus:text-primary transition-all">
                        <Link to={`/projects/${project.id}`} className="flex items-center px-4 py-3">
                          <Eye className="w-5 h-5 mr-4" /> 
                          <span className="font-bold text-[10px] uppercase tracking-[0.2em]">Intercept Logic</span>
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem className="rounded-xl my-1 cursor-pointer text-destructive focus:bg-destructive/10 transition-all" onClick={() => deleteProject(project.id)}>
                        <div className="flex items-center px-4 py-3 w-full">
                          <Trash2 className="w-5 h-5 mr-4" /> 
                          <span className="font-bold text-[10px] uppercase tracking-[0.2em]">Purge Data</span>
                        </div>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <p className="text-base text-muted-foreground/80 line-clamp-2 leading-relaxed font-medium min-h-[48px]">
                  {project.manualTopic || 'No data stream provided for this production manifest.'}
                </p>
              </CardContent>
              <CardFooter className="px-10 py-8 border-t border-white/5 bg-white/[0.01]">
                <div className="flex items-center justify-between w-full">
                  <div className="flex -space-x-4">
                    {[1, 2, 3].map(i => (
                      <div key={i} className="w-10 h-10 rounded-2xl border-4 border-background bg-secondary flex items-center justify-center text-[10px] font-bold shadow-2xl overflow-hidden group/avatar">
                        <img src={`https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=100&h=100&fit=crop&q=80`} alt="asset" className="w-full h-full object-cover opacity-40 group-hover/avatar:opacity-100 transition-opacity duration-500" />
                      </div>
                    ))}
                    <div className="w-10 h-10 rounded-2xl border-4 border-background bg-white/5 backdrop-blur-xl flex items-center justify-center text-[10px] font-bold text-primary shadow-2xl">
                      +4
                    </div>
                  </div>
                  <Button variant="ghost" size="sm" className="h-12 px-6 rounded-xl text-[11px] font-bold uppercase tracking-[0.2em] text-primary hover:bg-primary/10 group/btn transition-all" asChild>
                    <Link to={`/projects/${project.id}`}>
                      Production Spec 
                      <ChevronRight className="ml-3 w-5 h-5 group-hover/btn:translate-x-2 transition-transform duration-500" />
                    </Link>
                  </Button>
                </div>
              </CardFooter>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="glass border-white/5 overflow-hidden">
          <div className="divide-y divide-white/5">
            {filteredProjects.map((project) => (
              <div key={project.id} className="flex items-center gap-4 p-4 hover:bg-white/5 transition-colors group">
                <div className="w-16 h-10 rounded bg-secondary overflow-hidden shrink-0 border border-white/5">
                  <img 
                    src={`https://images.unsplash.com/photo-1620641788421-7a1c342ea42e?w=200&h=150&fit=crop`} 
                    alt={project.name}
                    className="w-full h-full object-cover opacity-60"
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h4 className="font-semibold truncate group-hover:text-primary transition-colors">{project.name}</h4>
                    <StatusBadge status={project.status} />
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground mt-1">
                    <span className="font-bold text-primary uppercase tracking-tighter">{project.selectedTemplate || 'Auto'}</span>
                    <span className="w-1 h-1 rounded-full bg-white/20" />
                    <span>Created {formatDistanceToNow(new Date(project.createdAt))} ago</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/projects/${project.id}`}>Details</Link>
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:bg-destructive/10" onClick={() => deleteProject(project.id)}>
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const styles = {
    queued: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
    planning: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
    rendering: 'bg-primary/10 text-primary border-primary/20',
    complete: 'bg-green-500/10 text-green-500 border-green-500/20',
    failed: 'bg-destructive/10 text-destructive border-destructive/20',
    draft: 'bg-muted/10 text-muted-foreground border-muted/20',
  }[status] || 'bg-muted/10 text-muted-foreground border-muted/20'

  return (
    <Badge variant="outline" className={cn("text-[9px] uppercase tracking-widest font-bold px-1.5 py-0 h-4", styles)}>
      {status}
    </Badge>
  )
}

function ArrowRight(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  )
}