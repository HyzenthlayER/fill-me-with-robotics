"""M01: bounded, versioned project data; atomic persistence and edit history."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .spec import EFFECTORS, MODEL_HASH, Q0

Vec2 = tuple[float, float]
State = Annotated[list[float], Field(min_length=11, max_length=11)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")]
Effector = Literal["left_foot", "right_foot", "left_hand", "right_hand"]


class Data(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, validate_assignment=True
    )


class Robot(Data):
    builtin_id: Literal["planar-11"] = "planar-11"
    version: Literal["1.0"] = "1.0"
    model_hash: Literal[MODEL_HASH] = MODEL_HASH


class Timeline(Data):
    tick_seconds: Literal[0.05] = 0.05
    duration_ticks: int = Field(default=120, ge=40, le=400, strict=True)


class InitialState(Data):
    q: State = Field(default_factory=lambda: Q0.copy())
    dq: State = Field(default_factory=lambda: [0.0] * 11)


class Surface(Data):
    id: Identifier
    segment_start: Vec2
    segment_end: Vec2
    normal: Vec2
    mu: float = Field(default=0.8, ge=0, le=5)
    force_cap_n: float = Field(default=400.0, gt=0, le=10000)

    @model_validator(mode="after")
    def frame(self):
        dx, dz = (b - a for a, b in zip(self.segment_start, self.segment_end))
        length = math.hypot(dx, dz)
        if length < 1e-6 or abs(math.hypot(*self.normal) - 1) > 1e-6:
            raise ValueError("Surface requires nonzero length and a unit normal")
        if abs(dx * self.normal[0] + dz * self.normal[1]) > 1e-6 * length:
            raise ValueError("Surface normal must be perpendicular to segment")
        if any(abs(v) > 10 for v in (*self.segment_start, *self.segment_end)):
            raise ValueError("Scene coordinates must be within 10 meters")
        return self


class Obstacle(Data):
    id: Identifier
    primitive: Literal["box"] = "box"
    position: Vec2
    dimensions: Vec2

    @model_validator(mode="after")
    def dimensions_valid(self):
        if any(v <= 0 or v > 10 for v in self.dimensions) or any(
            abs(v) > 10 for v in self.position
        ):
            raise ValueError("Box dimensions must be positive and scene bounds <= 10 m")
        return self


class Contact(Data):
    id: Identifier
    effector_id: Effector
    surface_id: Identifier
    anchor_u: float = Field(ge=0, le=1)
    start_tick: int = Field(ge=0, le=400, strict=True)
    end_tick: int = Field(ge=0, le=400, strict=True)
    mode: Literal["stick"] = "stick"

    @model_validator(mode="after")
    def interval(self):
        if self.end_tick - self.start_tick < 4:
            raise ValueError("Contact intervals must last at least four ticks")
        return self


class Target(Data):
    id: Identifier
    tick: int = Field(ge=0, le=400, strict=True)
    kind: Literal["base_position", "base_pitch", "joint_posture", "swing_endpoint"]
    effector_id: Effector | None = None
    target: list[float] = Field(min_length=1, max_length=8)
    weight: float = Field(default=1.0, gt=0, le=10000)
    tolerance: float = Field(default=0.001, gt=0, le=1)
    hardness: Literal["soft", "hard"] = "soft"

    @model_validator(mode="after")
    def shape(self):
        size = {
            "base_position": 2,
            "base_pitch": 1,
            "joint_posture": 8,
            "swing_endpoint": 2,
        }[self.kind]
        if len(self.target) != size:
            raise ValueError(f"{self.kind} requires {size} values")
        if (self.kind == "swing_endpoint") != (self.effector_id is not None):
            raise ValueError("Only swing_endpoint targets require an effector_id")
        return self


class Planning(Data):
    max_iterations: int = Field(default=100, ge=1, le=1000, strict=True)
    timeout_s: float = Field(default=30.0, gt=0, le=300)
    swing_clearance: float = Field(default=0.06, ge=0.005, le=0.3)


class Validation(Data):
    contact_tolerance_m: float = Field(default=0.001, gt=0, le=0.01)
    balance_tolerance: float = Field(default=1e-4, gt=0, le=0.01)
    penetration_tolerance_m: float = Field(default=0.001, ge=0, le=0.01)
    max_joint_speed: float = Field(default=1.5, gt=0, le=10)
    max_base_speed: float = Field(default=0.25, gt=0, le=2)
    inertial_ratio: float = Field(default=0.05, gt=0, le=1)


class Replay(Data):
    controller: Literal["whole_body", "joint_pd"] = "whole_body"
    physics_dt: float = Field(default=0.002, ge=0.0005, le=0.005)
    control_dt: float = Field(default=0.01, ge=0.001, le=0.05)
    kp: float = Field(default=60.0, ge=0, le=1000)
    kd: float = Field(default=1.0, ge=0, le=100)
    joint_rms_rad: float = Field(default=math.radians(2), gt=0, le=0.5)
    base_error_m: float = Field(default=0.03, gt=0, le=0.5)
    pitch_error_rad: float = Field(default=math.radians(5), gt=0, le=0.5)
    drift_m: float = Field(default=0.02, gt=0, le=0.1)
    support_loss_s: float = Field(default=0.1, gt=0, le=1)
    penetration_m: float = Field(default=0.005, gt=0, le=0.05)
    saturation_fraction: float = Field(default=0.05, ge=0, le=1)

    @model_validator(mode="after")
    def periods(self):
        ratio = self.control_dt / self.physics_dt
        if ratio < 1 or abs(ratio - round(ratio)) > 1e-6:
            raise ValueError("control_dt must be an integer multiple of physics_dt")
        return self


class Settings(Data):
    planning: Planning = Field(default_factory=Planning)
    validation: Validation = Field(default_factory=Validation)
    replay: Replay = Field(default_factory=Replay)


class Project(Data):
    schema_version: Literal["1.0"] = "1.0"
    id: Identifier = "untitled"
    name: str = Field(default="Untitled composition", min_length=1, max_length=160)
    revision: int = Field(default=0, ge=0, strict=True)
    units: Literal["SI"] = "SI"
    robot: Robot = Field(default_factory=Robot)
    timeline: Timeline = Field(default_factory=Timeline)
    initial_state: InitialState = Field(default_factory=InitialState)
    surfaces: list[Surface] = Field(min_length=1, max_length=20)
    obstacles: list[Obstacle] = Field(default_factory=list, max_length=20)
    contacts: list[Contact] = Field(default_factory=list, max_length=100)
    targets: list[Target] = Field(default_factory=list, max_length=100)
    settings: Settings = Field(default_factory=Settings)

    @model_validator(mode="after")
    def references(self):
        ids = [
            v.id
            for group in (self.surfaces, self.obstacles, self.contacts, self.targets)
            for v in group
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("All entity IDs must be unique")
        surfaces = {s.id for s in self.surfaces}
        duration = self.timeline.duration_ticks
        for c in self.contacts:
            if c.surface_id not in surfaces or c.end_tick > duration:
                raise ValueError(
                    f"Contact {c.id}: unknown surface or interval beyond duration"
                )
        for effector in EFFECTORS:
            blocks = sorted(
                (c for c in self.contacts if c.effector_id == effector),
                key=lambda c: c.start_tick,
            )
            for a, b in zip(blocks, blocks[1:]):
                if a.end_tick > b.start_tick:
                    raise ValueError(
                        f"CONTACT_CONFLICT: overlapping contacts for {effector}"
                    )
                if a.end_tick == b.start_tick and (a.surface_id, a.anchor_u) != (
                    b.surface_id,
                    b.anchor_u,
                ):
                    raise ValueError(
                        f"Anchor change for {effector} requires a release interval"
                    )
        if any(t.tick > duration for t in self.targets):
            raise ValueError("Target is beyond project duration")
        keys = [(t.kind, t.effector_id, t.tick) for t in self.targets]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate target kind/effector/time")
        if any(abs(v) > 10 for v in self.initial_state.q) or any(
            abs(v) > 1e-9 for v in self.initial_state.dq
        ):
            raise ValueError(
                "Quasi-static compositions require bounded initial q and zero initial velocity"
            )
        return self

    def canonical(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()


def parse_project(text: str) -> Project:
    if len(text.encode()) > 1_000_000:
        raise ValueError("Project exceeds 1 MB")
    return Project.model_validate_json(text)


def save_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(project.model_dump_json(indent=2))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class History:
    """Bounded transactional history; invalid imports never change current state."""

    def __init__(self, project: Project, limit: int = 100):
        self.current = project.model_copy(deep=True)
        self.past: list[str] = []
        self.future: list[str] = []
        self.limit = limit

    def replace(self, document: dict) -> Project:
        candidate = Project.model_validate(document)
        self.past = (self.past + [self.current.canonical()])[-self.limit :]
        self.future.clear()
        candidate.revision = self.current.revision + 1
        self.current = candidate
        return self.current

    def undo(self):
        if self.past:
            self.future.append(self.current.canonical())
            revision = self.current.revision + 1
            self.current = parse_project(self.past.pop())
            self.current.revision = revision
        return self.current

    def redo(self):
        if self.future:
            self.past.append(self.current.canonical())
            revision = self.current.revision + 1
            self.current = parse_project(self.future.pop())
            self.current.revision = revision
        return self.current


def standing_project(duration_ticks: int = 120) -> Project:
    return Project(
        id="standing",
        name="Double support",
        timeline=Timeline(duration_ticks=duration_ticks),
        surfaces=[
            Surface(
                id="floor",
                segment_start=(-1.0, 0.0),
                segment_end=(1.0, 0.0),
                normal=(0.0, 1.0),
            ),
            Surface(
                id="wall",
                segment_start=(0.48, 0.0),
                segment_end=(0.48, 1.5),
                normal=(-1.0, 0.0),
            ),
        ],
        contacts=[
            Contact(
                id=f"{name}_floor",
                effector_id=name,
                surface_id="floor",
                anchor_u=(x + 1) / 2,
                start_tick=0,
                end_tick=duration_ticks,
            )
            for name, x in (("left_foot", -0.09), ("right_foot", 0.09))
        ],
    )
