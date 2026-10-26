"""Constrained inverse dynamics for the eight real actuators only."""

import mujoco
import numpy as np
import osqp
from scipy import sparse

from .model import anchor_point, surface_frame
from .spec import EFFECTORS


def command(robot, schedule, q, dq, qref, dqref, ddqref, forces, tick):
    active = schedule.active(tick)
    n = 19 + 2 * len(active)
    robot.forward(q, dq)
    mass = np.zeros((11, 11))
    mujoco.mj_fullM(robot.mj, mass, robot.data.qM)
    bias = robot.data.qfrc_bias.copy()
    desired = ddqref + 100 * (qref - q) + 20 * (dqref - dq)
    weights = np.r_[100.0, 100.0, 100.0, np.ones(8)]
    h = np.eye(n) * 1e-5
    h[:11, :11] = np.diag(weights)
    linear = np.zeros(n)
    linear[:11] = -weights * desired
    dynamics = np.zeros((11, n))
    dynamics[:, :11] = mass / robot.weight
    dynamics[:, 11:19] = -np.eye(11)[:, 3:]
    lower = np.r_[
        np.full(11, -100.0),
        -robot.torque_limits / robot.weight,
        np.zeros(2 * len(active)),
    ]
    upper = np.r_[
        np.full(11, 100.0),
        robot.torque_limits / robot.weight,
        np.zeros(2 * len(active)),
    ]
    friction = []
    for i, contact in enumerate(active):
        surface = schedule.surfaces[contact.surface_id]
        tangent, normal = surface_frame(surface)
        frame = np.column_stack((tangent, normal))
        offset = 19 + 2 * i
        robot.forward(q, dq)
        force_jac = robot.jacobian(contact.effector_id, normal)
        jac = robot.jacobian(contact.effector_id)
        point = robot.data.site_xpos[robot.sites[EFFECTORS.index(contact.effector_id)]][
            [0, 2]
        ].copy()
        robot.forward(q + 1e-6 * dq, dq)
        jdot = (robot.jacobian(contact.effector_id) - jac) / 1e-6
        acceleration = (
            400 * (anchor_point(schedule.project, contact) - point)
            - 40 * jac @ dq
            - jdot @ dq
        )
        h[:11, :11] += 100 * jac.T @ jac
        linear[:11] -= 100 * jac.T @ acceleration
        dynamics[:, offset : offset + 2] = -force_jac.T @ frame
        cap = schedule.capacity(contact, tick) / robot.weight
        lower[offset : offset + 2] = [-surface.mu * cap, 0]
        upper[offset : offset + 2] = [surface.mu * cap, cap]
        h[offset : offset + 2, offset : offset + 2] = np.eye(2) * 0.01
        linear[offset : offset + 2] = (
            -0.01
            * frame.T
            @ forces[EFFECTORS.index(contact.effector_id)]
            / robot.weight
        )
        for sign in (-1, 1):
            row = np.zeros(n)
            row[offset] = sign
            row[offset + 1] = -surface.mu
            friction.append(row)
    rows = np.vstack([dynamics, np.eye(n), np.asarray(friction).reshape(-1, n)])
    low = np.r_[-bias / robot.weight, lower, np.full(len(friction), -np.inf)]
    high = np.r_[-bias / robot.weight, upper, np.zeros(len(friction))]
    solver = osqp.OSQP()
    solver.setup(
        P=sparse.csc_matrix(h),
        q=linear,
        A=sparse.csc_matrix(rows),
        l=low,
        u=high,
        verbose=False,
        eps_abs=1e-5,
        eps_rel=1e-5,
        max_iter=4000,
        polishing=True,
    )
    result = solver.solve(raise_error=False)
    if result.info.status_val not in (1, 2) or result.x is None:
        raise RuntimeError(f"Controller QP: {result.info.status}")
    violation = max(np.max(low - rows @ result.x), np.max(rows @ result.x - high))
    if violation > 1e-3:
        raise RuntimeError("Controller QP residual exceeded tolerance")
    return result.x[11:19] * robot.weight
