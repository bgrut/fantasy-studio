from __future__ import annotations

from app.planning.scene_plan import (
    AssetRequirement,
    AnimationInstruction,
    GenerationInput,
    ScenePlan,
)

# ---------------------------------------------------------------------------
# Subject scale hints (Blender units, ~1 unit = 1 metre).
# Used downstream by street_scene to set target_size per character type.
# ---------------------------------------------------------------------------
SUBJECT_SCALE_HINTS: dict[str, float] = {
    "cat":   0.45,
    "cats":  0.45,
    "dog":   0.60,
    "bear":  1.20,
    "yeti":  2.20,
    "human": 1.80,
    "person": 1.80,
    "character": 1.80,
}

# How much horizontal spacing (metres) to leave between character slots.
SUBJECT_SPACING_HINTS: dict[str, float] = {
    "cat":   0.90,
    "cats":  0.90,
    "dog":   1.00,
    "bear":  1.40,
    "yeti":  2.00,
    "human": 1.30,
    "person": 1.30,
    "character": 1.30,
}

# ---------------------------------------------------------------------------
# Word → integer mapping for spoken-out number words
# ---------------------------------------------------------------------------
_WORD_COUNTS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
    "6": 6, "7": 7, "8": 8,
    "a": 1, "an": 1, "single": 1, "pair": 2, "couple": 2,
    "trio": 3, "group": 3, "several": 3,
}


def _text_blob(inp: GenerationInput) -> str:
    return " ".join([
        inp.raw_prompt or "",
        inp.template_bias or "",
        inp.sonic_frequency or "",
        inp.technical_style_constraints or "",
    ]).lower()


def _has_any(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def _extract_subject_count(text: str, fallback: int = 1) -> int:
    """Return the first explicit numeric quantity found in the text blob."""
    for word, n in _WORD_COUNTS.items():
        if word in text.split():
            return n
    return fallback


def _extract_species(text: str) -> str:
    """
    Return the primary species/subject keyword for this prompt.
    Order matters — check specific animals before generic 'character'.
    """
    for species in ("cat", "cats", "dog", "bear", "yeti", "human", "person"):
        if species in text:
            return species
    if _has_any(text, ["character", "dancing", "dance", "talking", "singing"]):
        return "character"
    return "character"


def _species_tags(species: str) -> list[str]:
    """Return asset-resolver-friendly tags for the detected species."""
    mapping: dict[str, list[str]] = {
        "cat":       ["cat", "feline", "animal", "quadruped"],
        "cats":      ["cat", "feline", "animal", "quadruped"],
        "dog":       ["dog", "canine", "animal", "quadruped"],
        "bear":      ["bear", "animal", "quadruped"],
        "yeti":      ["yeti", "creature", "biped"],
        "human":     ["human", "person", "biped", "character"],
        "person":    ["human", "person", "biped", "character"],
        "character": ["character", "biped"],
    }
    return mapping.get(species, ["character", "biped"])


def _subject_scale(species: str) -> float:
    return SUBJECT_SCALE_HINTS.get(species, 1.80)


def _subject_spacing(species: str) -> float:
    return SUBJECT_SPACING_HINTS.get(species, 1.30)


def build_scene_plan(inp: GenerationInput) -> ScenePlan:
    text = _text_blob(inp)

    scene_family = "city_scene"
    template_name = "city_loop"
    environment = "urban_city"
    subject_type = "environment"
    focal_subject = "city"
    camera_mode = "drone_push"
    lighting_mode = "cinematic_night"
    animation_mode = "ambient"
    mood = "cinematic"
    style_tags: list[str] = []
    asset_requirements: list[AssetRequirement] = []
    animation_instructions: list[AnimationInstruction] = []
    debug_notes: list[str] = []

    # ── Product stage ──────────────────────────────────────────────────────
    if _has_any(text, ["watch", "perfume", "bottle", "product", "jewelry", "ring"]):
        scene_family = "product_stage"
        template_name = "product_scene"
        environment = "studio"
        subject_type = "product"
        focal_subject = "product"
        camera_mode = "orbit_macro"
        lighting_mode = "luxury_studio"
        animation_mode = "product_turntable"
        mood = "luxury"
        style_tags += ["product", "commercial", "clean"]
        asset_requirements += [
            AssetRequirement("product", True, 1, ["hero", "premium"]),
            AssetRequirement("hdri", True, 1, ["studio", "clean"]),
            AssetRequirement("texture", True, 1, ["studio", "matte", "luxury"]),
        ]
        animation_instructions += [
            AnimationInstruction("product", "rotate", "turntable", "low", "continuous", "Slow luxury rotation"),
        ]
        debug_notes.append("Matched product-stage family")

    # ── Street / character scene ───────────────────────────────────────────
    elif _has_any(text, ["cat", "cats", "dog", "bear", "yeti",
                         "character", "dancing", "dance",
                         "talking", "singing", "human", "person"]):

        species = _extract_species(text)
        char_count = _extract_subject_count(text, fallback=1)
        char_tags = _species_tags(species)
        scale_hint = _subject_scale(species)
        spacing_hint = _subject_spacing(species)

        scene_family = "street_scene"
        template_name = "street_scene"
        environment = "urban_street"
        subject_type = "character_group"

        # Specific focal_subject so downstream and debug logs are readable
        focal_subject = f"{species}_group" if char_count > 1 else species

        camera_mode = "music_video_wide"
        lighting_mode = "street_night"
        mood = "energetic"
        style_tags += ["performance", "character", "street", species]

        # animation_mode is species-aware
        if _has_any(text, ["dance", "dancing"]):
            animation_mode = f"{species}_dance" if species not in ("human", "person", "character") else "character_performance"
        elif _has_any(text, ["talk", "talking", "speak", "speaking"]):
            animation_mode = "character_dialogue"
        else:
            animation_mode = "character_performance"

        # Character requirement carries species tags so resolver can match them
        asset_requirements += [
            AssetRequirement("character", True, char_count, char_tags),
            AssetRequirement("prop", False, 2, ["street"]),
            AssetRequirement("building", True, 1, ["urban", "street"]),
            AssetRequirement("texture", True, 1, ["road", "street"]),
            AssetRequirement("hdri", True, 1, ["city", "night"]),
        ]

        if _has_any(text, ["dance", "dancing"]):
            animation_instructions += [
                AnimationInstruction("characters", "dance", "loop", "high", "continuous",
                                     "Stagger offsets between performers"),
            ]
        if _has_any(text, ["talk", "talking", "speak", "speaking"]):
            animation_instructions += [
                AnimationInstruction("characters", "talk", "lip_sync_placeholder", "medium", "beat_based",
                                     "Use placeholder talk gestures until facial system is ready"),
            ]

        # Embed scale and spacing hints so street_scene can read them without re-parsing
        debug_notes.append(
            f"Matched street-scene family | species={species} count={char_count} "
            f"scale_hint={scale_hint} spacing_hint={spacing_hint}"
        )
        # Attach hints to the plan via extra fields (scene_plan is a dataclass —
        # these go into debug_notes as structured tokens so street_scene can parse them
        # without changing the ScenePlan schema).
        debug_notes.append(f"subject_scale_hint={scale_hint}")
        debug_notes.append(f"subject_spacing_hint={spacing_hint}")
        debug_notes.append(f"subject_count={char_count}")
        debug_notes.append(f"subject_species={species}")

    # ── Ocean scene ────────────────────────────────────────────────────────
    elif _has_any(text, ["fish", "ocean", "underwater", "swimming", "sea", "whale", "shark"]):
        scene_family = "ocean_scene"
        template_name = "ocean_scene"
        environment = "underwater"
        subject_type = "creatures"
        focal_subject = "fish_school"
        camera_mode = "underwater_drift"
        lighting_mode = "ocean_caustic"
        animation_mode = "swim_school"
        mood = "dreamy"
        style_tags += ["ocean", "fluid", "underwater"]
        asset_requirements += [
            AssetRequirement("character", True, 5, ["fish", "creature", "marine"]),
            AssetRequirement("prop", False, 4, ["coral", "reef"]),
            AssetRequirement("texture", True, 1, ["ocean", "sand"]),
            AssetRequirement("hdri", False, 1, ["blue", "ambient"]),
        ]
        animation_instructions += [
            AnimationInstruction("fish_school", "swim", "spline_follow", "medium", "continuous",
                                 "Fish should move in offset schooling arcs"),
        ]
        debug_notes.append("Matched ocean-scene family")

    # ── Car hero ───────────────────────────────────────────────────────────
    elif _has_any(text, ["car", "supercar", "mclaren", "lamborghini", "porsche", "automotive"]):
        scene_family = "car_hero"
        template_name = "car_hero"
        environment = "city_road"
        subject_type = "vehicle"
        focal_subject = "car"
        camera_mode = "tracking_low"
        lighting_mode = "automotive_night"
        animation_mode = "vehicle_hero_motion"
        mood = "premium"
        style_tags += ["automotive", "hero", "cinematic"]
        asset_requirements += [
            AssetRequirement("car", True, 1, ["vehicle", "hero"]),
            AssetRequirement("building", False, 1, ["city"]),
            AssetRequirement("texture", True, 1, ["road", "wet"]),
            AssetRequirement("hdri", True, 1, ["city", "night"]),
        ]
        animation_instructions += [
            AnimationInstruction("car", "glide", "tracking_motion", "medium", "continuous",
                                 "Subtle hero movement rather than racing"),
        ]
        debug_notes.append("Matched car-hero family")

    # ── Default city scene ─────────────────────────────────────────────────
    else:
        style_tags += ["city", "cinematic"]
        asset_requirements += [
            AssetRequirement("building", True, 1, ["city", "urban"]),
            AssetRequirement("texture", True, 1, ["road", "wet"]),
            AssetRequirement("hdri", True, 1, ["city", "night"]),
            AssetRequirement("car", False, 1, ["vehicle"]),
        ]
        animation_instructions += [
            AnimationInstruction("environment", "ambient_motion", "camera_only", "low", "continuous",
                                 "Drone push through city district"),
        ]
        debug_notes.append("Matched default city-scene family")

    # ── Cross-cutting style modifiers ──────────────────────────────────────
    if _has_any(text, ["cyberpunk", "neon"]):
        style_tags += ["cyberpunk", "neon"]
        lighting_mode = "cyberpunk_night"

    if _has_any(text, ["hyper realistic", "hyper-realistic", "photoreal"]):
        style_tags += ["hyper_realistic"]

    reference_influence = "present" if inp.references else "none"

    return ScenePlan(
        scene_family=scene_family,
        template_name=template_name,
        environment=environment,
        subject_type=subject_type,
        focal_subject=focal_subject,
        style_tags=sorted(set(style_tags)),
        camera_mode=camera_mode,
        lighting_mode=lighting_mode,
        animation_mode=animation_mode,
        mood=mood,
        duration_seconds=inp.duration_seconds,
        asset_requirements=asset_requirements,
        animation_instructions=animation_instructions,
        reference_influence=reference_influence,
        debug_notes=debug_notes,
    )