"""GameSpec — the schema-validated contract between "what the user asked for"
(short prompt or long PRD) and the deterministic game emitters.

Everything is defaulted: a bare `GameSpec()` is already a playable
walk-around-world game. The Ollama extractor (Phase 26.5) only OVERRIDES
fields it can justify from the text — never invents required structure — so a
weak extraction degrades to a working default game, not a broken one.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class PlayerSpec(BaseModel):
    """The controllable character."""
    asset: str = ""                      # path to animated .glb (baked anim set)
    name: str = "player"
    height_m: float = Field(1.75, gt=0.2, le=10.0)
    walk_speed: float = Field(2.0, gt=0.0, le=50.0)    # m/s
    run_speed: float = Field(5.0, gt=0.0, le=80.0)
    turn_speed: float = Field(10.0, gt=0.0, le=40.0)   # rad/s smoothing
    jump: bool = False                   # off until foot-plant/land anims exist
    yaw_offset_deg: float = 0.0          # asset facing correction (glTF axes vary)
    attack: Literal["none", "melee", "ranged"] = "none"   # combat verb (Phase 36)
    hp: int = Field(5, ge=1, le=20)
    mode: Literal["walk", "drive", "fly", "swim"] = "walk"  # drive/fly/swim per species
    anims: dict = Field(default_factory=lambda: {
        "idle": "idle", "walk": "walk", "run": "run"})  # state -> glTF clip name


class CameraSpec(BaseModel):
    mode: Literal["third_person", "first_person", "orbit"] = "third_person"
    distance_m: float = Field(4.5, gt=0.5, le=50.0)
    height_m: float = Field(2.0, ge=0.0, le=20.0)
    fov_deg: float = Field(50.0, gt=20.0, le=110.0)


class ScatterSpec(BaseModel):
    """Instanced props scattered over the world (trees, rocks, lamps...)."""
    asset: str                            # .glb path
    count: int = Field(12, ge=1, le=500)
    min_dist_m: float = Field(4.0, ge=0.0)      # keep-out radius around spawn
    scale_jitter: float = Field(0.25, ge=0.0, le=1.0)
    collide: bool = True


class PlacedItemSpec(BaseModel):
    """Phase 42 Inspector: an object placed at EXPLICIT world coordinates
    (click-to-place). `kind` is either a built-in procedural prop the runtime
    draws instantly (book/sign/chest/building/rock/beacon/campfire) or any
    noun — resolved through the same casting ladder as entities."""
    kind: str = "book"
    name: str = ""                        # display label ("hint book")
    asset: str = ""                       # resolved GLB for non-procedural kinds
    x: float = 0.0
    z: float = 0.0
    yaw_deg: float = 0.0
    height_m: float = Field(0.0, ge=0.0, le=60.0)   # 0 = kind default
    interact: Optional[str] = None        # press E near it -> this text (hints/lore)
    collide: bool = True
    # RULE CHIPS (Phase 44): every rule here is HONORED by the runtime —
    # safe_zone (hostiles fear it), blocks_enemies (NPCs can't pass),
    # hurts_touch (damages the player standing in it). Never decorative.
    rules: List[str] = Field(default_factory=list)


class WorldSpec(BaseModel):
    name: str = "park"
    size_m: float = Field(120.0, gt=10.0, le=2000.0)   # square ground extent
    ground_color: List[float] = Field(default_factory=lambda: [0.35, 0.52, 0.28])
    sky: Literal["day", "sunset", "night", "overcast", "mars", "space", "dusk"] = "day"
    weather: Literal["none", "rain", "snow"] = "none"     # Phase 33 dynamics
    wind: float = Field(0.5, ge=0.0, le=1.0)              # prop sway strength
    grass: bool = True                                    # off for cities/snow
    fog: bool = True
    fog_density: Optional[float] = Field(None, ge=0.0, le=1.0)  # 0.5=default, 0.9=thick mist
    water_level: Optional[float] = None   # ocean/lake worlds: water plane height (m)
    health_packs: int = Field(0, ge=0, le=12)   # heart pickups scattered on the ground
    placed_items: List[PlacedItemSpec] = Field(default_factory=list)  # Inspector placements
    scatter: List[ScatterSpec] = Field(default_factory=list)
    level: Optional[dict] = None    # Phase 32 LevelPlan (terrain/path/goal), injected by the exporter

    @field_validator("ground_color")
    @classmethod
    def _rgb3(cls, v):
        if len(v) != 3 or not all(0.0 <= c <= 1.0 for c in v):
            raise ValueError("ground_color must be 3 floats in [0,1]")
        return v


class EntitySpec(BaseModel):
    """Non-player entity. hostile = chases and attacks the player (combat)."""
    asset: str = ""                       # resolved from the asset library by name
    name: str = "entity"
    behavior: Literal["static", "wander", "follow", "hostile", "vehicle"] = "wander"
    count: int = Field(1, ge=1, le=64)
    speed: float = Field(1.5, ge=0.0, le=40.0)
    height_m: float = Field(1.0, gt=0.1, le=10.0)
    hp: int = Field(3, ge=1, le=50)       # hostile only


class ObjectiveSpec(BaseModel):
    """A MISSION STEP. Objectives are an ordered sequence (quest log):
    collect N -> defeat N -> reach the beacon. Genres compose from these."""
    kind: Literal["collect", "defeat", "reach", "race", "survive"] = "collect"
    label: str = "stars"
    count: int = Field(5, ge=1, le=600)   # survive: SECONDS to hold out (waves escalate)
    asset: Optional[str] = None   # collect steps: generated mesh spawned instead of the orb


class GameSpec(BaseModel):
    title: str = "Fantasy Studio Game"
    player: PlayerSpec = Field(default_factory=PlayerSpec)
    camera: CameraSpec = Field(default_factory=CameraSpec)
    world: WorldSpec = Field(default_factory=WorldSpec)
    entities: List[EntitySpec] = Field(default_factory=list)
    objectives: List[ObjectiveSpec] = Field(default_factory=list)
    reward: Optional[str] = None          # "winner gets a banana" → shown on the win screen
    intro: Optional[str] = None           # narrative layer: 1-2 line quest intro (START screen)
    win_text: Optional[str] = None        # narrative layer: victory line (win screen)
    # STYLE PRESET (Phase 44): USER-SELECTED, never LLM-guessed — one global
    # render/post pack applied coherently to the whole game
    style: Literal["default", "cartoon", "anime", "horror", "pixel", "lowpoly"] = "default"
    seed: int = 7                         # deterministic scatter placement

    def runtime_json(self) -> dict:
        """The subset injected into the JS runtime as __GAME_SPEC__ (asset
        paths rewritten to dist-relative by the exporter, not here)."""
        return self.model_dump()


# NEAR-MISS NORMALIZATION (2026-07-07): the LLM says "sunrise" and the enum
# says sunset — rejecting the whole spec over an obvious synonym silently
# degraded races to keyword fallback. Map the synonyms, don't fail on them.
_SKY_ALIASES = {"sunrise": "sunset", "dawn": "sunset", "evening": "sunset",
                "golden hour": "sunset", "morning": "day", "noon": "day",
                "midnight": "night", "dark": "night", "starry": "night",
                "starry night": "night", "night sky": "night", "stars": "night",
                "moonlit": "night", "moonlight": "night",
                "cloudy": "overcast", "stormy": "overcast", "foggy": "overcast",
                "twilight": "dusk", "moon": "space", "alien": "mars"}
_WEATHER_ALIASES = {"blizzard": "snow", "snowy": "snow", "snowing": "snow",
                    "rainy": "rain", "raining": "rain", "drizzle": "rain",
                    "storm": "rain", "clear": "none", "sunny": "none",
                    "windy": "none", "fog": "none"}
_BEHAVIOR_ALIASES = {"rival": "vehicle", "racer": "vehicle", "race": "vehicle",
                     "pet": "follow", "companion": "follow", "ally": "follow",
                     "friendly": "wander", "roam": "wander", "neutral": "wander",
                     "enemy": "hostile", "monster": "hostile", "attack": "hostile",
                     "aggressive": "hostile", "guard": "hostile", "idle": "static",
                     "prop": "static", "object": "static"}
_KIND_ALIASES = {"find": "collect", "gather": "collect", "pick": "collect",
                 "kill": "defeat", "destroy": "defeat", "fight": "defeat",
                 "escape": "reach", "goto": "reach", "arrive": "reach",
                 "explore": "reach", "win": "race", "hold": "survive",
                 "defend": "survive", "endure": "survive"}


def spec_from_dict(data: dict) -> GameSpec:
    """Validate an extractor/user dict into a GameSpec, normalizing near-miss
    enum values first. Raises ValueError with a readable message; callers fall
    back to defaults rather than emitting a broken game."""
    try:
        w = data.get("world")
        if isinstance(w, dict):
            s = str(w.get("sky", "")).lower().strip()
            _VALID_SKY = {"day", "sunset", "night", "overcast", "mars", "space", "dusk"}
            if s in _SKY_ALIASES:
                w["sky"] = _SKY_ALIASES[s]
            elif s and s not in _VALID_SKY:
                # multiword / creative values ("deep starry night") — take the
                # first token that maps to something real
                for tok in s.split():
                    if tok in _VALID_SKY:
                        w["sky"] = tok
                        break
                    if tok in _SKY_ALIASES:
                        w["sky"] = _SKY_ALIASES[tok]
                        break
            we = str(w.get("weather", "")).lower().strip()
            if we in _WEATHER_ALIASES:
                w["weather"] = _WEATHER_ALIASES[we]
        for e in (data.get("entities") or []):
            if isinstance(e, dict):
                b = str(e.get("behavior", "")).lower().strip()
                if b in _BEHAVIOR_ALIASES:
                    e["behavior"] = _BEHAVIOR_ALIASES[b]
        for o in (data.get("objectives") or []):
            if isinstance(o, dict):
                k = str(o.get("kind", "")).lower().strip()
                if k in _KIND_ALIASES:
                    o["kind"] = _KIND_ALIASES[k]
    except Exception:
        pass                                # normalization is best-effort
    try:
        st = str(data.get("style", "")).lower().strip()
        _STYLE_ALIASES = {"low-poly": "lowpoly", "low poly": "lowpoly",
                          "flat": "lowpoly", "toon": "cartoon",
                          "cel": "cartoon", "cel-shaded": "cartoon",
                          "pixel art": "pixel", "retro": "pixel",
                          "8-bit": "pixel", "8bit": "pixel",
                          "scary": "horror", "spooky": "horror",
                          "photoreal": "default", "realistic": "default"}
        if st in _STYLE_ALIASES:
            data["style"] = _STYLE_ALIASES[st]
    except Exception:
        pass
    try:
        return GameSpec.model_validate(data)
    except Exception as e:  # pydantic.ValidationError
        raise ValueError(f"invalid GameSpec: {e}") from e
