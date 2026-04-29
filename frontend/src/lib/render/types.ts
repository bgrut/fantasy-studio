export type JobStatus = 'queued' | 'planning' | 'rendering' | 'complete' | 'failed';

export interface RenderSettings {
  engine: 'CYCLES' | 'EEVEE';
  samples: number;
  resolution: {
    width: number;
    height: number;
  };
  transparentBackground?: boolean;
}

export interface RenderStatusUpdate {
  status: JobStatus;
  stage?: string;
  message?: string;
  progress?: number;
  outputVideoUrl?: string;
  localOutputPath?: string;
  outputThumbnailUrl?: string;
  stdoutLog?: string;
  stderrLog?: string;
  startedAt?: string;
  completedAt?: string;
  errorText?: string;
}

export interface RenderJobRequest {
  jobId: string;
  projectId: string;
  templateName: string;
  sceneSpecJson: any;
  outputDir: string;
  renderSettings: RenderSettings;
}

export interface CameraBeat {
  id: string;
  type: 'Pan' | 'Tilt' | 'Dolly' | 'Zoom' | 'Static';
  duration: number;
  start?: number[];
  end?: number[];
}

export interface SceneManifest {
  template_name: string;
  title_text: string;
  subtitle_text: string;
  palette: {
    primary: string;
    accent: string;
  };
  subject: string;
  hook: string;
  camera_beats: CameraBeat[];
  audio_hint: string;
  caption_text: string;
  duration_seconds: number;
  aspect_ratio: string;
  fps: number;
  output_resolution: {
    width: number;
    height: number;
  };
}

export interface RenderProvider {
  render(request: RenderJobRequest, onUpdate: (update: RenderStatusUpdate) => Promise<void>): Promise<void>;
}