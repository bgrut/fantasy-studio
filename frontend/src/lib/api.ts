const API_BASE = "";

export type Settings = {
  blender_executable_path: string;
  ffmpeg_executable_path: string;
  local_render_mode: boolean;
};

export type RenderJob = {
  id: number;
  project_name?: string | null;
  topic: string;
  template_name: string;
  status: string;
  provider_name: string;
  local_output_path?: string | null;
  output_url?: string | null;
  stdout_log?: string | null;
  stderr_log?: string | null;
  error_text?: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
  // Wave 1 additions (backend columns added via migration in app/db.py):
  recipe_name?: string | null;
  source?: string | null; // 'queue' | 'preview'
};

export type JobEvent = {
  id: number;
  job_id: number;
  stage: string;
  message: string;
  created_at: string;
};

export async function getHealth() {
  const r = await fetch(`${API_BASE}/api/health`);
  if (!r.ok) throw new Error("Failed to load health");
  return r.json();
}

export async function getSettings(): Promise<Settings> {
  const r = await fetch(`${API_BASE}/api/settings`);
  if (!r.ok) throw new Error("Failed to load settings");
  return r.json();
}

export async function saveSettings(payload: Partial<Settings>) {
  const r = await fetch(`${API_BASE}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Failed to save settings");
  return r.json();
}

export async function listRenderJobs(): Promise<{ ok: boolean; jobs: RenderJob[] }> {
  const r = await fetch(`${API_BASE}/api/render-jobs`);
  if (!r.ok) throw new Error("Failed to load render jobs");
  return r.json();
}

export async function getRenderJob(id: number): Promise<{ ok: boolean; job: RenderJob; events: JobEvent[] }> {
  const r = await fetch(`${API_BASE}/api/render-jobs/${id}`);
  if (!r.ok) throw new Error("Failed to load render job");
  return r.json();
}

export type DirectorialControls = {
  motion_style?: "static" | "driving" | "walking" | "dancing" | "drifting";
  camera_style?: "orbit" | "tracking" | "follow" | "handheld" | "reveal";
  scene_dynamics?: "static" | "subtle" | "cinematic" | "high_energy";
  character_behavior?: "idle" | "walk" | "dance" | "perform";
  energy_level?: "calm" | "cinematic" | "high" | "chaotic";
};

export async function createRenderJob(payload: {
  project_name?: string;
  topic: string;
  template_name: string;
  directorial_controls?: DirectorialControls;
}) {
  const r = await fetch(`${API_BASE}/api/render-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Failed to create render job");
  return r.json();
}

export async function retryRenderJob(id: number) {
  const r = await fetch(`${API_BASE}/api/render-jobs/${id}/retry`, {
    method: "POST",
  });
  if (!r.ok) throw new Error("Failed to retry render job");
  return r.json();
}

// ════════════════════════════════════════════════════════════════════════
// Credits (CC-BY attribution) and scene recipe for a finished render
// ════════════════════════════════════════════════════════════════════════

export type CreditsItem = {
  name: string;
  author: string;
  source: string;
  license: string;
};

export type CreditsPayload = {
  required: boolean;
  text: string;
  items: CreditsItem[];
};

export async function getRenderJobCredits(
  id: number,
): Promise<{ ok: boolean; job_id: number; credits: CreditsPayload }> {
  const r = await fetch(`${API_BASE}/api/render-jobs/${id}/credits`);
  if (!r.ok) throw new Error("Failed to load job credits");
  return r.json();
}

export type SceneRecipeSummary = {
  subject: string;
  environment: string;
  action: string;
  time_of_day: string;
  mood: string;
};

export type SceneRecipe = {
  hero?: Record<string, any>;
  environment?: Record<string, any>;
  ground?: { material?: string; detail?: string };
  sky?: { hdri_keywords?: string[] };
  atmosphere?: { type?: string; density?: number; color?: number[] };
  lighting?: { style?: string; key_energy?: number; color_temp?: string; rim_light?: boolean; practical_lights?: boolean };
  camera?: { style?: string; lens?: number; dof_fstop?: number; angle?: string; speed?: string };
  props?: Array<{ query: string; placement: string; optional?: boolean }>;
  compositor?: { bloom?: boolean; bloom_threshold?: number; vignette?: boolean; lens_distortion?: number };
  summary?: SceneRecipeSummary;
};

export async function getRenderJobRecipe(
  id: number,
): Promise<{ ok: boolean; job_id: number; recipe: SceneRecipe | null; scene_plan?: Record<string, any> | null }> {
  const r = await fetch(`${API_BASE}/api/render-jobs/${id}/recipe`);
  if (!r.ok) throw new Error("Failed to load job recipe");
  return r.json();
}

// ════════════════════════════════════════════════════════════════════════
// Template marketplace
// ════════════════════════════════════════════════════════════════════════

export type TemplatePackRecord = {
  pack_id: string;
  name?: string | null;
  version?: string | null;
  author?: string | null;
  license?: string | null;
  scene_family?: string | null;
  template_name?: string | null;
  install_path?: string | null;
  installed_at?: number | null;
  manifest?: Record<string, any> | null;
};

export type PackListResponse = {
  ok: boolean;
  spec_version: number;
  packs: TemplatePackRecord[];
};

export type PackValidationResponse = {
  ok: boolean;
  pack_id?: string | null;
  manifest?: Record<string, any> | null;
  errors: string[];
  warnings: string[];
};

export type PackInstallResponse = {
  ok: boolean;
  pack_id?: string | null;
  record?: TemplatePackRecord | null;
  error?: string | null;
  warnings: string[];
};

export type SchemaField = {
  key: string;
  type: string;
  required: boolean;
  allowed: any | null;
};

export type PackSchemaResponse = {
  ok: boolean;
  spec_version: number;
  fields: SchemaField[];
};

export async function listTemplatePacks(): Promise<PackListResponse> {
  const r = await fetch(`${API_BASE}/api/templates/packs`);
  if (!r.ok) throw new Error("Failed to load template packs");
  return r.json();
}

export async function getTemplatePackSchema(): Promise<PackSchemaResponse> {
  const r = await fetch(`${API_BASE}/api/templates/schema`);
  if (!r.ok) throw new Error("Failed to load template pack schema");
  return r.json();
}

export async function validateTemplatePack(file: File): Promise<PackValidationResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API_BASE}/api/templates/packs/validate`, {
    method: "POST",
    body: fd,
  });
  if (!r.ok) throw new Error("Failed to validate template pack");
  return r.json();
}

export async function installTemplatePack(file: File, force = false): Promise<PackInstallResponse> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("force", force ? "true" : "false");
  const r = await fetch(`${API_BASE}/api/templates/packs/install`, {
    method: "POST",
    body: fd,
  });
  if (!r.ok) throw new Error("Failed to install template pack");
  return r.json();
}

export async function uninstallTemplatePack(packId: string): Promise<PackInstallResponse> {
  const r = await fetch(`${API_BASE}/api/templates/packs/${encodeURIComponent(packId)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error("Failed to uninstall template pack");
  return r.json();
}

// ════════════════════════════════════════════════════════════════════════
// Community catalog
// ════════════════════════════════════════════════════════════════════════

export type CatalogTemplate = {
  pack_id: string;
  name: string;
  author: string;
  version: string;
  description: string;
  scene_family: string;
  preview_image_url: string | null;
  tags: string[];
  rating: number;
  downloads: number;
  price: string;
  bundled: boolean;
  bundle_path?: string | null;
  download_url?: string | null;
};

export type CatalogResponse = {
  ok: boolean;
  catalog_version?: string;
  count: number;
  templates: CatalogTemplate[];
};

export async function getCatalog(): Promise<CatalogResponse> {
  const r = await fetch(`${API_BASE}/api/templates/catalog`);
  if (!r.ok) throw new Error("Failed to load catalog");
  return r.json();
}

export async function searchCatalog(params: {
  q?: string;
  family?: string;
  price?: string;
  sort?: string;
}): Promise<CatalogResponse> {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.family) sp.set("family", params.family);
  if (params.price) sp.set("price", params.price);
  if (params.sort) sp.set("sort", params.sort);
  const r = await fetch(`${API_BASE}/api/templates/catalog/search?${sp.toString()}`);
  if (!r.ok) throw new Error("Failed to search catalog");
  return r.json();
}

export async function submitTemplate(file: File): Promise<{ ok: boolean; message: string; filename: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API_BASE}/api/templates/submit`, { method: "POST", body: fd });
  if (!r.ok) throw new Error("Failed to submit template");
  return r.json();
}

// LLM diagnostics
export type LLMStatus = {
  ollama_reachable: boolean;
  ollama_host: string;
  model_loaded: string | null;
  llm_enabled: boolean;
  last_call_timestamp: string | null;
  last_call_latency_ms: number;
  total_calls: number;
  total_fallbacks: number;
  last_fallback_reason: string | null;
  mode: string;
};

export async function getLLMStatus(): Promise<LLMStatus> {
  const r = await fetch(`${API_BASE}/api/llm/status`);
  if (!r.ok) throw new Error("Failed to get LLM status");
  return r.json();
}

export async function testLLM(prompt: string): Promise<{ ok: boolean; model: string; response: string | null; error: string | null }> {
  const r = await fetch(`${API_BASE}/api/llm/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!r.ok) throw new Error("Failed to test LLM");
  return r.json();
}

// ════════════════════════════════════════════════════════════════════════
// WS5/WS7/WS8 — Render extras: preview, iterate, with_controls, variations
// ════════════════════════════════════════════════════════════════════════

export type RenderTier = "preview" | "fast" | "standard" | "cinematic";

export type RenderExtrasResult = {
  ok: boolean;
  render_tier?: string | null;
  output_path?: string | null;
  output_url?: string | null;
  // v1.4.3 polish — companion .blend file URL when the render saved one.
  // Backend writes a packed Blender scene next to the MP4; absent if save
  // failed or the render aborted before the save step.
  blend_url?: string | null;
  manifest_path?: string | null;
  recipe_name?: string | null;
  error?: string | null;
  stdout_tail?: string | null;
  stderr_tail?: string | null;
};

export type PreviewResponse = RenderExtrasResult & {
  session_id?: string | null;
  step_id?: string | null;
};

export type IterationStep = {
  step_id: string;
  parent_id: string | null;
  instruction: string;
  source: string;
  notes: string;
  created_at: number;
  manifest: Record<string, any>;
};

export type IterateResponse = {
  ok: boolean;
  session_id: string;
  step: IterationStep;
  rendered: boolean;
  render_result?: RenderExtrasResult;
};

export async function renderPreview(payload: {
  topic: string;
  template_name?: string;
  directorial_controls?: DirectorialControls;
  start_session?: boolean;
  forced_hero_id?: string;
  forced_environment_id?: string;
  template_v2_enabled?: boolean;
  // v1.3.7 — Scene Controls now flow through the main Generate flow, not
  // just the (deprecated) inner Render button.
  render_tier?: RenderTier;
  scene_params_override?: Record<string, any>;
  duration_seconds?: number;
}): Promise<PreviewResponse> {
  const r = await fetch(`${API_BASE}/api/render/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Failed to render preview");
  return r.json();
}

// ═════════════════════════════════════════════════════════════════════
// Phase 8 — Local-LLM orchestrator submission
// ═════════════════════════════════════════════════════════════════════

export interface OrchestrateResponse {
  job_id: number;
  status: string;
  prompt: string;
  template_name: string;
}

export interface OrchestrateHealth {
  ollama: boolean;
  bridge: boolean;
  ready: boolean;
  errors: string[];
}

/**
 * Submit a prompt to the local Ollama-driven orchestrator. The job lands in
 * the same render_jobs table as legacy renders, so PipelineStatus polling
 * picks it up automatically. Poll /api/render-jobs/{job_id} for status.
 */
export async function submitOrchestrate(payload: {
  prompt: string;
  project_name?: string;
  duration_seconds?: number;
  fps?: number;
  render_tier?: RenderTier;
  model?: string;
}): Promise<OrchestrateResponse> {
  const r = await fetch(`${API_BASE}/api/orchestrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Failed to submit orchestrate job");
  return r.json();
}

/** Check whether Ollama + Blender bridge are reachable from the backend. */
export async function getOrchestrateHealth(): Promise<OrchestrateHealth> {
  const r = await fetch(`${API_BASE}/api/orchestrate/health`);
  if (!r.ok) throw new Error("Failed to check orchestrator health");
  return r.json();
}

export async function renderIterate(payload: {
  session_id: string;
  instruction: string;
  render?: boolean;
  render_tier?: RenderTier;
}): Promise<IterateResponse> {
  const r = await fetch(`${API_BASE}/api/render/iterate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Failed to iterate scene");
  return r.json();
}

export async function getIterationHistory(sessionId: string): Promise<{ ok: boolean; session_id: string; steps: IterationStep[] }> {
  const r = await fetch(`${API_BASE}/api/render/iterate/${encodeURIComponent(sessionId)}`);
  if (!r.ok) throw new Error("Failed to load iteration history");
  return r.json();
}

export async function renderWithControls(payload: {
  topic: string;
  template_name?: string;
  render_tier?: RenderTier;
  directorial_controls?: DirectorialControls;
  scene_params_override?: Record<string, any>;
  duration_seconds?: number;
  forced_hero_id?: string;
  forced_environment_id?: string;
  template_v2_enabled?: boolean;
}): Promise<RenderExtrasResult> {
  const r = await fetch(`${API_BASE}/api/render/with_controls`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Failed to render with controls");
  return r.json();
}

export type Variation = {
  variation_id: string;
  label: string;
  mutation: Record<string, any>;
  manifest: Record<string, any>;
  render_result: RenderExtrasResult | null;
};

export type VariationsResponse = {
  ok: boolean;
  batch_id: string;
  source: string;
  count: number;
  variations: Variation[];
};

export async function renderVariations(payload: {
  topic: string;
  template_name?: string;
  count?: number;
  render?: boolean;
  render_tier?: RenderTier;
  directorial_controls?: DirectorialControls;
}): Promise<VariationsResponse> {
  const r = await fetch(`${API_BASE}/api/render/variations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Failed to generate variations");
  return r.json();
}

// ════════════════════════════════════════════════════════════════════════
// WS6 — Export endpoints
// ════════════════════════════════════════════════════════════════════════

export type ExportFormat = "mp4" | "gif" | "png_seq" | "poster" | "blend" | "glb";

export type ExportResult = {
  ok: boolean;
  format: string;
  local_path?: string | null;
  output_url?: string | null;
  error?: string | null;
  note?: string | null;
};

export async function listExportFormats(jobId: number): Promise<{ ok: boolean; job_id: number; formats: ExportFormat[]; source_mp4: string }> {
  const r = await fetch(`${API_BASE}/api/export/${jobId}/formats`);
  if (!r.ok) throw new Error("Failed to list export formats");
  return r.json();
}

export async function runExport(jobId: number, fmt: ExportFormat): Promise<{ ok: boolean; job_id: number; result: ExportResult }> {
  const r = await fetch(`${API_BASE}/api/export/${jobId}/${fmt}`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(`Failed to export ${fmt}`);
  return r.json();
}

// ════════════════════════════════════════════════════════════════════════
// Pipeline status + Analytics
// ════════════════════════════════════════════════════════════════════════

export type PipelineJob = {
  id: number;
  topic: string;
  status: string;
  output_url?: string | null;
  error?: string | null;
  duration_s?: number | null;
  completed_at?: string | null;
  created_at?: string;
  template_name?: string;
  progress?: number;
  stage?: string;
};

export type PipelineStats = {
  total_renders: number;
  completed: number;
  failed: number;
  queued: number;
  in_progress: number;
  avg_render_time_s: number;
  total_render_time_s: number;
};

export type PipelineStatusResponse = {
  ok: boolean;
  active: PipelineJob | null;
  queued: PipelineJob[];
  recent: PipelineJob[];
  stats: PipelineStats;
};

export async function getPipelineStatus(): Promise<PipelineStatusResponse> {
  const r = await fetch(`${API_BASE}/api/pipeline/status`);
  if (!r.ok) throw new Error("Failed to load pipeline status");
  return r.json();
}

export type AnalyticsSummary = {
  total_renders: number;
  completed: number;
  failed: number;
  avg_render_time_s: number;
  avg_preview_time_s: number;
  success_rate: number;
};

export type AnalyticsResponse = {
  ok: boolean;
  summary: AnalyticsSummary;
  tier_breakdown: Record<string, number>;
  top_subjects: { subject: string; count: number }[];
  template_usage: Record<string, number>;
  timeline: { hour: string; count: number }[];
  recent: PipelineJob[];
};

export async function getAnalytics(): Promise<AnalyticsResponse> {
  const r = await fetch(`${API_BASE}/api/analytics`);
  if (!r.ok) throw new Error("Failed to load analytics");
  return r.json();
}

// ════════════════════════════════════════════════════════════════════════
// Asset library — picker + browse
// ════════════════════════════════════════════════════════════════════════

export type AssetQuality = "tested" | "unverified" | "rejected" | string;

export type AssetAttribution = {
  author?: string | null;
  license?: string | null;
  source?: string | null;
  source_url?: string | null;
};

export type AssetMatch = {
  id: string;
  title: string;
  subject?: string;
  visual_descriptors?: string[];
  thumbnail_url: string;
  quality: AssetQuality;
  use_count?: number;
  attribution?: AssetAttribution;
};

export type AssetMatchResponse = {
  subject_detected?: string;
  visual_hints?: string[];
  matches: AssetMatch[];
  auto_pick_id?: string | null;
  reason?: string | null;
};

export async function matchAssets(prompt: string, limit = 12): Promise<AssetMatchResponse> {
  const r = await fetch(
    `${API_BASE}/api/assets/match?prompt=${encodeURIComponent(prompt)}&limit=${limit}`,
  );
  if (!r.ok) throw new Error("Failed to match assets");
  return r.json();
}

export type AssetCategory = "character" | "environment" | "prop" | "vehicle" | "hdri" | string;

export type AssetCountsResponse = {
  total: number;
  by_category: Record<string, number>;
};

export async function getAssetCounts(): Promise<AssetCountsResponse> {
  const r = await fetch(`${API_BASE}/api/assets/library/counts`);
  if (!r.ok) throw new Error("Failed to load asset counts");
  return r.json();
}

export type AssetLibraryItem = AssetMatch & {
  category?: AssetCategory;
  subject_tags?: string[];
};

export type AssetBrowseResponse = {
  items: AssetLibraryItem[];
  total: number;
  has_more: boolean;
};

export async function browseAssets(params: {
  category?: string;
  limit?: number;
  offset?: number;
}): Promise<AssetBrowseResponse> {
  const sp = new URLSearchParams();
  if (params.category && params.category !== "all") sp.set("category", params.category);
  sp.set("limit", String(params.limit ?? 50));
  sp.set("offset", String(params.offset ?? 0));
  const r = await fetch(`${API_BASE}/api/assets/library/browse?${sp.toString()}`);
  if (!r.ok) throw new Error("Failed to browse assets");
  return r.json();
}

// ════════════════════════════════════════════════════════════════════════
// Library match — used by the Cast Panel. Returns hits for ONE category
// (character | environment | prop | vehicle | hdri) scored against the prompt.
// ════════════════════════════════════════════════════════════════════════

export type LibraryMatchHit = {
  id: string;
  category: string;
  subject?: string;
  shape_class?: string | null;
  subject_tags?: string[];
  biome_hints?: string[];
  score?: number;
  thumbnail_url?: string | null;
  path?: string;
};

export type LibraryMatchResponse = {
  ok: boolean;
  q: string;
  category: string;
  keyword?: string | null;
  total: number;
  hits: LibraryMatchHit[];
};

export async function libraryMatch(params: {
  q: string;
  category: "character" | "environment" | "prop" | "vehicle" | "hdri" | string;
  limit?: number;
}): Promise<LibraryMatchResponse> {
  const sp = new URLSearchParams();
  sp.set("q", params.q);
  sp.set("category", params.category);
  sp.set("limit", String(params.limit ?? 12));
  const r = await fetch(`${API_BASE}/api/library/match?${sp.toString()}`);
  if (!r.ok) throw new Error("Failed to match library");
  return r.json();
}

// ════════════════════════════════════════════════════════════════════════
// v1.3.7 — Paginated library browse for the "Change cast" UI.
// ════════════════════════════════════════════════════════════════════════

export type LibraryBrowseAsset = {
  id: string;
  category: string;
  subject?: string | null;
  shape_class?: string | null;
  subject_tags?: string[];
  biome_hints?: string[];
  thumbnail_url?: string | null;
  path?: string;
};

export type LibraryBrowseResponse = {
  ok: boolean;
  category: string;
  page: number;
  per_page: number;
  total: number;
  pages: number;
  search?: string | null;
  assets: LibraryBrowseAsset[];
};

export async function libraryBrowse(params: {
  category?: string;
  page?: number;
  per_page?: number;
  search?: string;
}): Promise<LibraryBrowseResponse> {
  const sp = new URLSearchParams();
  if (params.category) sp.set("category", params.category);
  sp.set("page", String(params.page ?? 1));
  sp.set("per_page", String(params.per_page ?? 12));
  if (params.search) sp.set("search", params.search);
  const r = await fetch(`${API_BASE}/api/library/browse?${sp.toString()}`);
  if (!r.ok) throw new Error("Failed to browse library");
  return r.json();
}