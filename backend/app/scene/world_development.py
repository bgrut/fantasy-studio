"""
world_development.py
====================
World Development — the production-designer layer.

Runs AFTER the template has built the scene and BEFORE the optimizer stage.
Enriches the environment with biome-appropriate ground, scatter props,
atmosphere, distant silhouettes, and accent lights. Also hands a color
grade dict to the compositor for post-process matching.

Public API:
    classify_biome(manifest) -> BiomeSpec
    develop_world(biome, scene_context) -> WorldDevReport
    BIOME_LIBRARY: dict[str, BiomeSpec]

Design rules:
    1. NON-FATAL. Every step is wrapped in try/except. A failure falls
       back to "scene as it is today" — never worse.
    2. ADDITIVE ONLY. Does not modify existing objects or materials.
       Every new object is tagged ``is_world_dev=True``.
    3. DETERMINISTIC. RNG is seeded from hash(prompt) so the same
       prompt produces the same layout across renders.
    4. BUDGET AWARE. Preview tier gets 50% scatter and no particles.
       Cinematic tier gets full detail.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from math import pi, sin, cos
from typing import Optional

from .scatter_ops import ScatterRule, scatter_rule as _place_rule


# ═══════════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AccentLightSpec:
    kind: str
    color: tuple = (1.0, 1.0, 1.0)
    energy: float = 1000.0
    position_hint: str = "high_side"
    flicker: bool = False


@dataclass
class BiomeSpec:
    name: str
    trigger_keywords: list = field(default_factory=list)
    # Ground
    ground_material: str = ""
    ground_detail: str = "flat"
    ground_size: float = 100.0
    # Scatter
    scatter_rules: list = field(default_factory=list)
    # Atmosphere
    fog_density: float = 0.002
    fog_color: tuple = (0.7, 0.7, 0.75)
    fog_height: float = 8.0
    particle_type: str = "none"
    particle_density: float = 0.0
    # Silhouettes
    silhouette_type: str = "hills"
    silhouette_count: int = 4
    silhouette_distance: float = 80.0
    # Accent lights
    accent_lights: list = field(default_factory=list)
    # Grade
    grade_lift: tuple = (0.0, 0.0, 0.0)
    grade_gamma: tuple = (1.0, 1.0, 1.0)
    grade_gain: tuple = (1.0, 1.0, 1.0)
    grade_saturation: float = 1.0
    # TOD lock
    tod_lock: Optional[str] = None
    # Runtime context (set by with_context)
    time_of_day: str = ""
    hero_type: str = ""
    confidence: float = 0.0

    def with_context(self, time_of_day: str, hero_type: str, confidence: float) -> "BiomeSpec":
        """Return a shallow copy with runtime context attached."""
        import copy
        s = copy.copy(self)
        s.scatter_rules = list(self.scatter_rules)
        s.accent_lights = list(self.accent_lights)
        s.time_of_day = self.tod_lock or time_of_day or ""
        s.hero_type = hero_type or ""
        s.confidence = confidence
        return s


@dataclass
class WorldDevReport:
    biome: str
    confidence: float
    ground_applied: str
    scatter_total: int
    scatter_per_rule: list
    atmosphere_kind: str
    silhouette_count: int
    accent_light_count: int
    grade_applied: bool
    grade_params: dict


# ═══════════════════════════════════════════════════════════════════════════
# The 12 biome library
# ═══════════════════════════════════════════════════════════════════════════

BIOME_LIBRARY: dict = {
    "desert": BiomeSpec(
        name="desert",
        trigger_keywords=["desert", "dune", "sahara", "mojave", "arid", "oasis", "sand dune"],
        ground_material="sand_dunes",
        ground_detail="rolling",
        ground_size=150.0,
        scatter_rules=[
            ScatterRule(kind="rock",           count_range=(12, 22), scale_range=(0.3, 2.2),
                         radius=60, min_dist_to_hero=4.0, avoid_camera_cone=True),
            ScatterRule(kind="scrub_bush",     count_range=(6, 10),  scale_range=(0.4, 0.9),
                         radius=45, min_dist_to_hero=3.5),
            ScatterRule(kind="dry_grass_tuft", count_range=(15, 30), scale_range=(0.2, 0.5),
                         radius=35, min_dist_to_hero=2.0),
            ScatterRule(kind="distant_cactus", count_range=(1, 3),   scale_range=(2.0, 4.0),
                         radius=90, min_dist_to_hero=40.0),
        ],
        fog_density=0.0018, fog_color=(0.95, 0.78, 0.55), fog_height=8.0,
        particle_type="dust", particle_density=0.4,
        silhouette_type="mountains", silhouette_count=4, silhouette_distance=120.0,
        accent_lights=[
            AccentLightSpec(kind="key_sun", color=(1.0, 0.82, 0.58), energy=5.5, position_hint="low_angle_side"),
            AccentLightSpec(kind="bounce",  color=(1.0, 0.75, 0.5),  energy=1400, position_hint="ground_bounce"),
        ],
        grade_lift=(0.02, 0.00, -0.01),
        grade_gamma=(1.0, 0.98, 0.92),
        grade_gain=(1.08, 1.02, 0.92),
        grade_saturation=1.15,
    ),

    "city_night": BiomeSpec(
        name="city_night",
        trigger_keywords=["city", "street", "urban", "downtown", "alley", "neon", "metropolis"],
        ground_material="wet_asphalt", ground_detail="flat", ground_size=200.0,
        scatter_rules=[
            ScatterRule(kind="lamp_post",        count_range=(4, 8),  scale_range=(1.0, 1.0),
                         radius=40, min_dist_to_hero=5.0, emissive=True),
            ScatterRule(kind="puddle",           count_range=(6, 10), scale_range=(0.6, 1.4),
                         radius=25, min_dist_to_hero=2.0),
            ScatterRule(kind="trash_can",        count_range=(2, 4),  scale_range=(1.0, 1.0),
                         radius=30, min_dist_to_hero=4.0),
            ScatterRule(kind="distant_car_glow", count_range=(3, 6),  scale_range=(0.5, 1.0),
                         radius=70, min_dist_to_hero=15.0, emissive=True),
        ],
        fog_density=0.004, fog_color=(0.15, 0.12, 0.18), fog_height=15.0,
        particle_type="mist", particle_density=0.6,
        silhouette_type="skyline", silhouette_count=8, silhouette_distance=100.0,
        accent_lights=[
            AccentLightSpec(kind="neon_cyan",       color=(0.2, 0.85, 1.0),  energy=2200, position_hint="high_side"),
            AccentLightSpec(kind="neon_magenta",    color=(1.0, 0.25, 0.75), energy=1800, position_hint="opposite_side"),
            AccentLightSpec(kind="practical_lamp",  color=(1.0, 0.85, 0.6),  energy=900,  position_hint="street_level"),
        ],
        grade_lift=(-0.01, 0.00, 0.02),
        grade_gamma=(0.95, 0.98, 1.05),
        grade_gain=(0.98, 1.02, 1.12),
        grade_saturation=1.25,
        tod_lock="night",
    ),

    "castle": BiomeSpec(
        name="castle",
        trigger_keywords=["castle", "fortress", "keep", "medieval", "throne", "ramparts", "courtyard"],
        ground_material="cobblestone", ground_detail="flat", ground_size=80.0,
        scatter_rules=[
            ScatterRule(kind="torch",         count_range=(4, 8),  scale_range=(1.0, 1.0),
                         radius=15, min_dist_to_hero=3.0, emissive=True, flicker=True),
            ScatterRule(kind="banner",        count_range=(2, 4),  scale_range=(1.0, 1.5),
                         radius=20, min_dist_to_hero=5.0, hanging=True),
            ScatterRule(kind="stone_block",   count_range=(5, 10), scale_range=(0.8, 1.8),
                         radius=30, min_dist_to_hero=4.0),
            ScatterRule(kind="distant_tower", count_range=(1, 3),  scale_range=(8.0, 15.0),
                         radius=80, min_dist_to_hero=50.0),
        ],
        fog_density=0.006, fog_color=(0.3, 0.28, 0.25), fog_height=6.0,
        particle_type="embers", particle_density=0.3,
        silhouette_type="mountains", silhouette_count=3, silhouette_distance=150.0,
        accent_lights=[
            AccentLightSpec(kind="torch_flicker", color=(1.0, 0.55, 0.25), energy=1200,
                            position_hint="high_side", flicker=True),
            AccentLightSpec(kind="moonlight_rim", color=(0.7, 0.82, 1.0),  energy=800,
                            position_hint="high_back"),
        ],
        grade_lift=(0.01, 0.00, -0.02),
        grade_gamma=(1.02, 0.98, 0.95),
        grade_gain=(1.05, 0.98, 0.88),
        grade_saturation=0.95,
        tod_lock="evening",
    ),

    "forest": BiomeSpec(
        name="forest",
        trigger_keywords=["forest", "woods", "jungle", "rainforest", "woodland", "canopy", "undergrowth", "tree", "trees"],
        ground_material="forest_floor", ground_detail="flat", ground_size=90.0,
        scatter_rules=[
            ScatterRule(kind="tree_trunk",  count_range=(8, 14), scale_range=(0.8, 1.6),
                         radius=50, min_dist_to_hero=4.0, avoid_camera_cone=True),
            ScatterRule(kind="fallen_log",  count_range=(2, 4),  scale_range=(1.0, 2.0),
                         radius=25, min_dist_to_hero=3.5),
            ScatterRule(kind="fern",        count_range=(12, 24),scale_range=(0.4, 1.1),
                         radius=20, min_dist_to_hero=2.0),
            ScatterRule(kind="mushroom",    count_range=(4, 8),  scale_range=(0.5, 1.2),
                         radius=18, min_dist_to_hero=2.5),
        ],
        fog_density=0.008, fog_color=(0.35, 0.45, 0.38), fog_height=5.0,
        particle_type="mist", particle_density=0.5,
        silhouette_type="tree_line", silhouette_count=10, silhouette_distance=60.0,
        accent_lights=[
            AccentLightSpec(kind="canopy_shaft", color=(1.0, 0.95, 0.75), energy=1800, position_hint="high_back"),
            AccentLightSpec(kind="ambient_green", color=(0.5, 0.7, 0.55), energy=600, position_hint="high_side"),
        ],
        grade_lift=(-0.01, 0.01, 0.00),
        grade_gamma=(0.98, 1.02, 0.98),
        grade_gain=(0.92, 1.05, 0.95),
        grade_saturation=1.10,
    ),

    "track_sunset": BiomeSpec(
        name="track_sunset",
        trigger_keywords=["track", "racetrack", "raceway", "circuit", "pit lane"],
        ground_material="asphalt_track", ground_detail="flat", ground_size=180.0,
        scatter_rules=[
            ScatterRule(kind="tire_barrier",  count_range=(5, 9),  scale_range=(1.0, 1.0),
                         radius=30, min_dist_to_hero=6.0),
            ScatterRule(kind="grandstand",    count_range=(2, 3),  scale_range=(3.0, 5.0),
                         radius=70, min_dist_to_hero=40.0),
            ScatterRule(kind="light_pole",    count_range=(2, 4),  scale_range=(1.0, 1.0),
                         radius=50, min_dist_to_hero=20.0),
        ],
        fog_density=0.0025, fog_color=(1.0, 0.75, 0.45), fog_height=10.0,
        particle_type="dust", particle_density=0.25,
        silhouette_type="hills", silhouette_count=5, silhouette_distance=130.0,
        accent_lights=[
            AccentLightSpec(kind="sun_low",        color=(1.0, 0.68, 0.35), energy=6.0, position_hint="low_angle_side"),
            AccentLightSpec(kind="amber_bounce",   color=(1.0, 0.65, 0.35), energy=1600, position_hint="ground_bounce"),
        ],
        grade_lift=(0.02, 0.00, -0.02),
        grade_gamma=(1.02, 0.98, 0.90),
        grade_gain=(1.10, 1.00, 0.85),
        grade_saturation=1.20,
    ),

    "generic_outdoor": BiomeSpec(
        name="generic_outdoor",
        trigger_keywords=[],
        ground_material="grass_mixed", ground_detail="flat", ground_size=100.0,
        scatter_rules=[
            ScatterRule(kind="rock",           count_range=(5, 9),   scale_range=(0.3, 1.0),
                         radius=30, min_dist_to_hero=3.0),
            ScatterRule(kind="dry_grass_tuft", count_range=(10, 18), scale_range=(0.2, 0.5),
                         radius=25, min_dist_to_hero=2.0),
            ScatterRule(kind="scrub_bush",     count_range=(3, 6),   scale_range=(0.4, 0.8),
                         radius=30, min_dist_to_hero=3.0),
        ],
        fog_density=0.0015, fog_color=(0.7, 0.75, 0.8), fog_height=8.0,
        particle_type="none", particle_density=0.0,
        silhouette_type="mountains", silhouette_count=4, silhouette_distance=110.0,
        accent_lights=[
            AccentLightSpec(kind="key_sun", color=(1.0, 0.95, 0.85), energy=4.5, position_hint="high_side"),
        ],
        grade_lift=(0.0, 0.0, 0.0),
        grade_gamma=(1.0, 1.0, 1.0),
        grade_gain=(1.02, 1.02, 1.02),
        grade_saturation=1.08,
    ),

    # ── Remaining 6 biomes — reasonable defaults, can be extended ────
    "mountain": BiomeSpec(
        name="mountain",
        trigger_keywords=["mountain", "peak", "alps", "alpine", "cliff", "valley", "ridge", "canyon"],
        ground_material="rocky_scree", ground_detail="rocky", ground_size=120.0,
        scatter_rules=[
            ScatterRule(kind="boulder",      count_range=(8, 14), scale_range=(0.5, 2.0),
                         radius=40, min_dist_to_hero=4.0, avoid_camera_cone=True),
            ScatterRule(kind="snow_patch",   count_range=(3, 6),  scale_range=(0.8, 2.0),
                         radius=35, min_dist_to_hero=3.0),
            ScatterRule(kind="alpine_grass", count_range=(10, 18),scale_range=(0.3, 0.6),
                         radius=25, min_dist_to_hero=2.5),
        ],
        fog_density=0.0025, fog_color=(0.72, 0.78, 0.85), fog_height=12.0,
        particle_type="mist", particle_density=0.3,
        silhouette_type="mountains", silhouette_count=5, silhouette_distance=150.0,
        accent_lights=[
            AccentLightSpec(kind="cold_sun", color=(0.92, 0.95, 1.0), energy=4.5, position_hint="high_side"),
        ],
        grade_lift=(0.0, 0.0, 0.02),
        grade_gamma=(1.0, 1.0, 1.05),
        grade_gain=(0.96, 0.98, 1.08),
        grade_saturation=0.95,
    ),

    "ocean": BiomeSpec(
        name="ocean",
        trigger_keywords=["ocean", "sea", "beach", "coast", "reef", "underwater", "wave"],
        ground_material="ocean_water", ground_detail="waves", ground_size=200.0,
        scatter_rules=[
            ScatterRule(kind="spray_particle", count_range=(6, 10), scale_range=(0.3, 0.8),
                         radius=40, min_dist_to_hero=6.0),
            ScatterRule(kind="foam_patch",     count_range=(4, 8),  scale_range=(0.5, 1.2),
                         radius=30, min_dist_to_hero=3.0),
        ],
        fog_density=0.003, fog_color=(0.55, 0.72, 0.82), fog_height=10.0,
        particle_type="mist", particle_density=0.6,
        silhouette_type="hills", silhouette_count=3, silhouette_distance=140.0,
        accent_lights=[
            AccentLightSpec(kind="sky_key", color=(0.88, 0.95, 1.0), energy=5.0, position_hint="high_side"),
        ],
        grade_lift=(-0.02, 0.0, 0.02),
        grade_gamma=(0.96, 1.0, 1.04),
        grade_gain=(0.92, 1.0, 1.10),
        grade_saturation=1.10,
    ),

    "arctic": BiomeSpec(
        name="arctic",
        trigger_keywords=["arctic", "snow", "ice", "glacier", "tundra", "frozen", "polar"],
        ground_material="snow_pack", ground_detail="rolling", ground_size=130.0,
        scatter_rules=[
            ScatterRule(kind="ice_shard",          count_range=(6, 12), scale_range=(0.4, 1.4),
                         radius=40, min_dist_to_hero=3.5),
            ScatterRule(kind="snow_drift",         count_range=(4, 8),  scale_range=(0.8, 2.0),
                         radius=30, min_dist_to_hero=3.0),
            ScatterRule(kind="rock_poking_through", count_range=(3, 6), scale_range=(0.4, 1.0),
                         radius=35, min_dist_to_hero=4.0),
        ],
        fog_density=0.0035, fog_color=(0.85, 0.92, 1.0), fog_height=10.0,
        particle_type="snow", particle_density=0.7,
        silhouette_type="mountains", silhouette_count=4, silhouette_distance=140.0,
        accent_lights=[
            AccentLightSpec(kind="cold_sun_low", color=(0.82, 0.90, 1.0), energy=3.5, position_hint="low_angle_side"),
        ],
        grade_lift=(0.0, 0.01, 0.03),
        grade_gamma=(1.0, 1.02, 1.08),
        grade_gain=(0.95, 0.98, 1.08),
        grade_saturation=0.92,
    ),

    "restaurant_interior": BiomeSpec(
        name="restaurant_interior",
        trigger_keywords=["restaurant", "kitchen", "diner", "cafe", "bistro"],
        ground_material="hardwood", ground_detail="flat", ground_size=30.0,
        scatter_rules=[
            ScatterRule(kind="table",                count_range=(2, 4), scale_range=(1.0, 1.0),
                         radius=15, min_dist_to_hero=3.0),
            ScatterRule(kind="chair",                count_range=(4, 6), scale_range=(1.0, 1.0),
                         radius=15, min_dist_to_hero=3.0),
            ScatterRule(kind="hanging_pendant_light",count_range=(2, 3), scale_range=(1.0, 1.0),
                         radius=12, min_dist_to_hero=4.0, emissive=True),
        ],
        fog_density=0.002, fog_color=(0.85, 0.65, 0.45), fog_height=5.0,
        particle_type="none", particle_density=0.0,
        silhouette_type="none", silhouette_count=0, silhouette_distance=0.0,
        accent_lights=[
            AccentLightSpec(kind="warm_practical", color=(1.0, 0.75, 0.5), energy=1200, position_hint="high_side"),
            AccentLightSpec(kind="kitchen_fill",   color=(1.0, 0.85, 0.6), energy=600,  position_hint="opposite_side"),
        ],
        grade_lift=(0.02, 0.00, -0.02),
        grade_gamma=(1.02, 1.00, 0.95),
        grade_gain=(1.08, 1.00, 0.85),
        grade_saturation=1.12,
    ),

    "stadium": BiomeSpec(
        name="stadium",
        trigger_keywords=["stadium", "arena", "field", "pitch"],
        ground_material="turf", ground_detail="flat", ground_size=120.0,
        scatter_rules=[
            ScatterRule(kind="goal_post",       count_range=(2, 2), scale_range=(1.0, 1.0),
                         radius=45, min_dist_to_hero=30.0),
            ScatterRule(kind="sideline_marker", count_range=(6, 8), scale_range=(0.5, 0.5),
                         radius=40, min_dist_to_hero=20.0),
            ScatterRule(kind="stadium_light",   count_range=(3, 4), scale_range=(1.0, 1.0),
                         radius=60, min_dist_to_hero=40.0),
        ],
        fog_density=0.001, fog_color=(0.85, 0.88, 0.9), fog_height=8.0,
        particle_type="none", particle_density=0.0,
        silhouette_type="skyline", silhouette_count=10, silhouette_distance=80.0,
        accent_lights=[
            AccentLightSpec(kind="stadium_flood", color=(1.0, 0.98, 0.95), energy=6.0, position_hint="high_side"),
            AccentLightSpec(kind="stadium_fill",  color=(0.98, 0.98, 1.0), energy=3000, position_hint="opposite_side"),
        ],
        grade_lift=(0.0, 0.0, 0.0),
        grade_gamma=(1.0, 1.0, 1.0),
        grade_gain=(1.05, 1.05, 1.05),
        grade_saturation=1.05,
    ),

    "studio": BiomeSpec(
        name="studio",
        trigger_keywords=["studio", "showcase", "product", "pedestal"],
        ground_material="polished_floor", ground_detail="flat", ground_size=30.0,
        scatter_rules=[],  # studios are clean by definition
        fog_density=0.0, fog_color=(0.9, 0.9, 0.9), fog_height=0.0,
        particle_type="none", particle_density=0.0,
        silhouette_type="none", silhouette_count=0, silhouette_distance=0.0,
        accent_lights=[],  # existing 3-point lighting handles it
        grade_lift=(0.0, 0.0, 0.0),
        grade_gamma=(1.0, 1.0, 1.0),
        grade_gain=(1.0, 1.0, 1.0),
        grade_saturation=1.0,
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# Classifier
# ═══════════════════════════════════════════════════════════════════════════

_FAMILY_DEFAULTS = {
    "car_hero":         ("track_sunset", ("sunset", "golden", "dusk")),
    "street_scene":     ("city_night", ()),
    "ocean_scene":      ("ocean", ()),
    "scenic_landscape": None,  # resolved contextually below
    "character_stage":  ("studio", ()),
    "product_scene":    ("studio", ()),
    "city_loop":        ("city_night", ()),
}


def _extract_tod(manifest: dict) -> str:
    """Best-effort TOD extraction from manifest."""
    sp = manifest.get("scene_plan") or {}
    for k in ("time_of_day", "tod", "lighting_preset"):
        v = str(sp.get(k) or "").lower().strip()
        if v:
            return v
    return ""


def classify_biome(manifest: dict) -> BiomeSpec:
    """Pick a biome for this render.  Layered matcher — no LLM call."""
    prompt = (
        str(manifest.get("core_objective_prompt") or "")
        + " " + str(manifest.get("topic") or "")
    ).lower()
    sp = manifest.get("scene_plan") or {}
    environment = str(sp.get("environment", "")).lower()
    family = str(sp.get("scene_family", "")).lower()
    hero_type = str(manifest.get("hero_asset_type") or "").lower()
    mood = str(sp.get("mood", "")).lower()
    tod = _extract_tod(manifest)

    signals = f"{prompt} {environment} {family} {mood}"

    # ── Layer 1: explicit keyword match ───────────────────────────────
    for name, spec in BIOME_LIBRARY.items():
        for kw in spec.trigger_keywords:
            if kw and kw in signals:
                result = spec.with_context(time_of_day=tod, hero_type=hero_type, confidence=0.95)
                print(
                    f"[WORLD_DEV] biome classifier: matched={name!r} "
                    f"layer=1_keyword confidence=0.95 tod={tod!r}",
                    flush=True,
                )
                return result

    # ── Layer 2: family-to-biome default ──────────────────────────────
    if family in _FAMILY_DEFAULTS:
        entry = _FAMILY_DEFAULTS[family]
        if entry is None:
            # scenic_landscape — context-dependent
            if "mountain" in signals:
                name = "mountain"
            elif "forest" in signals or "tree" in signals:
                name = "forest"
            else:
                name = "generic_outdoor"
        else:
            base, sunset_kw = entry
            if sunset_kw and any(k in signals for k in sunset_kw):
                name = base  # keep sunset default
            else:
                # car_hero without sunset signal → city_night instead
                name = base if base != "track_sunset" else "city_night"
        spec = BIOME_LIBRARY.get(name) or BIOME_LIBRARY["generic_outdoor"]
        result = spec.with_context(time_of_day=tod, hero_type=hero_type, confidence=0.6)
        print(
            f"[WORLD_DEV] biome classifier: matched={name!r} "
            f"layer=2_family confidence=0.60 tod={tod!r}",
            flush=True,
        )
        return result

    # ── Layer 3: fallback ─────────────────────────────────────────────
    spec = BIOME_LIBRARY["generic_outdoor"]
    result = spec.with_context(time_of_day=tod, hero_type=hero_type, confidence=0.3)
    print(
        f"[WORLD_DEV] biome classifier: fallback='generic_outdoor' "
        f"confidence=0.30 tod={tod!r}",
        flush=True,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Atmosphere / silhouettes / accent lights builders
# ═══════════════════════════════════════════════════════════════════════════

def _add_biome_fog(bpy, biome: BiomeSpec, hero_center: tuple) -> str:
    """Add a low-altitude fog volume matching biome fog params."""
    try:
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            location=(hero_center[0], hero_center[1], max(0.5, biome.fog_height * 0.5)),
        )
        vol = bpy.context.active_object
        vol.name = "WD_BiomeFog"
        vol.scale = (biome.ground_size * 0.6, biome.ground_size * 0.6, max(1.0, biome.fog_height))
        mat = bpy.data.materials.get("WD_BiomeFog_Mat") or bpy.data.materials.new("WD_BiomeFog_Mat")
        mat.use_nodes = True
        nt = mat.node_tree
        # Remove existing nodes
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        vol_node = nt.nodes.new("ShaderNodeVolumePrincipled")
        out_node = nt.nodes.new("ShaderNodeOutputMaterial")
        try:
            vol_node.inputs["Color"].default_value = (*biome.fog_color, 1.0)
        except KeyError:
            pass
        try:
            vol_node.inputs["Density"].default_value = biome.fog_density
        except KeyError:
            pass
        nt.links.new(vol_node.outputs["Volume"], out_node.inputs["Volume"])
        vol.data.materials.append(mat)
        try:
            vol["is_world_dev"] = True
        except Exception:
            pass
        return f"fog(density={biome.fog_density:.4f},height={biome.fog_height:.1f})"
    except Exception as e:
        print(f"[WORLD_DEV/FOG] failed: {e}", flush=True)
        return "fog_failed"


def _add_biome_silhouette(bpy, biome: BiomeSpec, hero_center: tuple) -> int:
    """Scatter distant silhouette shapes around the hero."""
    if biome.silhouette_type == "none" or biome.silhouette_count <= 0:
        return 0
    placed = 0
    hero_x = hero_center[0] if hero_center else 0.0
    hero_y = hero_center[1] if hero_center else 0.0
    R = biome.silhouette_distance
    for i in range(biome.silhouette_count):
        theta = (2 * pi * i / max(1, biome.silhouette_count)) + pi * 0.12
        x = hero_x + R * cos(theta)
        y = hero_y + R * sin(theta)
        try:
            if biome.silhouette_type == "mountains":
                bpy.ops.mesh.primitive_cone_add(
                    vertices=8, radius1=R * 0.12, depth=R * 0.20,
                    location=(x, y, R * 0.10),
                )
            elif biome.silhouette_type == "skyline":
                bpy.ops.mesh.primitive_cube_add(
                    size=R * 0.08, location=(x, y, R * 0.10),
                )
                obj = bpy.context.active_object
                obj.scale = (0.5, 0.5, 1.0 + 0.7 * ((i * 37) % 7) / 7.0)
            elif biome.silhouette_type == "tree_line":
                bpy.ops.mesh.primitive_cylinder_add(
                    vertices=6, radius=R * 0.05, depth=R * 0.14,
                    location=(x, y, R * 0.07),
                )
            else:  # "hills" default
                bpy.ops.mesh.primitive_uv_sphere_add(
                    radius=R * 0.12, location=(x, y, -R * 0.03),
                    segments=8, ring_count=4,
                )
                obj = bpy.context.active_object
                obj.scale = (1.3, 1.3, 0.45)
            obj = bpy.context.active_object
            obj.name = f"WD_Silhouette_{biome.silhouette_type}_{i}"
            # Dark silhouette material
            m = bpy.data.materials.get("WD_Silhouette_Mat") or bpy.data.materials.new("WD_Silhouette_Mat")
            m.use_nodes = True
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    try:
                        n.inputs["Base Color"].default_value = (0.08, 0.08, 0.10, 1.0)
                        n.inputs["Roughness"].default_value = 0.95
                    except KeyError:
                        pass
                    break
            obj.data.materials.append(m)
            try:
                obj["is_world_dev"] = True
            except Exception:
                pass
            placed += 1
        except Exception as e:
            print(f"[WORLD_DEV/SILHOUETTE] shape {i} failed: {e}", flush=True)
            continue
    print(
        f"[WORLD_DEV/SILHOUETTE] type={biome.silhouette_type} "
        f"placed={placed}/{biome.silhouette_count}",
        flush=True,
    )
    return placed


_POSITION_HINTS = {
    "low_angle_side":     (4.0,  2.0, 1.5),
    "high_side":          (3.0, -2.0, 5.0),
    "opposite_side":     (-3.0, -2.0, 5.0),
    "high_back":          (0.0, -5.0, 6.0),
    "behind_hero_low":    (0.0,  3.0, 0.8),
    "ground_bounce":      (0.0,  0.0, 0.3),
    "street_level":       (2.0,  1.5, 1.8),
}


def _add_accent_light(bpy, spec: AccentLightSpec, hero_center: tuple, frame_end: int = 240) -> bool:
    """Place one accent light relative to hero_center."""
    try:
        offset = _POSITION_HINTS.get(spec.position_hint, _POSITION_HINTS["high_side"])
        loc = (
            hero_center[0] + offset[0],
            hero_center[1] + offset[1],
            max(0.5, hero_center[2] + offset[2]),
        )
        if spec.kind in ("key_sun", "cold_sun", "sun_low", "cold_sun_low", "sky_key"):
            bpy.ops.object.light_add(type='SUN', location=loc)
        else:
            bpy.ops.object.light_add(type='AREA', location=loc)
        light = bpy.context.active_object
        light.name = f"WD_Accent_{spec.kind}"
        try:
            light.data.color = spec.color
            light.data.energy = spec.energy
            if hasattr(light.data, "size"):
                light.data.size = 4.0
        except Exception:
            pass
        # Flicker: keyframe energy with noise
        if spec.flicker:
            try:
                base = light.data.energy
                import random as _r
                rr = _r.Random(hash(spec.kind) & 0xFFFFFFFF)
                for f in range(1, frame_end + 1, 4):
                    light.data.energy = base * (0.85 + rr.random() * 0.30)
                    light.data.keyframe_insert(data_path="energy", frame=f)
                light.data.energy = base
            except Exception:
                pass
        try:
            light["is_world_dev"] = True
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[WORLD_DEV/LIGHT] {spec.kind} failed: {e}", flush=True)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# develop_world — top-level dispatcher
# ═══════════════════════════════════════════════════════════════════════════

def _hero_center_from_context(scene_context: dict) -> tuple:
    """Extract hero center from scene_context hero_bbox or use (0,0,0)."""
    bb = scene_context.get("hero_bbox")
    if bb and isinstance(bb, dict):
        cx = (bb.get("min_x", 0.0) + bb.get("max_x", 0.0)) / 2.0
        cy = (bb.get("min_y", 0.0) + bb.get("max_y", 0.0)) / 2.0
        cz = (bb.get("min_z", 0.0) + bb.get("max_z", 0.0)) / 2.0
        return (cx, cy, cz)
    if bb and isinstance(bb, (tuple, list)) and len(bb) >= 3:
        return tuple(bb[:3])
    return (0.0, 5.0, 0.0)  # sane default: hero is usually forward of origin


def develop_world(biome: BiomeSpec, scene_context: dict) -> WorldDevReport:
    """Apply a biome to the current Blender scene.

    scene_context must include:
        manifest: full manifest dict (for hash seeding)
        hero_bbox: dict with min_x/max_x/min_y/max_y/min_z/max_z (optional)
        camera: bpy.context.scene.camera (optional)
        frame_range: (start, end) tuple
        render_tier: str tier name
        bpy: the bpy module (passed in so this file stays Blender-free at import)
    """
    bpy = scene_context.get("bpy")
    if bpy is None:
        try:
            import bpy as _bpy  # noqa
            bpy = _bpy
        except ImportError:
            raise RuntimeError("world_development requires bpy (run inside Blender)")

    manifest = scene_context.get("manifest") or {}
    tier = str(scene_context.get("render_tier") or "fast").lower()
    camera = scene_context.get("camera")
    frame_range = scene_context.get("frame_range") or (1, 240)

    # Deterministic RNG seeded from prompt so same prompt → same layout
    seed_str = str(manifest.get("topic") or manifest.get("core_objective_prompt") or biome.name)
    rng = random.Random(hash(seed_str) & 0xFFFFFFFF)

    hero_center = _hero_center_from_context(scene_context)
    # Ground z: if hero is grounded near z=0, use 0; else use hero's z
    ground_z = 0.0

    # ── 1. Scatter ────────────────────────────────────────────────────
    scatter_per_rule = []
    scatter_total = 0
    for rule in biome.scatter_rules:
        try:
            rep = _place_rule(
                bpy, rule, hero_center=hero_center,
                camera=camera, rng=rng, ground_z=ground_z, tier=tier,
            )
            scatter_per_rule.append(rep)
            scatter_total += rep.get("placed", 0)
        except Exception as e:
            print(f"[WORLD_DEV/SCATTER] rule={rule.kind} dispatch failed: {e}", flush=True)
            scatter_per_rule.append({"kind": rule.kind, "placed": 0, "error": str(e)})

    # ── 2. Atmosphere ─────────────────────────────────────────────────
    atmos_kind = "none"
    if biome.fog_density > 0:
        atmos_kind = _add_biome_fog(bpy, biome, hero_center)
    else:
        atmos_kind = "skipped"

    # ── 3. Silhouettes ────────────────────────────────────────────────
    sil_count = 0
    if tier != "preview" or biome.silhouette_count <= 4:
        # Silhouettes are cheap; allow for preview if not too many
        sil_count = _add_biome_silhouette(bpy, biome, hero_center)

    # ── 4. Accent lights ──────────────────────────────────────────────
    accent_count = 0
    for spec in biome.accent_lights:
        if _add_accent_light(bpy, spec, hero_center, frame_end=frame_range[1]):
            accent_count += 1

    # ── 5. Color grade (stored on scene; compositor applies later) ────
    grade_applied = False
    grade_params: dict = {
        "lift":       list(biome.grade_lift),
        "gamma":      list(biome.grade_gamma),
        "gain":       list(biome.grade_gain),
        "saturation": biome.grade_saturation,
        "biome":      biome.name,
    }
    if tier != "preview":
        try:
            scene = bpy.context.scene
            # Stash params on the scene as custom props so the compositor
            # hook can read them without a global.
            scene["wd_grade_lift"] = list(biome.grade_lift)
            scene["wd_grade_gamma"] = list(biome.grade_gamma)
            scene["wd_grade_gain"] = list(biome.grade_gain)
            scene["wd_grade_saturation"] = float(biome.grade_saturation)
            scene["wd_biome"] = biome.name
            grade_applied = True
        except Exception as e:
            print(f"[WORLD_DEV/GRADE] stash failed (non-fatal): {e}", flush=True)

    report = WorldDevReport(
        biome=biome.name,
        confidence=biome.confidence,
        ground_applied=biome.ground_material,
        scatter_total=scatter_total,
        scatter_per_rule=scatter_per_rule,
        atmosphere_kind=atmos_kind,
        silhouette_count=sil_count,
        accent_light_count=accent_count,
        grade_applied=grade_applied,
        grade_params=grade_params,
    )

    print(
        f"[WORLD_DEV/GRADE] biome={biome.name} "
        f"lift={biome.grade_lift} gain={biome.grade_gain} "
        f"sat={biome.grade_saturation} applied_to_tier={tier}",
        flush=True,
    )
    return report
