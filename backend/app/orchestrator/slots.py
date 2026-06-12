"""
Slot extraction — the LLM's ONLY job in the new architecture.

Instead of asking the LLM to compose a 12-step plan (which it fails at),
we ask it to extract structured parameters from English. The deterministic
composer (composer.py) then runs a fixed pipeline using those parameters.

This is how Sora/Runway architecturally work: LLM as semantic extractor,
deterministic pipeline as the executor. Reliable, scalable, works with
smaller models.

v1 scope: single hero, single material, simple motion, mood-based lighting.
v2 will extend to multi-subject, library asset selection, complex paths.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .llm import OllamaClient
from .scene_inference import COLOR_MAP, MATERIAL_VIBES, LIGHTING_MOOD


# ───────────────────────────────────────────────────────────────────────
# Schema definition — what the LLM must extract
# ───────────────────────────────────────────────────────────────────────

VALID_SHAPES = ["cube", "sphere", "icosphere", "cylinder", "cone", "torus", "plane", "monkey", "library"]
VALID_MATERIALS = ["matte", "metallic", "polished", "brushed", "glass", "glossy", "ceramic", "plastic", "rubber", "fuzzy", "wood", "stone", "fabric"]
VALID_MOODS     = ["neutral", "sunset", "sunrise", "golden hour", "dawn", "dusk", "noon", "daylight", "night", "moonlight", "studio", "dramatic", "moody", "dark", "bright"]
# Phase 19 — WHERE the scene takes place (the physical environment). Distinct
# from mood (which is lighting/time). "studio" is the safe neutral default.
VALID_SETTINGS  = ["studio", "grassland", "forest", "beach", "desert", "snow", "street", "interior", "mountain", "space", "underwater", "night_city"]
VALID_MOTIONS   = ["static", "orbit", "rotate_self", "translate", "bounce", "drift"]
VALID_SPEEDS    = ["slow", "medium", "fast"]
VALID_FRAMINGS  = ["close", "medium", "wide", "ultrawide"]
VALID_ANGLES    = ["front", "side", "above", "below", "three-quarter"]
VALID_RES       = ["720p", "1080p"]
VALID_RENDER_TIERS = ["preview", "fast", "standard", "cinematic"]
VALID_STYLES    = ["photoreal", "cartoon", "anime", "painting", "claymation"]
VALID_PATTERNS  = ["primitive_geo", "quadruped", "biped", "vehicle", "tree", "celestial"]
VALID_POSES     = ["standing", "sitting", "lying", "rearing", "arms_up", "running"]


SLOT_SCHEMA_TEXT = """{
  "subject": {
    "name":             // the subject as the user described it ("cat", "fox", "sports car", "pine tree")
    "base_pattern":     // CHOOSE ONE: primitive_geo, quadruped, biped, vehicle, tree, celestial.
                        //   quadruped     → animals with 4 legs (cat, dog, fox, sheep, horse, lion, rabbit, cow)
                        //   biped         → things with 2 legs and torso (human, character, robot, alien, person, kid)
                        //   vehicle       → things with wheels (car, truck, bike, motorcycle)
                        //   tree          → trunk+canopy organic (pine, oak, palm, any tree)
                        //   celestial     → moon, earth, mars, sun, planet, star (sphere with procedural surface)
                        //   primitive_geo → simple shape requested (cube, sphere, cone, etc.)
    "shape":            // for primitive_geo only: one of cube, sphere, icosphere, cylinder, cone, torus, plane, monkey, library
    "library_query":    // optional alternate name (e.g. "sports car" → "sports", "tabby cat" → "cat"). null if no extra.
    "identity_phrase":  // the subject EXACTLY as the user phrased it, keeping specific names/brands/roles/styles
                        //   ("a red ferrari driving" → "red ferrari", "a samurai warrior standing" → "samurai warrior",
                        //    "a fantasy wizard with a staff" → "fantasy wizard with a staff"). NEVER genericize.
    "pose":             // for quadruped: standing | sitting | lying. else null.
    "color_name":       // one color word from: red, blue, green, gold, silver, etc. ("neutral" if not mentioned)
    "material":         // one of: matte, metallic, polished, brushed, glass, glossy, ceramic, plastic, rubber, fuzzy, wood, stone, fabric
    "emissive":         // true if "glowing/neon/luminous/bright" appears, else false
    "scale":            // 1.0 = default. 0.5 = small. 2.0 = large. 3.0 = huge.
    "location":         // [x, y, z]. Default [0, 0, 1] (sitting on ground). Use [0, 0, 0] for plane-level.
  },
  "scene": {
    "mood":             // one of: neutral, sunset, sunrise, golden hour, dawn, dusk, noon, daylight, night, moonlight, studio, dramatic, moody, dark, bright
    "setting":          // WHERE it is: one of studio, grassland, forest, beach, desert, snow, street, interior, mountain, space, underwater, night_city. Default "studio" if no place is described. ("a field"→grassland, "the woods"→forest, "the city"→street, "a room/house"→interior, "outer space"→space)
    "ground":           // true if there's a floor/ground/plane/surface mentioned OR setting is outdoor, else false
  },
  "motion": {
    "type":             // one of: static, orbit, rotate_self, translate, bounce, drift
                        //   orbit = camera circles the subject
                        //   rotate_self = subject spins in place
                        //   translate = subject moves through space
                        //   bounce = subject bounces up/down
                        //   drift = subject moves slowly in random direction
    "speed":            // one of: slow, medium, fast
  },
  "camera": {
    "framing":          // close = tight, medium = default, wide = pulled back, ultrawide = whole environment
    "angle":            // front, side, above, below, three-quarter
  },
  "output": {
    "is_animation":     // true if any motion is described or implied, else false
    "duration_seconds": // 5 = default for animations. 0 for stills.
    "resolution":       // "720p" default. "1080p" if the user says "HD/high quality/1080".
    "render_tier":      // one of: preview (fast EEVEE), fast (better EEVEE), standard (CYCLES medium), cinematic (CYCLES high). Default "fast".
    "style":            // one of: photoreal (default), cartoon, anime, painting, claymation. The user's prompt style.
  }
}"""


FEW_SHOT_EXAMPLES = [
    {
        "prompt": "a red metallic cube",
        "slots": {
            "subject": {"name": "cube", "base_pattern": "primitive_geo", "shape": "cube", "library_query": None, "pose": None, "color_name": "red", "material": "metallic", "emissive": False, "scale": 1.0, "location": [0, 0, 1]},
            "scene":   {"mood": "neutral", "ground": False},
            "motion":  {"type": "static", "speed": "medium"},
            "camera":  {"framing": "medium", "angle": "three-quarter"},
            "output":  {"is_animation": False, "duration_seconds": 0, "resolution": "720p"},
        },
    },
    {
        "prompt": "a glowing blue glass sphere at sunset",
        "slots": {
            "subject": {"name": "sphere", "base_pattern": "primitive_geo", "shape": "sphere", "library_query": None, "pose": None, "color_name": "blue", "material": "glass", "emissive": True, "scale": 1.0, "location": [0, 0, 1]},
            "scene":   {"mood": "sunset", "ground": False},
            "motion":  {"type": "static", "speed": "medium"},
            "camera":  {"framing": "medium", "angle": "three-quarter"},
            "output":  {"is_animation": False, "duration_seconds": 0, "resolution": "720p"},
        },
    },
    {
        "prompt": "a fluffy orange cat sitting",
        "slots": {
            "subject": {"name": "cat", "base_pattern": "quadruped", "shape": None, "library_query": "cat", "pose": "sitting", "color_name": "orange", "material": "fuzzy", "emissive": False, "scale": 1.0, "location": [0, 0, 0]},
            "scene":   {"mood": "neutral", "ground": False},
            "motion":  {"type": "static", "speed": "medium"},
            "camera":  {"framing": "medium", "angle": "three-quarter"},
            "output":  {"is_animation": False, "duration_seconds": 0, "resolution": "720p"},
        },
    },
    {
        "prompt": "a brown dog standing in golden hour light",
        "slots": {
            "subject": {"name": "dog", "base_pattern": "quadruped", "shape": None, "library_query": "dog", "pose": "standing", "color_name": "brown", "material": "fuzzy", "emissive": False, "scale": 1.0, "location": [0, 0, 0]},
            "scene":   {"mood": "golden hour", "setting": "grassland", "ground": True},
            "motion":  {"type": "static", "speed": "medium"},
            "camera":  {"framing": "medium", "angle": "three-quarter"},
            "output":  {"is_animation": False, "duration_seconds": 0, "resolution": "720p"},
        },
    },
    {
        "prompt": "a red sports car",
        "slots": {
            "subject": {"name": "sports car", "base_pattern": "vehicle", "shape": None, "library_query": "sports", "pose": None, "color_name": "red", "material": "polished", "emissive": False, "scale": 1.0, "location": [0, 0, 0]},
            "scene":   {"mood": "neutral", "ground": False},
            "motion":  {"type": "static", "speed": "medium"},
            "camera":  {"framing": "medium", "angle": "three-quarter"},
            "output":  {"is_animation": False, "duration_seconds": 0, "resolution": "720p"},
        },
    },
    {
        "prompt": "a tall pine tree at sunset",
        "slots": {
            "subject": {"name": "pine tree", "base_pattern": "tree", "shape": None, "library_query": "pine", "pose": None, "color_name": "green", "material": "matte", "emissive": False, "scale": 1.0, "location": [0, 0, 0]},
            "scene":   {"mood": "sunset", "setting": "forest", "ground": True},
            "motion":  {"type": "static", "speed": "medium"},
            "camera":  {"framing": "wide", "angle": "three-quarter"},
            "output":  {"is_animation": False, "duration_seconds": 0, "resolution": "720p"},
        },
    },
    {
        "prompt": "an orange fox running through the snow",
        "slots": {
            "subject": {"name": "fox", "base_pattern": "quadruped", "shape": None, "library_query": "fox", "pose": "standing", "color_name": "orange", "material": "fuzzy", "emissive": False, "scale": 1.0, "location": [0, 0, 0]},
            "scene":   {"mood": "daylight", "ground": True},
            "motion":  {"type": "translate", "speed": "fast"},
            "camera":  {"framing": "medium", "angle": "side"},
            "output":  {"is_animation": True, "duration_seconds": 5, "resolution": "720p"},
        },
    },
]


# ───────────────────────────────────────────────────────────────────────
# Slot extraction
# ───────────────────────────────────────────────────────────────────────

EXTRACTOR_SYSTEM_PROMPT = """You are a scene-parameter extractor. Convert English scene descriptions into structured JSON.

Your ONLY output is valid JSON matching the schema below. No prose, no markdown, no code fences.

Schema:
{schema}

Examples:
{examples}

Your job: extract the slots. If a slot isn't explicitly mentioned, use the example defaults (neutral mood, medium framing, three-quarter angle, etc.). Be conservative — infer cautiously, not creatively.
"""


@dataclass
class SlotExtractionResult:
    slots: Dict[str, Any]
    raw_response: str = ""
    used_defaults: bool = False
    notes: List[str] = field(default_factory=list)


def _build_extractor_messages(user_prompt: str) -> List[Dict[str, str]]:
    examples_text = "\n\n".join(
        f"Prompt: \"{ex['prompt']}\"\nJSON: {json.dumps(ex['slots'])}"
        for ex in FEW_SHOT_EXAMPLES
    )
    system = EXTRACTOR_SYSTEM_PROMPT.format(schema=SLOT_SCHEMA_TEXT, examples=examples_text)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Prompt: \"{user_prompt}\"\nJSON:"},
    ]


def extract_slots(
    user_prompt: str,
    llm: Optional[OllamaClient] = None,
    verbose: bool = True,
) -> SlotExtractionResult:
    """Single LLM call → structured slots. Forces JSON mode via response_format."""
    if llm is None:
        llm = OllamaClient()

    messages = _build_extractor_messages(user_prompt)

    if verbose:
        print(f"[slots] extracting via {llm.model}…")

    # Use Ollama's JSON mode (OpenAI-compatible response_format)
    try:
        msg = llm.chat(
            messages=messages,
            temperature=0.1,         # low temperature — extraction not creativity
            max_tokens=600,
        )
        raw = msg.get("content", "") or ""
    except Exception as e:
        if verbose:
            print(f"[slots] LLM error: {e} — falling back to keyword defaults")
        _fb = _keyword_fallback(user_prompt); _fb["_user_prompt"] = user_prompt; _fb.setdefault("extra_subjects", _derive_extra_subjects(user_prompt, "") or None)
        return SlotExtractionResult(
            slots=_fb,
            raw_response="",
            used_defaults=True,
            notes=[f"LLM error: {e}"],
        )

    # Try to extract clean JSON from the response
    slots = _parse_slot_json(raw)
    if slots is None:
        if verbose:
            print(f"[slots] could not parse JSON from LLM, using keyword fallback")
            print(f"[slots] raw: {raw[:300]}")
        _fb = _keyword_fallback(user_prompt); _fb["_user_prompt"] = user_prompt; _fb.setdefault("extra_subjects", _derive_extra_subjects(user_prompt, "") or None)
        return SlotExtractionResult(
            slots=_fb,
            raw_response=raw,
            used_defaults=True,
            notes=["LLM returned unparseable JSON"],
        )

    # Validate + fill missing fields with defaults
    slots, validation_notes = _validate_and_fill(slots, user_prompt)
    slots["_user_prompt"] = user_prompt   # raw wording for downstream mode detection
    if not slots.get("extra_subjects"):
        _ex = _derive_extra_subjects(user_prompt, (slots.get("subject") or {}).get("identity_phrase") or "")
        if _ex:
            slots["extra_subjects"] = _ex
    result = SlotExtractionResult(slots=slots, raw_response=raw, used_defaults=False, notes=validation_notes)

    if verbose:
        subj_log = slots['subject']
        pose_part = f", pose={subj_log['pose']}" if subj_log.get('pose') else ""
        lq_part = f", query='{subj_log['library_query']}'" if subj_log.get('library_query') else ""
        print(f"[slots] extracted: pattern={subj_log['base_pattern']}{lq_part}{pose_part}, "
              f"shape={subj_log['shape']}, color={subj_log['color_name']}, "
              f"material={subj_log['material']}, mood={slots['scene']['mood']}, "
              f"motion={slots['motion']['type']}, animation={slots['output']['is_animation']}")
        if validation_notes:
            for note in validation_notes:
                print(f"[slots]   note: {note}")

    return result


def _parse_slot_json(text: str) -> Optional[Dict[str, Any]]:
    """Try several strategies to extract a JSON object from LLM output."""
    t = text.strip()
    # Strip ```json ... ``` fences
    if t.startswith("```"):
        lines = t.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()

    # Try direct parse first
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Find first balanced JSON object via raw_decode scanning
    decoder = json.JSONDecoder()
    for i, c in enumerate(t):
        if c == "{":
            try:
                obj, _ = decoder.raw_decode(t[i:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


def _derive_identity_phrase(prompt: str) -> Optional[str]:
    """Deterministically pull the subject phrase out of the raw prompt: cut at
    the first setting/motion clause, drop the leading article. Keeps specific
    identities ("red ferrari", "samurai warrior", "fantasy wizard with a staff")
    that the LLM extraction tends to genericize."""
    import re
    p = (prompt or "").strip().lower()
    if not p:
        return None
    # Strip PRESENTATION wrappers — "a showcase video of a red ferrari" is about
    # a ferrari, not a video. Leaving these in poisons the reference image.
    p = re.sub(r"^(a|an|the)?\s*(cinematic\s+)?(showcase|show case|turntable|display|promo(tional)?|beauty)?\s*"
               r"(video|clip|shot|render|scene|footage|film)\s+(of|showing|featuring)\s+", "", p).strip()
    p = re.sub(r"^(a\s+)?(showcase|turntable)\s+(of\s+)?", "", p).strip()
    # Cut at clauses describing place/time/motion — keep the subject head.
    cut_words = (r"\b(driving|walking|running|standing|sitting|flying|swimming|jumping|"
                 r"riding|galloping|sailing|floating|dancing|sprinting|crawling|"
                 r"in |on |at |through |across |under |over |during |while |near |inside )")
    m = re.search(cut_words, p)
    head = p[:m.start()] if m else p
    head = re.sub(r"^(a|an|the)\s+", "", head).strip(" ,.")
    # Guard: too long means we failed to find a clause boundary — clamp.
    words = head.split()
    if not words:
        return None
    return " ".join(words[:8])


def _validate_and_fill(slots: Dict[str, Any], user_prompt: str) -> tuple[Dict[str, Any], List[str]]:
    """Ensure all required fields exist; clamp invalid enum values to nearest valid."""
    notes: List[str] = []

    def _coerce(value, valid, default, name):
        if value in valid:
            return value
        if isinstance(value, str):
            # Try case-insensitive match
            for v in valid:
                if v.lower() == value.lower():
                    return v
        notes.append(f"{name}='{value}' invalid, using default '{default}'")
        return default

    # Subject
    subj = slots.setdefault("subject", {})
    subj.setdefault("name", "")
    subj["base_pattern"] = _coerce(subj.get("base_pattern", "primitive_geo"), VALID_PATTERNS, "primitive_geo", "subject.base_pattern")
    subj["shape"] = _coerce(subj.get("shape") or "cube", VALID_SHAPES, "cube", "subject.shape")
    subj.setdefault("library_query", None)
    # identity_phrase: keep the user's exact subject wording (brands/roles/styles)
    # so the reference image is SPECIFIC ("samurai warrior", not "character").
    # Deterministic fallback derives it from the raw prompt when the LLM omits it.
    if not subj.get("identity_phrase"):
        subj["identity_phrase"] = _derive_identity_phrase(user_prompt)
    if subj.get("pose") is not None:
        subj["pose"] = _coerce(subj["pose"], VALID_POSES, "standing", "subject.pose")
    subj.setdefault("color_name", "neutral")
    subj["material"] = _coerce(subj.get("material", "matte"), VALID_MATERIALS, "matte", "subject.material")
    subj.setdefault("emissive", False)
    subj["scale"] = float(subj.get("scale", 1.0))
    if not isinstance(subj.get("location"), list) or len(subj["location"]) != 3:
        subj["location"] = [0, 0, 1]

    # Scene
    scene = slots.setdefault("scene", {})
    scene["mood"] = _coerce(scene.get("mood", "neutral"), VALID_MOODS, "neutral", "scene.mood")
    scene["setting"] = _coerce(scene.get("setting", "studio"), VALID_SETTINGS, "studio", "scene.setting")
    # Outdoor settings imply a ground plane even if the user didn't say "floor".
    _OUTDOOR = {"grassland", "forest", "beach", "desert", "snow", "street", "mountain", "night_city"}
    scene.setdefault("ground", False)
    if scene["setting"] in _OUTDOOR or scene["setting"] == "interior":
        scene["ground"] = True

    # Motion
    motion = slots.setdefault("motion", {})
    motion["type"] = _coerce(motion.get("type", "static"), VALID_MOTIONS, "static", "motion.type")
    motion["speed"] = _coerce(motion.get("speed", "medium"), VALID_SPEEDS, "medium", "motion.speed")

    # Camera
    cam = slots.setdefault("camera", {})
    cam["framing"] = _coerce(cam.get("framing", "medium"), VALID_FRAMINGS, "medium", "camera.framing")
    cam["angle"] = _coerce(cam.get("angle", "three-quarter"), VALID_ANGLES, "three-quarter", "camera.angle")

    # Output
    out = slots.setdefault("output", {})
    out["is_animation"] = bool(out.get("is_animation", motion["type"] != "static"))
    out["duration_seconds"] = int(out.get("duration_seconds", 5 if out["is_animation"] else 0))
    out["resolution"] = _coerce(out.get("resolution", "720p"), VALID_RES, "720p", "output.resolution")
    out["render_tier"] = _coerce(out.get("render_tier", "fast"), VALID_RENDER_TIERS, "fast", "output.render_tier")
    out["style"] = _coerce(out.get("style", "photoreal"), VALID_STYLES, "photoreal", "output.style")

    return slots, notes


# ───────────────────────────────────────────────────────────────────────
# Keyword-based fallback if LLM fails entirely
# ───────────────────────────────────────────────────────────────────────

# Pattern guess for extra actors (deterministic, no LLM dependency).
_EXTRA_QUADRUPED = ("dog","cat","fox","horse","wolf","rabbit","sheep","cow","lion","tiger","bear","deer","pig","goat","cheetah","puppy","kitten")
_EXTRA_BIPED = ("man","woman","person","human","boy","girl","kid","child","warrior","samurai","ninja","wizard","knight","robot","soldier","character","alien")
_EXTRA_VEHICLE = ("car","truck","ferrari","lamborghini","motorcycle","bike","jeep","van","bus")


def _guess_pattern(phrase: str) -> str:
    w = phrase.lower()
    if any(k in w for k in _EXTRA_QUADRUPED): return "quadruped"
    if any(k in w for k in _EXTRA_BIPED): return "biped"
    if any(k in w for k in _EXTRA_VEHICLE): return "vehicle"
    return "biped"


def _derive_extra_subjects(prompt: str, primary: str) -> list:
    """Detect companion actors: 'a man walking his dog', 'a knight and a dragon',
    'a woman with her cat'. Returns [{identity_phrase, base_pattern}] (max 2)."""
    import re
    p = (prompt or "").lower()
    out, seen = [], set()
    pats = [
        r"(?<=\s)(?:and|with)\s+(?:a|an|his|her|their|the)\s+([a-z][a-z ]{2,30}?)(?=\s+(?:in|on|at|through|across|while|during|walking|running|standing)|[,.]|$)",
        r"(?<=\s)walking\s+(?:his|her|their|the)\s+([a-z][a-z ]{2,30}?)(?=\s+(?:in|on|at|through|across)|[,.]|$)",
    ]
    for rx in pats:
        for m in re.finditer(rx, p):
            ph = m.group(1).strip(" ,.")
            # trim trailing action verbs the lookahead didn't cover
            ph = __import__("re").sub(r"\s+(fighting|running|walking|standing|sitting|jumping|dancing|sparring|playing|racing|driving)$", "", ph)
            if not ph or ph in seen or ph in (primary or ""):
                continue
            # must contain a known actor noun — avoids "with a staff" props
            if not any(k in ph for k in _EXTRA_QUADRUPED + _EXTRA_BIPED + _EXTRA_VEHICLE):
                continue
            seen.add(ph)
            out.append({"identity_phrase": ph, "base_pattern": _guess_pattern(ph)})
            if len(out) >= 2:
                return out
    return out


def _keyword_fallback(prompt: str) -> Dict[str, Any]:
    """When the LLM fails, extract slots from keywords directly. Less rich, but never crashes."""
    p = prompt.lower()

    shape = "cube"
    for s in VALID_SHAPES:
        if s != "library" and re.search(rf"\b{s}\b", p):
            shape = s
            break

    color = "neutral"
    for c in COLOR_MAP:
        if re.search(rf"\b{c}\b", p):
            color = c
            break

    material = "matte"
    for m in VALID_MATERIALS:
        if re.search(rf"\b{m}\b", p):
            material = m
            break

    mood = "neutral"
    for m in VALID_MOODS:
        if re.search(rf"\b{re.escape(m)}\b", p):
            mood = m
            break

    # Phase 19 — setting (place) detection by keyword. Order matters: more
    # specific phrases first. Default studio when no place is described.
    setting = "studio"
    _SETTING_KEYWORDS = [
        ("night_city", ["night city", "neon city", "cyberpunk"]),
        ("street",     ["street", "city", "road", "urban", "sidewalk", "alley"]),
        ("grassland",  ["field", "meadow", "grass", "prairie", "savanna", "lawn"]),
        ("forest",     ["forest", "woods", "jungle", "woodland"]),
        ("beach",      ["beach", "shore", "coast", "ocean", "seaside"]),
        ("desert",     ["desert", "dunes", "sand"]),
        ("snow",       ["snow", "snowy", "arctic", "tundra", "winter"]),
        ("mountain",   ["mountain", "cliff", "peak", "hills", "valley"]),
        ("space",      ["space", "outer space", "cosmos", "galaxy", "stars", "nebula"]),
        ("underwater", ["underwater", "ocean floor", "sea floor", "reef", "submerged"]),
        ("interior",   ["room", "indoor", "inside", "house", "office", "kitchen", "studio apartment", "living room"]),
    ]
    for canonical, words in _SETTING_KEYWORDS:
        if any(w in p for w in words):
            setting = canonical
            break

    motion = "static"
    motion_words = {
        "orbit": "orbit", "orbiting": "orbit",
        "rotat": "rotate_self", "spin": "rotate_self",
        "mov": "translate", "moving": "translate", "running": "translate",
        "bounc": "bounce", "drift": "drift",
    }
    for kw, mt in motion_words.items():
        if kw in p:
            motion = mt
            break

    is_animation = motion != "static"
    emissive = any(w in p for w in ("glowing", "neon", "luminous", "bright", "emissive"))

    # Pattern guessing — look for quadruped/vehicle/tree keywords
    pattern = "primitive_geo"
    library_query = None
    pose = None
    QUADRUPED_KW = ["cat", "dog", "fox", "rabbit", "sheep", "horse", "lion", "tiger", "wolf", "cow", "deer", "bear"]
    BIPED_KW     = ["human", "person", "character", "robot", "alien", "man", "woman", "kid", "child", "boy", "girl", "guy"]
    VEHICLE_KW   = ["car", "truck", "bike", "motorcycle", "lorry", "pickup", "vehicle"]
    TREE_KW      = ["tree", "pine", "oak", "palm", "fir", "spruce", "maple"]
    for kw in QUADRUPED_KW:
        if kw in p:
            pattern = "quadruped"
            library_query = kw
            pose = "sitting" if "sitting" in p else ("lying" if "lying" in p else "standing")
            break
    if pattern == "primitive_geo":
        for kw in BIPED_KW:
            if kw in p:
                pattern = "biped"
                library_query = kw
                if "running" in p:
                    pose = "running"
                elif "sitting" in p:
                    pose = "sitting"
                elif "arms up" in p or "raised arms" in p:
                    pose = "arms_up"
                else:
                    pose = "standing"
                break
    if pattern == "primitive_geo":
        for kw in VEHICLE_KW:
            if kw in p:
                pattern = "vehicle"
                library_query = kw
                break
    if pattern == "primitive_geo":
        for kw in TREE_KW:
            if kw in p:
                pattern = "tree"
                library_query = kw
                break
    if pattern == "primitive_geo":
        CELESTIAL_KW = ["moon", "earth", "mars", "sun", "star", "planet", "saturn", "jupiter"]
        for kw in CELESTIAL_KW:
            if kw in p:
                pattern = "celestial"
                library_query = kw
                break

    return {
        "subject": {"name": "", "base_pattern": pattern, "shape": shape, "library_query": library_query, "pose": pose,
                    "identity_phrase": _derive_identity_phrase(prompt),
                    "color_name": color, "material": material,
                    "emissive": emissive, "scale": 1.0, "location": [0, 0, 1]},
        "scene":   {"mood": mood, "setting": setting,
                    "ground": setting != "studio" or "ground" in p or "floor" in p},
        "motion":  {"type": motion, "speed": "slow" if "slow" in p else ("fast" if "fast" in p else "medium")},
        "camera":  {"framing": "medium", "angle": "three-quarter"},
        "output":  {"is_animation": is_animation, "duration_seconds": 5 if is_animation else 0, "resolution": "720p"},
    }
