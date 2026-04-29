from __future__ import annotations

from dataclasses import replace as _dc_replace

from app.planning.scene_plan import (
    AssetRequirement,
    AnimationInstruction,
    GenerationInput,
    ScenePlan,
)

SUBJECT_SCALE_HINTS: dict[str, float] = {
    "cat": 0.45, "cats": 0.45, "dog": 0.60, "bear": 1.20,
    "yeti": 2.20, "human": 1.80, "person": 1.80, "character": 1.80,
}
SUBJECT_SPACING_HINTS: dict[str, float] = {
    "cat": 0.90, "cats": 0.90, "dog": 1.00, "bear": 1.40,
    "yeti": 2.00, "human": 1.30, "person": 1.30, "character": 1.30,
}
_WORD_COUNTS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
    "a": 1, "an": 1, "single": 1, "pair": 2, "couple": 2, "trio": 3, "group": 3,
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
    for word, n in _WORD_COUNTS.items():
        if word in text.split():
            return n
    return fallback

def _extract_species(text: str) -> str:
    # Longest-match first so "golden retriever" beats "golden".
    _SPECIES_ORDER = [
        # specific breeds / compound names first
        "golden retriever", "german shepherd", "t-rex",
        # big cats
        "cheetah", "leopard", "panther", "jaguar", "cougar", "lynx",
        # canines / wild
        "wolf", "fox", "hyena", "coyote",
        # large mammals
        "elephant", "giraffe", "zebra", "rhino", "hippo", "moose",
        "buffalo", "bison", "caribou", "camel", "llama",
        # primates
        "gorilla", "monkey", "chimpanzee", "orangutan", "baboon",
        # common pets
        "cat", "cats", "dog", "dogs",
        # farm
        "horse", "cow", "pig", "sheep", "goat", "chicken", "duck",
        # other mammals
        "rabbit", "deer", "bear", "panda", "kangaroo", "raccoon",
        "squirrel", "hedgehog", "lion", "tiger",
        # birds
        "eagle", "owl", "parrot", "pelican", "penguin", "flamingo",
        "swan", "hawk", "falcon", "bird",
        # marine
        "dolphin", "whale", "shark", "octopus", "jellyfish",
        "stingray", "crab", "lobster", "fish",
        # reptiles / amphibians
        "crocodile", "alligator", "lizard", "snake", "turtle", "frog",
        # insects
        "butterfly", "spider",
        # dinosaurs
        "dinosaur", "raptor", "velociraptor", "triceratops",
        "brontosaurus", "stegosaurus", "pterodactyl", "mammoth",
        # mythical
        "dragon", "unicorn", "phoenix", "yeti", "griffin",
        "centaur", "minotaur", "werewolf",
        # humanoids
        "human", "person", "robot", "android",
    ]
    for species in _SPECIES_ORDER:
        if species in text:
            return species
    if _has_any(text, ["character", "dancing", "dance", "talking", "singing"]):
        return "character"
    return "character"

# Map species → asset search tags. Anything not listed gets ["animal", "creature"].
_SPECIES_TAG_MAP: dict[str, list[str]] = {
    "cat": ["cat", "feline", "animal", "quadruped"],
    "cats": ["cat", "feline", "animal", "quadruped"],
    "dog": ["dog", "canine", "animal", "quadruped"],
    "dogs": ["dog", "canine", "animal", "quadruped"],
    "cheetah": ["cheetah", "big cat", "feline", "animal", "quadruped"],
    "leopard": ["leopard", "big cat", "feline", "animal", "quadruped"],
    "lion": ["lion", "big cat", "feline", "animal", "quadruped"],
    "tiger": ["tiger", "big cat", "feline", "animal", "quadruped"],
    "panther": ["panther", "big cat", "feline", "animal", "quadruped"],
    "jaguar": ["jaguar", "big cat", "feline", "animal", "quadruped"],
    "wolf": ["wolf", "canine", "animal", "quadruped"],
    "fox": ["fox", "canine", "animal", "quadruped"],
    "bear": ["bear", "animal", "quadruped"],
    "horse": ["horse", "equine", "animal", "quadruped"],
    "elephant": ["elephant", "animal", "quadruped", "large"],
    "gorilla": ["gorilla", "primate", "animal"],
    "monkey": ["monkey", "primate", "animal"],
    "dinosaur": ["dinosaur", "prehistoric", "creature"],
    "t-rex": ["t-rex", "dinosaur", "prehistoric", "creature"],
    "raptor": ["raptor", "dinosaur", "prehistoric", "creature"],
    "dragon": ["dragon", "mythical", "creature", "flying"],
    "unicorn": ["unicorn", "mythical", "horse", "creature"],
    "phoenix": ["phoenix", "mythical", "bird", "creature"],
    "yeti": ["yeti", "creature", "biped"],
    "eagle": ["eagle", "bird", "raptor", "animal"],
    "dolphin": ["dolphin", "marine", "animal"],
    "whale": ["whale", "marine", "creature"],
    "shark": ["shark", "marine", "creature"],
    "fish": ["fish", "marine", "creature"],
    "human": ["human", "person", "biped", "character"],
    "person": ["human", "person", "biped", "character"],
    "robot": ["robot", "mech", "biped", "character"],
    "character": ["character", "biped"],
}

def _species_tags(species: str) -> list[str]:
    return _SPECIES_TAG_MAP.get(species, ["animal", "creature"])

def _subject_scale(species: str) -> float:
    return SUBJECT_SCALE_HINTS.get(species, 1.80)

def _subject_spacing(species: str) -> float:
    return SUBJECT_SPACING_HINTS.get(species, 1.30)

# ═══════════════════════════════════════════════════════════════════════════
# LLM-enhanced planner — runs first when Ollama is available, then falls
# back to the rule-based logic below if the LLM is offline or returns
# malformed JSON. The legacy rule-based body has been preserved verbatim
# inside _legacy_build_scene_plan() so behaviour is unchanged when the LLM
# is unavailable.
# ═══════════════════════════════════════════════════════════════════════════

_LLM_PLANNER_SYSTEM = (
    "You are a cinematic scene planner for a 3D animation engine. "
    "Given a user prompt, extract a structured scene plan. "
    "Be precise — pick the single best template_family for the prompt.\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "NATURAL OUTDOOR SETTING OVERRIDE (HIGHEST PRIORITY — read first)\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "If the prompt contains any natural-landscape noun — mountain, "
    "mountains, alpine, canyon, canyons, gorge, desert, dune, forest, "
    "woods, jungle, ocean, sea, coast, beach, shore, arctic, tundra, "
    "glacier, valley, meadow, countryside, plains, savanna, cliff, "
    "cliffs — the scene_family is ALWAYS `scenic_landscape`, regardless "
    "of whether an animal, person, or creature is present.\n"
    "\n"
    "This applies even with active verbs like running, galloping, "
    "flying, walking, swimming, climbing. The landscape noun wins over "
    "the subject.\n"
    "\n"
    "Use `street_scene` ONLY when the prompt explicitly names a street, "
    "road, sidewalk, alley, highway, intersection, parking lot, or "
    "urban corridor.\n"
    "\n"
    "Examples of the override at work:\n"
    "- 'horse galloping through mountains' → scenic_landscape (mountains wins)\n"
    "- 'cat in a canyon' → scenic_landscape (canyon wins)\n"
    "- 'deer in a forest' → scenic_landscape (forest wins)\n"
    "- 'eagle flying over ocean' → scenic_landscape (ocean wins)\n"
    "- 'person walking on a sidewalk at night' → street_scene (sidewalk wins)\n"
    "- 'ferrari racing on a highway' → car_hero (vehicle + road)\n"
    "- 'cat on a couch' → character_stage (no natural landscape, indoor)\n"
    "\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "Scene family selection rules (applied AFTER the override above)\n"
    "═══════════════════════════════════════════════════════════════════\n"
    "- scenic_landscape: any natural outdoor landscape (see override above) "
    "AND vast uninhabited landscapes ('mountain at sunset', 'ocean horizon', "
    "'forest canopy').\n"
    "- street_scene: urban/city/neon scenes where the prompt explicitly "
    "names a street, road, sidewalk, alley, highway, or urban corridor "
    "('person at a city cafe', 'robot walking a neon street', "
    "'dog running in a city plaza').\n"
    "- car_hero: ONLY when a vehicle/car/truck/motorcycle is the primary "
    "subject ('Ferrari racing', 'truck on a highway'). Do NOT use for "
    "non-vehicle subjects.\n"
    "- ocean_scene: underwater, ocean surface from below, marine life, "
    "fish, dolphins, whales, submarines. Note: a hero ABOVE water in a "
    "coastal/beach scene is scenic_landscape (the natural-outdoor override "
    "catches 'ocean', 'coast', 'beach', 'shore').\n"
    "- character_stage: studio/stage setting, portrait, dance, performance, "
    "indoor scene with minimal environment ('chef in a restaurant', "
    "'dancer on stage', 'warrior in a hall', 'cat on a couch').\n"
    "- product_scene: product photography, item showcase, commercial, AND "
    "small objects / close-up shots ('close up of a tulip', 'diamond ring', "
    "'perfume bottle', 'single flower').\n"
    "\n"
    "CRITICAL subject-type rules (override only the Scene family rules, "
    "NOT the natural-outdoor override above):\n"
    "- Plants, flowers, trees, mushrooms → product_scene (close-up) or "
    "scenic_landscape (in nature context).\n"
    "- Food, cooking, chef, baker → character_stage.\n"
    "- Any vehicle (car, truck, motorcycle, plane) → car_hero.\n"
    "- Underwater-only creatures (fish, dolphin, whale, submarine) → "
    "ocean_scene.\n"
    "- Small objects, jewelry, gadgets → product_scene.\n"
    "- NEVER send a plant, flower, person, animal, or food to car_hero.\n"
    "\n"
    "Include hdri_query (a search phrase for finding the ideal HDRI sky), "
    "motion_speed (slow|medium|fast|static), and motion_blur (true|false). "
    "Also include ground_type (road|terrain|studio|water|auto). "
    "Respond as JSON only."
)


# ── Few-shot examples prepended to every user prompt ──────────────────
# These concrete input→output pairs teach the model the natural-outdoor
# override pattern more reliably than rules alone.  Kept short — three
# examples is enough to anchor the behaviour without dominating the
# context window.
_LLM_PLANNER_FEWSHOT = (
    "Here are three correctly-classified examples. Study them, then "
    "classify the actual user prompt at the bottom the same way.\n"
    "\n"
    "Example 1:\n"
    "User prompt: a horse galloping through mountains\n"
    "→ {\"subject\":\"horse\",\"action\":\"galloping\","
    "\"environment\":\"mountains\",\"template_family\":\"scenic_landscape\","
    "\"mood\":\"epic\",\"time_of_day\":\"golden_hour\","
    "\"hdri_query\":\"alpine mountain sunrise\","
    "\"motion_speed\":\"fast\",\"motion_blur\":true,\"ground_type\":\"terrain\"}\n"
    "\n"
    "Example 2:\n"
    "User prompt: a cat in a canyon\n"
    "→ {\"subject\":\"cat\",\"action\":\"sitting\","
    "\"environment\":\"canyon\",\"template_family\":\"scenic_landscape\","
    "\"mood\":\"cinematic\",\"time_of_day\":\"golden_hour\","
    "\"hdri_query\":\"desert canyon red rock sunset\","
    "\"motion_speed\":\"slow\",\"motion_blur\":false,\"ground_type\":\"terrain\"}\n"
    "\n"
    "Example 3:\n"
    "User prompt: a deer in a forest\n"
    "→ {\"subject\":\"deer\",\"action\":\"standing\","
    "\"environment\":\"forest\",\"template_family\":\"scenic_landscape\","
    "\"mood\":\"peaceful\",\"time_of_day\":\"morning\","
    "\"hdri_query\":\"forest dappled morning light\","
    "\"motion_speed\":\"static\",\"motion_blur\":false,\"ground_type\":\"terrain\"}\n"
    "\n"
    "Now classify this prompt using the same structure.\n"
)

_LLM_PLANNER_SCHEMA: dict = {
    "subject":           "primary subject of the shot",
    "subject_count":     1,
    "action":            "what the subject is doing",
    "environment":       "setting/location",
    "mood":              "emotional tone",
    "time_of_day":       "dawn|morning|midday|golden_hour|sunset|dusk|night",
    "weather":           "clear|cloudy|overcast|rain|fog|snow|storm",
    "template_family":   "street_scene|scenic_landscape|car_hero|ocean_scene|character_stage|product_scene",
    "camera_suggestion": "orbit|tracking|follow|reveal|handheld|static_low|dolly_in|arc",
    "energy_level":      "calm|moderate|energetic|intense",
    "hdri_query":        "search phrase for the best HDRI sky (e.g. 'dramatic sunset orange sky')",
    "motion_speed":      "static|slow|medium|fast",
    "motion_blur":       True,
    "ground_type":       "road|terrain|studio|water|auto",
}

# Map LLM template_family values onto the existing scene_family / template_name
# pairs the rule-based pipeline already understands.
_LLM_FAMILY_TO_INTERNAL: dict[str, tuple[str, str]] = {
    "street_scene":     ("street_scene",     "street_scene"),
    "scenic_landscape": ("scenic_landscape", "scenic_landscape"),
    "car_hero":         ("car_hero",         "car_hero"),
    "ocean_scene":      ("ocean_scene",      "ocean_scene"),
    "character_stage":  ("character_stage",  "character_stage"),
    "product_scene":    ("product_stage",    "product_scene"),
}


def _llm_plan_scene(inp: GenerationInput) -> ScenePlan | None:
    """
    Try to plan the scene with the local LLM. Returns ``None`` if the LLM
    is unavailable or its response can't be mapped onto a usable plan.
    On success, the returned ScenePlan is normalized through the existing
    rule-based logic so downstream code stays unchanged.
    """
    try:
        from .llm_service import structured_query, is_available
    except ImportError:
        return None

    if not is_available():
        return None

    raw_prompt = (inp.raw_prompt or "").strip()
    if not raw_prompt:
        return None

    parsed = structured_query(
        _LLM_PLANNER_SYSTEM,
        _LLM_PLANNER_FEWSHOT + f"User prompt: {raw_prompt}",
        schema=_LLM_PLANNER_SCHEMA,
    )
    if not parsed:
        return None

    family_key = (parsed.get("template_family") or "").strip().lower()
    if family_key not in _LLM_FAMILY_TO_INTERNAL:
        print(f"[PLANNER/LLM] unknown family '{family_key}', falling back to rules", flush=True)
        return None

    scene_family, template_name = _LLM_FAMILY_TO_INTERNAL[family_key]

    # Build a complete plan by running the rule-based logic FIRST (so all
    # existing asset_requirements, animation_instructions, mood mapping,
    # etc., still apply), then OVERRIDING the family/template based on the
    # LLM's classification. This is the safest way to merge LLM understanding
    # with the legacy rule machinery.
    #
    # We do this by tweaking the input's template_bias so the rule planner
    # is biased toward the LLM's chosen family, then mutating the result.
    biased_input = _dc_replace(
        inp,
        template_bias=(inp.template_bias or "") + " " + scene_family,
    )

    plan = _legacy_build_scene_plan(biased_input)

    # Hard-override the family/template using the LLM's call so it sticks
    # even if the keyword matcher disagreed.
    plan.scene_family = scene_family
    plan.template_name = template_name

    if parsed.get("mood"):
        plan.mood = str(parsed["mood"])
    if parsed.get("environment"):
        plan.environment = str(parsed["environment"])
    if parsed.get("subject"):
        plan.focal_subject = str(parsed["subject"])

    # WS5 P5: pass LLM-generated directorial hints into the plan so
    # downstream asset agent and templates can use them.
    _llm_hints: dict = {}
    if parsed.get("hdri_query"):
        _llm_hints["hdri_query"] = str(parsed["hdri_query"])
    if parsed.get("motion_speed"):
        _llm_hints["motion_speed"] = str(parsed["motion_speed"])
    if parsed.get("motion_blur") is not None:
        _llm_hints["motion_blur"] = bool(parsed["motion_blur"])
    if parsed.get("ground_type"):
        _llm_hints["ground_type"] = str(parsed["ground_type"])
    if parsed.get("camera_suggestion"):
        _llm_hints["camera_suggestion"] = str(parsed["camera_suggestion"])
    if parsed.get("energy_level"):
        _llm_hints["energy_level"] = str(parsed["energy_level"])
    if parsed.get("time_of_day"):
        _llm_hints["time_of_day"] = str(parsed["time_of_day"])
    if parsed.get("weather"):
        _llm_hints["weather"] = str(parsed["weather"])
    if _llm_hints:
        plan.debug_notes.append(f"llm_hints={_llm_hints}")
        # Stash for downstream consumption via plan.__dict__ or debug_notes.
        # ScenePlan is a frozen-ish dataclass so we piggyback on style_tags
        # to thread these through without changing the dataclass schema.
        plan.style_tags = list(set(plan.style_tags + [
            f"_llm_hint_{k}={v}" for k, v in _llm_hints.items()
        ]))

    plan.debug_notes.append(f"LLM planner picked family={family_key}")
    print(
        f"[PLANNER/LLM] family={family_key} subject={parsed.get('subject')} "
        f"mood={parsed.get('mood')} energy={parsed.get('energy_level')} "
        f"hdri={parsed.get('hdri_query')}",
        flush=True,
    )
    return plan


_QUALITY_CHECK_SYSTEM = (
    "You are a quality checker for a 3D scene planner. Given a scene plan "
    "summary, check for obvious composition errors and suggest fixes. "
    "Return JSON with: has_ground (bool), camera_sees_subject (bool), "
    "atmosphere_matches_mood (bool), suggestions (list of short strings)."
)
_QUALITY_CHECK_SCHEMA = {
    "has_ground": True,
    "camera_sees_subject": True,
    "atmosphere_matches_mood": True,
    "suggestions": ["string"],
}


def _quality_self_check(plan: ScenePlan) -> None:
    """
    Post-plan LLM self-check. Mutates plan.debug_notes with suggestions.
    Non-blocking: any failure is swallowed.
    """
    try:
        from .llm_service import structured_query, is_available
        if not is_available():
            return
        summary = (
            f"Scene: {plan.scene_family}, subject: {plan.focal_subject}, "
            f"environment: {plan.environment}, mood: {plan.mood}, "
            f"camera: {plan.camera_mode}, lighting: {plan.lighting_mode}"
        )
        parsed = structured_query(
            _QUALITY_CHECK_SYSTEM, summary,
            schema=_QUALITY_CHECK_SCHEMA, timeout=6.0,
        )
        if not parsed:
            return
        suggestions = parsed.get("suggestions") or []
        if suggestions:
            plan.debug_notes.append(f"quality_check_suggestions={suggestions}")
            print(f"[PLANNER/QC] {suggestions}", flush=True)
        for k in ("has_ground", "camera_sees_subject", "atmosphere_matches_mood"):
            if parsed.get(k) is False:
                plan.debug_notes.append(f"quality_check_WARN: {k}=False")
                print(f"[PLANNER/QC] WARNING: {k}=False", flush=True)
    except Exception as e:
        print(f"[PLANNER/QC] self-check failed (non-blocking): {e}", flush=True)


def _apply_prompt_intelligence(plan: ScenePlan, inp: GenerationInput) -> ScenePlan:
    """
    Run the word-intelligence layer over the scene plan.

    Builds a dict snapshot of the plan, enriches it against the prompt, and
    merges the resulting additive details back into the ScenePlan as:
      - style_tags tokens (time:*, weather:*, env:*, subject:*, cam:*, anim:*)
      - debug_notes entries so the run log shows exactly what was added

    Purely additive: never overrides values the planner (LLM or legacy)
    already set, and wrapped so an import / key failure can't break
    build_scene_plan.
    """
    try:
        from app.services.prompt_intelligence import enrich_scene_plan
    except Exception as e:
        print(f"[PLANNER] prompt_intelligence unavailable (non-fatal): {e}", flush=True)
        return plan

    try:
        snapshot = {
            "subject_type":     plan.subject_type,
            "template_family":  plan.scene_family,
            "environment_type": plan.environment,
            "mood":             plan.mood,
            "time_of_day":      "",
            "weather":          "",
        }
        enriched = enrich_scene_plan(inp.raw_prompt or "", dict(snapshot))

        new_tags: list[str] = []
        if enriched.get("time_of_day"):
            new_tags.append(f"time:{enriched['time_of_day']}")
        if enriched.get("weather"):
            new_tags.append(f"weather:{enriched['weather']}")
        if enriched.get("environment_type"):
            new_tags.append(f"env:{enriched['environment_type']}")
        if enriched.get("subject_type"):
            new_tags.append(f"subject:{enriched['subject_type']}")
        if enriched.get("suggested_camera"):
            new_tags.append(f"cam:{enriched['suggested_camera']}")
        if enriched.get("animation"):
            new_tags.append(f"anim:{enriched['animation']}")
        if enriched.get("default_animation") and not enriched.get("animation"):
            new_tags.append(f"anim:{enriched['default_animation']}")
        for sq in (enriched.get("search_queries") or [])[:3]:
            new_tags.append(f"search:{str(sq).replace(' ', '_')}")
        for kw in (enriched.get("hdri_keywords") or [])[:4]:
            new_tags.append(f"hdri:{str(kw).replace(' ', '_')}")
        if enriched.get("suggested_ground"):
            new_tags.append(f"ground:{enriched['suggested_ground']}")
        if enriched.get("ground_wet"):
            new_tags.append("ground:wet")
        if "atmosphere_density" in enriched:
            new_tags.append(f"atm:{enriched['atmosphere_density']:.3f}")

        merged_tags = list(plan.style_tags)
        for tok in new_tags:
            if tok not in merged_tags:
                merged_tags.append(tok)

        merged_notes = list(plan.debug_notes)
        if new_tags:
            merged_notes.append(f"prompt_intelligence: {', '.join(new_tags)}")

        return _dc_replace(plan, style_tags=merged_tags, debug_notes=merged_notes)
    except Exception as e:
        print(f"[PLANNER] prompt_intelligence enrich failed (non-fatal): {e}", flush=True)
        return plan


def build_scene_plan(inp: GenerationInput) -> ScenePlan:
    """
    Public entry point. Tries the LLM-enhanced planner first; on any
    failure (LLM offline, bad JSON, unknown family) falls back to the
    rule-based planner. Behaviour without Ollama is identical to before.

    After the base plan is produced (LLM or legacy), the prompt-intelligence
    enrichment layer adds synonym/weather/time/subject tokens into
    style_tags so downstream systems (asset_agent, world_builder) can
    consume them without extra plumbing.
    """
    llm_plan = _llm_plan_scene(inp)
    if llm_plan is not None:
        _quality_self_check(llm_plan)
        return _apply_prompt_intelligence(llm_plan, inp)
    return _apply_prompt_intelligence(_legacy_build_scene_plan(inp), inp)


def _legacy_build_scene_plan(inp: GenerationInput) -> ScenePlan:
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

    # ── Strong vehicle pre-guard ────────────────────────────────────────
    # Brand names and explicit vehicle nouns claim the prompt BEFORE the
    # scenic_landscape / street_scene branches can steal it via weak
    # matches like "sunset" / "road". This is what makes
    # "Ferrari driving at sunset" resolve to car_hero with an actual
    # vehicle asset requirement instead of ending up in scenic_landscape
    # requesting only an environment (which was rendering as gray
    # because the registry never got asked for a Ferrari).
    #
    # Ambiguous vehicle-adjacent words ("driving", "road", "highway",
    # plain "car" substring) stay OUT of this guard so they don't steal
    # prompts like "a dog walking down the road". They still match the
    # original car_hero elif further down as a fallback.
    _STRONG_VEHICLE_WORDS = [
        "ferrari", "lamborghini", "porsche", "mclaren", "bugatti",
        "rimac", "corvette", "mustang", "tesla", "supra", "hellcat",
        "bmw", "audi", "mercedes", "nissan", "dodge", "jeep",
        "supercar", "sports car", "race car", "vehicle",
        "motorcycle", "motorbike", "truck", "pickup", "sedan",
        "hatchback", "coupe",
    ]
    _claimed_car_hero = False
    if _has_any(text, _STRONG_VEHICLE_WORDS):
        _claimed_car_hero = True
        scene_family = "car_hero"
        template_name = "car_hero"
        environment = "hero_stage"
        subject_type = "vehicle"
        focal_subject = "vehicle"
        camera_mode = "tracking_low"
        lighting_mode = "automotive_night"
        animation_mode = "vehicle_hero_motion"
        mood = "premium"
        style_tags += ["automotive", "hero", "cinematic"]
        vehicle_tags = ["vehicle", "hero"]
        if "ferrari" in text:
            vehicle_tags += ["ferrari", "sports", "automotive"]
            focal_subject = "ferrari"
        elif "bmw" in text:
            vehicle_tags += ["bmw", "automotive"]
            focal_subject = "bmw"
        elif "mclaren" in text:
            vehicle_tags += ["mclaren", "sports", "automotive"]
            focal_subject = "mclaren"
        elif "lamborghini" in text:
            vehicle_tags += ["lamborghini", "sports", "automotive"]
            focal_subject = "lamborghini"
        elif "porsche" in text:
            vehicle_tags += ["porsche", "sports", "automotive"]
            focal_subject = "porsche"
        elif "rimac" in text:
            vehicle_tags += ["rimac", "electric", "automotive"]
            focal_subject = "rimac"
        asset_requirements += [
            AssetRequirement("vehicle", True, 1, vehicle_tags),
            AssetRequirement("hdri", False, 1, ["studio", "clean"]),
        ]
        animation_instructions += [
            AnimationInstruction("vehicle", "vehicle_glide", "tracking_motion", "medium", "continuous", "Subtle hero movement rather than racing"),
        ]
        debug_notes.append("Matched car-hero family (strong vehicle pre-guard)")

    # Plants / flowers / small natural subjects → product scene (close-up)
    # Must come before product and scenic_landscape so "tulip" doesn't
    # fall through to the default or get stolen by "nature" → landscape.
    elif _has_any(text, [
        "tulip", "rose", "orchid", "lily", "daisy", "sunflower",
        "chrysanthemum", "lotus", "peony", "poppy", "marigold",
        "carnation", "daffodil", "iris", "lavender", "magnolia",
        "cherry blossom", "sakura", "hibiscus", "violet", "pansy",
        "succulent", "cactus", "bonsai", "bouquet",
        "flower", "plant", "herb", "fern", "mushroom",
        "close up", "close-up", "closeup", "macro",
    ]):
        scene_family = "product_stage"
        template_name = "product_scene"
        environment = "studio"
        subject_type = "product"
        focal_subject = text.split()[0] if text else "flower"
        camera_mode = "orbit_macro"
        lighting_mode = "luxury_studio"
        animation_mode = "product_turntable"
        mood = "elegant"
        style_tags += ["botanical", "close-up", "clean"]
        asset_requirements += [
            AssetRequirement("product", True, 1, ["hero", "botanical"]),
            AssetRequirement("hdri", True, 1, ["studio", "clean"]),
        ]
        animation_instructions += [
            AnimationInstruction("product", "rotate", "turntable", "low", "continuous", "Slow elegant rotation"),
        ]
        debug_notes.append("Matched plant/flower/close-up → product_scene")

    # Chef / cooking / food → character_stage
    elif _has_any(text, [
        "chef", "cook", "cooking", "baker", "baking", "kitchen",
        "restaurant", "barista", "waiter", "waitress", "bartender",
        "food", "recipe", "meal", "dish",
    ]):
        scene_family = "character_stage"
        template_name = "character_stage"
        environment = "studio_stage"
        subject_type = "character"
        focal_subject = "chef" if "chef" in text else "character"
        camera_mode = "stage_push"
        lighting_mode = "studio_clean"
        animation_mode = "character_performance"
        mood = "warm"
        style_tags += ["character", "studio", "warm"]
        asset_requirements += [
            AssetRequirement("character", True, 1, ["character", "humanoid"]),
            AssetRequirement("hdri", False, 1, ["studio", "warm"]),
        ]
        animation_instructions += [
            AnimationInstruction("character", "idle", "idle", "low", "continuous", "Subtle idle"),
        ]
        debug_notes.append("Matched chef/cooking/food → character_stage")

    # Product
    elif _has_any(text, ["watch", "perfume", "bottle", "product", "jewelry", "ring",
                        "shoe", "sneaker", "phone", "gadget", "luxury", "item",
                        "object", "cosmetic", "lipstick", "headphone", "speaker"]):
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

    # Character stage (clean studio/stage, no city)
    elif _has_any(text, ["cat", "cats", "dog", "bear", "yeti", "human", "person", "character"]) and _has_any(text, ["stage", "studio", "platform", "clean background", "clean stage", "clean cinematic stage"]):
        species = _extract_species(text)
        char_count = _extract_subject_count(text, fallback=1)
        char_tags = _species_tags(species)
        scale_hint = _subject_scale(species)
        spacing_hint = _subject_spacing(species)

        scene_family = "character_stage"
        template_name = "character_stage"
        environment = "studio_stage"
        subject_type = "character_group"
        focal_subject = f"{species}_group" if char_count > 1 else species
        camera_mode = "stage_push"
        lighting_mode = "studio_clean"
        animation_mode = "character_performance"
        mood = "clean"
        style_tags += ["character", "studio", "clean", species]

        asset_requirements += [
            AssetRequirement("character", True, char_count, char_tags),
            AssetRequirement("texture", False, 1, ["studio", "matte"]),
            AssetRequirement("hdri", False, 1, ["studio", "clean"]),
        ]

        if _has_any(text, ["dance", "dancing", "performing", "performance"]):
            animation_instructions += [
                AnimationInstruction("characters", "dance", "loop", "medium", "continuous", "Stage choreography"),
            ]
        else:
            animation_instructions += [
                AnimationInstruction("characters", "bounce", "idle", "low", "continuous", "Subtle idle motion"),
            ]

        debug_notes.append(f"Matched character-stage family | species={species} count={char_count}")
        debug_notes.append(f"subject_scale_hint={scale_hint}")
        debug_notes.append(f"subject_spacing_hint={spacing_hint}")
        debug_notes.append(f"subject_count={char_count}")
        debug_notes.append(f"subject_species={species}")

    # ── Active-subject guard ────────────────────────────────────────────
    # Before scenic_landscape gets a chance to claim "dog in the park",
    # divert to street_scene / character_stage when the prompt has both
    # a living subject AND an active verb. Scenic_landscape is for
    # ENVIRONMENT-focused shots only. If there's a dog running, we want
    # the template that foregrounds the dog, not the one that orbits a
    # mountain.
    _LIVING_SUBJECTS = [
        "dog", "dogs", "cat", "cats", "person", "people", "human", "man",
        "woman", "boy", "girl", "robot", "android", "character", "dancer",
        "warrior", "knight", "samurai", "astronaut", "alien",
        "chef", "cook", "baker", "barista",
        # dog breeds
        "retriever", "labrador", "poodle", "bulldog", "husky", "terrier",
        "beagle", "shepherd", "chihuahua", "dachshund", "pug", "corgi",
        "puppy", "golden",
        # cat breeds
        "kitten", "tabby", "siamese",
        # other animals — big cats, canines, farm, wild
        "horse", "wolf", "fox", "lion", "tiger", "bear", "elephant",
        "rabbit", "deer", "monkey", "gorilla", "giraffe", "zebra",
        "panda", "kangaroo", "raccoon", "squirrel", "hedgehog",
        "cheetah", "leopard", "panther", "jaguar", "cougar", "lynx",
        "hyena", "jackal", "coyote", "moose", "caribou", "bison",
        "buffalo", "rhino", "hippo", "gazelle", "antelope",
        "cow", "pig", "sheep", "goat", "chicken", "duck", "goose",
        "donkey", "llama", "camel",
        # birds, sea life, reptiles, insects
        "bird", "eagle", "owl", "parrot", "pelican", "penguin",
        "dolphin", "whale", "shark", "lizard", "snake", "frog",
        "turtle", "crocodile", "alligator", "flamingo", "swan",
        "butterfly", "spider", "octopus", "crab", "lobster",
        "jellyfish", "stingray", "seahorse",
        "hawk", "falcon", "raven", "crow", "hummingbird",
        # primates
        "chimpanzee", "orangutan", "baboon",
        # dinosaurs
        "dinosaur", "t-rex", "trex", "raptor", "velociraptor",
        "brontosaurus", "stegosaurus", "triceratops", "pterodactyl",
        "mammoth",
        # mythical
        "dragon", "unicorn", "phoenix", "yeti", "griffin", "centaur",
        "minotaur", "werewolf",
    ]
    _ACTIVE_VERBS = [
        "running", "walking", "dancing", "playing", "sitting", "fighting",
        "jumping", "flying", "singing", "talking", "performing",
    ]
    _has_subject = _has_any(text, _LIVING_SUBJECTS)
    _has_action  = _has_any(text, _ACTIVE_VERBS)
    _outdoor_setting = _has_any(text, ["park", "garden", "yard", "field",
                                       "outdoor", "outside", "meadow",
                                       "backyard", "countryside", "street",
                                       "sidewalk", "plaza", "alley",
                                       "desert", "jungle", "forest", "beach",
                                       "mountain", "savanna", "tundra",
                                       "swamp", "canyon", "valley", "river",
                                       "lake", "ocean", "coast", "island",
                                       "volcano", "prairie", "hills"])
    _stage_setting = _has_any(text, ["stage", "studio", "spotlight",
                                     "platform", "runway", "podium"])

    # A living subject is ALWAYS foregrounded — even without an active
    # verb or explicit setting. "A cheetah in the desert" must NOT fall
    # through to scenic_landscape just because there's no action word.
    if _has_subject:
        species = _extract_species(text)
        char_count = _extract_subject_count(text, fallback=1)
        char_tags = _species_tags(species)
        scale_hint = _subject_scale(species)
        spacing_hint = _subject_spacing(species)

        if _stage_setting and not _outdoor_setting:
            scene_family = "character_stage"
            template_name = "character_stage"
            environment = "studio_stage"
            camera_mode = "stage_push"
            lighting_mode = "studio_clean"
            mood = "clean"
            style_tags += ["character", "studio", "clean", species]
        else:
            scene_family = "street_scene"
            template_name = "street_scene"
            environment = "urban_street" if not _outdoor_setting else "outdoor_open"
            camera_mode = "music_video_wide"
            lighting_mode = "street_night" if not _outdoor_setting else "golden_hour"
            mood = "energetic"
            style_tags += ["performance", "character", species]

        subject_type = "character_group"
        focal_subject = f"{species}_group" if char_count > 1 else species
        if _has_any(text, ["dance", "dancing"]):
            animation_mode = "character_performance"
        elif _has_any(text, ["talk", "talking", "speak", "speaking"]):
            animation_mode = "character_dialogue"
        elif _has_any(text, ["running"]):
            animation_mode = "run_cycle"
        elif _has_any(text, ["walking"]):
            animation_mode = "walk_cycle"
        else:
            animation_mode = "character_performance"

        asset_requirements += [
            AssetRequirement("character", True, char_count, char_tags),
            AssetRequirement("hdri", True, 1, ["outdoor" if _outdoor_setting else "city"]),
        ]
        if _outdoor_setting:
            asset_requirements += [
                AssetRequirement("texture", True, 1, ["grass", "park", "ground"]),
            ]
        else:
            asset_requirements += [
                AssetRequirement("texture", True, 1, ["road", "street"]),
            ]

        animation_instructions += [
            AnimationInstruction(
                "characters", animation_mode, "loop", "medium",
                "continuous", f"{species} {animation_mode} in {environment}",
            ),
        ]
        debug_notes.append(
            f"Matched active-subject guard | species={species} "
            f"action_verb={_has_action} outdoor={_outdoor_setting} "
            f"family={scene_family}"
        )
        debug_notes.append(f"subject_scale_hint={scale_hint}")
        debug_notes.append(f"subject_spacing_hint={spacing_hint}")
        debug_notes.append(f"subject_count={char_count}")
        debug_notes.append(f"subject_species={species}")

    # Scenic landscape — skipped when a strong vehicle has already
    # claimed the prompt (so "Ferrari at sunset" stays car_hero instead
    # of being pulled into a landscape shot because "sunset" matched).
    elif (not _claimed_car_hero) and _has_any(text, ["mountain", "lake", "glacial", "forest", "landscape", "vista",
                          "scenic", "sunrise", "sunset", "cliffs", "nature", "valley",
                          "river", "field", "meadow", "sky", "canyon", "desert",
                          "aurora", "volcano", "waterfall", "hills", "prairie",
                          "tundra", "savanna", "rainforest", "jungle",
                          "park", "garden", "countryside", "beach", "coast",
                          "swamp", "marsh", "lagoon", "plateau", "gorge"]):
        env_tags = ["landscape", "scenic", "cinematic"]
        if "mountain" in text:
            env_tags = ["mountain", "landscape", "scenic"]
        elif "lake" in text or "glacial" in text:
            env_tags = ["lake", "glacial", "water", "scenic"]
        elif "forest" in text:
            env_tags = ["forest", "landscape", "scenic"]
        elif "ocean" in text or "coast" in text:
            env_tags = ["ocean", "water", "scenic"]

        scene_family = "scenic_landscape"
        template_name = "scenic_landscape"
        environment = "landscape"
        subject_type = "environment"
        focal_subject = "environment"
        camera_mode = "cinematic_drift"
        lighting_mode = "golden_hour"
        animation_mode = "camera_only"
        mood = "cinematic"
        style_tags += ["scenic", "landscape", "cinematic"]
        asset_requirements += [
            AssetRequirement("environment", True, 1, env_tags),
            AssetRequirement("hdri", False, 1, ["ambient", "cinematic"]),
        ]
        animation_instructions += [
            AnimationInstruction("environment", "ambient_motion", "camera_only", "low", "continuous", "Slow scenic drift"),
        ]
        debug_notes.append("Matched scenic-landscape family")

    # Street / character (expanded: breeds, more species, action words)
    elif _has_any(text, [
        # generic
        "cat", "cats", "dog", "dogs", "bear", "yeti", "character",
        "dancing", "dance", "talking", "singing", "human", "person",
        # dog breeds
        "retriever", "labrador", "poodle", "bulldog", "husky", "terrier",
        "beagle", "shepherd", "chihuahua", "dachshund", "pug", "corgi",
        "puppy", "golden",
        # cat breeds / kitten
        "kitten", "tabby", "siamese",
        # other animals commonly requested
        "horse", "wolf", "fox", "lion", "tiger", "elephant", "rabbit",
        "deer", "monkey", "gorilla", "giraffe", "zebra", "panda",
        "kangaroo", "raccoon", "squirrel", "hedgehog",
        "bird", "eagle", "owl", "parrot", "pelican", "penguin",
        "dolphin", "whale", "shark", "lizard", "snake", "frog",
        "turtle", "crocodile", "alligator", "flamingo", "swan",
        "butterfly", "spider", "octopus", "crab",
        # mythical
        "dragon", "unicorn", "phoenix",
        # actions that imply living subject
        "running", "jumping", "walking", "playing", "sitting", "flying",
    ]):
        species = _extract_species(text)
        char_count = _extract_subject_count(text, fallback=1)
        char_tags = _species_tags(species)
        scale_hint = _subject_scale(species)
        spacing_hint = _subject_spacing(species)

        scene_family = "street_scene"
        template_name = "street_scene"
        environment = "urban_street"
        subject_type = "character_group"
        focal_subject = f"{species}_group" if char_count > 1 else species
        camera_mode = "music_video_wide"
        lighting_mode = "street_night"
        mood = "energetic"
        style_tags += ["performance", "character", "street", species]

        if _has_any(text, ["dance", "dancing"]):
            animation_mode = "character_performance"
        elif _has_any(text, ["talk", "talking", "speak", "speaking"]):
            animation_mode = "character_dialogue"
        else:
            animation_mode = "character_performance"

        asset_requirements += [
            AssetRequirement("character", True, char_count, char_tags),
            AssetRequirement("prop", False, 2, ["street"]),
            AssetRequirement("building", True, 1, ["urban", "street"]),
            AssetRequirement("texture", True, 1, ["road", "street"]),
            AssetRequirement("hdri", True, 1, ["city", "night"]),
        ]

        if _has_any(text, ["dance", "dancing"]):
            animation_instructions += [
                AnimationInstruction("characters", "dance", "loop", "high", "continuous", "Stagger offsets between performers"),
            ]

        debug_notes.append(f"Matched street-scene family | species={species} count={char_count} scale_hint={scale_hint} spacing_hint={spacing_hint}")
        debug_notes.append(f"subject_scale_hint={scale_hint}")
        debug_notes.append(f"subject_spacing_hint={spacing_hint}")
        debug_notes.append(f"subject_count={char_count}")
        debug_notes.append(f"subject_species={species}")

    # Ocean
    elif _has_any(text, ["fish", "ocean", "underwater", "swimming", "sea", "whale",
                          "shark", "dolphin", "coral", "beach", "wave", "waves",
                          "reef", "aquatic", "marine", "seabed", "deep sea"]):
        ocean_species = "fish"
        if "whale" in text:
            ocean_species = "whale"
        elif "shark" in text:
            ocean_species = "shark"

        creature_count = _extract_subject_count(text, fallback=2 if ocean_species == "whale" else 5)
        wanted_tags = _species_tags(ocean_species)

        scene_family = "ocean_scene"
        template_name = "ocean_scene"
        environment = "underwater"
        subject_type = "creatures"
        focal_subject = f"{ocean_species}_group" if creature_count > 1 else ocean_species
        camera_mode = "underwater_drift"
        lighting_mode = "ocean_caustic"
        animation_mode = "swim_school"
        mood = "dreamy"
        style_tags += ["ocean", "fluid", "underwater", ocean_species]
        asset_requirements += [
            AssetRequirement("character", True, creature_count, wanted_tags),
            AssetRequirement("prop", False, 4, ["coral", "reef"]),
            AssetRequirement("texture", True, 1, ["ocean", "sand"]),
            AssetRequirement("hdri", False, 1, ["blue", "ambient"]),
        ]
        animation_instructions += [
            AnimationInstruction(focal_subject, "swim", "spline_follow", "medium", "continuous", "Creatures should move in offset underwater arcs"),
        ]
        debug_notes.append(f"Matched ocean-scene family | species={ocean_species} count={creature_count}")
        debug_notes.append(f"subject_species={ocean_species}")
        debug_notes.append(f"subject_count={creature_count}")

    # Car hero
    elif _has_any(text, ["car", "supercar", "mclaren", "lamborghini", "porsche",
                          "automotive", "ferrari", "bmw", "rimac", "vehicle",
                          "truck", "motorcycle", "motorbike", "racing", "driving",
                          "road", "highway", "audi", "mercedes", "bugatti",
                          "corvette", "mustang", "tesla", "supra", "nissan",
                          "dodge", "hellcat", "jeep", "suv"]):
        scene_family = "car_hero"
        template_name = "car_hero"
        environment = "hero_stage"
        subject_type = "vehicle"
        focal_subject = "vehicle"
        camera_mode = "tracking_low"
        lighting_mode = "automotive_night"
        animation_mode = "vehicle_hero_motion"
        mood = "premium"
        style_tags += ["automotive", "hero", "cinematic"]
        vehicle_tags = ["vehicle", "hero"]
        if "ferrari" in text:
            vehicle_tags += ["ferrari", "sports", "automotive"]
        elif "bmw" in text:
            vehicle_tags += ["bmw", "automotive"]
        elif "mclaren" in text:
            vehicle_tags += ["mclaren", "sports", "automotive"]
        elif "lamborghini" in text:
            vehicle_tags += ["lamborghini", "sports", "automotive"]
        elif "rimac" in text:
            vehicle_tags += ["rimac", "electric", "automotive"]

        asset_requirements += [
            AssetRequirement("vehicle", True, 1, vehicle_tags),
            AssetRequirement("hdri", False, 1, ["studio", "clean"]),
        ]
        animation_instructions += [
            AnimationInstruction("vehicle", "vehicle_glide", "tracking_motion", "medium", "continuous", "Subtle hero movement rather than racing"),
        ]
        debug_notes.append("Matched car-hero family")

    # City / street / urban (explicit match rather than silent default)
    elif _has_any(text, ["city", "street", "urban", "neon", "tokyo", "night",
                          "alley", "downtown", "buildings", "skyscraper",
                          "metropolis", "chinatown", "district", "plaza",
                          "bridge", "overpass", "subway"]):
        style_tags += ["city", "cinematic"]
        asset_requirements += [
            AssetRequirement("building", True, 1, ["city", "urban"]),
            AssetRequirement("texture", True, 1, ["road", "wet"]),
            AssetRequirement("hdri", True, 1, ["city", "night"]),
            AssetRequirement("car", False, 1, ["vehicle"]),
        ]
        animation_instructions += [
            AnimationInstruction("environment", "ambient_motion", "camera_only", "low", "continuous", "Drone push through city district"),
        ]
        debug_notes.append("Matched city-scene family (keyword)")

    # Character (standalone without stage keyword)
    elif _has_any(text, ["person", "figure", "statue", "portrait", "dancer",
                          "warrior", "hero", "knight", "soldier", "samurai",
                          "astronaut", "robot", "android", "alien"]):
        scene_family = "character_stage"
        template_name = "character_stage"
        environment = "studio_stage"
        subject_type = "character"
        focal_subject = "character"
        camera_mode = "stage_push"
        lighting_mode = "studio_clean"
        animation_mode = "character_performance"
        mood = "cinematic"
        style_tags += ["character", "studio"]
        asset_requirements += [
            AssetRequirement("character", True, 1, ["character", "hero"]),
            AssetRequirement("hdri", False, 1, ["studio", "clean"]),
        ]
        animation_instructions += [
            AnimationInstruction("character", "idle", "idle", "low", "continuous", "Subtle idle"),
        ]
        debug_notes.append("Matched character-stage family (standalone)")

    # Default → scenic_landscape (most visually forgiving). Skipped when
    # a strong vehicle has already claimed the prompt, so we don't
    # overwrite car_hero with a city default on Ferrari prompts.
    elif not _claimed_car_hero:
        scene_family = "scenic_landscape"
        template_name = "scenic_landscape"
        environment = "landscape"
        subject_type = "environment"
        focal_subject = "environment"
        camera_mode = "cinematic_drift"
        lighting_mode = "golden_hour"
        animation_mode = "camera_only"
        mood = "cinematic"
        style_tags += ["scenic", "cinematic"]
        asset_requirements += [
            AssetRequirement("building", True, 1, ["city", "urban"]),
            AssetRequirement("texture", True, 1, ["road", "wet"]),
            AssetRequirement("hdri", True, 1, ["city", "night"]),
            AssetRequirement("car", False, 1, ["vehicle"]),
        ]
        animation_instructions += [
            AnimationInstruction("environment", "ambient_motion", "camera_only", "low", "continuous", "Drone push through city district"),
        ]
        debug_notes.append("Matched default city-scene family")

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

