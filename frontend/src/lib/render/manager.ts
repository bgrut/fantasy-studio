import { blink } from '@/blink/client';
import { RenderProvider, RenderJobRequest, RenderStatusUpdate } from './types';
import { MockRenderProvider } from './mock-provider';
import { LocalBlenderCliProvider } from './local-blender-provider';
import { getSystemSetting, SYSTEM_SETTING_KEYS } from '../system-settings';

class RenderManager {
  private activeJobs = new Set<string>();

  async processQueue() {
    try {
      // Check if Blender is enabled globally
      const enabled = await getSystemSetting(SYSTEM_SETTING_KEYS.BLENDER_ENABLED);
      if (enabled !== 'true') return;

      // Find jobs that are 'queued' and not already being processed
      const queuedJobs = await blink.db.renderJobs.list({
        where: { status: 'queued' }
      }) as any[];

      for (const job of queuedJobs) {
        if (this.activeJobs.has(job.id)) continue;
        this.runJob(job);
      }
    } catch (error) {
      console.error('Failed to process render queue:', error);
    }
  }

  private async runJob(job: any) {
    this.activeJobs.add(job.id);
    console.log(`[RenderManager] Starting job ${job.id}`);
    
    try {
      // Determine provider based on settings
      const localMode = await getSystemSetting(SYSTEM_SETTING_KEYS.LOCAL_RENDER_MODE);
      const isLocal = localMode === 'true';
      const providerName = isLocal ? 'Hybrid CLI (Local)' : 'Simulated (Cloud Mock)';
      const provider: RenderProvider = isLocal 
        ? new LocalBlenderCliProvider() 
        : new MockRenderProvider();

      // Get project to find template
      const project = await blink.db.projects.get(job.projectId) as any;
      if (!project) throw new Error('Associated project not found');
      
      // Get scene spec
      const specs = await blink.db.sceneSpecs.list({
        where: { projectId: job.projectId },
        limit: 1
      }) as any[];
      const spec = specs[0];
      if (!spec) throw new Error('Scene specification not found for project');

      // Update provider name in DB immediately
      await blink.db.renderJobs.update(job.id, { providerName });

      // Get paths from settings
      const templateRoot = await getSystemSetting(SYSTEM_SETTING_KEYS.BLENDER_TEMPLATE_ROOT) || './templates';
      const outputRoot = await getSystemSetting(SYSTEM_SETTING_KEYS.BLENDER_OUTPUT_ROOT) || './renders';

      await provider.render({
        jobId: job.id,
        projectId: job.projectId,
        templateName: project?.selectedTemplate || 'Neon News',
        sceneSpecJson: spec ? JSON.parse(spec.rawJson) : {},
        outputDir: `${outputRoot}/${job.id}`,
        renderSettings: {
          engine: 'CYCLES',
          samples: 128,
          resolution: { width: 1080, height: 1920 }
        }
      }, async (update: RenderStatusUpdate) => {
        console.log(`[RenderManager] Job ${job.id} update: ${update.status} - ${update.message}`);
        
        // Update job status in DB
        await blink.db.renderJobs.update(job.id, {
          status: update.status,
          updatedAt: new Date().toISOString(),
          outputVideoUrl: update.outputVideoUrl,
          outputThumbnailUrl: update.outputThumbnailUrl,
          localOutputPath: update.localOutputPath,
          stdoutLog: update.stdoutLog,
          stderrLog: update.stderrLog,
          errorText: update.errorText,
          startedAt: update.startedAt,
          completedAt: update.completedAt
        });

        // Add event
        if (update.message) {
          await blink.db.jobEvents.create({
            id: `event_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
            renderJobId: job.id,
            stage: update.stage || update.status,
            message: update.message
          });
        }

        // Update project status
        await blink.db.projects.update(job.projectId, { status: update.status });
      });
    } catch (error) {
      console.error(`[RenderManager] Job ${job.id} failed:`, error);
      
      await blink.db.renderJobs.update(job.id, {
        status: 'failed',
        errorText: String(error)
      });
      
      await blink.db.jobEvents.create({
        id: `event_${Date.now()}_error`,
        renderJobId: job.id,
        stage: 'failed',
        message: `Internal processing error: ${String(error)}`
      });
    } finally {
      this.activeJobs.delete(job.id);
      console.log(`[RenderManager] Job ${job.id} finished processing`);
    }
  }
}

export const renderManager = new RenderManager();
