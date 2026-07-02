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


class WorldSpec(BaseModel):
    name: str = "park"
    size_m: float = Field(120.0, gt=10.0, le=2000.0)   # square ground extent
    ground_color: List[float] = Field(default_factory=lambda: [0.35, 0.52, 0.28])
    sky: Literal["day", "sunset", "night", "overcast"] = "day"
    fog: bool = True
    scatter: List[ScatterSpec] = Field(default_factory=list)

    @field_validator("ground_color")
    @classmethod
    def _rgb3(cls, v):
        if len(v) != 3 or not all(0.0 <= c <= 1.0 for c in v):
            raise ValueError("ground_color must be 3 floats in [0,1]")
        return v


class EntitySpec(BaseModel):
    """Non-player entity. MVP behaviors are deterministic template AI."""
    asset: str = ""                       # resolved from the asset library by name
    name: str = "entity"
    behavior: Literal["static", "wander", "follow"] = "wander"
    count: int = Field(1, ge=1, le=64)
    speed: float = Field(1.5, ge=0.0, le=40.0)
    height_m: float = Field(1.0, gt=0.1, le=10.0)


class ObjectiveSpec(BaseModel):
    """MVP objective: collect N of a thing. More types in Phase 27."""
    kind: Literal["collect"] = "collect"
    label: str = "stars"
    count: int = Field(5, ge=1, le=100)


class GameSpec(BaseModel):
    title: str = "Fantasy Studio Game"
    player: PlayerSpec = Field(default_factory=PlayerSpec)
    camera: CameraSpec = Field(default_factory=CameraSpec)
    world: WorldSpec = Field(default_factory=WorldSpec)
    entities: List[EntitySpec] = Field(default_factory=list)
    objectives: List[ObjectiveSpec] = Field(default_factory=list)
    seed: int = 7                         # deterministic scatter placement

    def runtime_json(self) -> dict:
        """The subset injected into the JS runtime as __GAME_SPEC__ (asset
        paths rewritten to dist-relative by the exporter, not here)."""
        return self.model_dump()


def spec_from_dict(data: dict) -> GameSpec:
    """Validate an extractor/user dict into a GameSpec. Raises ValueError with
    a readable message; callers fall back to defaults rather than emitting a
    broken game."""
    try:
        return GameSpec.model_validate(data)
    except Exception as e:  # pydantic.ValidationError
        raise ValueError(f"invalid GameSpec: {e}") from e
