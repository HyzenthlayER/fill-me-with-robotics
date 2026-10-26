"""M06: contact-preserving dense trajectory generation and independent checks."""

import time
from dataclasses import dataclass, field

import mujoco
import numpy as np

from .diagnostics import Issue, coalesce, solver_issue
from .model import RobotModel, surface_frame
from .planning import StopSolve, allocate_forces, check_stop, pose_residuals, solve_pose
from .project import Project
from .schedule import Schedule
from .spec import EFFECTORS


@dataclass
class Trajectory:
    project_hash: str
    time_s: np.ndarray
    q: np.ndarray
    dq: np.ndarray
    ddq: np.ndarray
    tau_reference: np.ndarray
    contact_force_world: np.ndarray
    contact_scheduled: np.ndarray
    contact_loaded: np.ndarray
    endpoint_world: np.ndarray
    solve_status: str
    check_status: str = "not_run"
    issues: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def summary(self):
        return {
            "project_hash": self.project_hash,
            "solve_status": self.solve_status,
            "check_status": self.check_status,
            "samples": len(self.time_s),
            "issues": [i.to_dict() for i in self.issues],
            "metadata": self.metadata,
        }

    def arrays(self):
        return {k: v for k, v in vars(self).items() if isinstance(v, np.ndarray)}


def validate_trajectory(project, trajectory, robot=None, cancel=None, deadline=None):
    robot = robot or RobotModel(project)
    schedule = Schedule(project)
    settings = project.settings.validation
    issues = []
    if trajectory.project_hash != project.digest():
        return [
            Issue(
                "STALE_RESULT",
                "Project hash differs from the planned project",
                source="validation",
            )
        ]
    n = len(trajectory.time_s)
    if n < 2:
        return [
            Issue(
                "INCOMPLETE", "No complete trajectory to validate", source="validation"
            )
        ]
    shapes = {
        "time_s": (n,),
        "q": (n, 11),
        "dq": (n, 11),
        "ddq": (n, 11),
        "tau_reference": (n, 8),
        "contact_force_world": (n, 4, 2),
        "contact_scheduled": (n, 4),
        "contact_loaded": (n, 4),
        "endpoint_world": (n, 4, 2),
    }
    if any(
        getattr(trajectory, key).shape != shape
        or not np.isfinite(getattr(trajectory, key)).all()
        for key, shape in shapes.items()
    ):
        return [
            Issue(
                "INVALID_ARRAY",
                "Result arrays have invalid shapes or nonfinite values",
                source="validation",
            )
        ]
    expected = np.linspace(
        0,
        project.timeline.duration_ticks * 0.05,
        project.timeline.duration_ticks * 5 + 1,
    )
    if len(expected) != n or not np.allclose(
        expected, trajectory.time_s, atol=1e-9, rtol=0
    ):
        return [
            Issue(
                "INCOMPLETE",
                "Expected complete 100 Hz coverage including event boundaries",
                source="validation",
            )
        ]
    derivative = np.gradient(trajectory.q, trajectory.time_s, axis=0, edge_order=2)
    if not np.allclose(
        derivative, trajectory.dq, atol=1e-7, rtol=1e-6
    ) or not np.allclose(
        np.gradient(derivative, trajectory.time_s, axis=0, edge_order=2),
        trajectory.ddq,
        atol=1e-6,
        rtol=1e-6,
    ):
        issues.append(
            Issue(
                "INVALID_DERIVATIVE",
                "Stored derivatives disagree with the sampled poses",
                source="validation",
            )
        )

    def add(code, message, t, measured, limit, unit="", entities=None):
        if measured > limit + 1e-9:
            issues.append(
                Issue(
                    code,
                    message,
                    (float(t), float(t)),
                    measured=float(measured),
                    limit=float(limit),
                    unit=unit,
                    source="validation",
                    entity_ids=entities or [],
                )
            )

    initial_error = np.max(np.abs(trajectory.q[0] - project.initial_state.q))
    add(
        "INITIAL_STATE",
        "Initial pose differs from authored state",
        0,
        initial_error,
        1e-6,
    )
    for index, t in enumerate(trajectory.time_s):
        check_stop(deadline, cancel)
        q, dq, ddq = trajectory.q[index], trajectory.dq[index], trajectory.ddq[index]
        tick = t / 0.05
        residual = pose_residuals(robot, schedule, q, tick)
        add(
            "CONTACT_POSITION",
            "Active endpoint misses its anchor",
            t,
            residual["contact"],
            settings.contact_tolerance_m,
            "m",
        )
        add("JOINT_LIMIT", "Joint limit exceeded", t, residual["joint"], 1e-5, "rad")
        add(
            "COLLISION",
            "Checked geometry penetrates",
            t,
            residual["penetration"],
            settings.penetration_tolerance_m,
            "m",
        )
        add(
            "HARD_TARGET",
            "Authored hard target not satisfied",
            t,
            max(residual["hard_target"], 0),
            1e-6,
        )
        gravity = robot.gravity(q)
        generalized = np.r_[np.zeros(3), trajectory.tau_reference[index]].copy()
        active = schedule.active(tick)
        active_ids = {c.effector_id for c in active}
        if not np.array_equal(
            trajectory.contact_scheduled[index], [e in active_ids for e in EFFECTORS]
        ):
            issues.append(
                Issue(
                    "INVALID_MASK",
                    "Scheduled contact mask disagrees with project",
                    (float(t), float(t)),
                    source="validation",
                )
            )
        add(
            "INVALID_ENDPOINT",
            "Stored endpoint does not match forward kinematics",
            t,
            np.max(np.abs(robot.endpoints(q) - trajectory.endpoint_world[index])),
            1e-7,
            "m",
        )
        for c in active:
            e = EFFECTORS.index(c.effector_id)
            surface = schedule.surfaces[c.surface_id]
            tangent, normal = surface_frame(surface)
            force = trajectory.contact_force_world[index, e]
            generalized += robot.jacobian(c.effector_id, normal).T @ force
            ft, fn = float(force @ tangent), float(force @ normal)
            if bool(trajectory.contact_loaded[index, e]) != (fn > 0.02 * robot.weight):
                issues.append(
                    Issue(
                        "INVALID_MASK",
                        "Loaded contact mask disagrees with planned normal force",
                        (float(t), float(t)),
                        source="validation",
                    )
                )
            add(
                "FRICTION_LIMIT",
                "Contact force outside unilateral/friction/cap limits",
                t,
                max(-fn, abs(ft) - surface.mu * fn, fn - schedule.capacity(c, tick), 0)
                / robot.weight,
                settings.balance_tolerance,
                "",
                [c.id],
            )
        for e, name in enumerate(EFFECTORS):
            if name not in active_ids:
                if trajectory.contact_loaded[index, e]:
                    issues.append(
                        Issue(
                            "INVALID_MASK",
                            "Inactive contact marked as loaded",
                            (float(t), float(t)),
                            source="validation",
                        )
                    )
                add(
                    "INACTIVE_FORCE",
                    "Inactive contact carries planned load",
                    t,
                    np.linalg.norm(trajectory.contact_force_world[index, e]),
                    1e-7,
                    "N",
                    [name],
                )
        add(
            "STATIC_BALANCE",
            "Generalized static force balance failed",
            t,
            np.max(np.abs(generalized - gravity) / robot.force_scale),
            settings.balance_tolerance,
        )
        add(
            "TORQUE_LIMIT",
            "Actuator torque exceeds limit",
            t,
            max(
                np.max(
                    (np.abs(trajectory.tau_reference[index]) - robot.torque_limits)
                    / robot.torque_limits
                ),
                0,
            ),
            1e-4,
        )
        add(
            "RATE_LIMIT",
            "Joint/angular rate exceeds limit",
            t,
            np.max(np.abs(dq[2:])),
            settings.max_joint_speed,
            "rad/s",
        )
        add(
            "RATE_LIMIT",
            "Base translation exceeds rate limit",
            t,
            np.linalg.norm(dq[:2]),
            settings.max_base_speed,
            "m/s",
        )
        robot.forward(q, dq)
        mass = np.zeros((11, 11))
        mujoco.mj_fullM(robot.mj, mass, robot.data.qM)
        inertial = mass @ ddq + robot.data.qfrc_bias - gravity
        add(
            "INERTIAL_SCREEN",
            "Motion exceeds the quasi-static inertial screen",
            t,
            np.max(np.abs(inertial) / robot.force_scale),
            settings.inertial_ratio,
        )
    midpoint_count = 0
    for index in range(n - 1):
        check_stop(deadline, cancel)
        left, right = trajectory.q[index : index + 2]
        near_surface = robot.distances(left).min(initial=1.0) < 0.02
        if not near_surface and np.max(np.abs(right - left)) < 0.02:
            continue
        midpoint_count += 1
        t = float((trajectory.time_s[index] + trajectory.time_s[index + 1]) / 2)
        residual = pose_residuals(robot, schedule, (left + right) / 2, t / 0.05)
        add(
            "CONTACT_POSITION",
            "Interpolated midpoint misses its active anchor",
            t,
            residual["contact"],
            settings.contact_tolerance_m,
            "m",
        )
        add(
            "COLLISION",
            "Interpolated midpoint penetrates geometry",
            t,
            residual["penetration"],
            settings.penetration_tolerance_m,
            "m",
        )
        add(
            "HARD_TARGET",
            "Interpolated midpoint misses a hard target",
            t,
            max(residual["hard_target"], 0),
            1e-6,
        )
    trajectory.metadata["additional_geometry_midpoints"] = midpoint_count
    trajectory.metadata["maximum_check_gap_s"] = 0.01
    return coalesce(
        sorted(issues, key=lambda i: (i.code, i.entity_ids, i.time_interval_s))
    )


def generate(project: Project, progress=None, cancel=None) -> Trajectory:
    started = time.monotonic()
    deadline = started + project.settings.planning.timeout_s
    robot = RobotModel(project)
    schedule = Schedule(project)
    q0 = np.asarray(project.initial_state.q)
    initial_endpoints = robot.endpoints(q0)
    duration = project.timeline.duration_ticks * 0.05
    # Direct dense construction avoids unconstrained joint-angle interpolation.
    times = np.linspace(0, duration, round(duration * 100) + 1)
    rows = []
    taus = []
    forces = []
    scheduled = []
    loaded = []
    endpoints = []
    completed = []
    status = "success"
    issues = []
    previous = q0.copy()
    try:
        for index, t in enumerate(times):
            check_stop(deadline, cancel)
            tick = float(t / 0.05)
            if index == 0:
                residual = pose_residuals(robot, schedule, q0, 0)
                force = allocate_forces(robot, schedule, q0, 0)
                if (
                    residual["contact"]
                    > project.settings.validation.contact_tolerance_m
                    or not force.success
                ):
                    status = "invalid_input"
                    issues.append(
                        Issue(
                            "INITIAL_STATE",
                            "Initial pose/contact forces are inconsistent",
                        )
                    )
                    break
                q = q0.copy()
            else:
                pose = solve_pose(
                    robot, schedule, tick, previous, initial_endpoints, deadline, cancel
                )
                if pose.status != "success":
                    status = pose.status
                    issues.append(solver_issue(status, float(t), pose.message))
                    break
                q = pose.q
                force = pose.force
            active = schedule.active(tick)
            mask = np.array([e in [c.effector_id for c in active] for e in EFFECTORS])
            load = np.zeros(4, dtype=bool)
            for c in active:
                e = EFFECTORS.index(c.effector_id)
                load[e] = (
                    force.forces[e] @ np.asarray(schedule.surfaces[c.surface_id].normal)
                    > 0.02 * robot.weight
                )
            rows.append(q)
            taus.append(force.tau)
            forces.append(force.forces)
            scheduled.append(mask)
            loaded.append(load)
            endpoints.append(robot.endpoints(q))
            completed.append(t)
            previous = q
            if progress is not None and index % 10 == 0:
                progress(
                    0.8 * index / len(times), f"Generating {t:.2f} / {duration:.2f} s"
                )
    except StopSolve as stop:
        status = stop.status
        issues.append(solver_issue(status, float(completed[-1] if completed else 0)))
    n = len(rows)
    q = np.asarray(rows).reshape(n, 11)
    t = np.asarray(completed)
    dq = np.gradient(q, t, axis=0, edge_order=2) if n >= 3 else np.zeros_like(q)
    ddq = np.gradient(dq, t, axis=0, edge_order=2) if n >= 3 else np.zeros_like(q)
    result = Trajectory(
        project.digest(),
        t,
        q,
        dq,
        ddq,
        np.asarray(taus).reshape(n, 8),
        np.asarray(forces).reshape(n, 4, 2),
        np.asarray(scheduled, dtype=bool).reshape(n, 4),
        np.asarray(loaded, dtype=bool).reshape(n, 4),
        np.asarray(endpoints).reshape(n, 4, 2),
        status,
        issues=issues,
        metadata={
            "sample_hz": 100,
            "duration_s": duration,
            "event_ticks": schedule.events,
            "construction": "direct constrained samples; analytic limb IK with nonlinear fallback",
            "continuous_time_guarantee": False,
            "coverage_end_s": float(t[-1]) if n else None,
        },
    )
    if status == "success":
        try:
            if progress:
                progress(
                    0.85, "Independently checking geometry, forces, and inertial screen"
                )
            result.issues.extend(
                validate_trajectory(project, result, robot, cancel, deadline)
            )
            result.check_status = "passed" if not result.issues else "failed"
        except StopSolve as stop:
            result.solve_status = stop.status
            result.check_status = "incomplete"
            result.issues.append(solver_issue(stop.status, float(t[-1])))
    else:
        result.check_status = "incomplete"
    result.metadata["elapsed_s"] = time.monotonic() - started
    if progress:
        progress(1.0, f"{result.solve_status}; checks {result.check_status}")
    return result
