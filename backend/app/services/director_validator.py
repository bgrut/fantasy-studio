from __future__ import annotations

"""
director_validator.py
=====================
Post-LLM-director sanity layer.

The LLM director picks a `behavior`, `camera_style`, and other fields
from free-form prompts. It's smart but not perfect — we see failures like:

  - user says "Ferrari racing at golden hour" → director sets
    behavior="idle", camera_style="static" (a stationary Ferrari).
  - user says "eagle soaring over mountains" → director sets
    behavior="idle" (a perched eagle).
  - user says "cat dancing on a rooftop" → director sets
    behavior="character_performance" but leaves motion_style="idle".

These contradictions silently kill the animation layer. This validator
runs AFTER the director's output is projected onto the manifest and
BEFORE the render pipeline consumes it. It enforces a handful of
obvious-correctness rules without trying to out-think the director on
subtle calls.

Rules:
  1. Movement-verb actions (run/walk/race/fly/swim/gallop/dance/sprint
     /drive/soar/jump) MUST have a non-"idle" behavior. If director
     picked idle, overwrite with the verb itself.
  2. Vehicle subjects (car, motorcycle, plane, truck, etc.) with idle
     behavior get bumped to "driving".
  3. Moving subjects with "static" or "dolly_in" camera_style get
     bumped to "tracking" — static cameras on moving subjects lose
     the subject out of frame after 30 frames.
  4. Flying subjects (eagle, plane, dragon, ufo) with behavior=idle
     or camera looking DOWN get the camera pitched UP so the subject
     doesn't disappear below horizon.

Every rule is conservative, additive, and wrapped in a try/except — a
validator that crashes is worse than one that's occasionally wrong.
"""

# Motion-verb catalog. If the prompt or action field contains one of
# these, the subject is moving and behavior != idle.
_MOVEMENT_ACTIONS: set[str] = {
    "run", "running", "jog", "jogging", "sprint", "sprinting",
    "walk", "walking", "stroll", "strolling",
    "drive", "driving", "race", "racing", "cruise", "cruising",
    "fly", "flying", "soar", "soaring", "glide", "gliding",
    "swim", "swimming", "dive", "diving",
    "gallop", "galloping", "trot", "trotting",
    "dance", "dancing",
    "jump", "jumping", "leap", "leaping",
    "fight", "fighting", "attack", "attacking", "charge", "charging",
    "chase", "chasing",
}

# Subject → preferred behavior when the director left it at idle/ambient.
_SUBJECT_BEHAVIOR_HINTS: dict[str, str] = {
    # Vehicles
    "car": "driving", "ferrari": "driving", "lamborghini": "driving",
    "porsche": "driving", "bmw": "driving", "mustang": "driving",
    "corvette": "driving", "truck": "driving", "van": "driving",
    "motorcycle": "driving", "bike": "driving", "motorbike": "driving",
    "sedan": "driving", "coupe": "driving",
    # Aircraft
    "plane": "flying", "jet": "flying", "aircraft": "flying",
    # Birds
    "eagle": "flying", "hawk": "flying", "bird": "flying", "falcon": "flying",
    "owl": "flying",
    # Mythical flyers
    "dragon": "flying", "wyvern": "flying",
    # Marine (swimming is the natural idle)
    "dolphin": "swimming", "whale": "swimming", "shark": "swimming",
    "fish": "swimming",
    # Land animals that default to action-coded verbs when "just standing"
    # would look dead on video.
    "cheetah": "running", "horse": "galloping", "wolf": "running",
    "tiger": "walking", "lion": "walking",
}


def _flatten_prompt_blob(manifest: dict) -> str:
    """Every place the user's subject/action might be hiding."""
    parts: list[str] = []
    for k in ("topic", "prompt", "user_prompt", "subject", "action"):
        v = manifest.get(k)
        if v:
            parts.append(str(v))
    plan = manifest.get("_scene_plan") or manifest.get("scene_plan") or {}
    if isinstance(plan, dict):
        for k in ("subject", "action", "animation_style", "motion_style"):
            v = plan.get(k)
            if v:
                parts.append(str(v))
    dc = manifest.get("directorial_controls") or {}
    if isinstance(dc, dict):
        for k in ("behavior", "motion_style", "camera_style"):
            v = dc.get(k)
            if v:
                parts.append(str(v))
    return " ".join(parts).lower()


def _first_movement_verb(blob: str) -> str | None:
    """Return the first movement verb found in the blob, or None."""
    for verb in _MOVEMENT_ACTIONS:
        if len(verb) < 4:
            continue
        # Word-ish boundary check — avoid "run" matching "truncate".
        for sep in (" ", ",", ".", "_", "-", "!", "?", ";", ":"):
            if f"{sep}{verb}" in blob or blob.startswith(f"{verb}{sep}"):
                return verb
        # Fallback: long-enough verbs can match as bare substrings
        # ("soar" in "soaring").
        if len(verb) >= 5 and verb in blob:
            return verb
    return None


def _subject_hint(blob: str) -> str | None:
    """Match blob against _SUBJECT_BEHAVIOR_HINTS — return the hinted behavior."""
    for subj, hint in _SUBJECT_BEHAVIOR_HINTS.items():
        for sep in (" ", ",", ".", "_", "-"):
            if f"{sep}{subj}" in blob or blob.startswith(f"{subj}{sep}"):
                return hint
        if len(subj) >= 5 and subj in blob:
            return hint
    return None


def validate_director_output(manifest: dict) -> dict:
    """
    Enforce behavior / camera_style sanity on an LLM-produced manifest.

    Never raises. Mutates `manifest["directorial_controls"]` in place
    and also updates `manifest["_scene_plan"]` motion fields so
    downstream consumers that read from either see a consistent value.
    """
    try:
        dc = dict(manifest.get("directorial_controls") or {})
        behavior = str(dc.get("behavior") or "").lower().strip()
        cam_style = str(dc.get("camera_style") or "").lower().strip()

        blob = _flatten_prompt_blob(manifest)
        moved = False

        # ── Rule 1: movement verb vs idle behavior ──────────────────────
        verb = _first_movement_verb(blob)
        if verb and behavior in ("", "idle", "ambient", "character_performance"):
            # "dance" → "dancing" canonical form for downstream matches.
            canonical = verb if verb.endswith("ing") else (
                verb + "ing" if not verb.endswith("e") else verb[:-1] + "ing"
            )
            dc["behavior"] = canonical
            behavior = canonical
            moved = True
            print(
                f"[DIRECTOR_VALIDATE] rule 1: movement verb {verb!r} found — "
                f"behavior set to {canonical!r}",
                flush=True,
            )

        # ── Rule 2: vehicle / subject-specific behavior fallback ────────
        if not behavior or behavior in ("idle", "ambient"):
            hint = _subject_hint(blob)
            if hint:
                dc["behavior"] = hint
                behavior = hint
                moved = True
                print(
                    f"[DIRECTOR_VALIDATE] rule 2: subject hint → behavior={hint!r}",
                    flush=True,
                )

        # ── Rule 3: moving subject + static camera = bad ────────────────
        if (verb or (behavior and behavior not in ("idle", "ambient", "sitting",
                                                   "standing", "lying"))):
            if cam_style in ("static", "dolly_in", "locked"):
                dc["camera_style"] = "tracking"
                cam_style = "tracking"
                print(
                    f"[DIRECTOR_VALIDATE] rule 3: moving subject on "
                    f"static camera — switched to tracking",
                    flush=True,
                )

        # ── Rule 4: flying subject needs upward-pitched camera ─────────
        fly_hints = ("fly", "flying", "soar", "soaring", "glide", "gliding")
        if any(h in blob for h in fly_hints):
            pitch = dc.get("camera_pitch_hint")
            if pitch in (None, "", "down", "level"):
                dc["camera_pitch_hint"] = "up"
                print(
                    "[DIRECTOR_VALIDATE] rule 4: flying subject — camera "
                    "pitch hint set to 'up'",
                    flush=True,
                )

        manifest["directorial_controls"] = dc

        # Mirror behavior into _scene_plan so consumers that read from
        # either field see a consistent value.
        plan = manifest.setdefault("_scene_plan", {})
        if isinstance(plan, dict) and behavior:
            if not plan.get("animation_style") or plan.get("animation_style") == "idle":
                plan["animation_style"] = behavior
            if not plan.get("action") or plan.get("action") == "idle":
                plan["action"] = behavior

        if not moved:
            print("[DIRECTOR_VALIDATE] no corrections needed", flush=True)
    except Exception as e:
        print(f"[DIRECTOR_VALIDATE] validator crashed (non-fatal): {e}", flush=True)
    return manifest
