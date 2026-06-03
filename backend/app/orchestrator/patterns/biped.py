"""
Biped anatomical pattern.

Covers humans, characters, robots, aliens. Two arms + two legs + torso + head.

Anatomy:
    torso         — main body (cube or sphere, taller than wide)
    head          — sphere on top
    eye_l, eye_r  — small dark spheres
    arm_l, arm_r  — cylinders hanging from shoulders (or raised if pose=arms_up)
    hand_l, hand_r — small spheres at arm ends (optional)
    leg_l, leg_r  — cylinders below torso

Species presets:
    human    — proportional, soft features
    child    — bigger head ratio, smaller body
    robot    — boxy torso (cube), rectangular limbs
    alien    — elongated, larger head, thinner limbs
    character — generic stylized
"""

import math
from typing import Any, Dict, List
from . import register_pattern


SPECIES_PRESETS = {
    "human": {
        "torso_shape":   "sphere",
        "torso_scale":   [0.40, 0.30, 0.70],
        "head_offset_z": 0.65,
        "head_scale":    [0.32, 0.32, 0.38],
        "arm_length":    0.70,
        "arm_thickness": 0.10,
        "leg_length":    0.90,
        "leg_thickness": 0.12,
        "has_hands":     True,
        "blocky":        False,
    },
    "child": {
        "torso_shape":   "sphere",
        "torso_scale":   [0.32, 0.22, 0.55],
        "head_offset_z": 0.55,
        "head_scale":    [0.36, 0.36, 0.40],   # larger head ratio
        "arm_length":    0.55,
        "arm_thickness": 0.09,
        "leg_length":    0.65,
        "leg_thickness": 0.11,
        "has_hands":     True,
        "blocky":        False,
    },
    "robot": {
        "torso_shape":   "cube",
        "torso_scale":   [0.45, 0.32, 0.70],
        "head_offset_z": 0.65,
        "head_scale":    [0.32, 0.32, 0.32],
        "arm_length":    0.70,
        "arm_thickness": 0.13,
        "leg_length":    0.85,
        "leg_thickness": 0.15,
        "has_hands":     True,
        "blocky":        True,        # use cubes for limbs too
    },
    "alien": {
        "torso_shape":   "sphere",
        "torso_scale":   [0.30, 0.22, 0.55],
        "head_offset_z": 0.70,
        "head_scale":    [0.45, 0.40, 0.50],   # giant head
        "arm_length":    0.95,                  # spindly long arms
        "arm_thickness": 0.07,
        "leg_length":    0.85,
        "leg_thickness": 0.09,
        "has_hands":     False,
        "blocky":        False,
    },
    "character": {
        "torso_shape":   "sphere",
        "torso_scale":   [0.42, 0.32, 0.65],
        "head_offset_z": 0.60,
        "head_scale":    [0.36, 0.36, 0.40],
        "arm_length":    0.68,
        "arm_thickness": 0.11,
        "leg_length":    0.80,
        "leg_thickness": 0.13,
        "has_hands":     True,
        "blocky":        False,
    },
}


def _preset_for(slots: Dict[str, Any]) -> Dict[str, Any]:
    text = " ".join([
        (slots["subject"].get("name") or "").lower(),
        (slots["subject"].get("library_query") or "").lower(),
    ])
    for species in ("robot", "alien", "child", "human", "character"):
        if species in text:
            return SPECIES_PRESETS[species]
    if "person" in text or "man" in text or "woman" in text or "guy" in text or "girl" in text:
        return SPECIES_PRESETS["human"]
    if "kid" in text or "boy" in text or "girl" in text:
        return SPECIES_PRESETS["child"]
    return SPECIES_PRESETS["character"]


def _pose_offsets(pose: str) -> Dict[str, Any]:
    """Pose adjusts limb angles."""
    if pose == "arms_up":
        return {"arm_rotation_y": -1.2, "torso_z_offset": 0.0}
    if pose == "sitting":
        return {"arm_rotation_y": 0.0, "torso_z_offset": -0.20, "leg_z_offset": -0.20, "leg_rotation_y": 1.2}
    if pose == "running":
        return {"arm_rotation_y": 0.4, "torso_z_offset": 0.0, "leg_rotation_y": 0.3}
    return {"arm_rotation_y": 0.0, "torso_z_offset": 0.0}


def instantiate(slots: Dict[str, Any]) -> List[Dict[str, Any]]:
    subj = slots["subject"]
    pose = subj.get("pose", "standing")
    s = float(subj.get("scale", 1.0))

    p = _preset_for(slots)
    pose_adj = _pose_offsets(pose)
    limb_primitive = "cube" if p.get("blocky") else "cylinder"

    parts: List[Dict[str, Any]] = []

    # ── TORSO
    torso_height = p["torso_scale"][2] * 2
    leg_len = p["leg_length"]
    torso_z = leg_len + torso_height * 0.5 + pose_adj.get("torso_z_offset", 0.0)
    parts.append({
        "name": "Torso",
        "primitive": p["torso_shape"],
        "location": [0, 0, torso_z * s],
        "scale": [v * s for v in p["torso_scale"]],
        "size": 1.0,
        "role": "body",
        "modifiers": [{"kind": "subdivision", "settings": {"levels": 2, "render_levels": 2}}]
            if not p["blocky"] else [{"kind": "bevel", "settings": {"width": 0.04, "segments": 3}}],
    })

    # ── HEAD
    head_z = torso_z + p["head_offset_z"]
    parts.append({
        "name": "Head",
        "primitive": "sphere",
        "location": [0, 0, head_z * s],
        "scale": [v * s for v in p["head_scale"]],
        "size": 1.0,
        "role": "head",
        "modifiers": [{"kind": "subdivision", "settings": {"levels": 2, "render_levels": 2}}],
    })

    # ── EYES (front-facing — +X is forward) — layered sclera + iris + pupil
    eye_x = p["head_scale"][0] * 0.7
    eye_z = head_z + p["head_scale"][2] * 0.15
    eye_r = 0.06 * s
    for side, sign in (("L", 1), ("R", -1)):
        ey = sign * p["head_scale"][1] * 0.45 * s
        # Sclera (the white) — base sphere
        parts.append({
            "name": f"Eye_{side}",
            "primitive": "sphere",
            "location": [eye_x * s, ey, eye_z * s],
            "scale": [eye_r, eye_r, eye_r],
            "size": 1.0,
            "role": "detail",
            "material_hint": "eyes",
        })
        # Iris — smaller, pushed forward (+X) so it sits on the front of the sclera
        parts.append({
            "name": f"Iris_{side}",
            "primitive": "sphere",
            "location": [eye_x * s + eye_r * 0.55, ey, eye_z * s],
            "scale": [eye_r * 0.55, eye_r * 0.55, eye_r * 0.55],
            "size": 1.0,
            "role": "detail",
            "material_hint": "iris",
        })
        # Pupil — smallest, further forward, dead-center of iris
        parts.append({
            "name": f"Pupil_{side}",
            "primitive": "sphere",
            "location": [eye_x * s + eye_r * 0.80, ey, eye_z * s],
            "scale": [eye_r * 0.25, eye_r * 0.25, eye_r * 0.25],
            "size": 1.0,
            "role": "detail",
            "material_hint": "pupil",
        })

    # ── FACE FEATURES (nose, mouth, ears) — added as metaball blobs to fuse
    # into the head. Without these, biped faces look like blank balls. WITH them,
    # the head reads as a face.
    nose_x = p["head_scale"][0] * 0.85
    nose_z = head_z + p["head_scale"][2] * 0.02   # slightly below eye line
    parts.append({
        "name": "Nose",
        "primitive": "sphere",
        "location": [nose_x * s, 0, nose_z * s],
        "scale": [p["head_scale"][0] * 0.30 * s, p["head_scale"][1] * 0.20 * s, p["head_scale"][2] * 0.18 * s],
        "size": 1.0,
        "role": "detail",  # no material_hint → uses hero material → joins metaball
    })

    # Mouth — thin elongated blob below the nose
    mouth_x = p["head_scale"][0] * 0.78
    mouth_z = head_z - p["head_scale"][2] * 0.30
    parts.append({
        "name": "Mouth",
        "primitive": "sphere",
        "location": [mouth_x * s, 0, mouth_z * s],
        "scale": [p["head_scale"][0] * 0.18 * s, p["head_scale"][1] * 0.30 * s, p["head_scale"][2] * 0.08 * s],
        "size": 1.0,
        "role": "detail",
    })

    # ── DETAIL MESHES (Phase 15) — colored accents on top of metaball-fused face.
    # These have material_hint so they spawn AS SEPARATE PRIMITIVES (not merged),
    # giving the face actual readable features rather than a blank blob.

    # Nostrils — two dark dots on the front of the nose
    nostril_x = p["head_scale"][0] * 0.99
    nostril_z = nose_z - p["head_scale"][2] * 0.05
    nostril_y = p["head_scale"][1] * 0.08
    nostril_r = p["head_scale"][0] * 0.04
    for side, sign in (("L", 1), ("R", -1)):
        parts.append({
            "name": f"Nostril_{side}",
            "primitive": "sphere",
            "location": [nostril_x * s, sign * nostril_y * s, nostril_z * s],
            "scale": [nostril_r * s, nostril_r * s, nostril_r * s],
            "size": 1.0,
            "role": "detail",
            "material_hint": "nostril",
        })

    # Lips — flattened colored disk on the mouth blob (upper + lower)
    lips_x = p["head_scale"][0] * 0.92
    lips_y_scale = p["head_scale"][1] * 0.22
    lips_z_thick = p["head_scale"][2] * 0.035
    for tag, offset in (("Upper", 0.04), ("Lower", -0.04)):
        parts.append({
            "name": f"Lip_{tag}",
            "primitive": "sphere",
            "location": [lips_x * s, 0, (mouth_z + p["head_scale"][2] * offset) * s],
            "scale": [p["head_scale"][0] * 0.07 * s, lips_y_scale * s, lips_z_thick * s],
            "size": 1.0,
            "role": "detail",
            "material_hint": "lips",
        })

    # Ears — side blobs on the head
    ear_y = p["head_scale"][1] * 0.85
    ear_z = head_z + p["head_scale"][2] * 0.10
    for side, sign in (("L", 1), ("R", -1)):
        parts.append({
            "name": f"Ear_{side}",
            "primitive": "sphere",
            "location": [0, sign * ear_y * s, ear_z * s],
            "scale": [p["head_scale"][0] * 0.18 * s, p["head_scale"][1] * 0.22 * s, p["head_scale"][2] * 0.30 * s],
            "size": 1.0,
            "role": "detail",
        })

    # Brows — small blobs above the eyes (gives expression)
    brow_x = p["head_scale"][0] * 0.65
    brow_z = head_z + p["head_scale"][2] * 0.30
    for side, sign in (("L", 1), ("R", -1)):
        parts.append({
            "name": f"Brow_{side}",
            "primitive": "sphere",
            "location": [brow_x * s, sign * p["head_scale"][1] * 0.40 * s, brow_z * s],
            "scale": [p["head_scale"][0] * 0.20 * s, p["head_scale"][1] * 0.12 * s, p["head_scale"][2] * 0.06 * s],
            "size": 1.0,
            "role": "detail",
        })

    # ── ARMS — cylinders (or cubes if robot) hanging from shoulders
    shoulder_y = p["torso_scale"][1] + p["arm_thickness"] * 1.2
    shoulder_z = torso_z + p["torso_scale"][2] * 0.55
    arm_rot_y = pose_adj.get("arm_rotation_y", 0.0)
    for side, sign in (("L", 1), ("R", -1)):
        arm_z = shoulder_z - p["arm_length"] * 0.5 * math.cos(abs(arm_rot_y))
        arm_x = p["arm_length"] * 0.5 * math.sin(arm_rot_y)
        parts.append({
            "name": f"Arm_{side}",
            "primitive": limb_primitive,
            "location": [arm_x * s, sign * shoulder_y * s, arm_z * s],
            "rotation": [0, sign * arm_rot_y, 0] if arm_rot_y else [0, 0, 0],
            "scale": [p["arm_thickness"] * s, p["arm_thickness"] * s, p["arm_length"] * 0.5 * s],
            "size": 1.0,
            "role": "limb",
        })
        if p.get("has_hands"):
            hand_z = arm_z - p["arm_length"] * 0.5
            parts.append({
                "name": f"Hand_{side}",
                "primitive": "sphere",
                "location": [arm_x * s * 2, sign * shoulder_y * s, hand_z * s],
                "scale": [p["arm_thickness"] * 1.2 * s, p["arm_thickness"] * 1.2 * s, p["arm_thickness"] * 1.2 * s],
                "size": 1.0,
                "role": "detail",
            })

    # ── LEGS — cylinders below torso
    hip_offset_y = p["torso_scale"][1] * 0.5
    leg_rot_y = pose_adj.get("leg_rotation_y", 0.0)
    leg_z_offset = pose_adj.get("leg_z_offset", 0.0)
    leg_z = leg_len * 0.5 + leg_z_offset
    for side, sign in (("L", 1), ("R", -1)):
        rot_y = sign * leg_rot_y if leg_rot_y else 0
        parts.append({
            "name": f"Leg_{side}",
            "primitive": limb_primitive,
            "location": [0, sign * hip_offset_y * s, leg_z * s],
            "rotation": [0, rot_y, 0] if rot_y else [0, 0, 0],
            "scale": [p["leg_thickness"] * s, p["leg_thickness"] * s, leg_len * 0.5 * s],
            "size": 1.0,
            "role": "limb",
        })

    return parts


register_pattern("biped", instantiate)
