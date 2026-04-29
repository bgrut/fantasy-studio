from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class SettingsPayload(BaseModel):
    blender_executable_path: Optional[str] = None
    ffmpeg_executable_path: Optional[str] = None
    local_render_mode: Optional[bool] = None


class DirectorialControls(BaseModel):
    """Optional user-guided directorial controls.

    Every field is optional.  When omitted the AI director decides
    automatically (existing behaviour).  When provided, these take
    priority over prompt-inferred defaults.
    """
    motion_style: Optional[str] = None       # static | driving | walking | dancing | drifting
    camera_style: Optional[str] = None       # orbit | tracking | follow | handheld | reveal
    scene_dynamics: Optional[str] = None     # static | subtle | cinematic | high_energy
    character_behavior: Optional[str] = None # idle | walk | dance | perform
    energy_level: Optional[str] = None       # calm | cinematic | high | chaotic


class RenderJobCreate(BaseModel):
    project_name: Optional[str] = None
    topic: str
    template_name: str = "neon_news"
    directorial_controls: Optional[DirectorialControls] = None


class RenderJobOut(BaseModel):
    id: int
    project_name: Optional[str]
    topic: str
    template_name: str
    status: str
    provider_name: str
    local_output_path: Optional[str] = None
    output_url: Optional[str] = None
    stdout_log: Optional[str] = None
    stderr_log: Optional[str] = None
    error_text: Optional[str] = None
    retry_count: int
    created_at: str
    updated_at: str
