"""
cinematic_setup.py
==================
Reusable cinematic quality orchestrator.

Templates call `apply_cinematic_base()` to get a complete scene-direction
baseline in one call instead of repeating boilerplate across every builder.

This module does NOT replace template-specific logic — it provides the shared
foundation that every family benefits from.

Usage in a template:
    from ..scene.cinematic_setup import apply_cinematic_base

    def build_my_scene(bpy, manifest, scene):
        ctx = apply_cinematic_base(bpy, scene, manifest, family="car_hero")
        # ctx contains the ground plane, atmosphere obj, etc.
        ...
"""
from __future__ import annotations

from .layout_ops import (
    ensure_hdri_world,
    ensure_world_background,
    ensure_scene_look,
    add_atmosphere_box,
    add_contact_shadow_gradient,
)

# ---------------------------------------------------------------------------
# Per-family presets — keeps template files short and consistent.
# Each preset overrides only the fields it cares about; everything else
# falls through to _DEFAULTS.
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "exposure": 0.0,
    "hdri_path": None,
    "hdri_strength": 1.15,
    "world_color": (0.05, 0.06, 0.08, 1.0),
    "world_strength": 1.25,
    "atmo_location": (0, 14, 6),
    "atmo_scale": (30, 12, 8),
    "atmo_density": 0.008,
    "atmo_color": (0.80, 0.85, 0.95, 1.0),
    "contact_shadow": True,
    "contact_radius": 2.5,
}

_FAMILY_PRESETS: dict[str, dict] = {
    "car_hero": {
        "exposure": 0.08,
        "hdri_path": "assets/hdri/qwantani_moon_noon_puresky_4k.exr",
        "hdri_strength": 1.15,
        "atmo_density": 0.005,
        "atmo_color": (0.75, 0.78, 0.88, 1.0),
        "contact_radius": 3.5,
    },
    "street_scene": {
        "exposure": 0.0,
        "hdri_path": "assets/hdri/citrus_orchard_road_puresky_4k.exr",
        "hdri_strength": 1.20,
        "atmo_density": 0.007,
        "atmo_color": (0.72, 0.75, 0.85, 1.0),
        "contact_radius": 2.0,
    },
    "scenic_landscape": {
        "exposure": 0.15,
        "hdri_path": "assets/hdri/horn-koppe_spring_4k.exr",
        "hdri_strength": 1.20,
        "atmo_density": 0.008,
        "atmo_color": (0.82, 0.86, 0.92, 1.0),
        "contact_shadow": False,   # landscapes don't need a contact disc
    },
    "ocean_scene": {
        "exposure": -0.12,
        "hdri_path": "assets/hdris/docklands_02_4k.exr",
        "hdri_strength": 0.85,
        "world_color": (0.03, 0.08, 0.12, 1.0),
        "atmo_density": 0.018,
        "atmo_color": (0.10, 0.35, 0.55, 1.0),
        "contact_shadow": False,
    },
    "character_stage": {
        "exposure": 0.0,
        "hdri_path": "assets/hdris/studio_small_03_4k.exr",
        "hdri_strength": 0.70,
        "world_color": (0.06, 0.065, 0.075, 1.0),
        "atmo_density": 0.003,
        "atmo_color": (0.60, 0.60, 0.65, 1.0),
        "atmo_scale": (14, 8, 6),
        "contact_radius": 1.8,
    },
    "product_scene": {
        "exposure": 0.05,
        "hdri_path": "assets/hdris/studio_clean_01.exr",
        "hdri_strength": 0.80,
        "world_color": (0.08, 0.08, 0.085, 1.0),
        "atmo_density": 0.002,
        "atmo_color": (0.70, 0.70, 0.72, 1.0),
        "atmo_scale": (10, 6, 5),
        "contact_radius": 1.2,
    },
    "city_loop": {
        "exposure": -0.05,
        "hdri_path": "assets/hdris/city_night_01.exr",
        "hdri_strength": 0.95,
        "atmo_density": 0.010,
        "atmo_color": (0.55, 0.55, 0.70, 1.0),
        "contact_shadow": False,
    },
}


def _resolve_preset(family: str) -> dict:
    """Merge family preset over defaults."""
    base = dict(_DEFAULTS)
    override = _FAMILY_PRESETS.get(family, {})
    base.update(override)
    return base


def apply_cinematic_base(
    bpy,
    scene,
    manifest: dict,
    family: str,
    *,
    subject_center: tuple = (0, 0, 0),
    override: dict | None = None,
) -> dict:
    """
    One-call cinematic baseline for any template.

    Returns a context dict with references to created objects so templates
    can adjust or skip pieces.

    Parameters
    ----------
    family        One of the _FAMILY_PRESETS keys (or a custom string that
                  falls through to _DEFAULTS).
    subject_center  XYZ where the main subject sits — contact shadow is placed
                    here.
    override      Optional dict to override any preset field for this call.
    """
    cfg = _resolve_preset(family)
    if override:
        cfg.update(override)

    ctx: dict = {"preset": cfg, "family": family}

    # --- Exposure ---
    ensure_scene_look(scene, exposure=cfg["exposure"])

    # --- HDRI sky ---
    hdri_used = False
    if cfg["hdri_path"]:
        hdri_used = ensure_hdri_world(bpy, scene, cfg["hdri_path"], strength=cfg["hdri_strength"])
    ctx["hdri_used"] = hdri_used

    if not hdri_used:
        ensure_world_background(scene, strength=cfg["world_strength"], color=cfg["world_color"])

    # --- Atmosphere ---
    atmo = add_atmosphere_box(
        bpy,
        location=cfg["atmo_location"],
        scale=cfg["atmo_scale"],
        density=cfg["atmo_density"],
        color=cfg["atmo_color"],
        name=f"{family}_Atmosphere",
    )
    ctx["atmosphere"] = atmo

    # --- Contact shadow ---
    if cfg["contact_shadow"]:
        shadow = add_contact_shadow_gradient(
            bpy,
            center=(subject_center[0], subject_center[1], subject_center[2] + 0.003),
            radius=cfg["contact_radius"],
            name=f"{family}_ContactShadow",
        )
        ctx["contact_shadow"] = shadow
    else:
        ctx["contact_shadow"] = None

    print(
        f"DEBUG cinematic_setup applied: family={family} "
        f"hdri={'yes' if hdri_used else 'fallback'} "
        f"atmo_density={cfg['atmo_density']} "
        f"contact={'yes' if cfg['contact_shadow'] else 'no'}",
        flush=True,
    )
    return ctx
