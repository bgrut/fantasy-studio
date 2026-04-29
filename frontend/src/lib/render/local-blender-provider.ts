import { RenderProvider, RenderJobRequest, RenderStatusUpdate } from './types';

export class LocalBlenderCliProvider implements RenderProvider {
  async render(request: RenderJobRequest, onUpdate: (update: RenderStatusUpdate) => Promise<void>): Promise<void> {
    const startedAt = new Date().toISOString();
    let stdoutLog = `[CLI] Local Blender CLI session initialized for ${request.jobId}\n`;
    
    // Stub implementation
    await onUpdate({
      status: 'failed',
      stage: 'initialization',
      message: 'Local Blender CLI Provider is not yet configured with a valid binary path.',
      errorText: 'BINARY_NOT_FOUND',
      stdoutLog,
      stderrLog: 'FATAL: blender executable not found in PATH.',
      startedAt,
      completedAt: new Date().toISOString()
    });
  }
}
