"""M04: fixed contact phases, load envelopes, and smooth swing tasks."""

from dataclasses import dataclass

import numpy as np

from .model import anchor_point
from .project import Project
from .spec import EFFECTORS


def smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * u * (10 + u * (-15 + 6 * u))


@dataclass(frozen=True)
class Phase:
    start_tick: int
    end_tick: int
    contact_ids: tuple[str, ...]


class Schedule:
    def __init__(self, project: Project):
        self.project = project
        self.duration = project.timeline.duration_ticks
        self.dt = project.timeline.tick_seconds
        self.by_effector = {
            e: sorted(
                [c for c in project.contacts if c.effector_id == e],
                key=lambda c: c.start_tick,
            )
            for e in EFFECTORS
        }
        self.surfaces = {s.id: s for s in project.surfaces}
        self.events = sorted(
            {0, self.duration}
            | {v for c in project.contacts for v in (c.start_tick, c.end_tick)}
            | {t.tick for t in project.targets}
        )
        self.phases = [
            Phase(a, b, tuple(c.id for c in self.active((a + b) / 2)))
            for a, b in zip(self.events, self.events[1:])
        ]

    def active(self, tick):
        t = min(tick, np.nextafter(float(self.duration), -np.inf))
        return [c for c in self.project.contacts if c.start_tick <= t < c.end_tick]

    def capacity(self, contact, tick):
        blocks = self.by_effector[contact.effector_id]
        same = lambda c: (c.surface_id, c.anchor_u) == (
            contact.surface_id,
            contact.anchor_u,
        )
        continuous_start = contact.start_tick == 0 or any(
            c.end_tick == contact.start_tick and same(c) for c in blocks
        )
        continuous_end = contact.end_tick == self.duration or any(
            c.start_tick == contact.end_tick and same(c) for c in blocks
        )
        up = 1.0 if continuous_start else smooth((tick - contact.start_tick) / 2)
        down = 1.0 if continuous_end else smooth((contact.end_tick - tick) / 2)
        return self.surfaces[contact.surface_id].force_cap_n * min(up, down)

    def tasks(self, tick, initial_endpoints):
        """Return endpoint center targets; touching is distinct from carrying load."""
        active = {c.effector_id: c for c in self.active(tick)}
        points = []
        for i, e in enumerate(EFFECTORS):
            if e in active:
                points.append(anchor_point(self.project, active[e]))
                continue
            previous = [c for c in self.by_effector[e] if c.end_tick <= tick]
            following = [c for c in self.by_effector[e] if c.start_tick > tick]
            before = previous[-1] if previous else None
            after = following[0] if following else None
            a = anchor_point(self.project, before) if before else initial_endpoints[i]
            b = anchor_point(self.project, after) if after else initial_endpoints[i]
            start = before.end_tick if before else 0
            end = after.start_tick if after else self.duration
            u = np.clip((tick - start) / max(end - start, 1), 0, 1)
            point = a + (b - a) * smooth(u)
            if before or after:
                surface = self.surfaces[(after or before).surface_id]
                # A quartic arch has zero first derivative at each end.
                point = point + np.asarray(
                    surface.normal
                ) * self.project.settings.planning.swing_clearance * 16 * u * u * (
                    1 - u
                ) * (1 - u)
            points.append(point)
        return np.asarray(points)

    def targets_at(self, tick):
        groups = {}
        for target in self.project.targets:
            groups.setdefault((target.kind, target.effector_id), []).append(target)
        values = []
        q0 = np.asarray(self.project.initial_state.q)
        defaults = {
            "base_position": q0[:2],
            "base_pitch": q0[2:3],
            "joint_posture": q0[3:],
        }
        for (kind, effector), targets in groups.items():
            targets.sort(key=lambda t: t.tick)
            before = [t for t in targets if t.tick <= tick]
            after = [t for t in targets if t.tick > tick]
            a = before[-1] if before else None
            b = after[0] if after else a
            if a is None:
                start = defaults.get(kind, np.asarray(b.target))
                u = smooth(tick / max(b.tick, 1))
                value = start + (np.asarray(b.target) - start) * u
            elif b is a:
                value = np.asarray(a.target)
            else:
                u = smooth((tick - a.tick) / (b.tick - a.tick))
                value = np.asarray(a.target) + (np.asarray(b.target) - a.target) * u
            definition = b if a is None else a
            values.append((definition, value))
        return values


def compile_phases(project):
    return Schedule(Project.model_validate(project.model_dump()))
