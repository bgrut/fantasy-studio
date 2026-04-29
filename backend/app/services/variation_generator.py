from __future__ import annotations

"""
variation_generator.py
======================
WS8 — Batch variation generation.

Given a seed manifest and a count, produce N meaningfully-different
directorial manifests so the user can compare alternative takes side-by-
side. Variation only touches the same surface area scene_iterator does
(directorial_controls + scene_params + render_tier + duration_seconds);
geometry and assets stay locked.

Strategy
--------
1. If the LLM is reachable, ask it for ``count`` distinct mutation dicts
   shaped like scene_iterator's mutation schema, each with a short
   ``label`` summarizing what changed.
2. If LLM is unreachable, use a built-in palette of preset mutations
   (golden_hour / blue_hour / neon_night / handheld / orbit / chaotic …)
   and rotate through it.
3. Apply each mutation through scene_iterator._apply_mutation so the
   safety boundary is identical to single-step iteration.
"""

import copy
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from .llm_service import is_available as llm_available
from .llm_service import structured_query
from . import scene_iterator


# ════════════════════════════════════════════════════════════════════════════
# Built-in fallback variation palette
# ════════════════════════════════════════════════════════════════════════════

_PRESET_VARIATIONS: list[dict] = [
    {
        "label": "Golden Hour Wide",
        "scene_params": {"lighting_preset": "golden_hour", "camera_mode": "wide"},
        "directorial_controls": {"energy_level": "calm", "scene_dynamics": "subtle"},
    },
    {
        "label": "Blue Hour Tracking",
        "scene_params": {"lighting_preset": "blue_hour"},
        "directorial_controls": {"camera_style": "tracking", "energy_level": "cinematic"},
    },
    {
        "label": "Neon Night Orbit",
        "scene_params": {"lighting_preset": "neon_night", "brand_primary": "#0EA5E9"},
        "directorial_controls": {"camera_style": "orbit", "energy_level": "high", "scene_dynamics": "cinematic"},
    },
    {
        "label": "Handheld Chaos",
        "directorial_controls": {
            "camera_style": "handheld",
            "energy_level": "chaotic",
            "scene_dynamics": "high_energy",
        },
    },
    {
        "label": "Static Hero Pose",
        "directorial_controls": {
            "camera_style": "reveal",
            "energy_level": "calm",
            "scene_dynamics": "static",
            "character_behavior": "idle",
        },
    },
    {
        "label": "Driving Energy",
        "directorial_controls": {
            "motion_style": "driving",
            "camera_style": "follow",
            "energy_level": "high",
        },
    },
]


# ════════════════════════════════════════════════════════════════════════════
# In-memory batch store
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class Variation:
    variation_id: str
    label: str
    mutation: dict
    manifest: dict
    render_result: dict | None = None


@dataclass
class VariationBatch:
    batch_id: str
    seed_manifest: dict
    variations: list[Variation] = field(default_factory=list)
    source: str = "fallback"  # "llm" or "fallback"


_BATCHES: dict[str, VariationBatch] = {}


def get_batch(batch_id: str) -> VariationBatch | None:
    return _BATCHES.get(batch_id)


# ════════════════════════════════════════════════════════════════════════════
# LLM-driven generation with fallback
# ════════════════════════════════════════════════════════════════════════════

_VARIATION_SCHEMA = {
    "variations": [
        {
            "label": "string",
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
        }
    ]
}

_VARIATION_SYSTEM = (
    "You are the directorial layer of a Blender cinematic engine. "
    "Given a base scene manifest, propose a batch of distinct directorial "
    "alternatives. Each variation must be meaningfully different (different "
    "lighting OR camera OR energy). Keep geometry and assets untouched. "
    "Each variation needs a short human label."
)


def _llm_variations(seed_manifest: dict, count: int) -> list[dict] | None:
    if not llm_available():
        return None
    user_prompt = (
        f"Produce exactly {count} variations for the manifest below.\n\n"
        + json.dumps(
            {
                "topic": seed_manifest.get("topic"),
                "template_name": seed_manifest.get("template_name"),
                "directorial_controls": seed_manifest.get("directorial_controls", {}),
                "scene_params": seed_manifest.get("scene_params", {}),
            },
            indent=2,
        )
    )
    try:
        parsed = structured_query(_VARIATION_SYSTEM, user_prompt, _VARIATION_SCHEMA, timeout=15.0)
    except Exception as e:
        print(f"[variation_generator] llm failed: {e}", flush=True)
        return None
    if not isinstance(parsed, dict):
        return None
    items = parsed.get("variations")
    if not isinstance(items, list) or not items:
        return None
    # Defensive trim
    return items[:count]


def _fallback_variations(count: int) -> list[dict]:
    out: list[dict] = []
    palette = _PRESET_VARIATIONS
    for i in range(count):
        preset = palette[i % len(palette)]
        out.append(copy.deepcopy(preset))
    return out


# ════════════════════════════════════════════════════════════════════════════
# Public entry point
# ════════════════════════════════════════════════════════════════════════════

def generate_variations(seed_manifest: dict, count: int = 4) -> VariationBatch:
    """
    Build a VariationBatch with `count` directorial alternatives. Does NOT
    render — that is the caller's job (the API endpoint typically renders
    each one synchronously, one at a time).
    """
    count = max(1, min(int(count or 4), 8))

    raw = _llm_variations(seed_manifest, count)
    source = "llm"
    if not raw:
        raw = _fallback_variations(count)
        source = "fallback"

    batch = VariationBatch(
        batch_id=uuid.uuid4().hex[:12],
        seed_manifest=copy.deepcopy(seed_manifest),
        source=source,
    )

    for item in raw:
        label = str(item.get("label") or "Variation")
        mutation = {
            "directorial_controls": item.get("directorial_controls") or {},
            "scene_params": item.get("scene_params") or {},
            "render_tier": item.get("render_tier"),
        }
        new_manifest = scene_iterator._apply_mutation(seed_manifest, mutation)
        batch.variations.append(
            Variation(
                variation_id=uuid.uuid4().hex[:8],
                label=label,
                mutation=mutation,
                manifest=new_manifest,
            )
        )

    _BATCHES[batch.batch_id] = batch
    return batch


def variation_to_dict(v: Variation) -> dict:
    return {
        "variation_id": v.variation_id,
        "label": v.label,
        "mutation": v.mutation,
        "manifest": v.manifest,
        "render_result": v.render_result,
    }


def batch_to_dict(b: VariationBatch) -> dict:
    return {
        "batch_id": b.batch_id,
        "source": b.source,
        "variations": [variation_to_dict(v) for v in b.variations],
    }
