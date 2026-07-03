"""
Quadruped anatomical pattern.

Covers cats, dogs, foxes, rabbits, sheep, horses, lions, etc. The LLM picks
proportions via the slots; the pattern instantiates the actual geometry.

Anatomy (all coordinates in Blender world space, Z-up, +X is forward):
    body          — main torso (sphere, scaled long)
    head          — front-up sphere
    snout         — small cylinder extending from head (optional, prominent on dog/fox)
    ear_l, ear_r  — cones on top of head
    eye_l, eye_r  — small black-glossy spheres
    leg_fl, fr,
       bl, br     — 4 cylinders
    tail          — cylinder, angled up or trailing
    (paws)        — small spheres at leg ends (optional, on cats)

Pose variants:
    "standing"   — default, all legs down
    "sitting"    — back legs folded, front legs straight, body lower at rear
    "lying"      — body close to ground, head forward

Proportion presets (from species hint in slots):
    cat:    short body, large head ratio, long tail, pointed ears
    dog:    medium body, prominent snout, floppy ears (or pointed)
    fox:    cat-like but with bushy tail and pointier features
    rabbit: short body, very long ears, tiny tail
    sheep:  fluffy body, small head, stub tail
    horse:  long body, long legs, mane (chunky cylinder along neck)
    lion:   large body, prominent mane (multiple spheres around head)
"""

import math
from typing import Any, Dict, List
from . import register_pattern


# Species-driven proportion tweaks. Each value modifies the base anatomy.
SPECIES_PRESETS = {
    "cat": {
        "body_scale":   [1.4, 0.65, 0.55],
        "head_scale":   [0.55, 0.50, 0.50],
        "head_offset":  [1.0, 0, 0.45],
        "snout_length": 0.0,   # cats have flat faces
        "ear_size":     0.32,
        "ear_angle":    0.25,  # pointed up
        "ear_tilt":     0.35,  # spread outward
        "leg_length":   0.55,
        "leg_thickness": 0.16,
        "tail_length": 1.2,
        "tail_thickness": 0.10,
        "tail_angle":   1.2,    # raised
    },
    "dog": {
        "body_scale":   [1.5, 0.70, 0.60],
        "head_scale":   [0.55, 0.50, 0.55],
        "head_offset":  [1.0, 0, 0.40],
        "snout_length": 0.45,
        "ear_size":     0.28,
        "ear_angle":    -0.4,   # floppy
        "ear_tilt":     0.45,
        "leg_length":   0.65,
        "leg_thickness": 0.18,
        "tail_length": 0.8,
        "tail_thickness": 0.10,
        "tail_angle":   0.6,
    },
    "fox": {
        "body_scale":   [1.3, 0.55, 0.50],
        "head_scale":   [0.50, 0.45, 0.45],
        "head_offset":  [1.0, 0, 0.40],
        "snout_length": 0.30,
        "ear_size":     0.38,
        "ear_angle":    0.30,
        "ear_tilt":     0.30,
        "leg_length":   0.50,
        "leg_thickness": 0.13,
        "tail_length": 1.3,
        "tail_thickness": 0.18,  # bushy
        "tail_angle":   0.5,
    },
    "rabbit": {
        "body_scale":   [0.9, 0.65, 0.60],
        "head_scale":   [0.50, 0.45, 0.50],
        "head_offset":  [0.65, 0, 0.55],
        "snout_length": 0.10,
        "ear_size":     0.55,
        "ear_angle":    0.10,   # tall, straight up
        "ear_tilt":     0.10,
        "leg_length":   0.50,
        "leg_thickness": 0.15,
        "tail_length": 0.15,    # stub
        "tail_thickness": 0.18,
        "tail_angle":   0.0,
    },
    "sheep": {
        "body_scale":   [1.2, 0.75, 0.70],
        "head_scale":   [0.45, 0.40, 0.45],
        "head_offset":  [0.95, 0, 0.30],
        "snout_length": 0.25,
        "ear_size":     0.18,
        "ear_angle":    -0.3,
        "ear_tilt":     0.55,
        "leg_length":   0.60,
        "leg_thickness": 0.14,
        "tail_length": 0.25,
        "tail_thickness": 0.10,
        "tail_angle":   -0.3,
    },
    "horse": {
        "body_scale":   [1.8, 0.65, 0.80],
        "head_scale":   [0.45, 0.40, 0.55],
        "head_offset":  [1.4, 0, 0.80],
        "snout_length": 0.65,
        "ear_size":     0.20,
        "ear_angle":    0.20,
        "ear_tilt":     0.30,
        "leg_length":   1.20,
        "leg_thickness": 0.16,
        "tail_length": 1.0,
        "tail_thickness": 0.12,
        "tail_angle":   -0.4,
    },
    "lion": {
        "body_scale":   [1.7, 0.80, 0.75],
        "head_scale":   [0.65, 0.65, 0.55],
        "head_offset":  [1.1, 0, 0.55],
        "snout_length": 0.30,
        "ear_size":     0.25,
        "ear_angle":    0.30,
        "ear_tilt":     0.40,
        "leg_length":   0.75,
        "leg_thickness": 0.22,
        "tail_length": 1.4,
        "tail_thickness": 0.13,
        "tail_angle":   -0.2,
    },
}


def _preset_for(slots: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the proportion preset based on subject name / library_query."""
    subj = slots["subject"]
    candidates = [
        (subj.get("name") or "").lower(),
        (subj.get("library_query") or "").lower(),
        " ".join(subj.get("aliases", [])).lower(),
    ]
    for c in candidates:
        for species in SPECIES_PRESETS:
            if species in c:
                return SPECIES_PRESETS[species]
    return SPECIES_PRESETS["cat"]  # safe default — most common request


def _pose_offsets(pose: str) -> Dict[str, float]:
    """Pose adjusts which legs fold and body height.

    Phase 15: aggressive offsets so silhouette actually reads. A sitting dog
    needs the *rear* to drop substantially while front legs stay vertical;
    too-subtle offsets look like a slightly hunched standing dog.
    """
    if pose == "sitting":
        # Rear legs fold flat under hips, body tilts back, head stays up alert.
        return {
            "body_z_offset": -0.18,
            "body_pitch": 0.35,       # front-up tilt (rear lower than front)
            "back_legs_z": -0.45,     # back paws on ground but legs folded
            "back_legs_tilt": 1.2,    # rotate so they read as folded
            "front_legs_z": 0.0,
            "head_lift": 0.18,
            "tail_drop": -0.10,
        }
    if pose == "lying":
        return {
            "body_z_offset": -0.40,
            "body_pitch": 0.0,
            "back_legs_z": -0.40,
            "back_legs_tilt": 1.4,
            "front_legs_z": -0.35,
            "head_lift": -0.25,
            "tail_drop": -0.20,
        }
    return {"body_z_offset": 0.0, "body_pitch": 0.0, "back_legs_z": 0.0,
            "back_legs_tilt": 0.0, "front_legs_z": 0.0, "head_lift": 0.0,
            "tail_drop": 0.0}


def instantiate(slots: Dict[str, Any]) -> List[Dict[str, Any]]:
    subj = slots["subject"]
    pose = subj.get("pose", "standing")
    overall_scale = float(subj.get("scale", 1.0))

    preset = dict(_preset_for(slots))
    # Allow per-prompt overrides from LLM
    for k, v in (subj.get("proportion_overrides") or {}).items():
        preset[k] = v

    p = preset
    pose_adj = _pose_offsets(pose)

    s = overall_scale  # convenience

    parts: List[Dict[str, Any]] = []

    # ── BODY (torso) — defined first; coords for other parts relative to body center
    body_z = 0.55 + pose_adj["body_z_offset"]
    parts.append({
        "name": "Body",
        "primitive": "sphere",
        "location": [0, 0, body_z * s],
        "scale": [p["body_scale"][0] * s, p["body_scale"][1] * s, p["body_scale"][2] * s],
        "size": 1.0,
        "role": "body",
        "modifiers": [{"kind": "subdivision", "settings": {"levels": 2, "render_levels": 3}}],
    })

    # ── HEAD
    head_z = body_z + p["head_offset"][2] + pose_adj["head_lift"]
    head_loc = [p["head_offset"][0] * s, 0, head_z * s]
    parts.append({
        "name": "Head",
        "primitive": "sphere",
        "location": head_loc,
        "scale": [p["head_scale"][0] * s, p["head_scale"][1] * s, p["head_scale"][2] * s],
        "size": 1.0,
        "role": "head",
        "modifiers": [{"kind": "subdivision", "settings": {"levels": 2, "render_levels": 3}}],
    })

    # ── SNOUT (optional — small cylinder extending from head)
    if p["snout_length"] > 0:
        snout_x = head_loc[0] + p["head_scale"][0] * 0.7 * s
        parts.append({
            "name": "Snout",
            "primitive": "sphere",
            "location": [snout_x, 0, head_z * s - 0.05],
            "scale": [p["snout_length"] * s, p["head_scale"][1] * 0.6 * s, p["head_scale"][2] * 0.6 * s],
            "size": 1.0,
            "role": "detail",
        })

    # ── EARS (cones, mirrored)
    ear_z = head_z + p["head_scale"][2] * 0.7
    ear_offset_y = p["head_scale"][1] * 0.55 * s
    for side, sign in (("L", 1), ("R", -1)):
        parts.append({
            "name": f"Ear_{side}",
            "primitive": "cone",
            "location": [head_loc[0] - 0.05 * s, sign * ear_offset_y, ear_z * s],
            "rotation": [sign * p["ear_tilt"], -p["ear_angle"], 0],
            "scale": [p["ear_size"] * s, p["ear_size"] * s, p["ear_size"] * 1.6 * s],
            "size": 1.0,
            "role": "detail",
        })

    # ── EYES — layered sclera + iris + pupil for proper reading eyes
    eye_x = head_loc[0] + p["head_scale"][0] * 0.5 * s
    eye_z = head_z * s + p["head_scale"][2] * 0.15 * s
    eye_offset_y = p["head_scale"][1] * 0.45 * s
    eye_r = 0.08 * s
    for side, sign in (("L", 1), ("R", -1)):
        ey = sign * eye_offset_y
        parts.append({
            "name": f"Eye_{side}",
            "primitive": "sphere",
            "location": [eye_x, ey, eye_z],
            "scale": [eye_r, eye_r, eye_r],
            "size": 1.0,
            "role": "detail",
            "material_hint": "eyes",
        })
        parts.append({
            "name": f"Iris_{side}",
            "primitive": "sphere",
            "location": [eye_x + eye_r * 0.55, ey, eye_z],
            "scale": [eye_r * 0.55, eye_r * 0.55, eye_r * 0.55],
            "size": 1.0,
            "role": "detail",
            "material_hint": "iris",
        })
        parts.append({
            "name": f"Pupil_{side}",
            "primitive": "sphere",
            "location": [eye_x + eye_r * 0.80, ey, eye_z],
            "scale": [eye_r * 0.25, eye_r * 0.25, eye_r * 0.25],
            "size": 1.0,
            "role": "detail",
            "material_hint": "pupil",
        })

    # ── LEGS (4 cylinders)
    leg_len = p["leg_length"]
    leg_r = p["leg_thickness"]
    body_half_x = p["body_scale"][0] * 0.6
    body_half_y = p["body_scale"][1] * 0.55
    leg_z = (body_z * s) - (p["body_scale"][2] * 0.5 * s) - (leg_len * 0.5 * s)
    for name, dx, dy in (
        ("Leg_FL",  body_half_x,  body_half_y),
        ("Leg_FR",  body_half_x, -body_half_y),
        ("Leg_BL", -body_half_x,  body_half_y),
        ("Leg_BR", -body_half_x, -body_half_y),
    ):
        is_back = name.startswith("Leg_B")
        z_offset = pose_adj.get("back_legs_z", 0.0) if is_back else pose_adj.get("front_legs_z", 0.0)
        rot_y = pose_adj.get("back_legs_tilt", 0.0) if is_back else 0.0
        parts.append({
            "name": name,
            "primitive": "cylinder",
            "location": [dx * s, dy * s, (leg_z + z_offset * s)],
            "rotation": [0, rot_y, 0],
            "scale": [leg_r * s, leg_r * s, leg_len * 0.5 * s],
            "size": 1.0,
            "role": "limb",
        })

    # ── TAIL (single cylinder, angled)
    tail_base = [-p["body_scale"][0] * 0.55 * s, 0, body_z * s + 0.05 * s]
    tail_len = p["tail_length"]
    parts.append({
        "name": "Tail",
        "primitive": "cylinder",
        "location": [
            tail_base[0] - tail_len * 0.4 * math.cos(p["tail_angle"]) * s,
            0,
            tail_base[2] + tail_len * 0.4 * math.sin(p["tail_angle"]) * s,
        ],
        "rotation": [0, math.pi / 2 - p["tail_angle"], 0],
        "scale": [p["tail_thickness"] * s, p["tail_thickness"] * s, tail_len * 0.5 * s],
        "size": 1.0,
        "role": "limb",
    })

    return parts


register_pattern("quadruped", instantiate)
