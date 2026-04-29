from __future__ import annotations

"""
executor.py
===========
Fork A executor — translates a V2 recipe into scene_plan fields that the
existing V1.1 preset system (cinematic_presets.apply_*) already consumes.

This keeps V1.3 additive: no template builder code changes, no
render_from_manifest.py churn, no Blender ops.  The dispatcher picks a
recipe, the executor writes its decisions into manifest["scene_plan"],
and the existing template builder reads them exactly as if a human had
typed them.

Later rounds can swap this for a Blender-direct executor without
touching layer/recipe files.

Canonical slot order:
    base → environment → composition → lighting → animation → ambient → post

Each slot's layer JSON is a pure-data blob whose `applies` dict we merge
with any per-slot `overrides` from the recipe, then dispatch to a
slot-specific mapper below.

All writes go into manifest["scene_plan"]; a few flags also go on
manifest itself (``_template_v2_applied``, ``_template_v2_recipe``).
"""

from typing import Any

from .registry import TemplateRegistry, LAYER_KINDS


# ── slot mappers ───────────────────────────────────────────────────────
# Each mapper takes (scene_plan_dict, merged_applies_dict, log_fn) and
# mutates scene_plan in place.  Return value ignored.

def _map_base(sp: dict, body: dict, log) -> None:
    # Render tier hint — the request's render_tier still takes precedence
    # inside blender_runner, so this is a suggestion only.
    if "render_tier" in body:
        sp["render_tier_hint"] = body["render_tier"]
    if "duration_frames" in body:
        sp["duration_frames_hint"] = int(body["duration_frames"])
    if "resolution_hint" in body:
        sp["resolution_hint"] = body["resolution_hint"]
    log(f"base={body}")


def _map_environment(sp: dict, body: dict, log) -> None:
    if "preset_name" in body:
        sp["environment_preset"] = body["preset_name"]
    # Optional hints consumed by V1.1 forced-env block if present
    for k in ("ground_material", "ground_plane_size_m", "skybox_hint",
              "horizon_treatment"):
        if k in body:
            sp[k] = body[k]
    log(f"environment preset={body.get('preset_name')!r}")


def _map_composition(sp: dict, body: dict, log) -> None:
    # Camera preset comes from cinematic_presets.CAMERA_PRESETS
    if "preset_name" in body:
        sp["camera_preset"] = body["preset_name"]
    # Shot semantics — carried through to frame/verify logs
    for k in ("shot_type", "lens_mm", "distance_multiplier",
              "angle_pitch_deg", "angle_yaw_deg",
              "height_above_hero_m", "target_offset",
              "subject_screen_position"):
        if k in body:
            sp[k] = body[k]
    log(f"composition preset={body.get('preset_name')!r} shot={body.get('shot_type')!r}")


def _map_lighting(sp: dict, body: dict, log) -> None:
    if "preset_name" in body:
        sp["lighting_preset"] = body["preset_name"]
    for k in ("key_energy_multiplier", "rim_light", "ambient_intensity",
              "hdri_keywords", "time_of_day_hint"):
        if k in body:
            sp[k] = body[k]
    log(f"lighting preset={body.get('preset_name')!r}")


def _map_animation(sp: dict, body: dict, log) -> None:
    # style maps 1:1 to directorial_motion._MOTION_PROFILES keys.
    # Valid today: vehicle_drive, vehicle_drift, character_walk,
    # character_dance, idle_breathe.  Future camera profiles (orbit,
    # push_in, epic_pullback) land here in Phase 5.
    if "style" in body:
        sp["animation_style"] = body["style"]
    for k in ("speed", "intensity", "camera_motion", "duration_frames",
              "stagger_frames"):
        if k in body:
            sp[k if k != "duration_frames" else "animation_duration_frames"] = body[k]
    log(f"animation style={body.get('style')!r}")


def _map_ambient(sp: dict, body: dict, log) -> None:
    # Ambient is a list — multiple effects can stack.
    fx = body.get("effect_name") or body.get("name")
    if not fx:
        log("ambient: no effect_name, skipping")
        return
    lst = sp.setdefault("ambient_effects", [])
    lst.append({
        "name": fx,
        **{k: v for k, v in body.items() if k not in ("effect_name",)},
    })
    log(f"ambient effect={fx!r}")


def _map_post(sp: dict, body: dict, log) -> None:
    if "preset_name" in body:
        sp["post_preset"] = body["preset_name"]
    for k in ("grade", "bloom_intensity", "vignette", "grain", "contrast"):
        if k in body:
            sp[k] = body[k]
    log(f"post preset={body.get('preset_name')!r}")


_MAPPERS = {
    "base":        _map_base,
    "environment": _map_environment,
    "composition": _map_composition,
    "lighting":    _map_lighting,
    "animation":   _map_animation,
    "ambient":     _map_ambient,
    "post":        _map_post,
}


# ── public entry point ─────────────────────────────────────────────────

def apply_recipe(
    manifest: dict,
    recipe: dict,
    registry: TemplateRegistry,
    log_prefix: str = "[TEMPLATE_V2]",
) -> dict:
    """Mutate ``manifest`` in place by applying every layer in ``recipe``.

    Returns the same manifest for chaining convenience.

    Missing layers (dangling references) are skipped with a warning —
    the dispatcher already validated references at load time, so this
    only triggers if someone mutates the registry mid-flight.
    """
    def _log(msg: str) -> None:
        print(f"{log_prefix} {msg}", flush=True)

    _log(f"DISPATCH selected recipe={recipe.get('name')!r}")

    sp = manifest.setdefault("scene_plan", {})
    overrides_all = recipe.get("overrides") or {}
    layers_ref = recipe.get("layers") or {}

    # V1.3 batch-2 Bug 3b: recipe `template` field overrides the LLM's
    # template_name choice.  A specialized recipe (e.g. cat_canyon_cinematic
    # with template=scenic_landscape) is a MORE specific directorial
    # decision than the family classifier's choice, so it wins.
    # MUST use `in` membership test — recipe.get() would blank the field
    # for recipes that omit `template` (like _default), which would
    # stomp the LLM's choice with None.
    if "template" in recipe:
        prev = manifest.get("template_name")
        manifest["template_name"] = recipe["template"]
        _log(
            f"template override: template_name={recipe['template']!r} "
            f"(was {prev!r}) from recipe={recipe.get('name')!r}"
        )

    for slot in LAYER_KINDS:
        ref = layers_ref.get(slot)
        if not ref:
            continue
        refs = ref if isinstance(ref, list) else [ref]
        for layer_name in refs:
            layer = registry.get_layer(slot, layer_name)
            if layer is None:
                _log(f"WARN unresolved layer {slot}={layer_name!r}, skipping")
                continue
            merged = dict(layer.get("applies") or {})
            # Per-slot overrides apply to every referenced layer in that
            # slot (rare: only ambient is list-valued in practice).
            merged.update(overrides_all.get(slot) or {})
            mapper = _MAPPERS.get(slot)
            if mapper is None:
                _log(f"WARN no mapper for slot={slot}, skipping")
                continue
            mapper(sp, merged, lambda m, s=slot, n=layer_name: _log(f"LAYER {s}={n!r} | {m}"))

    manifest["_template_v2_applied"] = True
    manifest["_template_v2_recipe"] = recipe.get("name")
    _log(f"COMPLETE recipe={recipe.get('name')!r}")
    return manifest
