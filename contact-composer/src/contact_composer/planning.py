"""M05: constrained IK and full generalized static equilibrium."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import osqp
from scipy import sparse
from scipy.optimize import minimize

from .model import RobotModel, anchor_point, surface_frame
from .schedule import Schedule
from .spec import EFFECTORS


class StopSolve(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


def check_stop(deadline=None, cancel=None):
    if cancel is not None and cancel():
        raise StopSolve("cancelled")
    if deadline is not None and time.monotonic() > deadline:
        raise StopSolve("timeout")


@dataclass
class ForceSolution:
    status: str
    tau: np.ndarray | None
    forces: np.ndarray | None
    residual: float
    violation: float
    message: str = ""

    @property
    def success(self):
        return self.status == "success"


def force_system(robot, schedule, q, tick):
    gravity = robot.gravity(q)
    active = schedule.active(tick)
    columns = [np.eye(11)[:, 3:]]
    frames = []
    for contact in active:
        surface = schedule.surfaces[contact.surface_id]
        tangent, normal = surface_frame(surface)
        frame = np.column_stack((tangent, normal))
        frames.append(frame)
        columns.append(robot.jacobian(contact.effector_id, normal).T @ frame)
    return np.concatenate(columns, axis=1), gravity, active, frames


def allocate_forces(robot: RobotModel, schedule: Schedule, q, tick) -> ForceSolution:
    matrix, gravity, active, frames = force_system(robot, schedule, q, tick)
    count = 8 + 2 * len(active)
    rows = [matrix]
    low = [gravity / robot.weight]
    high = [gravity / robot.weight]
    # Variables are forces/torques divided by robot weight (length scale = 1 m).
    bounds = np.eye(count)
    lower = list(-robot.torque_limits / robot.weight)
    upper = list(robot.torque_limits / robot.weight)
    for contact in active:
        cap = schedule.capacity(contact, tick) / robot.weight
        mu = schedule.surfaces[contact.surface_id].mu
        lower.extend([-mu * cap, 0.0])
        upper.extend([mu * cap, cap])
    rows.append(bounds)
    low.append(lower)
    high.append(upper)
    for i, contact in enumerate(active):
        mu = schedule.surfaces[contact.surface_id].mu
        for sign in (-1.0, 1.0):
            row = np.zeros(count)
            row[8 + 2 * i] = sign
            row[9 + 2 * i] = -mu
            rows.append(row[None])
            low.append([-np.inf])
            high.append([0.0])
    weights = np.r_[np.full(8, 0.01), np.tile([2.0, 1.0], len(active))]
    solver = osqp.OSQP()
    solver.setup(
        P=sparse.diags(weights, format="csc"),
        q=np.zeros(count),
        A=sparse.csc_matrix(np.vstack(rows)),
        l=np.concatenate(low),
        u=np.concatenate(high),
        eps_abs=1e-8,
        eps_rel=1e-8,
        max_iter=10000,
        verbose=False,
        polishing=True,
    )
    answer = solver.solve(raise_error=False)
    if answer.info.status_val not in (1, 2):
        status = (
            "fixed_pose_infeasible"
            if answer.info.status_val in (3, 4)
            else "numerical_error"
        )
        return ForceSolution(
            status, None, None, float("inf"), float("inf"), answer.info.status
        )
    actual = answer.x * robot.weight
    residual = float(np.max(np.abs(matrix @ actual - gravity) / robot.force_scale))
    values = np.vstack(rows) @ answer.x
    l, u = np.concatenate(low), np.concatenate(high)
    violation = float(max(np.max(l - values), np.max(values - u), 0.0))
    forces = np.zeros((4, 2))
    for i, (contact, frame) in enumerate(zip(active, frames)):
        forces[EFFECTORS.index(contact.effector_id)] = (
            frame @ actual[8 + 2 * i : 10 + 2 * i]
        )
    passed = (
        max(residual, violation)
        <= schedule.project.settings.validation.balance_tolerance
    )
    return ForceSolution(
        "success" if passed else "numerical_error",
        actual[:8],
        forces,
        residual,
        violation,
        answer.info.status,
    )


def target_value(robot, q, target):
    if target.kind == "base_position":
        return np.asarray(q[:2])
    if target.kind == "base_pitch":
        return np.asarray(q[2:3])
    if target.kind == "joint_posture":
        return np.asarray(q[3:])
    return robot.endpoints(q)[EFFECTORS.index(target.effector_id)]


def pose_residuals(robot, schedule, q, tick):
    points = robot.endpoints(q)
    errors = [
        np.linalg.norm(
            points[EFFECTORS.index(c.effector_id)] - anchor_point(schedule.project, c)
        )
        for c in schedule.active(tick)
    ]
    joint_excess = float(max(np.max(np.abs(q[3:]) - 2.6), 0))
    collision = float(max(-robot.distances(q).min(initial=0), 0))
    hard_error = 0.0
    for target, value in schedule.targets_at(tick):
        if target.hardness == "hard":
            hard_error = max(
                hard_error,
                float(np.max(np.abs(target_value(robot, q, target) - value)))
                - target.tolerance,
            )
    return {
        "contact": float(max(errors, default=0)),
        "joint": joint_excess,
        "penetration": collision,
        "hard_target": hard_error,
    }


@dataclass
class PoseSolution:
    q: np.ndarray
    force: ForceSolution
    status: str
    residuals: dict
    message: str


def solve_pose(
    robot, schedule, tick, previous, initial_endpoints, deadline=None, cancel=None
):
    check_stop(deadline, cancel)
    active = schedule.active(tick)
    desired = schedule.tasks(tick, initial_endpoints)
    targets = schedule.targets_at(tick)
    q0 = np.asarray(schedule.project.initial_state.q)
    base = np.asarray(previous[:3]).copy()
    for target, value in targets:
        if target.kind == "base_position":
            base[:2] = value
        if target.kind == "base_pitch":
            base[2] = value[0]
        if target.kind == "swing_endpoint" and target.effector_id not in [
            c.effector_id for c in active
        ]:
            desired[EFFECTORS.index(target.effector_id)] = value
    analytic = robot.inverse_endpoints(base, desired, previous)
    if analytic is not None and not any(t.kind == "joint_posture" for t, _ in targets):
        residual = pose_residuals(robot, schedule, analytic, tick)
        force = allocate_forces(robot, schedule, analytic, tick)
        if (
            residual["penetration"]
            <= schedule.project.settings.validation.penetration_tolerance_m
            and residual["hard_target"] <= 1e-6
            and force.success
        ):
            return PoseSolution(
                analytic,
                force,
                "success",
                residual,
                "Analytic limb IK and checked force QP",
            )

    def objective(q):
        check_stop(deadline, cancel)
        endpoints = robot.endpoints(q)
        cost = 20 * np.sum((endpoints - desired) ** 2) + 0.001 * np.sum(
            (q - previous) ** 2
        )
        cost += 0.05 * np.sum((q - q0) ** 2)
        for target, value in targets:
            if target.hardness == "soft":
                cost += target.weight * np.sum(
                    (target_value(robot, q, target) - value) ** 2
                )
        return cost

    def equality(q):
        endpoints = robot.endpoints(q)
        values = [
            endpoints[EFFECTORS.index(c.effector_id)]
            - anchor_point(schedule.project, c)
            for c in active
        ]
        for target, value in targets:
            if target.hardness == "hard":
                values.append(target_value(robot, q, target) - value)
        return np.concatenate(values) if values else np.zeros(0)

    tol = schedule.project.settings.validation.penetration_tolerance_m

    def clearance(q):
        return robot.distances(q) + tol

    bounds = [(-2, 2), (0.1, 2), (-0.9, 0.9)] + [(-2.6, 2.6)] * 8
    constraints = [{"type": "ineq", "fun": clearance}]
    if equality(previous).size:
        constraints.append({"type": "eq", "fun": equality})
    answer = minimize(
        objective,
        previous,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={
            "maxiter": schedule.project.settings.planning.max_iterations,
            "ftol": 1e-10,
        },
    )
    q = answer.x
    residual = pose_residuals(robot, schedule, q, tick)
    force = allocate_forces(robot, schedule, q, tick)
    # Coupled fallback lets posture change when this particular IK pose cannot support gravity.
    if not force.success and max(residual["contact"], residual["hard_target"]) < 0.002:
        A, g, contacts, frames = force_system(robot, schedule, q, tick)
        initial = np.zeros(8 + 2 * len(contacts))
        for i, contact in enumerate(contacts):
            normal = schedule.surfaces[contact.surface_id].normal
            if normal[1] > 0.5:
                initial[9 + 2 * i] = 1 / max(len(contacts), 1)
        force_bounds = [
            (-limit / robot.weight, limit / robot.weight)
            for limit in robot.torque_limits
        ]
        for contact in contacts:
            cap = schedule.capacity(contact, tick) / robot.weight
            mu = schedule.surfaces[contact.surface_id].mu
            force_bounds.extend([(-mu * cap, mu * cap), (0, cap)])

        def coupled_eq(x):
            matrix, gravity, _, _ = force_system(robot, schedule, x[:11], tick)
            return np.r_[equality(x[:11]), matrix @ x[11:] - gravity / robot.weight]

        def coupled_ineq(x):
            friction = []
            for i, c in enumerate(contacts):
                ft, fn = x[19 + 2 * i : 21 + 2 * i]
                mu = schedule.surfaces[c.surface_id].mu
                friction.extend([mu * fn - ft, mu * fn + ft])
            return np.r_[clearance(x[:11]), friction]

        coupled = minimize(
            lambda x: objective(x[:11]) + 1e-5 * np.sum(x[11:] ** 2),
            np.r_[q, initial],
            method="SLSQP",
            bounds=bounds + force_bounds,
            constraints=[
                {"type": "eq", "fun": coupled_eq},
                {"type": "ineq", "fun": coupled_ineq},
            ],
            options={
                "maxiter": schedule.project.settings.planning.max_iterations,
                "ftol": 1e-10,
            },
        )
        q = coupled.x[:11]
        answer = coupled
        residual = pose_residuals(robot, schedule, q, tick)
        force = allocate_forces(robot, schedule, q, tick)
    check_stop(deadline, cancel)
    valid = (
        residual["contact"] <= schedule.project.settings.validation.contact_tolerance_m
        and residual["joint"] <= 1e-5
        and residual["penetration"] <= tol + 1e-7
        and residual["hard_target"] <= 1e-6
        and force.success
    )
    return PoseSolution(
        q,
        force,
        "success" if valid else "no_solution_found",
        residual,
        str(answer.message),
    )
