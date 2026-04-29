from __future__ import annotations

from typing import Any

from app.planning.scene_plan import GenerationInput, UIReference


def _pick(d: dict[str, Any], *keys: str, default=None):
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return default


def map_ui_payload_to_generation_input(payload: dict[str, Any]) -> GenerationInput:
    """
    Accepts current/future UI payloads and normalizes them into a stable backend input.
    This is designed to tolerate naming drift between frontend iterations.
    """

    manifest_name = _pick(
        payload,
        "manifest_name",
        "manifestName",
        "project_name",
        "projectName",
        default="Untitled_Production"
    )

    raw_prompt = _pick(
        payload,
        "core_objective_prompt",
        "coreObjectivePrompt",
        "prompt",
        "user_prompt",
        "raw_prompt",
        default=""
    )

    template_bias = _pick(
        payload,
        "template_bias",
        "templateBias",
        default="auto"
    )

    duration_seconds = int(_pick(
        payload,
        "timeline_duration_s",
        "timelineDurationSeconds",
        "duration_seconds",
        "duration",
        default=12
    ))

    brand_primary = _pick(
        payload,
        "brand_primary",
        "brandPrimary",
        "brand_primary_hex",
        "brandPrimaryHex",
        default="#0EA5E9"
    )

    sonic_frequency = _pick(
        payload,
        "sonic_frequency",
        "sonicFrequency",
        default=""
    )

    technical_style_constraints = _pick(
        payload,
        "technical_style_constraints",
        "technicalStyleConstraints",
        "style_constraints",
        default=""
    )

    refs_raw = _pick(payload, "references", "assets", "uploaded_assets", default=[]) or []
    references: list[UIReference] = []

    for item in refs_raw:
        if isinstance(item, str):
            references.append(UIReference(filename=item, kind="unknown"))
        elif isinstance(item, dict):
            references.append(
                UIReference(
                    filename=str(_pick(item, "filename", "name", default="unknown_reference")),
                    kind=str(_pick(item, "kind", "type", default="unknown"))
                )
            )

    return GenerationInput(
        manifest_name=str(manifest_name),
        raw_prompt=str(raw_prompt),
        template_bias=str(template_bias),
        duration_seconds=duration_seconds,
        brand_primary=str(brand_primary),
        sonic_frequency=str(sonic_frequency),
        technical_style_constraints=str(technical_style_constraints),
        references=references,
        raw_ui_context=dict(payload),
    )

