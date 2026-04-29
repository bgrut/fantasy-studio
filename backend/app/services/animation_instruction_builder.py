from __future__ import annotations

from app.planning.scene_plan import AnimationInstruction, ScenePlan


def build_animation_payload(scene_plan: ScenePlan) -> list[dict]:
    payload: list[dict] = []

    for item in scene_plan.animation_instructions:
        payload.append({
            "subject": item.subject,
            "action": item.action,
            "mode": item.mode,
            "intensity": item.intensity,
            "timing": item.timing,
            "notes": item.notes,
        })

    return payload


