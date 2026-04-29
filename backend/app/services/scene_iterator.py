from __future__ import annotations

"""
scene_iterator.py
=================
WS5 — Conversational scene iteration.

Given an existing manifest dict and a natural-language instruction
("make the lighting warmer", "lower the camera", "swap the car for a
truck"), produce a *new* manifest by mutating only the directorial layer.
The geometry-building stays in the templates; this layer just rewrites
intent.

Design rules
------------
- Never break callers. If the LLM is unavailable, fall back to a small
  rule-based mutator that recognises a handful of common instructions
  (color, time-of-day, motion, camera lens, energy).
- Never lose history. Every mutated manifest is recorded so callers can
  display the iteration thread or roll back.
- The mutator only writes to a defined surface area:
      directorial_controls
      scene_params
      output_resolution
      duration_seconds
      render_tier
  It is *not* allowed to overwrite scene_plan, animation_instructions,
  resolved_assets — those are produced by the planner / asset agent and
  are off-limits to keep iteration safe.
"""

import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .llm_service import structured_query, is_available as llm_available


# ════════════════════════════════════════════════════════════════════════════
# Iteration history (in-memory; per-process)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class IterationStep:
    step_id: str
    parent_id: str | None
    instruction: str
    manifest: dict
    source: str  # "llm" | "rules" | "seed"
    notes: str = ""
    created_at: float = field(default_factory=time.time)


# session_id -> list[IterationStep]
_HISTORY: dict[str, list[IterationStep]] = {}


def start_session(seed_manifest: dict) -> tuple[str, IterationStep]:
    """Open a new iteration session anchored on a freshly built manifest."""
    session_id = uuid.uuid4().hex[:12]
    seed = IterationStep(
        step_id=uuid.uuid4().hex[:12],
        parent_id=None,
        instruction="",
        manifest=copy.deepcopy(seed_manifest),
        source="seed",
        notes="initial manifest",
    )
    _HISTORY[session_id] = [seed]
    return session_id, seed


def get_history(session_id: str) -> list[IterationStep]:
    return list(_HISTORY.get(session_id, []))


def latest_manifest(session_id: str) -> dict | None:
    steps = _HISTORY.get(session_id)
    if not steps:
        return None
    return copy.deepcopy(steps[-1].manifest)


# ════════════════════════════════════════════════════════════════════════════
# Mutation entry point
# ════════════════════════════════════════════════════════════════════════════

_MUTATION_SCHEMA = {
    "directorial_controls": {
        "motion_style": "string|null",
        "camera_style": "string|null",
        "scene_dynamics": "string|null",
        "character_behavior": "string|null",
        "energy_level": "string|null",
    },
    "scene_params": {
        "lighting_preset": "string|null",
        "camera_mode": "string|null",
        "brand_primary": "string|null",
    },
    "render_tier": "string|null",
    "duration_seconds": "integer|null",
    "notes": "string",
}

_MUTATION_SYSTEM = (
    "You are the directorial layer of a Blender cinematic engine. "
    "The user will give you an existing scene manifest and a free-form "
    "instruction (e.g. 'warmer lighting', 'wider lens', 'more chaotic'). "
    "Output ONLY the fields that need to change. Leave anything you don't "
    "want to touch as null. Do NOT rewrite the geometry, scene_plan, "
    "animations, or assets — only directorial intent."
)


def iterate(
    session_id: str,
    instruction: str,
) -> IterationStep | None:
    """
    Apply a natural-language instruction to the latest manifest in the
    session and return a new IterationStep. Returns None if the session
    does not exist.
    """
    steps = _HISTORY.get(session_id)
    if not steps:
        return None

    parent = steps[-1]
    base_manifest = copy.deepcopy(parent.manifest)

    mutation, source = _generate_mutation(base_manifest, instruction)
    new_manifest = _apply_mutation(base_manifest, mutation)

    step = IterationStep(
        step_id=uuid.uuid4().hex[:12],
        parent_id=parent.step_id,
        instruction=instruction,
        manifest=new_manifest,
        source=source,
        notes=str(mutation.get("notes", "")),
    )
    steps.append(step)
    return step


# ════════════════════════════════════════════════════════════════════════════
# Mutation generation: LLM with rule-based fallback
# ════════════════════════════════════════════════════════════════════════════

def _generate_mutation(manifest: dict, instruction: str) -> tuple[dict, str]:
    """
    Try the LLM first. On any failure (Ollama down, malformed JSON,
    timeout), fall back to a deterministic rule-based mutator.
    """
    if llm_available():
        try:
            user_prompt = (
                "INSTRUCTION:\n"
                f"{instruction}\n\n"
                "CURRENT MANIFEST (relevant fields only):\n"
                + json.dumps(
                    {
                        "directorial_controls": manifest.get("directorial_controls", {}),
                        "scene_params": manifest.get("scene_params", {}),
                        "render_tier": manifest.get("render_tier"),
                        "duration_seconds": manifest.get("duration_seconds"),
                    },
                    indent=2,
                )
            )
            mutation = structured_query(
                _MUTATION_SYSTEM,
                user_prompt,
                _MUTATION_SCHEMA,
                timeout=10.0,
            )
            if isinstance(mutation, dict):
                return mutation, "llm"
        except Exception as e:
            print(f"[scene_iterator] llm path failed: {e}", flush=True)

    return _rule_based_mutation(instruction), "rules"


def _rule_based_mutation(instruction: str) -> dict:
    """
    Tiny deterministic mutator. Recognises a handful of common phrases.
    Always returns a well-formed mutation dict (often a no-op note).
    """
    text = (instruction or "").lower()
    out: dict[str, Any] = {
        "directorial_controls": {},
        "scene_params": {},
        "notes": f"rule-based fallback for: {instruction}",
    }
    dc = out["directorial_controls"]
    sp = out["scene_params"]

    # Lighting / time of day
    if any(w in text for w in ("warmer", "warm", "sunset", "golden")):
        sp["lighting_preset"] = "golden_hour"
    if any(w in text for w in ("cooler", "cold", "blue hour", "moonlit", "night")):
        sp["lighting_preset"] = "blue_hour"
    if "neon" in text or "cyberpunk" in text:
        sp["lighting_preset"] = "neon_night"
        sp["brand_primary"] = "#0EA5E9"

    # Camera
    if "wider" in text or "wide lens" in text or "zoom out" in text:
        sp["camera_mode"] = "wide"
    if "tighter" in text or "close up" in text or "zoom in" in text:
        sp["camera_mode"] = "close_up"
    if "orbit" in text:
        dc["camera_style"] = "orbit"
    if "tracking" in text or "track shot" in text:
        dc["camera_style"] = "tracking"
    if "handheld" in text or "shaky" in text:
        dc["camera_style"] = "handheld"

    # Energy / dynamics
    if any(w in text for w in ("calmer", "calm", "relaxed", "subtle")):
        dc["energy_level"] = "calm"
        dc["scene_dynamics"] = "subtle"
    if any(w in text for w in ("intense", "high energy", "epic", "dramatic")):
        dc["energy_level"] = "high"
        dc["scene_dynamics"] = "cinematic"
    if "chaotic" in text or "frenzy" in text:
        dc["energy_level"] = "chaotic"
        dc["scene_dynamics"] = "high_energy"

    # Motion / behavior
    if "dance" in text:
        dc["character_behavior"] = "dance"
        dc["motion_style"] = "dancing"
    if "walk" in text:
        dc["character_behavior"] = "walk"
        dc["motion_style"] = "walking"
    if "drive" in text or "driving" in text:
        dc["motion_style"] = "driving"
    if "drift" in text:
        dc["motion_style"] = "drifting"

    # Render tier
    if "preview" in text or "draft" in text or "fast" in text:
        out["render_tier"] = "preview"
    if "final" in text or "cinematic quality" in text or "hero render" in text:
        out["render_tier"] = "cinematic"

    # Duration
    if "longer" in text:
        out["duration_seconds"] = 16
    if "shorter" in text:
        out["duration_seconds"] = 6

    return out


# ════════════════════════════════════════════════════════════════════════════
# Mutation application (safe surface area only)
# ════════════════════════════════════════════════════════════════════════════

_ALLOWED_DC_KEYS = {
    "motion_style",
    "camera_style",
    "scene_dynamics",
    "character_behavior",
    "energy_level",
}
_ALLOWED_SP_KEYS = {
    "lighting_preset",
    "camera_mode",
    "brand_primary",
    "focal_subject",
    "environment",
}


def _apply_mutation(manifest: dict, mutation: dict) -> dict:
    """
    Apply a mutation dict to a deep copy of the manifest. Only the
    whitelisted surface areas are touched.
    """
    new_manifest = copy.deepcopy(manifest)

    # directorial_controls
    dc_mut = mutation.get("directorial_controls") or {}
    if isinstance(dc_mut, dict) and dc_mut:
        existing = dict(new_manifest.get("directorial_controls") or {})
        for k, v in dc_mut.items():
            if v is None:
                continue
            if k in _ALLOWED_DC_KEYS:
                existing[k] = v
        new_manifest["directorial_controls"] = existing

    # scene_params
    sp_mut = mutation.get("scene_params") or {}
    if isinstance(sp_mut, dict) and sp_mut:
        existing = dict(new_manifest.get("scene_params") or {})
        for k, v in sp_mut.items():
            if v is None:
                continue
            if k in _ALLOWED_SP_KEYS:
                existing[k] = v
        new_manifest["scene_params"] = existing

    # render_tier
    tier = mutation.get("render_tier")
    if isinstance(tier, str) and tier.strip():
        new_manifest["render_tier"] = tier.strip().lower()

    # duration_seconds
    dur = mutation.get("duration_seconds")
    if isinstance(dur, int) and 1 <= dur <= 120:
        new_manifest["duration_seconds"] = dur

    return new_manifest


# ════════════════════════════════════════════════════════════════════════════
# Serialization helpers for API responses
# ════════════════════════════════════════════════════════════════════════════

def step_to_dict(step: IterationStep) -> dict:
    return {
        "step_id": step.step_id,
        "parent_id": step.parent_id,
        "instruction": step.instruction,
        "source": step.source,
        "notes": step.notes,
        "created_at": step.created_at,
        "manifest": step.manifest,
    }
