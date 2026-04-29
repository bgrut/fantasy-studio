import { RenderProvider, RenderJobRequest, RenderStatusUpdate } from './types';

export class MockRenderProvider implements RenderProvider {
  async render(request: RenderJobRequest, onUpdate: (update: RenderStatusUpdate) => Promise<void>): Promise<void> {
    const startedAt = new Date().toISOString();
    let stdoutLog = `[MOCK] Initializing render for job ${request.jobId}\n`;
    stdoutLog += `[MOCK] Template: ${request.templateName}\n`;
    stdoutLog += `[MOCK] Output Dir: ${request.outputDir}\n`;
    stdoutLog += `[MOCK] Settings: ${JSON.stringify(request.renderSettings)}\n`;

    // 1. Planning
    await onUpdate({
      status: 'planning',
      stage: 'planning',
      message: 'Allocating GPU resources and pre-calculating light maps.',
      progress: 0,
      startedAt,
      stdoutLog
    });
    await new Promise(r => setTimeout(r, 3000));

    // 2. Rendering
    for (let i = 1; i <= 10; i++) {
      const frameLog = `[MOCK] Cycles engine active. Rendering frame ${i * 36}/360.\n`;
      stdoutLog += frameLog;

      await onUpdate({
        status: 'rendering',
        stage: 'rendering',
        message: frameLog.trim(),
        progress: i * 10,
        startedAt,
        stdoutLog
      });
      await new Promise(r => setTimeout(r, 2000));
      
      // Simulate random failure (reduced for demo)
      if (Math.random() < 0.02) {
        const errorText = 'GPU Out of Memory error during denoising pass.';
        const stderrLog = `FATAL: CUDA_ERROR_OUT_OF_MEMORY\n${errorText}`;
        
        await onUpdate({
          status: 'failed',
          stage: 'failed',
          message: errorText,
          errorText,
          stdoutLog,
          stderrLog,
          startedAt,
          completedAt: new Date().toISOString()
        });
        return;
      }
    }

    // 3. Complete
    const completedAt = new Date().toISOString();
    stdoutLog += `[MOCK] Render cycle finished successfully at ${completedAt}.\n`;

    await onUpdate({
      status: 'complete',
      stage: 'complete',
      message: 'Render complete. Assets exported to cloud storage.',
      progress: 100,
      outputVideoUrl: 'https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4',
      outputThumbnailUrl: 'https://images.unsplash.com/photo-1620641788421-7a1c342ea42e?w=800&q=80',
      stdoutLog,
      startedAt,
      completedAt
    });
  }
}
