from __future__ import annotations

"""
quality_eval.py
===============
Lightweight rule-based scene quality evaluation framework.

Runs after scene construction (but before render) to log potential quality
issues.  Does NOT fix anything automatically -- it logs structured warnings
that can drive future retry/adjustment logic.

Usage:
    from ..scene.quality_eval import evaluate_scene, log_evaluation

    issues = evaluate_scene(bpy, scene, subject_meshes, scene_plan)
    log_evaluation(issues)

Each issue is a dict:
    {"check": str, "severity": "warning"|"error", "detail": str, "value": float}
"""

from .layout_ops import bounds_world, _get_depsgraph


# ═══════════════════════════════════════════════════════════════════════════
# Individual checks
# ═══════════════════════════════════════════════════════════════════════════

def _check_subject_too_small(
    scene, cam, subject_meshes, depsgraph=None,
) -> dict | None:
    """
    Subject occupies too little of the frame.
    Uses approximate projected height vs render height.
    """
    if not subject_meshes or not cam:
        return None

    mins, maxs = bounds_world(subject_meshes, depsgraph)
    if mins is None:
        return None

    subject_height = maxs.z - mins.z
    subject_center_y = (mins.y + maxs.y) * 0.5

    # Approximate: ratio of subject height to distance from camera
    cam_dist = abs(cam.location.y - subject_center_y)
    if cam_dist < 0.1:
        return None

    # Rough angular coverage (simplified, ignores lens properly)
    angular_ratio = subject_height / cam_dist
    if angular_ratio < 0.08:
        return {
            "check": "subject_too_small",
            "severity": "warning",
            "detail": f"Subject angular ratio {angular_ratio:.3f} < 0.08 threshold",
            "value": angular_ratio,
        }
    return None


def _check_dead_foreground(
    scene, cam, subject_meshes, depsgraph=None,
) -> dict | None:
    """
    Too much empty space between camera and subject (dead foreground).
    """
    if not subject_meshes or not cam:
        return None

    mins, maxs = bounds_world(subject_meshes, depsgraph)
    if mins is None:
        return None

    # Distance from camera to nearest subject edge
    cam_y = cam.location.y
    nearest_y = mins.y
    gap = nearest_y - cam_y

    # If camera is very far from subjects with nothing in between
    if gap > 12.0:
        return {
            "check": "dead_foreground",
            "severity": "warning",
            "detail": f"Camera-to-subject gap {gap:.1f}m with no foreground elements",
            "value": gap,
        }
    return None


def _check_empty_sky(
    scene, cam, subject_meshes, depsgraph=None,
) -> dict | None:
    """
    Subject is very low in frame, leaving too much empty sky.
    """
    if not subject_meshes or not cam:
        return None

    mins, maxs = bounds_world(subject_meshes, depsgraph)
    if mins is None:
        return None

    subject_top = maxs.z
    cam_z = cam.location.z

    # If camera is much higher than subject top, sky will dominate
    if cam_z > subject_top + 5.0:
        return {
            "check": "empty_sky",
            "severity": "warning",
            "detail": f"Camera z={cam_z:.1f} is {cam_z - subject_top:.1f}m above subject top",
            "value": cam_z - subject_top,
        }
    return None


def _check_horizon_mismatch(
    scene, cam, subject_meshes, scene_plan=None, depsgraph=None,
) -> dict | None:
    """
    Camera height doesn't match the family's intended feel.
    E.g., a car_hero shot should be low, not overhead.
    """
    if not cam or not scene_plan:
        return None

    family = scene_plan.get("scene_family", "")
    cam_z = cam.location.z

    # Family-specific expectations
    expected_ranges = {
        "car_hero": (0.5, 2.5),        # low angle
        "street_scene": (1.5, 4.0),     # eye-level to slightly above
        "scenic_landscape": (2.0, 8.0), # grounded to moderate crane
        "ocean_scene": (1.0, 5.0),      # submerged to surface
        "character_stage": (1.5, 3.5),   # eye-level
        "product_scene": (0.3, 2.0),     # intimate
    }

    expected = expected_ranges.get(family)
    if not expected:
        return None

    low, high = expected
    if cam_z < low or cam_z > high:
        return {
            "check": "horizon_mismatch",
            "severity": "warning",
            "detail": f"Camera z={cam_z:.1f} outside expected range [{low}, {high}] for {family}",
            "value": cam_z,
        }
    return None


def _check_weak_grounding(
    scene, cam, subject_meshes, depsgraph=None,
) -> dict | None:
    """
    Subject bottom face is floating above ground plane (z > 0.05).
    """
    if not subject_meshes:
        return None

    mins, maxs = bounds_world(subject_meshes, depsgraph)
    if mins is None:
        return None

    if mins.z > 0.05:
        return {
            "check": "weak_grounding",
            "severity": "warning",
            "detail": f"Subject bottom at z={mins.z:.3f} -- appears to float above ground",
            "value": mins.z,
        }
    return None


def _check_subject_clipping(
    scene, cam, subject_meshes, depsgraph=None,
) -> dict | None:
    """
    Subject extends below ground (z < -0.1) suggesting sinking/clipping.
    Exempt scenic_landscape which intentionally sinks mountains.
    """
    if not subject_meshes:
        return None

    mins, maxs = bounds_world(subject_meshes, depsgraph)
    if mins is None:
        return None

    if mins.z < -0.1:
        return {
            "check": "subject_clipping",
            "severity": "warning",
            "detail": f"Subject bottom at z={mins.z:.3f} -- may be clipping through ground",
            "value": mins.z,
        }
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Main evaluation runner
# ═══════════════════════════════════════════════════════════════════════════

def evaluate_scene(
    bpy,
    scene,
    subject_meshes: list | None = None,
    scene_plan: dict | None = None,
    cam=None,
) -> list[dict]:
    """
    Run all quality checks and return list of issues found.
    Empty list = scene passed all checks.

    Parameters
    ----------
    bpy             Blender module
    scene           bpy scene
    subject_meshes  List of subject mesh objects (the main focus, not backdrop)
    scene_plan      Scene plan dict from director (optional)
    cam             Camera object (defaults to scene.camera)
    """
    if cam is None:
        cam = scene.camera

    depsgraph = _get_depsgraph(bpy)
    issues: list[dict] = []

    checks = [
        _check_subject_too_small,
        _check_dead_foreground,
        _check_empty_sky,
        _check_weak_grounding,
        _check_subject_clipping,
    ]

    for check_fn in checks:
        try:
            result = check_fn(scene, cam, subject_meshes, depsgraph)
            if result:
                issues.append(result)
        except Exception as e:
            print(f"[QUALITY] check {check_fn.__name__} failed: {e}", flush=True)

    # Horizon check needs scene_plan
    try:
        result = _check_horizon_mismatch(scene, cam, subject_meshes, scene_plan, depsgraph)
        if result:
            issues.append(result)
    except Exception as e:
        print(f"[QUALITY] horizon check failed: {e}", flush=True)

    return issues


def log_evaluation(issues: list[dict], family: str = "") -> None:
    """
    Log evaluation results in a structured format.
    """
    prefix = f"[QUALITY:{family}]" if family else "[QUALITY]"

    if not issues:
        print(f"{prefix} PASS -- all checks passed", flush=True)
        return

    for issue in issues:
        severity = issue.get("severity", "warning").upper()
        check = issue.get("check", "unknown")
        detail = issue.get("detail", "")
        print(f"{prefix} {severity}: {check} -- {detail}", flush=True)

    print(f"{prefix} {len(issues)} issue(s) found", flush=True)
