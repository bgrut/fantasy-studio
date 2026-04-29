from __future__ import annotations

"""
asset_query_generator.py
========================
Turn a high-level asset need (subject + style + role) into concrete
search queries for the asset providers (Sketchfab for models,
PolyHaven for HDRIs and textures).

Why a separate module?
----------------------
The asset agent used to hand the raw scene prompt to PolyHaven verbatim,
which produced poor matches ("luxury sunset car drive" matched random
HDRIs that mentioned "car" once). With an LLM in the loop we can:

  1. Decompose the directorial manifest into one query per asset role
     (hero model, environment HDRI, ground texture, prop, fx).
  2. Use synonyms / domain terms the artist would actually search with
     ("dragon" -> "wyvern fantasy creature", "studio shot" -> "softbox
     three point neutral grey backdrop").
  3. Provide several candidate queries per role so the fetcher can fall
     back if the first one returns nothing usable.

If the LLM is offline, this module returns a safe rule-based query so
the rest of the pipeline keeps working.
"""

from dataclasses import dataclass, field

from .llm_service import structured_query, is_available


# ═══════════════════════════════════════════════════════════════════════════
# Schema for the LLM
# ═══════════════════════════════════════════════════════════════════════════

_QUERY_SCHEMA: dict = {
    "hero_model_queries":   ["string ranked best to worst"],
    "environment_queries":  ["string for HDRI search"],
    "ground_texture_queries": ["string for PolyHaven texture search"],
    "prop_queries":         ["string for secondary models, optional"],
    "notes": "one-line rationale",
}

_QUERY_SYSTEM = (
    "You generate asset search queries for a 3D animation engine. "
    "Given a directorial scene plan, output concrete, specific search "
    "queries for: a hero downloadable 3D model (Sketchfab style), an HDRI "
    "(PolyHaven style), a ground/floor texture (PolyHaven style), and "
    "optional props. Use words an asset library would actually tag with — "
    "include style, time-of-day, material, and one synonym per query. "
    "IMPORTANT: the hero_model_queries must search for the MAIN SUBJECT "
    "only. Do NOT include accessories, toys, leashes, frisbees, balls, or "
    "other props in hero_model_queries. For 'dog running in the park', "
    "hero queries should be like ['dog', 'dog 3d model animated', "
    "'dog rigged'] — NOT ['frisbee', 'ball toy', 'dog leash']. Accessories "
    "belong in prop_queries, never in hero_model_queries. "
    "Return JSON only."
)


# ═══════════════════════════════════════════════════════════════════════════
# Public dataclass
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AssetQuerySet:
    """Concrete search queries the asset fetcher will try, in order."""
    hero_model:      list[str] = field(default_factory=list)
    environment:     list[str] = field(default_factory=list)
    ground_texture:  list[str] = field(default_factory=list)
    props:           list[str] = field(default_factory=list)
    source:          str = "fallback"
    notes:           str = ""

    def is_empty(self) -> bool:
        return not (self.hero_model or self.environment or self.ground_texture or self.props)


# ═══════════════════════════════════════════════════════════════════════════
# Subject synonym broadening — cascade helpers
# ═══════════════════════════════════════════════════════════════════════════
#
# Many prompts ("chef", "eagle", "robot") return nothing useful on
# Sketchfab because the exact subject term doesn't match what model
# uploaders actually tag. Expanding each subject into a small set of
# related terms — a search cascade — gives the fetcher more ways to
# land a hit without modifying the forbidden asset_agent/asset_fetcher/
# asset_resolver/sketchfab_fetcher files. The fetcher already iterates
# `hero_model` in order, so we just need to append broader fallbacks.
#
# Keys are lowercase; values are ordered broadest-first-after-the-exact
# term. The exact subject itself is always kept as the first query.

_SUBJECT_SYNONYMS: dict[str, list[str]] = {
    # Occupations / human characters
    "chef":       ["cook", "kitchen worker", "baker", "chef character"],
    "cook":       ["chef", "cooking character", "kitchen worker"],
    "baker":      ["chef", "baker character", "pastry chef"],
    "dancer":     ["dancing character", "ballet", "performer"],
    "soldier":    ["military character", "combat character", "infantry"],
    "knight":     ["medieval warrior", "armor character", "paladin"],
    "astronaut":  ["space suit", "cosmonaut", "spaceman"],
    "pirate":     ["pirate character", "buccaneer", "corsair"],
    "ninja":      ["ninja character", "shinobi", "assassin"],
    "wizard":     ["mage", "sorcerer", "robe character"],
    "doctor":     ["medical character", "surgeon", "physician"],
    "athlete":    ["sports character", "runner", "gym"],
    "musician":   ["guitarist", "performer", "rock star"],

    # Animals (birds)
    "eagle":      ["eagle bird", "bald eagle", "hawk", "bird of prey"],
    "hawk":       ["hawk bird", "bird of prey", "eagle"],
    "owl":        ["owl bird", "barn owl", "snowy owl"],
    "falcon":     ["falcon bird", "peregrine", "bird of prey"],
    "crow":       ["crow bird", "raven", "corvid"],
    "raven":      ["raven bird", "crow", "corvid"],
    "parrot":     ["parrot bird", "macaw", "tropical bird"],
    "bird":       ["songbird", "sparrow", "generic bird"],

    # Animals (mammals)
    "monkey":     ["ape", "chimpanzee", "primate", "gorilla"],
    "ape":        ["gorilla", "chimpanzee", "primate"],
    "tiger":      ["big cat", "bengal tiger", "feline predator"],
    "lion":       ["big cat", "lioness", "feline"],
    "bear":       ["grizzly", "polar bear", "brown bear"],
    "wolf":       ["gray wolf", "timber wolf", "canine"],
    "fox":        ["red fox", "arctic fox", "canine"],
    "deer":       ["stag", "doe", "elk"],
    "horse":      ["stallion", "pony", "equine"],
    "elephant":   ["african elephant", "mammoth"],
    "rhino":      ["rhinoceros", "white rhino"],
    "giraffe":    ["african giraffe", "tall animal"],
    "dog":        ["puppy", "canine", "hound"],
    "cat":        ["kitten", "feline", "house cat"],

    # Animals (aquatic)
    "dolphin":    ["bottlenose dolphin", "porpoise", "marine mammal"],
    "whale":      ["humpback whale", "blue whale", "ocean mammal"],
    "shark":      ["great white shark", "hammerhead", "predator fish"],
    "fish":       ["generic fish", "tropical fish", "marine life"],
    "octopus":    ["kraken", "squid", "cephalopod"],

    # Fantasy / sci-fi / mechanical
    "dragon":     ["wyvern", "mythical creature", "fantasy dragon"],
    "robot":      ["mech", "android", "droid", "mechanical"],
    "mech":       ["robot", "exosuit", "battle mech"],
    "alien":      ["extraterrestrial", "sci-fi creature", "xenomorph"],
    "dinosaur":   ["t-rex", "raptor", "prehistoric", "velociraptor"],
    "zombie":     ["undead", "zombie character", "walking dead"],
    "skeleton":   ["undead skeleton", "bones character"],
    "ghost":      ["spirit", "phantom", "specter"],

    # Vehicles
    "car":        ["sports car", "sedan", "vehicle"],
    "ferrari":    ["sports car", "supercar", "exotic car"],
    "truck":      ["pickup truck", "semi truck", "lorry"],
    "motorcycle": ["sport bike", "chopper", "motorbike"],
    "bike":       ["bicycle", "mountain bike", "road bike"],
    "plane":      ["airplane", "jet", "airliner"],
    "helicopter": ["chopper", "rotorcraft"],
    "boat":       ["sailboat", "yacht", "fishing boat"],
    "ship":       ["cargo ship", "naval vessel", "tanker"],
    "spaceship":  ["spacecraft", "starship", "space fighter"],

    # Food / quirky
    "pickle":     ["cucumber", "food character", "gherkin"],
    "donut":      ["doughnut", "pastry", "food"],
    "pizza":      ["pizza slice", "food"],
    "burger":     ["hamburger", "cheeseburger", "food"],
}


def _broaden_hero_queries(subject: str, existing: list[str]) -> list[str]:
    """
    Append synonym queries after the user-provided / LLM queries so the
    fetcher has more terms to cascade through before giving up. Keeps
    existing order intact and dedupes case-insensitively.
    """
    key = (subject or "").strip().lower()
    if not key:
        return existing

    seen: set[str] = {q.strip().lower() for q in existing if q}
    out = list(existing)

    synonyms = _SUBJECT_SYNONYMS.get(key, [])
    for syn in synonyms:
        if syn.lower() not in seen:
            out.append(syn)
            seen.add(syn.lower())
    # Final, very broad phrasings — catch "chef character animated"
    # style tags uploaders use when they don't include the bare word.
    for tail in (f"{key} character", f"{key} character animated", f"{key} rigged"):
        if tail.lower() not in seen and tail.strip() != key:
            out.append(tail)
            seen.add(tail.lower())
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Rule-based fallback
# ═══════════════════════════════════════════════════════════════════════════

def _fallback_queries(scene_plan: dict, directorial_manifest: dict | None = None) -> AssetQuerySet:
    """
    Build a usable query set from the scene plan and directorial manifest
    without calling the LLM. Intentionally pragmatic, not clever.
    """
    subject = (
        scene_plan.get("focal_subject")
        or scene_plan.get("subject")
        or "subject"
    )
    family = (
        scene_plan.get("scene_family")
        or scene_plan.get("template_family")
        or "scenic_landscape"
    )
    environment = scene_plan.get("environment") or ""
    mood = scene_plan.get("mood") or ""

    hdri_query = None
    if directorial_manifest:
        hdri_query = (directorial_manifest.get("lighting") or {}).get("hdri_search_query")

    # P5: Also extract LLM hdri_query from scene_plan style_tags
    if not hdri_query:
        for tag in (scene_plan.get("style_tags") or []):
            if isinstance(tag, str) and tag.startswith("_llm_hint_hdri_query="):
                hdri_query = tag.split("=", 1)[1]
                break

    queries = AssetQuerySet(source="fallback")

    # Hero model — simple subject-first queries so Sketchfab sees the
    # obvious search before any family-qualified phrasings.
    if subject and subject != "environment":
        queries.hero_model.append(subject.strip())
        queries.hero_model.append(f"{subject} 3d model".strip())
        queries.hero_model.append(f"{subject} animated".strip())
        queries.hero_model.append(f"{subject} rigged".strip())
        queries.hero_model.append(f"{subject} {family}".strip())

    # Environment / HDRI
    if hdri_query:
        queries.environment.append(hdri_query)
    if environment:
        queries.environment.append(f"{environment} {mood}".strip())
    if family == "street_scene":
        queries.environment.append("neon city night")
    elif family == "scenic_landscape":
        queries.environment.append("golden hour mountain sky")
    elif family == "ocean_scene":
        queries.environment.append("underwater caustics blue")
    elif family == "character_stage":
        queries.environment.append("studio softbox five point")
    elif family == "product_scene":
        queries.environment.append("studio luxury softbox")
    elif family == "car_hero":
        queries.environment.append("sunset highway dramatic")

    # Ground texture
    if family == "street_scene":
        queries.ground_texture.append("wet asphalt road night")
    elif family == "scenic_landscape":
        queries.ground_texture.append("rocky mountain ground")
    elif family in ("character_stage", "product_scene"):
        queries.ground_texture.append("studio matte floor")

    # Cascade: add synonym / broadening queries after the exact subject
    # phrasings so the fetcher has more chances to land a relevant asset.
    queries.hero_model = _broaden_hero_queries(subject, queries.hero_model)

    queries.notes = f"fallback queries for family={family} subject={subject}"
    return queries


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def generate_asset_queries(
    scene_plan: dict,
    directorial_manifest: dict | None = None,
) -> AssetQuerySet:
    """
    Produce a ranked set of concrete search queries for every asset role
    the scene needs. Uses the LLM when available, falls back to rules.
    """
    if not is_available():
        qs = _fallback_queries(scene_plan, directorial_manifest)
        return qs

    subject = scene_plan.get("focal_subject") or scene_plan.get("subject") or ""
    family = scene_plan.get("scene_family") or scene_plan.get("template_family") or ""
    environment = scene_plan.get("environment") or ""
    mood = scene_plan.get("mood") or ""
    tod = scene_plan.get("time_of_day") or ""
    weather = scene_plan.get("weather") or ""

    cam = (directorial_manifest or {}).get("camera") or {}
    lighting = (directorial_manifest or {}).get("lighting") or {}
    atmosphere = (directorial_manifest or {}).get("atmosphere") or {}

    user_prompt = (
        "Generate concrete asset search queries for this shot.\n"
        f"Subject: {subject}\n"
        f"Scene family: {family}\n"
        f"Environment: {environment}\n"
        f"Mood: {mood}\n"
        f"Time of day: {tod}\n"
        f"Weather: {weather}\n"
        f"Camera style: {cam.get('style')}\n"
        f"Lighting hint: {lighting.get('hdri_search_query')}\n"
        f"Color temperature: {atmosphere.get('color_temperature')}\n\n"
        "Provide 2-4 ranked queries per role. Be specific."
    )

    parsed = structured_query(_QUERY_SYSTEM, user_prompt, schema=_QUERY_SCHEMA)
    if not parsed:
        return _fallback_queries(scene_plan, directorial_manifest)

    def _as_str_list(value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            out = []
            for v in value:
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
            return out
        return []

    qs = AssetQuerySet(
        hero_model=_as_str_list(parsed.get("hero_model_queries")),
        environment=_as_str_list(parsed.get("environment_queries")),
        ground_texture=_as_str_list(parsed.get("ground_texture_queries")),
        props=_as_str_list(parsed.get("prop_queries")),
        source="llm",
        notes=str(parsed.get("notes") or ""),
    )

    # If the LLM somehow returned nothing usable, fall back so callers
    # always have at least one query per role.
    if qs.is_empty():
        return _fallback_queries(scene_plan, directorial_manifest)

    # Backfill any empty roles with rule-based queries so the fetcher
    # can still try every provider.
    rule_qs = _fallback_queries(scene_plan, directorial_manifest)
    if not qs.hero_model:
        qs.hero_model = rule_qs.hero_model
    if not qs.environment:
        qs.environment = rule_qs.environment
    if not qs.ground_texture:
        qs.ground_texture = rule_qs.ground_texture

    # Prepend simple subject-only queries so Sketchfab sees the obvious
    # search ("dog") before any of the more elaborate LLM phrasings.
    # This protects us from LLM-generated hero queries that drift into
    # props ("frisbee", "ball toy") or over-constrained phrases.
    if subject and subject.lower() not in {"environment", "subject", ""}:
        simple = [
            subject,
            f"{subject} 3d model",
            f"{subject} animated",
            f"{subject} rigged",
        ]
        # Deduplicate while preserving order (simple first, then LLM).
        seen: set[str] = set()
        merged: list[str] = []
        for q in simple + qs.hero_model:
            key = q.strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(q)
        qs.hero_model = merged

    # Cascade: append synonym / broadening queries after the LLM+exact
    # phrasings. Keeps the LLM's ranking on top but gives the fetcher
    # a fallback path for terms like "chef", "eagle", "robot" where
    # Sketchfab's exact-match often misses.
    qs.hero_model = _broaden_hero_queries(subject, qs.hero_model)

    print(
        f"[ASSET_QUERY] hero={qs.hero_model[:3]} env={qs.environment[:1]} "
        f"tex={qs.ground_texture[:1]} (source={qs.source})",
        flush=True,
    )
    return qs
