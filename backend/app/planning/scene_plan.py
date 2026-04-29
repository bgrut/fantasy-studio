from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UIReference:
    filename: str
    kind: str = "unknown"


@dataclass
class GenerationInput:
    manifest_name: str
    raw_prompt: str
    template_bias: str = "auto"
    duration_seconds: int = 12
    brand_primary: str = "#0EA5E9"
    sonic_frequency: str = ""
    technical_style_constraints: str = ""
    references: list[UIReference] = field(default_factory=list)
    raw_ui_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssetRequirement:
    asset_type: str
    required: bool = True
    count: int = 1
    tags: list[str] = field(default_factory=list)


@dataclass
class AnimationInstruction:
    subject: str
    action: str
    mode: str
    intensity: str = "medium"
    timing: str = "continuous"
    notes: str = ""


@dataclass
class ScenePlan:
    scene_family: str
    template_name: str
    environment: str
    subject_type: str
    focal_subject: str
    style_tags: list[str] = field(default_factory=list)
    camera_mode: str = "push_in"
    lighting_mode: str = "cinematic_default"
    animation_mode: str = "ambient"
    mood: str = "cinematic"
    duration_seconds: int = 12
    asset_requirements: list[AssetRequirement] = field(default_factory=list)
    animation_instructions: list[AnimationInstruction] = field(default_factory=list)
    reference_influence: str = "none"
    debug_notes: list[str] = field(default_factory=list)
