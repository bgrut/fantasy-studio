import React from 'react'
import {
  createRouter,
  createRoute,
  createRootRoute,
  RouterProvider,
  Outlet,
} from '@tanstack/react-router'
import { Toaster } from 'react-hot-toast'
import { useRenderCluster } from './hooks/useRenderCluster'
import { AppLayout } from './components/AppLayout'
import { ToastProvider } from './components/Toast'
import CommandPalette from './components/CommandPalette'
import PipelineStatus from './components/PipelineStatus'
import Onboarding from './components/Onboarding'
import OnboardingTour from './components/OnboardingTour'
import { TooltipProvider } from './components/ui/tooltip'

// Pages
import SceneStudio from './pages/SceneStudio'
import Templates from './pages/Templates'
import Marketplace from './pages/Marketplace'
import Outputs from './pages/Outputs'
import Settings from './pages/Settings'
import Insights from './pages/Insights'
import RenderQueue from './pages/RenderQueue'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import CreateProject from './pages/CreateProject'
import ProjectDetail from './pages/ProjectDetail'

const rootRoute = createRootRoute({
  component: () => (
    // v1.4 polish — TooltipProvider with 180ms delay so tooltips don't feel
    // spammy. All in-app tooltips wrap individual triggers underneath.
    <TooltipProvider delay={180}>
      <ToastProvider>
        <Outlet />
        <PipelineStatus />
        <CommandPalette />
        <Onboarding />
        <OnboardingTour />
      </ToastProvider>
    </TooltipProvider>
  ),
})

// Studio is the default landing page
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => <AppLayout><SceneStudio /></AppLayout>,
})

const studioRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/studio',
  component: () => <AppLayout><SceneStudio /></AppLayout>,
})

// Create route redirects to Studio (merged)
const createRoutePath = createRoute({
  getParentRoute: () => rootRoute,
  path: '/create',
  component: () => <AppLayout><SceneStudio /></AppLayout>,
})

const outputsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/outputs',
  component: () => <AppLayout><Outputs /></AppLayout>,
})

const templatesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/templates',
  component: () => <AppLayout><Templates /></AppLayout>,
})

const marketplaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/marketplace',
  component: () => <AppLayout><Marketplace /></AppLayout>,
})

const insightsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/insights',
  component: () => <AppLayout><Insights /></AppLayout>,
})

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  component: () => <AppLayout><Settings /></AppLayout>,
})

// Keep legacy routes working
const queueRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/queue',
  component: () => <AppLayout><RenderQueue /></AppLayout>,
})

const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/projects',
  component: () => <AppLayout><Projects /></AppLayout>,
})

const projectDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/projects/$id',
  component: () => <AppLayout><ProjectDetail /></AppLayout>,
})

const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/dashboard',
  component: () => <AppLayout><Dashboard /></AppLayout>,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  studioRoute,
  createRoutePath,
  outputsRoute,
  templatesRoute,
  insightsRoute,
  marketplaceRoute,
  settingsRoute,
  queueRoute,
  projectsRoute,
  projectDetailRoute,
  dashboardRoute,
])

// v1.4 follow-up — preload routes on hover/focus so navigation feels
// instant. TanStack Router will fetch the route's component code as soon
// as the user shows intent (hover or keyboard focus).
const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  defaultPreloadDelay: 50,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

export default function App() {
  useRenderCluster()
  return <RouterProvider router={router} />
}
